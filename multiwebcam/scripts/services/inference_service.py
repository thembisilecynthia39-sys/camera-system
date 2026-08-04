#!/usr/bin/env python3
"""Standalone inference worker for Jetson py38 environments."""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import traceback
from typing import Iterable

import cv2
import numpy as np

cv2.setNumThreads(1)

if "bool" not in np.__dict__:
    np.bool = np.bool_


_MAX_PRIMARY_OBJECT_AREA_RATIO = 0.55


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("ultralytics_tensorrt", "heuristic"), required=True)
    parser.add_argument("--engine-path")
    parser.add_argument("--device", default="0")
    parser.add_argument("--input-width", type=int, default=640)
    parser.add_argument("--input-height", type=int, default=640)
    parser.add_argument("--confidence-threshold", type=float, default=0.25)
    parser.add_argument("--class-id", action="append", type=int, default=[])
    return parser.parse_args()


class _HeuristicDetector:
    backend_name = "heuristic_subprocess"

    def detect(self, frame, frame_index):
        started = time.perf_counter()
        region = _detect_primary_object(frame)
        return {
            "frame_index": frame_index,
            "backend": self.backend_name,
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "object_region": _region_to_payload(region),
        }


class _UltralyticsTensorRTDetector:
    backend_name = "ultralytics_tensorrt_subprocess"

    def __init__(self, args: argparse.Namespace) -> None:
        if not args.engine_path:
            raise ValueError("ultralytics_tensorrt backend requires --engine-path")
        from ultralytics import YOLO

        self._model = YOLO(args.engine_path, task="detect")
        self._device = args.device
        self._imgsz = max(args.input_width, args.input_height)
        self._confidence_threshold = args.confidence_threshold
        self._class_ids = list(args.class_id) or None
        self._disable_torchvision_nms()

    def detect(self, frame, frame_index):
        started = time.perf_counter()
        self._disable_torchvision_nms()
        prediction = self._model.predict(
            source=frame,
            imgsz=self._imgsz,
            conf=self._confidence_threshold,
            verbose=False,
            device=self._device,
            classes=self._class_ids,
        )[0]
        region = _extract_primary_region(prediction, frame.shape[1], frame.shape[0])
        return {
            "frame_index": frame_index,
            "backend": self.backend_name,
            "latency_ms": (time.perf_counter() - started) * 1000.0,
            "object_region": _region_to_payload(region),
        }

    @staticmethod
    def _disable_torchvision_nms() -> None:
        """Force Ultralytics to use its TorchNMS fallback on Jetson py38 stacks.

        Some Jetson torch/torchvision combinations ship a torchvision package whose
        Python layer imports but whose compiled custom ops are ABI-incompatible.
        Ultralytics only chooses torchvision.ops.nms() when the top-level
        ``torchvision`` module is present in ``sys.modules``; removing that entry
        makes it use its built-in pure Torch NMS instead.
        """
        for name in list(sys.modules):
            if name == "torchvision" or name.startswith("torchvision."):
                sys.modules.pop(name, None)


def _make_detector(args: argparse.Namespace):
    if args.backend == "heuristic":
        return _HeuristicDetector()
    return _UltralyticsTensorRTDetector(args)


def _region_to_payload(region):
    if region is None:
        return None
    return {
        "x": int(region["x"]),
        "y": int(region["y"]),
        "width": int(region["width"]),
        "height": int(region["height"]),
        "area_ratio": float(region["area_ratio"]),
        "centeredness": float(region["centeredness"]),
        "fill_ratio": float(region["fill_ratio"]),
        "confidence": float(region["confidence"]),
    }


def _extract_primary_region(prediction, width: int, height: int):
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
        if area_ratio > _MAX_PRIMARY_OBJECT_AREA_RATIO:
            continue
        center_x = x1 + box_w / 2.0
        center_y = y1 + box_h / 2.0
        distance = ((center_x - frame_center_x) ** 2 + (center_y - frame_center_y) ** 2) ** 0.5
        max_distance = max(1.0, (frame_center_x**2 + frame_center_y**2) ** 0.5)
        centeredness = max(0.0, min(1.0, 1.0 - distance / max_distance))
        confidence = float(conf)
        area_score = _score_object_area(area_ratio)
        score = 0.50 * centeredness + 0.30 * confidence + 0.20 * area_score
        if score <= best_score:
            continue

        best_score = score
        best_region = {
            "x": x1,
            "y": y1,
            "width": box_w,
            "height": box_h,
            "area_ratio": area_ratio,
            "centeredness": centeredness,
            "fill_ratio": 1.0,
            "confidence": confidence,
        }
    return best_region


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _score_object_area(area_ratio: float) -> float:
    target = 0.08
    tolerance = 0.14
    return _clamp(1.0 - abs(area_ratio - target) / tolerance)


def _detect_primary_object(frame: np.ndarray):
    if frame.size == 0:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    kernel = np.ones((5, 5), dtype=np.uint8)
    mask = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    frame_center = np.array([width / 2.0, height / 2.0])
    best_region = None
    best_score = 0.0
    frame_area = float(width * height)

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        bbox_area = float(w * h)
        area_ratio = bbox_area / frame_area
        if area_ratio < 0.002 or area_ratio > 0.90:
            continue

        contour_area = max(1.0, cv2.contourArea(contour))
        fill_ratio = _clamp(contour_area / bbox_area)
        center = np.array([x + w / 2.0, y + h / 2.0])
        distance = float(np.linalg.norm(center - frame_center))
        max_distance = max(1.0, np.linalg.norm(frame_center))
        centeredness = _clamp(1.0 - distance / max_distance)
        area_score = _score_object_area(area_ratio)
        confidence = _clamp(0.40 * centeredness + 0.35 * area_score + 0.25 * fill_ratio)
        score = 0.55 * centeredness + 0.25 * area_score + 0.20 * fill_ratio
        if score > best_score:
            best_score = score
            best_region = {
                "x": x,
                "y": y,
                "width": w,
                "height": h,
                "area_ratio": area_ratio,
                "centeredness": centeredness,
                "fill_ratio": fill_ratio,
                "confidence": confidence,
            }
    return best_region


def _iter_requests(stream: Iterable[str]):
    for line in stream:
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)


def _decode_frame(payload: dict) -> np.ndarray:
    encoded = base64.b64decode(payload["image_jpeg_b64"])
    array = np.frombuffer(encoded, dtype=np.uint8)
    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Failed to decode JPEG frame")
    return frame


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def main() -> int:
    args = _parse_args()
    try:
        detector = _make_detector(args)
    except Exception as exc:
        _emit({"status": "error", "error": str(exc), "traceback": traceback.format_exc()})
        return 1

    _emit({"status": "ready", "backend": detector.backend_name})
    for request in _iter_requests(sys.stdin):
        if request.get("command") == "shutdown":
            break
        try:
            frame = _decode_frame(request)
            result = detector.detect(frame, int(request["frame_index"]))
            result["status"] = "ok"
            _emit(result)
        except Exception as exc:
            _emit({"status": "error", "error": str(exc), "traceback": traceback.format_exc()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
