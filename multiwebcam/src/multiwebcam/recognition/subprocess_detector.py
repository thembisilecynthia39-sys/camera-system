from __future__ import annotations
"""Subprocess-backed detector client for running inference in a separate Python runtime."""


import base64
import json
import logging
import subprocess
from collections import deque
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from time import monotonic, perf_counter

import cv2
import numpy as np

from multiwebcam.profiles.settings import InferenceSettings
from multiwebcam.quality.metrics import ObjectRegion
from multiwebcam.recognition.service_runtime import build_service_env
from multiwebcam.recognition.types import DetectionResult

logger = logging.getLogger(__name__)


def _sanitized_service_env() -> dict[str, str]:
    """Drop main-app Python overrides while preserving service user packages."""
    return build_service_env()


class SubprocessObjectDetector:
    """Run inference through an external Python worker process."""

    backend_name = "subprocess"

    def __init__(
        self,
        settings: InferenceSettings,
        cancel_event: Event | None = None,
    ) -> None:
        if not settings.service_python and not settings.service_conda_env:
            raise ValueError("Inference backend 'subprocess' requires service_python or service_conda_env")

        self._settings = settings
        self._service_backend = settings.service_backend or "ultralytics_tensorrt"
        self._stdout_noise_lines: deque[str] = deque(maxlen=50)
        self._stderr_lines: deque[str] = deque(maxlen=50)
        self._process = self._start_process()
        self._stderr_thread = Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()
        try:
            self._await_ready(cancel_event)
        except Exception:
            self.close()
            raise

    def detect(self, frame: np.ndarray, frame_index: int) -> DetectionResult:
        started = perf_counter()
        source_height, source_width = frame.shape[:2]
        input_width, input_height = self._settings.input_size
        scale = min(
            1.0,
            input_width / float(max(1, source_width)),
            input_height / float(max(1, source_height)),
        )
        transport_frame = frame
        if scale < 1.0:
            transport_frame = cv2.resize(
                frame,
                (
                    max(1, round(source_width * scale)),
                    max(1, round(source_height * scale)),
                ),
                interpolation=cv2.INTER_AREA,
            )
        transport_height, transport_width = transport_frame.shape[:2]
        success, encoded = cv2.imencode(
            ".jpg",
            transport_frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), 80],
        )
        if not success:
            raise RuntimeError("Failed to encode frame for subprocess inference")

        request = {
            "frame_index": frame_index,
            "image_jpeg_b64": base64.b64encode(encoded.tobytes()).decode("ascii"),
        }
        self._write_message(request)
        response = self._read_message()
        if response.get("status") != "ok":
            error = response.get("error", "subprocess detector failed")
            remote_traceback = response.get("traceback")
            if remote_traceback:
                raise RuntimeError(f"{error}\n{remote_traceback}")
            raise RuntimeError(error)

        region_payload = response.get("object_region")
        region = None
        if region_payload is not None:
            region = ObjectRegion(
                x=round(int(region_payload["x"]) * source_width / transport_width),
                y=round(int(region_payload["y"]) * source_height / transport_height),
                width=round(
                    int(region_payload["width"]) * source_width / transport_width
                ),
                height=round(
                    int(region_payload["height"]) * source_height / transport_height
                ),
                area_ratio=float(region_payload["area_ratio"]),
                centeredness=float(region_payload["centeredness"]),
                fill_ratio=float(region_payload["fill_ratio"]),
                confidence=float(region_payload["confidence"]),
            )

        latency_ms = float(response.get("latency_ms", (perf_counter() - started) * 1000.0))
        backend_name = str(response.get("backend", f"subprocess:{self._service_backend}"))
        return DetectionResult(
            frame_index=frame_index,
            object_region=region,
            backend=backend_name,
            latency_ms=latency_ms,
        )

    def close(self) -> None:
        if self._process.poll() is None:
            try:
                self._write_message({"command": "shutdown"})
            except Exception:
                pass
            try:
                self._process.terminate()
                self._process.wait(timeout=3.0)
            except Exception:
                self._process.kill()
                self._process.wait(timeout=3.0)
        for stream in (self._process.stdin, self._process.stdout, self._process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        if self._stderr_thread is not None and self._stderr_thread.is_alive():
            self._stderr_thread.join(timeout=1.0)

    def _start_process(self) -> subprocess.Popen[str]:
        script_path = self._settings.service_script or str(self._default_service_script())
        command = self._base_command(script_path)
        if self._settings.engine_path:
            command.extend(["--engine-path", self._settings.engine_path])
        for class_id in self._settings.target_class_ids or ():
            command.extend(["--class-id", str(class_id)])

        logger.info("Starting inference service: %s", command)
        return subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=_sanitized_service_env(),
        )

    def _base_command(self, script_path: str) -> list[str]:
        suffix = [
            script_path,
            "--backend",
            self._service_backend,
            "--device",
            str(self._settings.device),
            "--input-width",
            str(self._settings.input_size[0]),
            "--input-height",
            str(self._settings.input_size[1]),
            "--confidence-threshold",
            str(self._settings.confidence_threshold),
        ]
        if self._settings.service_python:
            return [
                self._settings.service_python,
                *suffix,
            ]
        if self._settings.service_conda_env:
            return [
                "conda",
                "run",
                "-p",
                self._settings.service_conda_env,
                "python",
                *suffix,
            ]
        raise RuntimeError("subprocess inference requires service_python or service_conda_env")

    def _await_ready(self, cancel_event: Event | None = None) -> None:
        result = Queue(maxsize=1)

        def read_ready() -> None:
            try:
                result.put((self._read_message(), None))
            except Exception as exc:
                result.put((None, exc))

        reader = Thread(target=read_ready, daemon=True)
        reader.start()
        deadline = monotonic() + 30.0
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("inference service startup cancelled")
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise RuntimeError("inference service startup timed out")
            try:
                response, error = result.get(timeout=min(0.1, remaining))
                break
            except Empty:
                continue
        if error is not None:
            raise error
        if response.get("status") != "ready":
            raise RuntimeError(response.get("error", "inference service failed to start"))

    def _write_message(self, payload: dict) -> None:
        if self._process.stdin is None:
            raise RuntimeError("inference service stdin unavailable")
        self._process.stdin.write(json.dumps(payload) + "\n")
        self._process.stdin.flush()

    def _read_message(self) -> dict:
        if self._process.stdout is None:
            raise RuntimeError("inference service stdout unavailable")
        while True:
            line = self._process.stdout.readline()
            if not line:
                stderr = " | ".join(self._stderr_lines)
                stdout = " | ".join(self._stdout_noise_lines)
                detail = stderr or stdout or "no stderr"
                raise RuntimeError(f"inference service exited unexpectedly: {detail}")
            text = line.rstrip()
            if not text:
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                self._stdout_noise_lines.append(text)
                logger.debug("Skipping non-JSON inference service stdout: %s", text)

    def _drain_stderr(self) -> None:
        if self._process.stderr is None:
            return
        for line in self._process.stderr:
            text = line.rstrip()
            if text:
                self._stderr_lines.append(text)

    @staticmethod
    def _default_service_script() -> Path:
        return Path(__file__).resolve().parents[3] / "scripts" / "services" / "inference_service.py"
