"""Tests for deterministic camera-tour sampling."""

from __future__ import annotations

import pytest

from camera_system_app.application.viewer_timeline import (
    easing_value,
    interpolate_camera_pose,
    sample_timeline,
    timeline_frame_count,
)
from camera_system_app.domain.viewer import (
    CameraPose,
    CameraShot,
    CameraTimeline,
    ViewerValidationError,
)


def test_interpolation_returns_exact_camera_endpoints():
    start = CameraPose(position=(0.0, 0.0, 5.0), fov_degrees=40.0)
    end = CameraPose(position=(4.0, 2.0, 1.0), target=(1.0, 2.0, 3.0), fov_degrees=70.0)

    assert interpolate_camera_pose(start, end, 0.0) == start
    assert interpolate_camera_pose(start, end, 1.0) == end


def test_interpolation_uses_shortest_quaternion_path():
    start = CameraPose(rotation_xyzw=(0.0, 0.0, 0.0, 1.0))
    same_orientation_with_opposite_sign = CameraPose(rotation_xyzw=(0.0, 0.0, 0.0, -1.0))

    midpoint = interpolate_camera_pose(start, same_orientation_with_opposite_sign, 0.5)

    assert midpoint.rotation_xyzw == pytest.approx(start.rotation_xyzw)


def test_timeline_holds_start_pose_before_interpolating():
    start = CameraPose(position=(0.0, 0.0, 5.0))
    end = CameraPose(position=(10.0, 0.0, 5.0))
    timeline = CameraTimeline(
        fps=10.0,
        shots=(
            CameraShot(
                shot_id="move",
                name="Move",
                start=start,
                end=end,
                duration_seconds=1.0,
                hold_start_seconds=0.5,
                hold_end_seconds=0.5,
                easing="linear",
            ),
        ),
    )

    assert sample_timeline(timeline, 0) == start
    assert sample_timeline(timeline, 5) == start
    assert sample_timeline(timeline, 10).position == pytest.approx((5.0, 0.0, 5.0))
    assert sample_timeline(timeline, timeline_frame_count(timeline) - 1) == end


def test_timeline_frame_count_is_integer_and_includes_final_pose():
    pose = CameraPose()
    timeline = CameraTimeline(
        fps=24.0,
        shots=(
            CameraShot(
                shot_id="one",
                name="One",
                start=pose,
                end=pose,
                duration_seconds=1.25,
            ),
        ),
    )

    assert timeline_frame_count(timeline) == 31
    assert sample_timeline(timeline, 30) == pose


@pytest.mark.parametrize("easing", ["linear", "smoothstep"])
def test_easing_is_monotonic_and_keeps_endpoints(easing):
    values = [easing_value(index / 10.0, easing) for index in range(11)]

    assert values[0] == pytest.approx(0.0)
    assert values[-1] == pytest.approx(1.0)
    assert values == sorted(values)


def test_empty_timeline_is_rejected_when_sampling():
    with pytest.raises(ViewerValidationError, match="at least one"):
        timeline_frame_count(CameraTimeline())
