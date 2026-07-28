"""Bounded reconstruction queue and isolated baseline subprocess worker."""

from __future__ import annotations

import hashlib
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Set

from gaussianobject_rx.protocol.models import TaskStatus
from gaussianobject_rx.server.baseline_adapter import build_baseline_invocation
from gaussianobject_rx.server.config import ReceiverConfig
from gaussianobject_rx.server.files import fsync_directory
from gaussianobject_rx.server.task_registry import TaskRecord, TaskRegistry

logger = logging.getLogger(__name__)


class ReconstructionQueueFull(Exception):
    """No more reconstruction jobs can be accepted."""


class ReconstructionManager:
    def __init__(self, config: ReceiverConfig, registry: TaskRegistry) -> None:
        self.config = config
        self.registry = registry
        self._queue: queue.Queue[Optional[str]] = queue.Queue(maxsize=config.reconstruction_queue_size)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="reconstruction-worker", daemon=False)
        self._lock = threading.Lock()
        self._queued: Set[str] = set()
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._thread.start()

    def submit(self, task_id: str) -> TaskRecord:
        record = self.registry.get(task_id)
        if record is None:
            raise KeyError(task_id)
        if record.status in {
            TaskStatus.RUNNING_COLMAP.value,
            TaskStatus.RUNNING_3DGS.value,
            TaskStatus.FINISHED.value,
        }:
            return record
        with self._lock:
            if task_id in self._queued:
                return record
            try:
                self._queue.put_nowait(task_id)
            except queue.Full as exc:
                raise ReconstructionQueueFull("reconstruction queue is full") from exc
            self._queued.add(task_id)
        return self.registry.update(
            task_id,
            status=TaskStatus.READY.value,
            progress=5,
            message="queued for reconstruction",
            error="",
            log_summary="",
        )

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=self.config.process_stop_timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=self.config.process_stop_timeout_seconds)
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout=self.config.process_stop_timeout_seconds + 2)
        if self._thread.is_alive():
            raise RuntimeError("reconstruction worker did not stop")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                task_id = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if task_id is None:
                self._queue.task_done()
                break
            try:
                self._execute(task_id)
            except Exception as exc:
                if self._stop_event.is_set():
                    logger.info("reconstruction task %s stopped: %s", task_id, exc)
                    self.registry.update(
                        task_id,
                        status=TaskStatus.READY.value,
                        progress=5,
                        message="receiver stopped; task will resume automatically",
                        error="",
                        log_summary=_log_tail(Path(self.registry.get(task_id).task_dir) / "reconstruction.log"),
                    )
                else:
                    logger.exception("reconstruction task %s failed", task_id)
                    self.registry.update(
                        task_id,
                        status=TaskStatus.FAILED.value,
                        progress=100,
                        message="reconstruction failed",
                        error=f"RECONSTRUCTION_ERROR: {exc}",
                        log_summary=_log_tail(Path(self.registry.get(task_id).task_dir) / "reconstruction.log"),
                    )
            finally:
                with self._lock:
                    self._queued.discard(task_id)
                    self._process = None
                self._queue.task_done()

    def _execute(self, task_id: str) -> None:
        record = self.registry.get(task_id)
        if record is None:
            return
        task_dir = Path(record.task_dir)
        invocation = build_baseline_invocation(
            task_id,
            task_dir,
            self.config.baseline_path,
            self.config.baseline_iterations,
        )
        self.registry.update(
            task_id,
            status=TaskStatus.RUNNING_COLMAP.value,
            progress=10,
            message="baseline front-end and SfM running",
            expected_output_ply=str(invocation.expected_output_ply),
        )
        environment = os.environ.copy()
        environment.update(invocation.environment)
        invocation.log_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        saw_training = False
        with invocation.log_path.open("wb") as log_stream:
            process = subprocess.Popen(
                invocation.command,
                cwd=str(self.config.baseline_path.parent),
                env=environment,
                stdout=log_stream,
                stderr=subprocess.STDOUT,
            )
            with self._lock:
                self._process = process
            while process.poll() is None:
                if self._stop_event.is_set():
                    process.terminate()
                    raise RuntimeError("receiver stopped during reconstruction")
                if time.monotonic() - started > self.config.reconstruction_timeout_seconds:
                    process.terminate()
                    try:
                        process.wait(timeout=self.config.process_stop_timeout_seconds)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise TimeoutError("baseline reconstruction timed out")
                log_stream.flush()
                if not saw_training and _log_contains(invocation.log_path, b"training one baseline model"):
                    saw_training = True
                    self.registry.update(
                        task_id,
                        status=TaskStatus.RUNNING_3DGS.value,
                        progress=55,
                        message="3DGS training running",
                    )
                time.sleep(0.2)
            return_code = process.returncode
        if return_code != 0:
            raise RuntimeError(f"baseline exited with code {return_code}")
        if not invocation.expected_output_ply.is_file():
            raise FileNotFoundError(f"expected PLY was not created: {invocation.expected_output_ply}")
        size = invocation.expected_output_ply.stat().st_size
        if size <= 0:
            raise ValueError("expected PLY is empty")
        if size > self.config.max_ply_size_bytes:
            raise ValueError(f"PLY exceeds configured maximum: {size}")

        result_path = task_dir / "result" / "3DGS.ply"
        digest = _copy_result_atomic(invocation.expected_output_ply, result_path, self.config.max_ply_size_bytes)
        self.registry.update(
            task_id,
            status=TaskStatus.FINISHED.value,
            progress=100,
            message="reconstruction finished",
            result_path=str(result_path),
            result_size=result_path.stat().st_size,
            result_sha256=digest,
            error="",
            log_summary=_log_tail(invocation.log_path),
        )


def _copy_result_atomic(source: Path, destination: Path, maximum_size: int) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    digest = hashlib.sha256()
    total = 0
    try:
        with source.open("rb") as input_stream, temporary.open("wb") as output_stream:
            for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
                total += len(chunk)
                if total > maximum_size:
                    raise ValueError("PLY exceeds configured maximum while copying")
                output_stream.write(chunk)
                digest.update(chunk)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        os.replace(str(temporary), str(destination))
        fsync_directory(destination.parent)
        return digest.hexdigest()
    except Exception:
        corrupt = temporary.with_suffix(temporary.suffix + ".corrupt")
        if temporary.exists():
            os.replace(str(temporary), str(corrupt))
        raise


def _log_contains(path: Path, needle: bytes) -> bool:
    try:
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 64 * 1024))
            return needle in stream.read(64 * 1024)
    except OSError:
        return False


def _log_tail(path: Path, maximum_bytes: int = 16 * 1024) -> str:
    try:
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - maximum_bytes))
            return stream.read(maximum_bytes).decode("utf-8", errors="replace")
    except OSError:
        return ""
