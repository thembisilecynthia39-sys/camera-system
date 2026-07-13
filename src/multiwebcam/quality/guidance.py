from __future__ import annotations
"""Realtime capture guidance for fixed-angle sparse-reconstruction photo sets."""


from dataclasses import dataclass

import cv2
import numpy as np

from multiwebcam.quality.metrics import CaptureSetQuality
from multiwebcam.sources.frame_packet import FramePacket

REQUIRED_ANGLES = (0, 45, 90, 135, 180, 225, 270, 315)
_READINESS_READY = 80.0
_READINESS_MIN_CAPTURE = 50.0
_RETAKE_MARGIN = 5.0
_LOW_OVERLAP_THRESHOLD = 0.05
_DUPLICATE_OVERLAP_THRESHOLD = 0.35


@dataclass(frozen=True)
class CapturedAngle:
    """Best accepted capture for one angle bin."""

    angle_deg: int
    frame_id: int
    readiness_percent: float


@dataclass(frozen=True)
class CaptureGuidance:
    """Live operator guidance for the 8-angle capture loop."""

    current_angle_deg: int
    readiness_percent: float
    readiness_label: str
    progress_percent: float
    next_angle_deg: int | None
    completed_angles: tuple[int, ...]
    suggested_retake_angle: int | None
    warning: str | None
    ready_to_capture: bool
    loop_complete: bool


@dataclass(frozen=True)
class CaptureValidation:
    """Validation result for a still-image capture request."""

    accepted: bool
    guidance: CaptureGuidance
    message: str


class CaptureGuidanceTracker:
    """Tracks accepted angle captures and derives live guidance."""

    def __init__(self, required_angles: tuple[int, ...] = REQUIRED_ANGLES) -> None:
        self._required_angles = tuple(required_angles)
        self._captures: dict[int, CapturedAngle] = {}
        self._reference_frames: dict[int, np.ndarray] = {}

    @property
    def required_angles(self) -> tuple[int, ...]:
        return self._required_angles

    def evaluate(
        self,
        packets: dict[str, FramePacket],
        quality: CaptureSetQuality,
        selected_angle_deg: int,
    ) -> CaptureGuidance:
        angle = _normalize_angle(selected_angle_deg, self._required_angles)
        completed_angles = tuple(angle_deg for angle_deg in self._required_angles if angle_deg in self._captures)
        next_angle_deg = self._next_angle()
        progress_percent = self._progress_percent()
        warning = self._target_warning(quality) or self._matchability_warning(angle, packets, quality)
        readiness_label = _readiness_label(quality.readiness_percent)
        ready_to_capture = quality.readiness_percent >= _READINESS_MIN_CAPTURE and self._target_detected(quality)
        suggested_retake_angle = self._retake_angle()
        loop_complete = len(self._captures) >= len(self._required_angles)

        if warning is None and next_angle_deg is not None and angle != next_angle_deg and angle not in self._captures:
            warning = f"preferred next angle {next_angle_deg} deg"

        return CaptureGuidance(
            current_angle_deg=angle,
            readiness_percent=quality.readiness_percent,
            readiness_label=readiness_label,
            progress_percent=progress_percent,
            next_angle_deg=next_angle_deg,
            completed_angles=completed_angles,
            suggested_retake_angle=suggested_retake_angle,
            warning=warning,
            ready_to_capture=ready_to_capture,
            loop_complete=loop_complete,
        )

    def validate_capture(
        self,
        selected_angle_deg: int,
        packets: dict[str, FramePacket],
        quality: CaptureSetQuality,
    ) -> CaptureValidation:
        guidance = self.evaluate(packets, quality, selected_angle_deg)
        existing = self._captures.get(guidance.current_angle_deg)

        if quality.readiness_percent < _READINESS_MIN_CAPTURE:
            return CaptureValidation(
                accepted=False,
                guidance=guidance,
                message=f"{guidance.readiness_label} {quality.readiness_percent:.0f}%: improve sharpness or exposure",
            )

        if not self._target_detected(quality):
            return CaptureValidation(
                accepted=False,
                guidance=guidance,
                message="target not detected; center the object before capture",
            )

        if existing and quality.readiness_percent <= existing.readiness_percent + _RETAKE_MARGIN:
            return CaptureValidation(
                accepted=False,
                guidance=guidance,
                message=(
                    f"angle {guidance.current_angle_deg} deg already covered at "
                    f"{existing.readiness_percent:.0f}%"
                ),
            )

        if guidance.warning and guidance.warning.startswith("duplicate"):
            return CaptureValidation(
                accepted=False,
                guidance=guidance,
                message=guidance.warning,
            )

        if guidance.warning and guidance.warning.startswith("low overlap"):
            return CaptureValidation(
                accepted=False,
                guidance=guidance,
                message=guidance.warning,
            )

        return CaptureValidation(
            accepted=True,
            guidance=guidance,
            message=f"{guidance.readiness_label} {quality.readiness_percent:.0f}%",
        )

    def register_capture(
        self,
        selected_angle_deg: int,
        frame_id: int,
        packets: dict[str, FramePacket],
        quality: CaptureSetQuality,
    ) -> CaptureGuidance:
        angle = _normalize_angle(selected_angle_deg, self._required_angles)
        existing = self._captures.get(angle)
        if existing is None or quality.readiness_percent >= existing.readiness_percent:
            self._captures[angle] = CapturedAngle(
                angle_deg=angle,
                frame_id=frame_id,
                readiness_percent=quality.readiness_percent,
            )
            representative = _representative_gray_frame(packets, quality)
            if representative is not None:
                self._reference_frames[angle] = representative
        return self.evaluate(packets, quality, angle)

    def _next_angle(self) -> int | None:
        for angle in self._required_angles:
            if angle not in self._captures:
                return angle
        return None

    def _retake_angle(self) -> int | None:
        if not self._captures:
            return self._required_angles[0]
        if len(self._captures) < len(self._required_angles):
            return None
        return min(self._captures.values(), key=lambda capture: capture.readiness_percent).angle_deg

    def _progress_percent(self) -> float:
        angle_coverage = len(self._captures) / max(1, len(self._required_angles))
        if self._captures:
            mean_quality = sum(c.readiness_percent for c in self._captures.values()) / len(self._required_angles)
        else:
            mean_quality = 0.0
        return 100.0 * (0.65 * angle_coverage + 0.35 * (mean_quality / 100.0))

    def _matchability_warning(
        self,
        angle_deg: int,
        packets: dict[str, FramePacket],
        quality: CaptureSetQuality,
    ) -> str | None:
        gray = _representative_gray_frame(packets, quality)
        if gray is None:
            return None

        if angle_deg in self._reference_frames:
            overlap = _descriptor_overlap(self._reference_frames[angle_deg], gray)
            if overlap >= _DUPLICATE_OVERLAP_THRESHOLD:
                return f"duplicate view at {angle_deg} deg; move to next angle"

        neighbor_angle = _nearest_captured_angle(angle_deg, self._captures)
        if neighbor_angle is None:
            return None

        reference = self._reference_frames.get(neighbor_angle)
        if reference is None:
            return None
        overlap = _descriptor_overlap(reference, gray)
        if overlap <= _LOW_OVERLAP_THRESHOLD:
            return f"low overlap with {neighbor_angle} deg; rotate less or improve texture"
        return None

    def _target_detected(self, quality: CaptureSetQuality) -> bool:
        return any(
            frame_quality.object_region is not None and frame_quality.object_region.confidence >= 0.25
            for frame_quality in quality.frame_qualities.values()
        )

    def _target_warning(self, quality: CaptureSetQuality) -> str | None:
        if self._target_detected(quality):
            return None
        return "target not detected; center the object"


