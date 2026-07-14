"""Recognition backend implementations and factory."""

from __future__ import annotations


from dataclasses import dataclass
from time import perf_counter

import numpy as np

from multiwebcam.profiles.settings import InferenceSettings
from multiwebcam.quality.metrics import (
    MAX_PRIMARY_OBJECT_AREA_RATIO,
    ObjectRegion,
    detect_primary_object,
)
from multiwebcam.recognition.subprocess_detector import SubprocessObjectDetector
from multiwebcam.recognition.types import DetectionResult, ObjectDetector


@dataclass()
class HeuristicObjectDetector:
    """CPU heuristic fallback matching the legacy contour-based guidance."""

    backend_name: str = "heuristic"

    def detect(self, frame: np.ndarray, frame_index: int) -> DetectionResult:
        started = perf_counter()
        region = detect_primary_object(frame)
        return DetectionResult(
            frame_index=frame_index,
            object_region=region,
            backend=self.backend_name,
            latency_ms=(perf_counter() - started) * 1000.0,
        )


class UltralyticsTensorRTDetector:
    """TensorRT detector via Ultralytics `.engine` runtime."""

    backend_name = "ultralytics_tensorrt"

    def __init__(self, settings: InferenceSettings) -> None:
        if not settings.engine_path:
            raise ValueError("Inference backend 'ultralytics_tensorrt' requires engine_path")
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("ultralytics is required for TensorRT inference") from exc

        self._settings = settings
        self._model = YOLO(settings.engine_path, task="detect")
        self._classes = list(settings.target_class_ids) if settings.target_class_ids else None

    def detect(self, frame: np.ndarray, frame_index: int) -> DetectionResult:
        started = perf_counter()
        width, height = self._settings.input_size
        prediction = self._model.predict(
            source=frame,
            imgsz=max(width, height),
            conf=self._settings.confidence_threshold,
            verbose=False,
            device=self._settings.device,
            classes=self._classes,
        )[0]
        region = self._extract_primary_region(prediction, frame.shape[1], frame.shape[0])
        return DetectionResult(
            frame_index=frame_index,
            object_region=region,
            backend=self.backend_name,
            latency_ms=(perf_counter() - started) * 1000.0,
        )

    def _extract_primary_region(self, prediction, width: int, height: int) -> ObjectRegion | None:
        boxes = getattr(prediction, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return None

        frame_area = float(max(1, width * height))
        frame_center_x = width / 2.0
        frame_center_y = height / 2.0
        best_region = None
        best_score = -1.0

        for xyxy, conf in zip(boxes.xyxy.cpu().numpy(), boxes.conf.cpu().numpy()):
            x1, y1, x2, y2 = [int(round(v)) for v in xyxy.tolist()]
            x1 = max(0, min(x1, width - 1))
            y1 = max(0, min(y1, height - 1))
            x2 = max(x1 + 1, min(x2, width))
            y2 = max(y1 + 1, min(y2, height))
            box_w = x2 - x1
            box_h = y2 - y1
            area_ratio = float(box_w * box_h) / frame_area
            if area_ratio > MAX_PRIMARY_OBJECT_AREA_RATIO:
                continue
            center_x = x1 + box_w / 2.0
            center_y = y1 + box_h / 2.0
            distance = ((center_x - frame_center_x) ** 2 + (center_y - frame_center_y) ** 2) ** 0.5
            max_distance = max(1.0, (frame_center_x**2 + frame_center_y**2) ** 0.5)
            centeredness = max(0.0, min(1.0, 1.0 - distance / max_distance))
            confidence = float(conf)
            area_score = _score_small_target_area(area_ratio)
            score = 0.50 * centeredness + 0.30 * confidence + 0.20 * area_score
            if score <= best_score:
                continue

            best_score = score
            best_region = ObjectRegion(
                x=x1,
                y=y1,
                width=box_w,
                height=box_h,
                area_ratio=area_ratio,
                centeredness=centeredness,
                fill_ratio=1.0,
                confidence=confidence,
            )
        return best_region


def _score_small_target_area(area_ratio: float) -> float:
    target = 0.08
    tolerance = 0.14
    return max(0.0, min(1.0, 1.0 - abs(area_ratio - target) / tolerance))


def create_detector(settings: InferenceSettings) -> ObjectDetector:
    """Create the requested detector backend."""
    if settings.backend == "subprocess":
        return SubprocessObjectDetector(settings)
    if settings.backend == "ultralytics_tensorrt":
        return UltralyticsTensorRTDetector(settings)
    return HeuristicObjectDetector()
