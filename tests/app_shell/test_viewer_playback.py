"""Deterministic playback and Camera Director timeline behavior."""

from __future__ import annotations

import pytest

from camera_system_app.domain.viewer import CameraPose, CameraShot, CameraTimeline
from camera_system_app.application.viewer_playback import (
    ViewerPlayback,
    ViewerPlaybackError,
)
from camera_system_app.ui.widgets.viewer_timeline import ViewerTimelineWidget


def _timeline():
    first = CameraPose(position=(0.0, 0.0, 5.0))
    second = CameraPose(position=(1.0, 0.0, 5.0))
    third = CameraPose(position=(2.0, 0.0, 5.0))
    return CameraTimeline(
        shots=(
            CameraShot("one", "第一段", first, second, duration_seconds=1.0),
            CameraShot("two", "第二段", second, third, duration_seconds=1.0),
        ),
        fps=2.0,
    )


def test_playback_emits_started_frames_and_finished_in_order(qapp):
    playback = ViewerPlayback(_timeline())
    events = []
    playback.playback_started.connect(lambda: events.append("started"))
    playback.frame_changed.connect(lambda frame: events.append(("frame", frame)))
    playback.playback_finished.connect(lambda: events.append("finished"))

    playback.play()
    playback.tick()
    playback.tick()
    playback.tick()
    playback.tick()

    assert events[:3] == ["started", ("frame", 1), ("frame", 2)]
    assert events[-1] == "finished"
    assert playback.current_frame == 4
    assert not playback.is_playing


def test_playback_pause_stop_and_frame_range_are_explicit(qapp):
    playback = ViewerPlayback(_timeline())
    playback.set_frame_range(1, 3)
    playback.set_frame(1)
    playback.play()
    assert playback.is_playing

    playback.pause()
    assert not playback.is_playing
    assert playback.current_frame == 1

    with pytest.raises(ViewerPlaybackError):
        playback.set_frame(0)

    playback.stop()
    assert playback.current_frame == 1
    assert playback.frame_range == (1, 3)


def test_playback_rejects_empty_timeline_and_invalid_ranges(qapp):
    playback = ViewerPlayback(CameraTimeline())
    with pytest.raises(ViewerPlaybackError):
        playback.play()

    playback = ViewerPlayback(_timeline())
    with pytest.raises(ViewerPlaybackError):
        playback.set_frame_range(3, 1)
    with pytest.raises(ViewerPlaybackError):
        playback.set_frame_range(0, 99)


def test_playback_loops_and_supports_explicit_frame_steps(qapp):
    timeline = CameraTimeline(
        shots=_timeline().shots,
        fps=2.0,
        loop=True,
    )
    playback = ViewerPlayback(timeline)
    playback.set_frame(3)
    playback.step_backward()
    assert playback.current_frame == 2
    playback.step_forward()
    assert playback.current_frame == 3

    playback.play()
    playback.tick()
    assert playback.current_frame == 4
    assert playback.is_playing
    playback.tick()
    assert playback.current_frame == 0
    assert playback.is_playing
    playback.stop()


def test_timeline_widget_is_model_backed_and_exposes_shot_actions(qapp):
    widget = ViewerTimelineWidget()
    widget.set_timeline(_timeline())
    assert widget.timeline == _timeline()
    assert len(widget.shot_markers) == 2
    assert widget.duration_label.text() == "时长 2.00 s · 2 FPS"
    assert widget.frame_slider.maximum() == 4

    selected = []
    changed = []
    widget.frame_selected.connect(selected.append)
    widget.timeline_changed.connect(changed.append)
    widget.frame_slider.setValue(3)
    widget.duplicate_button.click()

    assert selected == [3]
    assert changed
    assert len(widget.timeline.shots) == 3
    assert any(shot.name.endswith("副本") for shot in widget.timeline.shots)


def test_timeline_add_shot_captures_the_current_camera_pose(qapp):
    widget = ViewerTimelineWidget()
    first_pose = CameraPose(position=(1.0, 0.0, 5.0))
    second_pose = CameraPose(position=(2.0, 0.0, 5.0))

    widget.set_current_pose(first_pose)
    widget.add_button.click()
    widget.set_current_pose(second_pose)
    widget.add_button.click()

    assert widget.timeline.shots[0].start == first_pose
    assert widget.timeline.shots[0].end == second_pose
    assert widget.timeline.shots[1].start == second_pose


def test_timeline_edits_shot_timing_easing_fps_and_loop(qapp):
    widget = ViewerTimelineWidget()
    widget.set_timeline(_timeline())
    widget.shot_editor_toggle.click()

    widget.duration_spinbox.setValue(2.5)
    widget.hold_start_spinbox.setValue(0.25)
    widget.hold_end_spinbox.setValue(0.5)
    widget.easing_combo.setCurrentIndex(widget.easing_combo.findData("linear"))
    widget.fps_spinbox.setValue(24.0)
    widget.loop_checkbox.setChecked(True)

    shot = widget.timeline.shots[0]
    assert shot.duration_seconds == 2.5
    assert shot.hold_start_seconds == 0.25
    assert shot.hold_end_seconds == 0.5
    assert shot.easing == "linear"
    assert widget.timeline.fps == 24.0
    assert widget.timeline.loop is True


def test_timeline_supports_frame_and_shot_navigation(qapp):
    widget = ViewerTimelineWidget()
    widget.set_timeline(_timeline())
    widget.set_current_frame(2)

    widget.previous_frame_button.click()
    assert widget.frame_slider.value() == 1
    widget.next_frame_button.click()
    assert widget.frame_slider.value() == 2
    widget.next_shot_button.click()
    assert widget.selected_shot_index == 1
    widget.previous_shot_button.click()
    assert widget.selected_shot_index == 0


def test_timeline_generates_unique_shot_ids_after_delete_and_add(qapp):
    pose = CameraPose(position=(0.0, 0.0, 5.0))
    timeline = CameraTimeline(
        shots=(
            CameraShot("shot-1", "一", pose, pose),
            CameraShot("shot-2", "二", pose, pose),
        )
    )
    widget = ViewerTimelineWidget()
    widget.set_timeline(timeline)
    widget.delete_button.click()
    widget.set_current_pose(pose)
    widget.add_button.click()

    ids = [shot.shot_id for shot in widget.timeline.shots]
    assert len(ids) == 2
    assert len(ids) == len(set(ids))
