"""Lightweight realtime quality metrics for image capture.

These metrics are meant for live guidance before saving frames for COLMAP/3DGS.
They intentionally avoid slow reconstruction steps.
"""

from __future__ import annotations


from dataclasses import dataclass
from enum import Enum

import cv2
import numpy as np

from multiwebcam.sources.frame_packet import FramePacket


class QualityLevel(str, Enum):
    GOOD = "good"
    WARN = "warn"
    BAD = "bad"


# The capture target should remain a subject inside the frame, not the frame
# itself.  Keep this shared guard consistent across heuristic, YOLO and UI
# rendering paths so a large false positive cannot become a giant overlay.
MAX_PRIMARY_OBJECT_AREA_RATIO = 0.55


@dataclass(frozen=True)
class ObjectRegion:
    """Estimated primary object region in a frame."""

    x: int
    y: int
    width: int
    height: int
    area_ratio: float
    centeredness: float
    fill_ratio: float
    confidence: float

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)


@dataclass(frozen=True)
class FrameQuality:
    """Quality metrics for a single frame."""

    level: QualityLevel
    sharpness: float
    brightness: float
    underexposed_pct: float
    overexposed_pct: float
    feature_count: int
    sharpness_score: float
    brightness_score: float
    clipping_score: float
    feature_score: float
    object_score: float
    score_percent: float
    object_region: ObjectRegion | None
    reasons: tuple[str, ...]

    @property
    def ok_to_capture(self) -> bool:
        return self.level != QualityLevel.BAD

    def summary(self) -> str:
        reason = "" if not self.reasons else f" | {', '.join(self.reasons[:2])}"
        return (
            f"{self.level.upper()} | sharp {self.sharpness:.0f} | "
            f"exp {self.brightness:.0f} | feat {self.feature_count}{reason}"
        )


@dataclass(frozen=True)
class CaptureSetQuality:
    """Quality metrics for a synchronized set of camera frames."""

    level: QualityLevel
    timestamp_spread_ms: float
    sync_score: float
    readiness_percent: float
    frame_qualities: dict[str, FrameQuality]
    reasons: tuple[str, ...]

    @property
    def ok_to_capture(self) -> bool:
        return self.level != QualityLevel.BAD

    def summary(self) -> str:
        reason = "" if not self.reasons else f" | {', '.join(self.reasons[:2])}"
        return f"Capture {self.level.upper()} | sync {self.timestamp_spread_ms:.0f}ms{reason}"


def evaluate_frame(
    frame: np.ndarray,
    object_region: ObjectRegion | None = None,
    detect_when_missing: bool = True,
) -> FrameQuality:
    """Evaluate blur, exposure, and texture richness for one BGR frame."""
    if frame.size == 0:
        return FrameQuality(
            level=QualityLevel.BAD,
            sharpness=0.0,
            brightness=0.0,
            underexposed_pct=100.0,
            overexposed_pct=0.0,
            feature_count=0,
            sharpness_score=0.0,
            brightness_score=0.0,
            clipping_score=0.0,
            feature_score=0.0,
            object_score=0.0,
            score_percent=0.0,
            object_region=None,
            reasons=("empty frame",),
        )

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    underexposed_pct = float((gray < 10).mean() * 100.0)
    overexposed_pct = float((gray > 245).mean() * 100.0)
    feature_count = _count_orb_features(gray)
    sharpness_score = _score_sharpness(sharpness)
    brightness_score = _score_brightness(brightness)
    clipping_score = _score_clipping(underexposed_pct, overexposed_pct)
    feature_score = _score_features(feature_count)
    if object_region is None and detect_when_missing:
        object_region = _detect_primary_object(gray)
    object_score = _score_object_region(object_region)
    score_percent = 100.0 * (
        0.25 * sharpness_score
        + 0.20 * brightness_score
        + 0.20 * feature_score
        + 0.15 * clipping_score
        + 0.20 * object_score
    )

    bad_reasons: list[str] = []
    warn_reasons: list[str] = []

    if sharpness < 20:
        bad_reasons.append("blurry")
    elif sharpness < 45:
        warn_reasons.append("soft")

    if brightness < 25:
        bad_reasons.append("too dark")
    elif brightness < 45:
        warn_reasons.append("dark")
    elif brightness > 235:
        bad_reasons.append("too bright")
    elif brightness > 210:
        warn_reasons.append("bright")

    if underexposed_pct > 18:
        bad_reasons.append("underexposed")
    elif underexposed_pct > 8:
        warn_reasons.append("shadow clipping")

    if overexposed_pct > 18:
        bad_reasons.append("overexposed")
    elif overexposed_pct > 8:
        warn_reasons.append("highlight clipping")

    if feature_count < 60:
        bad_reasons.append("low texture")
    elif feature_count < 180:
        warn_reasons.append("few features")

    if object_region is None or object_region.confidence < 0.25:
        warn_reasons.append("subject unclear")
    elif object_region.centeredness < 0.35:
        warn_reasons.append("off-center subject")

    if bad_reasons:
        level = QualityLevel.BAD
        reasons = tuple(bad_reasons)
    elif warn_reasons:
        level = QualityLevel.WARN
        reasons = tuple(warn_reasons)
    else:
        level = QualityLevel.GOOD
        reasons = ()

    return FrameQuality(
        level=level,
        sharpness=sharpness,
        brightness=brightness,
        underexposed_pct=underexposed_pct,
        overexposed_pct=overexposed_pct,
        feature_count=feature_count,
        sharpness_score=sharpness_score,
        brightness_score=brightness_score,
        clipping_score=clipping_score,
        feature_score=feature_score,
        object_score=object_score,
        score_percent=score_percent,
        object_region=object_region,
        reasons=reasons,
    )