def _normalize_angle(angle_deg: int, required_angles: tuple[int, ...]) -> int:
    normalized = angle_deg % 360
    if normalized == 360:
        normalized = 0
    if normalized not in required_angles:
        raise ValueError(f"Unsupported angle {angle_deg}")
    return normalized


def _readiness_label(readiness_percent: float) -> str:
    if readiness_percent >= _READINESS_READY:
        return "READY"
    if readiness_percent >= _READINESS_MIN_CAPTURE:
        return "BORDERLINE"
    return "WAIT"


def _representative_gray_frame(
    packets: dict[str, FramePacket],
    quality: CaptureSetQuality,
) -> np.ndarray | None:
    if not packets or not quality.frame_qualities:
        return None
    best_path = max(
        quality.frame_qualities,
        key=lambda path: quality.frame_qualities[path].score_percent,
    )
    packet = packets.get(best_path)
    if packet is None or packet.frame.size == 0:
        return None
    return cv2.cvtColor(packet.frame, cv2.COLOR_BGR2GRAY)


def _nearest_captured_angle(angle_deg: int, captures: dict[int, CapturedAngle]) -> int | None:
    if not captures:
        return None
    nearest = None
    nearest_distance = None
    for captured_angle in captures:
        distance = _circular_distance(angle_deg, captured_angle)
        if nearest_distance is None or distance < nearest_distance:
            nearest = captured_angle
            nearest_distance = distance
    return nearest


def _circular_distance(angle_a: int, angle_b: int) -> int:
    delta = abs(angle_a - angle_b) % 360
    return min(delta, 360 - delta)


def _descriptor_overlap(reference_gray: np.ndarray, candidate_gray: np.ndarray) -> float:
    orb = cv2.ORB_create(nfeatures=800)
    ref_keypoints, ref_descriptors = orb.detectAndCompute(reference_gray, None)
    cand_keypoints, cand_descriptors = orb.detectAndCompute(candidate_gray, None)
    if ref_descriptors is None or cand_descriptors is None or not ref_keypoints or not cand_keypoints:
        return 0.0

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    raw_matches = matcher.knnMatch(ref_descriptors, cand_descriptors, k=2)
    good_matches = [
        match
        for match_pair in raw_matches
        if len(match_pair) == 2
        for match, neighbor in [match_pair]
        if match.distance < 0.75 * neighbor.distance
    ]
    normalizer = max(1, min(len(ref_keypoints), len(cand_keypoints)))
    return len(good_matches) / normalizer
