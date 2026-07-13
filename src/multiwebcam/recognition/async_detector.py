from __future__ import annotations
"""Background object detector that keeps only the newest frame per source."""


import logging
from threading import Condition, Event, Thread

import numpy as np

from multiwebcam.recognition.types import DetectionResult, ObjectDetector

logger = logging.getLogger(__name__)


class AsyncObjectDetector:
    """Asynchronously run recognition without back-pressuring capture."""

    def __init__(self, detector: ObjectDetector) -> None:
        self._detector = detector
        self._pending: dict[str, tuple[np.ndarray, int]] = {}
        self._results: dict[str, DetectionResult] = {}
        self._condition = Condition()
        self._shutdown = Event()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def backend_name(self) -> str:
        return self._detector.backend_name

    def submit(self, device_path: str, frame: np.ndarray, frame_index: int) -> None:
        """Keep only the newest pending frame for a source."""
        with self._condition:
            self._pending[device_path] = (frame, frame_index)
            self._condition.notify()

    def results(self) -> dict[str, DetectionResult]:
        with self._condition:
            return dict(self._results)

    def stop(self, timeout: float = 3.0) -> None:
        self._shutdown.set()
        with self._condition:
            self._condition.notify_all()
        self._thread.join(timeout=timeout)
        close = getattr(self._detector, "close", None)
        if callable(close):
            close()

    def _run(self) -> None:
        while not self._shutdown.is_set():
            with self._condition:
                while not self._pending and not self._shutdown.is_set():
                    self._condition.wait(timeout=0.5)
                if self._shutdown.is_set():
                    return
                pending = self._pending
                self._pending = {}

            for device_path, (frame, frame_index) in pending.items():
                try:
                    result = self._detector.detect(frame, frame_index)
                except Exception:
                    logger.exception("Object detector failed for %s", device_path)
                    continue
                with self._condition:
                    previous = self._results.get(device_path)
                    if previous is None or result.frame_index >= previous.frame_index:
                        self._results[device_path] = result