def evaluate_capture_set(
    packets: dict[str, FramePacket],
    object_regions: dict[str, ObjectRegion | None] | None = None,
) -> CaptureSetQuality:
    """Evaluate per-frame quality plus cross-camera timestamp spread."""
    if not packets:
        return CaptureSetQuality(
            level=QualityLevel.BAD,
            timestamp_spread_ms=0.0,
            sync_score=0.0,
            readiness_percent=0.0,
            frame_qualities={},
            reasons=("no frames",),
        )

    qualities = {
        path: evaluate_frame(
            packet.frame,
            object_region=None if object_regions is None else object_regions.get(path),
            detect_when_missing=object_regions is None,
        )
        for path, packet in packets.items()
    }
    frame_times = [packet.frame_time for packet in packets.values()]
    timestamp_spread_ms = (max(frame_times) - min(frame_times)) * 1000.0 if len(frame_times) > 1 else 0.0

    bad_reasons: list[str] = []
    warn_reasons: list[str] = []

    bad_cameras = sum(1 for quality in qualities.values() if quality.level == QualityLevel.BAD)
    warn_cameras = sum(1 for quality in qualities.values() if quality.level == QualityLevel.WARN)
    if bad_cameras:
        bad_reasons.append(f"{bad_cameras} bad camera(s)")
    elif warn_cameras:
        warn_reasons.append(f"{warn_cameras} warning camera(s)")

    if timestamp_spread_ms > 300:
        bad_reasons.append("sync spread high")
    elif timestamp_spread_ms > 180:
        warn_reasons.append("sync spread elevated")

    frame_scores = [quality.score_percent / 100.0 for quality in qualities.values()]
    median_frame_score = float(np.median(frame_scores)) if frame_scores else 0.0
    min_frame_score = min(frame_scores) if frame_scores else 0.0
    camera_score = 0.70 * median_frame_score + 0.30 * min_frame_score
    sync_score = _score_sync(timestamp_spread_ms)
    readiness_percent = 100.0 * (0.85 * camera_score + 0.15 * sync_score)

    total_cameras = max(1, len(qualities))
    severe_bad = bad_cameras >= max(2, total_cameras)

    if severe_bad or "sync spread high" in bad_reasons:
        level = QualityLevel.BAD
        reasons = tuple(bad_reasons)
    elif bad_reasons or warn_reasons:
        level = QualityLevel.WARN
        reasons = tuple(bad_reasons + warn_reasons)
    else:
        level = QualityLevel.GOOD
        reasons = ()

    return CaptureSetQuality(
        level=level,
        timestamp_spread_ms=timestamp_spread_ms,
        sync_score=sync_score,
        readiness_percent=readiness_percent,
        frame_qualities=qualities,
        reasons=reasons,
    )


def _count_orb_features(gray: np.ndarray) -> int:
    orb = cv2.ORB_create(nfeatures=1000)
    keypoints = orb.detect(gray, None)
    return len(keypoints)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _score_sharpness(sharpness: float) -> float:
    return _clamp((sharpness - 20.0) / 100.0)


def _score_brightness(brightness: float) -> float:
    center = 140.0
    half_width = 105.0
    return _clamp(1.0 - abs(brightness - center) / half_width)


def _score_clipping(underexposed_pct: float, overexposed_pct: float) -> float:
    return _clamp(1.0 - (underexposed_pct + overexposed_pct) / 24.0)


def _score_features(feature_count: int) -> float:
    return _clamp(feature_count / 250.0)


def _score_sync(timestamp_spread_ms: float) -> float:
    return _clamp(1.0 - timestamp_spread_ms / 300.0)


def _score_object_region(region: ObjectRegion | None) -> float:
    if region is None:
        return 0.0
    return _clamp(0.35 * region.confidence + 0.45 * region.centeredness + 0.20 * _score_object_area(region.area_ratio))


def _score_object_area(area_ratio: float) -> float:
    target = 0.08
    tolerance = 0.14
    return _clamp(1.0 - abs(area_ratio - target) / tolerance)


def _detect_primary_object(gray: np.ndarray) -> ObjectRegion | None:
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
        if area_ratio < 0.002 or area_ratio > MAX_PRIMARY_OBJECT_AREA_RATIO:
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
            best_region = ObjectRegion(
                x=x,
                y=y,
                width=w,
                height=h,
                area_ratio=area_ratio,
                centeredness=centeredness,
                fill_ratio=fill_ratio,
                confidence=confidence,
            )

    return best_region


def detect_primary_object(frame: np.ndarray) -> ObjectRegion | None:
    """Public helper so non-quality modules can reuse the heuristic region detector."""
    if frame.size == 0:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return _detect_primary_object(gray)
