"""Deterministic render-plan and GUI scheduling tests with fake adapters."""

from __future__ import annotations

import time

import numpy as np
import pytest

from camera_system_app.application.viewer_render_plan import RenderPlan, RenderPlanError
from camera_system_app.domain.viewer import (
    AppearanceSettings,
    CameraPose,
    CameraShot,
    CameraTimeline,
    DisplaySettings,
    OutputKind,
    RenderSettings,
    ViewerProject,
)
from camera_system_app.ui.viewer_render_controller import ViewerRenderController
from camera_system_app.ui.widgets.viewer_render_dialog import ViewerRenderDialog
from camera_system_app.infrastructure.viewer_encoder import BoundedFrameSink, EncoderState


def _project(kind=OutputKind.PNG_SEQUENCE):
    start = CameraPose(position=(0.0, 0.0, 5.0))
    end = CameraPose(position=(2.0, 0.0, 5.0))
    timeline = CameraTimeline(
        shots=(CameraShot("shot", "镜头", start, end, duration_seconds=1.0),),
        fps=2.0,
    )
    return ViewerProject(
        camera=start,
        timeline=timeline,
        display=DisplaySettings(),
        appearance=AppearanceSettings(),
        render=RenderSettings(
            width=3,
            height=2,
            fps=2.0,
            output_kind=kind,
            transparent_background=False,
        ),
    )


def test_render_plan_freezes_settings_and_samples_inclusive_endpoints(tmp_path):
    project = _project()
    plan = RenderPlan.from_project(project, tmp_path / "frames")

    assert plan.frame_count == 3
    assert plan.frame_pose(0) == project.timeline.shots[0].start
    assert plan.frame_pose(2) == project.timeline.shots[0].end
    assert plan.display == project.display
    assert plan.appearance == project.appearance
    assert plan.render == project.render

    with pytest.raises(RenderPlanError):
        plan.frame_pose(3)


def test_render_plan_allows_single_png_without_a_timeline(tmp_path):
    project = ViewerProject(
        camera=CameraPose(position=(1.0, 2.0, 3.0)),
        render=RenderSettings(
            width=3,
            height=2,
            output_kind=OutputKind.PNG,
        ),
    )
    plan = RenderPlan.from_project(project, tmp_path / "still.png")
    assert plan.frame_count == 1
    assert plan.frame_pose(0) == project.camera

    with pytest.raises(RenderPlanError):
        RenderPlan.from_project(
            ViewerProject(render=RenderSettings(output_kind=OutputKind.MP4)),
            tmp_path / "empty.mp4",
        )


class FakeRenderAdapter:
    def __init__(self):
        self.poses = []
        self.display = []
        self.appearance = []
        self.capture_count = 0

    def set_display_settings(self, settings):
        self.display.append(settings)

    def set_appearance_settings(self, settings):
        self.appearance.append(settings)

    def set_camera_pose(self, pose):
        self.poses.append(pose)

    def capture_frame(self, width=None, height=None, camera_pose=None):
        self.capture_count += 1
        return np.full((height, width, 3), len(self.poses), dtype=np.uint8)


def test_render_controller_reports_every_frame_and_final_progress(qapp, tmp_path):
    adapter = FakeRenderAdapter()
    plan = RenderPlan.from_project(_project(), tmp_path / "frames")
    controller = ViewerRenderController(adapter)
    progress = []
    finished = []
    controller.progress_changed.connect(progress.append)
    controller.finished.connect(finished.append)

    controller.start(plan)
    deadline = time.monotonic() + 5.0
    while controller.is_running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)

    assert not controller.is_running
    assert progress[-1] == 1.0
    assert len(adapter.poses) == 3
    assert finished == [tmp_path / "frames"]


def test_render_controller_cancel_is_terminal_and_does_not_publish(qapp, tmp_path):
    adapter = FakeRenderAdapter()
    output = tmp_path / "cancelled"
    controller = ViewerRenderController(adapter)
    cancelled = []
    controller.cancelled.connect(lambda: cancelled.append(True))

    controller.start(RenderPlan.from_project(_project(), output))
    controller.cancel()
    qapp.processEvents()

    assert not controller.is_running
    assert cancelled == [True]
    assert not output.exists()


def test_render_dialog_exposes_frozen_output_summary_and_cancel(qapp, tmp_path):
    dialog = ViewerRenderDialog(
        RenderPlan.from_project(_project(), tmp_path / "frames")
    )
    assert "3 × 2" in dialog.resolution_label.text()
    assert "3" in dialog.frame_count_label.text()
    assert dialog.progress_bar.value() == 0
    cancelled = []
    dialog.cancel_requested.connect(lambda: cancelled.append(True))
    dialog.cancel_button.click()
    assert cancelled == [True]
    dialog.deleteLater()


def test_render_controller_does_not_advance_or_rerender_when_sink_is_full(qapp, tmp_path):
    class StalledEncoder:
        def __init__(self, _config):
            self.sink = BoundedFrameSink(maxsize=1)
            self._state = EncoderState.CREATED
            self.error = None

        @property
        def state(self):
            return self._state

        def start(self):
            self._state = EncoderState.RUNNING

        def submit(self, frame, *, block=False):
            self.sink.put(frame, block=block)

        def abort(self):
            self.sink.abort()
            self._state = EncoderState.ABORTED

    adapter = FakeRenderAdapter()
    controller = ViewerRenderController(adapter, encoder_factory=StalledEncoder)
    controller.start(RenderPlan.from_project(_project(), tmp_path / "stalled"))
    controller._timer.stop()
    controller._render_next()
    assert controller.current_frame == 1
    assert adapter.capture_count == 1

    controller._render_next()
    assert controller.current_frame == 1
    assert adapter.capture_count == 1
    controller.cancel()
