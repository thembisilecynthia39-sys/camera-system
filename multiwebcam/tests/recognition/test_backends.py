from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from multiwebcam.profiles.settings import InferenceSettings
from multiwebcam.recognition.backends import UltralyticsTensorRTDetector


class _Tensor:
    def __init__(self, values) -> None:
        self._values = np.array(values, dtype=np.float32)

    def cpu(self):
        return self

    def numpy(self) -> np.ndarray:
        return self._values


class _Boxes:
    def __init__(self, xyxy=None, conf=None) -> None:
        self.xyxy = _Tensor(xyxy or [[100, 120, 260, 300]])
        self.conf = _Tensor(conf or [0.91])
        self.cls = _Tensor([0])

    def __len__(self) -> int:
        return 1


class _Prediction:
    def __init__(self, boxes=None) -> None:
        self.boxes = boxes or _Boxes()


class _FakeYOLO:
    last_call: dict | None = None
    prediction = _Prediction()

    def __init__(self, engine_path: str, task: str) -> None:
        self.engine_path = engine_path
        self.task = task

    def predict(self, **kwargs):
        _FakeYOLO.last_call = kwargs
        return [_FakeYOLO.prediction]


def test_tensorrt_detector_uses_configured_cuda_device_and_class_filter(monkeypatch):
    _FakeYOLO.prediction = _Prediction()
    monkeypatch.setitem(
        sys.modules,
        "ultralytics",
        types.SimpleNamespace(YOLO=_FakeYOLO),
    )
    settings = InferenceSettings(
        backend="ultralytics_tensorrt",
        engine_path="/models/yolo.engine",
        device="cuda:1",
        target_class_ids=(0, 2),
        input_size=(640, 640),
        confidence_threshold=0.35,
    )
    detector = UltralyticsTensorRTDetector(settings)

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = detector.detect(frame, frame_index=7)

    assert _FakeYOLO.last_call is not None
    assert _FakeYOLO.last_call["device"] == "cuda:1"
    assert _FakeYOLO.last_call["classes"] == [0, 2]
    assert _FakeYOLO.last_call["conf"] == 0.35
    assert result.frame_index == 7
    assert result.object_region is not None
    assert result.object_region.confidence == pytest.approx(0.91)


def test_tensorrt_detector_prefers_center_object_over_edge_high_confidence(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "ultralytics",
        types.SimpleNamespace(YOLO=_FakeYOLO),
    )
    _FakeYOLO.prediction = _Prediction(
        _Boxes(
            xyxy=[
                [0, 0, 170, 170],
                [292, 212, 348, 268],
            ],
            conf=[0.95, 0.55],
        )
    )
    settings = InferenceSettings(
        backend="ultralytics_tensorrt",
        engine_path="/models/yolo.engine",
        device="cuda:0",
        input_size=(640, 640),
        confidence_threshold=0.25,
    )
    detector = UltralyticsTensorRTDetector(settings)

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = detector.detect(frame, frame_index=8)

    assert result.object_region is not None
    assert result.object_region.x == 292
    assert result.object_region.y == 212
    assert result.object_region.confidence == pytest.approx(0.55)


def test_tensorrt_detector_ignores_oversized_primary_box(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "ultralytics",
        types.SimpleNamespace(YOLO=_FakeYOLO),
    )
    _FakeYOLO.prediction = _Prediction(
        _Boxes(
            xyxy=[[0, 0, 600, 450]],
            conf=[0.95],
        )
    )
    settings = InferenceSettings(
        backend="ultralytics_tensorrt",
        engine_path="/models/yolo.engine",
        device="cuda:0",
        input_size=(640, 640),
        confidence_threshold=0.25,
    )
    detector = UltralyticsTensorRTDetector(settings)

    result = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8), frame_index=9)

    assert result.object_region is None
