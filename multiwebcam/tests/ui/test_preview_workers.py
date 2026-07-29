from __future__ import annotations

from threading import Event

import numpy as np
from PySide6.QtGui import QImage

from multiwebcam.quality.metrics import CaptureSetQuality, QualityLevel
from multiwebcam.sources.frame_packet import FramePacket
from multiwebcam.ui.conversion import frame_to_qimage
from multiwebcam.ui.preview_workers import (
    PreviewRequest,
    PreviewWorker,
    QualityWorker,
)


def _frame(value: int, width: int = 64, height: int = 48) -> np.ndarray:
    return np.full((height, width, 3), value, dtype=np.uint8)


def _packet(value: int) -> FramePacket:
    return FramePacket(
        device_path="/dev/video0",
        device_id=0,
        frame_index=value,
        frame_time=float(value),
        timestamp_source="wall_clock",
        frame=_frame(value),
        fps=30.0,
    )


def test_frame_to_qimage_caps_preview_size_without_upscaling():
    wide = frame_to_qimage(_frame(1, 1280, 720), max_size=(640, 360))
    four_by_three = frame_to_qimage(_frame(2, 640, 480), max_size=(640, 360))
    small = frame_to_qimage(_frame(3, 320, 240), max_size=(640, 360))

    assert (wide.width(), wide.height()) == (640, 360)
    assert (four_by_three.width(), four_by_three.height()) == (480, 360)
    assert (small.width(), small.height()) == (320, 240)


def test_preview_worker_replaces_stale_pending_frame():
    first_started = Event()
    release_first = Event()
    latest_processed = Event()
    seen = []

    def converter(frame, **_kwargs):
        value = int(frame[0, 0, 0])
        seen.append(value)
        if value == 1:
            first_started.set()
            assert release_first.wait(2.0)
        if value == 3:
            latest_processed.set()
        return QImage(1, 1, QImage.Format.Format_RGB888)

    worker = PreviewWorker(converter=converter)
    worker.submit({0: PreviewRequest(_frame(1), False, None)})
    assert first_started.wait(2.0)
    worker.submit({0: PreviewRequest(_frame(2), False, None)})
    worker.submit({0: PreviewRequest(_frame(3), False, None)})
    release_first.set()

    assert latest_processed.wait(2.0)
    assert worker.stop()
    assert seen == [1, 3]


def test_preview_request_can_override_worker_size_for_focus_mode():
    processed = Event()
    sizes = []

    def converter(_frame, **kwargs):
        sizes.append(kwargs["max_size"])
        processed.set()
        return QImage(1, 1, QImage.Format.Format_RGB888)

    worker = PreviewWorker(max_size=(640, 360), converter=converter)
    worker.submit(
        {
            0: PreviewRequest(
                _frame(1),
                False,
                None,
                max_size=(1280, 720),
            )
        }
    )

    assert processed.wait(2.0)
    assert worker.stop()
    assert sizes == [(1280, 720)]


def test_quality_worker_replaces_stale_capture_set():
    first_started = Event()
    release_first = Event()
    latest_processed = Event()
    seen = []

    def evaluator(packets, object_regions):
        value = next(iter(packets.values())).frame_index
        seen.append(value)
        if value == 1:
            first_started.set()
            assert release_first.wait(2.0)
        if value == 3:
            latest_processed.set()
        return CaptureSetQuality(
            level=QualityLevel.GOOD,
            timestamp_spread_ms=0.0,
            sync_score=1.0,
            readiness_percent=100.0,
            frame_qualities={},
            reasons=(),
        )

    worker = QualityWorker(evaluator=evaluator)
    worker.submit({"/dev/video0": _packet(1)}, {})
    assert first_started.wait(2.0)
    worker.submit({"/dev/video0": _packet(2)}, {})
    worker.submit({"/dev/video0": _packet(3)}, {})
    release_first.set()

    assert latest_processed.wait(2.0)
    assert worker.stop()
    assert seen == [1, 3]
