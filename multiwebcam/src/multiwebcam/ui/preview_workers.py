"""Latest-frame background workers for preview conversion and quality checks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Condition, Event, Thread
from typing import Callable

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from multiwebcam.quality.metrics import (
    CaptureSetQuality,
    ObjectRegion,
    evaluate_capture_set,
)
from multiwebcam.sources.frame_packet import FramePacket
from multiwebcam.ui.conversion import frame_to_qimage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreviewRequest:
    """One immutable request to prepare a preview image."""

    frame: np.ndarray
    mirror: bool
    object_region: ObjectRegion | None
    max_size: tuple[int, int] | None = None


class PreviewWorker(QObject):
    """Prepare only the newest pending preview for each source."""

    images_ready = Signal(object)  # dict[int, QImage]

    def __init__(
        self,
        max_size: tuple[int, int] = (640, 360),
        converter: Callable[..., QImage] = frame_to_qimage,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._max_size = max_size
        self._converter = converter
        self._condition = Condition()
        self._shutdown = Event()
        self._thread: Thread | None = None
        self._pending: dict[int, PreviewRequest] = {}

    def submit(self, requests: dict[int, PreviewRequest]) -> None:
        """Replace pending work per source instead of building a frame queue."""
        if not requests:
            return
        with self._condition:
            if self._shutdown.is_set():
                return
            if self._thread is None:
                self._thread = Thread(
                    target=self._run,
                    name="multiwebcam-preview",
                    daemon=True,
                )
                self._thread.start()
            self._pending.update(requests)
            self._condition.notify()

    def clear_pending(self) -> None:
        with self._condition:
            self._pending.clear()

    def stop(self, timeout: float = 3.0) -> bool:
        self._shutdown.set()
        with self._condition:
            self._pending.clear()
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=max(0.0, timeout))
            if self._thread.is_alive():
                logger.error("Preview worker did not stop within %.1fs", timeout)
                return False
            self._thread = None
        return True

    def _run(self) -> None:
        while not self._shutdown.is_set():
            with self._condition:
                while not self._pending and not self._shutdown.is_set():
                    self._condition.wait(timeout=0.5)
                if self._shutdown.is_set():
                    return
                pending = self._pending
                self._pending = {}

            images: dict[int, QImage] = {}
            for source_id, request in pending.items():
                if self._shutdown.is_set():
                    return
                try:
                    images[source_id] = self._converter(
                        request.frame,
                        mirror=request.mirror,
                        object_region=request.object_region,
                        max_size=request.max_size or self._max_size,
                    )
                except Exception:
                    logger.exception(
                        "Preview conversion failed for source %s",
                        source_id,
                    )
            if images and not self._shutdown.is_set():
                self.images_ready.emit(images)


class QualityWorker(QObject):
    """Evaluate the newest capture set without blocking the Qt event loop."""

    quality_ready = Signal(object)  # CaptureSetQuality

    def __init__(
        self,
        evaluator: Callable[..., CaptureSetQuality] = evaluate_capture_set,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._evaluator = evaluator
        self._condition = Condition()
        self._shutdown = Event()
        self._thread: Thread | None = None
        self._pending: tuple[
            dict[str, FramePacket],
            dict[str, ObjectRegion | None],
        ] | None = None

    def submit(
        self,
        packets: dict[str, FramePacket],
        object_regions: dict[str, ObjectRegion | None],
    ) -> None:
        if not packets:
            return
        with self._condition:
            if self._shutdown.is_set():
                return
            if self._thread is None:
                self._thread = Thread(
                    target=self._run,
                    name="multiwebcam-quality",
                    daemon=True,
                )
                self._thread.start()
            self._pending = (dict(packets), dict(object_regions))
            self._condition.notify()

    def clear_pending(self) -> None:
        with self._condition:
            self._pending = None

    def stop(self, timeout: float = 3.0) -> bool:
        self._shutdown.set()
        with self._condition:
            self._pending = None
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=max(0.0, timeout))
            if self._thread.is_alive():
                logger.error("Quality worker did not stop within %.1fs", timeout)
                return False
            self._thread = None
        return True

    def _run(self) -> None:
        while not self._shutdown.is_set():
            with self._condition:
                while self._pending is None and not self._shutdown.is_set():
                    self._condition.wait(timeout=0.5)
                if self._shutdown.is_set():
                    return
                packets, object_regions = self._pending
                self._pending = None

            try:
                quality = self._evaluator(
                    packets,
                    object_regions=object_regions,
                )
            except Exception:
                logger.exception("Background capture quality evaluation failed")
                continue
            if not self._shutdown.is_set():
                self.quality_ready.emit(quality)
