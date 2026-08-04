"""Deterministic camera timeline interpolation for preview and final renders."""

from __future__ import annotations

import math
from typing import Tuple

from camera_system_app.domain.viewer import (
    CameraPose,
    CameraShot,
    CameraTimeline,
    ViewerValidationError,
)


def _clamped_unit(value: float, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ViewerValidationError("{} must be a number".format(label))
    if not math.isfinite(result):
        raise ViewerValidationError("{} must be finite".format(label))
    return max(0.0, min(1.0, result))


def easing_value(progress: float, easing: str = "smoothstep") -> float:
    """Return a bounded easing value without depending on wall-clock time."""

    t = _clamped_unit(progress, "progress")
    name = str(easing).lower()
    if name == "linear":
        return t
    if name == "smoothstep":
        return t * t * (3.0 - 2.0 * t)
    raise ViewerValidationError("unsupported shot easing: {}".format(easing))


def _normalize_quaternion(quaternion: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    norm = math.sqrt(sum(component * component for component in quaternion))
    if norm <= 1e-12:
        raise ViewerValidationError("cannot interpolate a zero quaternion")
    return tuple(component / norm for component in quaternion)  # type: ignore


def _slerp_quaternion(
    start: Tuple[float, float, float, float],
    end: Tuple[float, float, float, float],
    progress: float,
) -> Tuple[float, float, float, float]:
    first = _normalize_quaternion(start)
    second = _normalize_quaternion(end)
    dot = sum(left * right for left, right in zip(first, second))
    if dot < 0.0:
        second = tuple(-component for component in second)  # type: ignore
        dot = -dot
    dot = max(-1.0, min(1.0, dot))
    if dot > 0.9995:
        blended = tuple(
            left + progress * (right - left) for left, right in zip(first, second)
        )
        return _normalize_quaternion(blended)
    angle = math.acos(dot)
    sine = math.sin(angle)
    if abs(sine) <= 1e-12:
        return first
    first_weight = math.sin((1.0 - progress) * angle) / sine
    second_weight = math.sin(progress * angle) / sine
    return _normalize_quaternion(
        tuple(
            first_weight * left + second_weight * right
            for left, right in zip(first, second)
        )
    )


def _lerp_vector(
    start: Tuple[float, float, float],
    end: Tuple[float, float, float],
    progress: float,
) -> Tuple[float, float, float]:
    return tuple(
        left + progress * (right - left) for left, right in zip(start, end)
    )  # type: ignore


def interpolate_camera_pose(
    start: CameraPose, end: CameraPose, progress: float
) -> CameraPose:
    """Interpolate two poses using linear vectors and quaternion slerp."""

    if not isinstance(start, CameraPose) or not isinstance(end, CameraPose):
        raise ViewerValidationError("camera interpolation requires CameraPose values")
    t = _clamped_unit(progress, "progress")
    if t <= 0.0:
        return start
    if t >= 1.0:
        return end
    return CameraPose(
        position=_lerp_vector(start.position, end.position, t),
        target=_lerp_vector(start.target, end.target, t),
        rotation_xyzw=_slerp_quaternion(start.rotation_xyzw, end.rotation_xyzw, t),
        fov_degrees=start.fov_degrees + t * (end.fov_degrees - start.fov_degrees),
    )


def timeline_frame_count(timeline: CameraTimeline) -> int:
    """Return the inclusive frame count needed to reach the final pose."""

    if not isinstance(timeline, CameraTimeline):
        raise ViewerValidationError("timeline must be a CameraTimeline value")
    if not timeline.shots:
        raise ViewerValidationError("timeline must contain at least one shot")
    return max(1, int(math.ceil(timeline.duration_seconds * timeline.fps - 1e-9)) + 1)


def _sample_shot(shot: CameraShot, local_seconds: float) -> CameraPose:
    if local_seconds <= shot.hold_start_seconds:
        return shot.start
    moving_seconds = local_seconds - shot.hold_start_seconds
    if moving_seconds <= shot.duration_seconds:
        progress = moving_seconds / shot.duration_seconds
        return interpolate_camera_pose(
            shot.start,
            shot.end,
            easing_value(progress, shot.easing),
        )
    return shot.end


def sample_timeline_at_time(timeline: CameraTimeline, time_seconds: float) -> CameraPose:
    """Sample a timeline at a clamped presentation time in seconds."""

    if not isinstance(timeline, CameraTimeline):
        raise ViewerValidationError("timeline must be a CameraTimeline value")
    if not timeline.shots:
        raise ViewerValidationError("timeline must contain at least one shot")
    try:
        requested = float(time_seconds)
    except (TypeError, ValueError):
        raise ViewerValidationError("time_seconds must be a number")
    if not math.isfinite(requested):
        raise ViewerValidationError("time_seconds must be finite")
    time = max(0.0, min(timeline.duration_seconds, requested))
    elapsed = 0.0
    for index, shot in enumerate(timeline.shots):
        end_time = elapsed + shot.total_seconds
        if time <= end_time or index == len(timeline.shots) - 1:
            return _sample_shot(shot, max(0.0, time - elapsed))
        elapsed = end_time
    return timeline.shots[-1].end


def sample_timeline(timeline: CameraTimeline, frame_index: int) -> CameraPose:
    """Sample an inclusive frame index using the timeline's fixed FPS."""

    if isinstance(frame_index, bool):
        raise ViewerValidationError("frame_index must be an integer")
    try:
        index = int(frame_index)
    except (TypeError, ValueError):
        raise ViewerValidationError("frame_index must be an integer")
    if index != frame_index or index < 0:
        raise ViewerValidationError("frame_index must be a non-negative integer")
    count = timeline_frame_count(timeline)
    if index >= count:
        raise ViewerValidationError("frame_index is outside the timeline")
    return sample_timeline_at_time(timeline, index / timeline.fps)


__all__ = [
    "easing_value",
    "interpolate_camera_pose",
    "sample_timeline",
    "sample_timeline_at_time",
    "timeline_frame_count",
]
