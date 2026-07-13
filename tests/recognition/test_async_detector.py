from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from multiwebcam.profiles.settings import InferenceSettings
from multiwebcam.quality.metrics import ObjectRegion
from multiwebcam.recognition import AsyncObjectDetector, create_detector
from multiwebcam.recognition.types import DetectionResult


@dataclass
class _RecordingDetector:
    backend_name: str = "recording"
    calls: list[int] = field(default_factory=list)
    closed: bool = False

    def detect(self, frame: np.ndarray, frame_index: int) -> DetectionResult:
        self.calls.append(frame_index)
        time.sleep(0.01)
        return DetectionResult(
            frame_index=frame_index,
            object_region=ObjectRegion(0, 0, 10, 10, 0.1, 0.8, 1.0, 0.9),
            backend=self.backend_name,
            latency_ms=1.0,
        )

    def close(self) -> None:
        self.closed = True


def test_async_detector_keeps_newest_frame_per_source():
    detector = _RecordingDetector()
    async_detector = AsyncObjectDetector(detector)
    try:
        frame = np.zeros((16, 16, 3), dtype=np.uint8)
        async_detector.submit("/dev/video0", frame, 1)
        async_detector.submit("/dev/video0", frame, 2)
        async_detector.submit("/dev/video0", frame, 3)

        deadline = time.monotonic() + 1.0
        result = None
        while time.monotonic() < deadline:
            result = async_detector.results().get("/dev/video0")
            if result is not None and result.frame_index == 3:
                break
            time.sleep(0.01)

        assert result is not None
        assert result.frame_index == 3
        assert detector.calls[-1] == 3
    finally:
        async_detector.stop()


def test_create_detector_defaults_to_heuristic():
    detector = create_detector(InferenceSettings())

    assert detector.backend_name == "heuristic"


def test_async_detector_stop_closes_underlying_detector():
    detector = _RecordingDetector()
    async_detector = AsyncObjectDetector(detector)

    async_detector.stop()

    assert detector.closed
