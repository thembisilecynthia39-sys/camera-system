from __future__ import annotations
"""Subprocess-backed detector client for running inference in a separate Python runtime."""


import base64
import json
import logging
import subprocess
from collections import deque
from pathlib import Path
from threading import Thread
from time import perf_counter

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

    def __init__(self, settings: InferenceSettings) -> None:
        if not settings.service_python and not settings.service_conda_env:
            raise ValueError("Inference backend 'subprocess' requires service_python or service_conda_env")

        self._settings = settings
        self._service_backend = settings.service_backend or "ultralytics_tensorrt"
        self._process = self._start_process()
        self._stdout_noise_lines: deque[str] = deque(maxlen=50)
        self._stderr_lines: deque[str] = deque(maxlen=50)
        self._stderr_thread = Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()
        self._await_ready()

    def detect(self, frame: np.ndarray, frame_index: int) -> DetectionResult:
        started = perf_counter()
        success, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
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
                x=int(region_payload["x"]),
                y=int(region_payload["y"]),
                width=int(region_payload["width"]),
                height=int(region_payload["height"]),
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
        if self._process.poll() is not None:
            return
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

    def _await_ready(self) -> None:
        response = self._read_message()
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
