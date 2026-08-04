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
    DisplayMode,
    OutputKind,
    RenderSettings,
    ViewerProject,
)
from camera_system_app.ui.viewer_render_controller import (
    ViewerRenderController,
    ViewerRenderControllerError,
)
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
    assert plan.duration_seconds == pytest.approx(1.0)

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
        self.appearance_settings = AppearanceSettings(exposure=0.5)
        self.capture_count = 0

    def set_display_settings(self, settings):
        self.display.append(settings)

    def set_appearance_settings(self, settings):
        self.appearance.append(settings)
        self.appearance_settings = settings

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


def test_final_render_bypasses_gpu_appearance_once_and_restores_previous_state(
    qapp, tmp_path
):
    adapter = FakeRenderAdapter()
    original = adapter.appearance_settings
    plan = RenderPlan.from_project(_project(), tmp_path / "frames")
    controller = ViewerRenderController(adapter)

    controller.start(plan)
    deadline = time.monotonic() + 5.0
    while controller.is_running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)

    assert not controller.is_running
    assert adapter.appearance[0].tone_mapping == "none"
    assert adapter.appearance[0].exposure == 0.0
    assert adapter.appearance_settings == original


def test_render_controller_produces_a_real_playable_mp4(qapp, tmp_path):
    av = pytest.importorskip("av")
    project = _project(OutputKind.MP4)
    project = ViewerProject(
        camera=project.camera,
        timeline=project.timeline,
        display=project.display,
        appearance=project.appearance,
        render=RenderSettings(
            width=16,
            height=16,
            fps=2.0,
            output_kind=OutputKind.MP4,
        ),
    )
    output = tmp_path / "tour.mp4"
    adapter = FakeRenderAdapter()
    controller = ViewerRenderController(adapter)
    controller.start(RenderPlan.from_project(project, output))
    deadline = time.monotonic() + 5.0
    while controller.is_running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)

    assert not controller.is_running
    assert output.is_file()
    with av.open(str(output), mode="r") as container:
        stream = container.streams.video[0]
        frames = list(container.decode(stream))
    assert len(frames) == 3
    assert stream.width == 16
    assert stream.height == 16


def test_render_plan_resamples_timeline_at_the_requested_output_fps(tmp_path):
    project = _project()
    project = ViewerProject(
        camera=project.camera,
        timeline=project.timeline,
        display=project.display,
        appearance=project.appearance,
        render=RenderSettings(
            width=3,
            height=2,
            fps=4.0,
            output_kind=OutputKind.PNG_SEQUENCE,
        ),
    )

    plan = RenderPlan.from_project(project, tmp_path / "frames")

    assert plan.timeline.fps == 4.0
    assert plan.frame_count == 5
    assert plan.frame_pose(4) == project.timeline.shots[0].end


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


def test_render_controller_aborts_encoder_when_setup_fails(qapp, tmp_path):
    class SetupFailAdapter:
        appearance_settings = None

        def set_display_settings(self, _settings):
            raise RuntimeError("display setup failed")

    class TrackingEncoder:
        instance = None

        def __init__(self, _config):
            self._state = EncoderState.CREATED
            self.error = None
            self.abort_called = False
            TrackingEncoder.instance = self

        @property
        def state(self):
            return self._state

        def start(self):
            self._state = EncoderState.RUNNING

        def abort(self):
            self.abort_called = True
            self._state = EncoderState.ABORTED

    controller = ViewerRenderController(
        SetupFailAdapter(),
        encoder_factory=TrackingEncoder,
    )

    with pytest.raises(ViewerRenderControllerError, match="display setup failed"):
        controller.start(RenderPlan.from_project(_project(), tmp_path / "failed"))

    assert TrackingEncoder.instance is not None
    assert TrackingEncoder.instance.abort_called
    assert TrackingEncoder.instance.state is EncoderState.ABORTED


def test_transparent_render_temporarily_sets_clear_alpha(qapp, tmp_path):
    class AlphaAdapter(FakeRenderAdapter):
        def __init__(self):
            super().__init__()
            self.background_alpha = 1.0
            self.alpha_history = []

        def set_background_alpha(self, alpha):
            self.background_alpha = float(alpha)
            self.alpha_history.append(self.background_alpha)

    project = ViewerProject(
        camera=CameraPose(position=(0.0, 0.0, 5.0)),
        render=RenderSettings(
            width=3,
            height=2,
            output_kind=OutputKind.PNG,
            transparent_background=True,
        ),
    )
    adapter = AlphaAdapter()
    controller = ViewerRenderController(adapter)

    controller.start(RenderPlan.from_project(project, tmp_path / "transparent.png"))
    deadline = time.monotonic() + 5.0
    while controller.is_running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)

    assert adapter.alpha_history[0] == pytest.approx(0.0)
    assert adapter.alpha_history[-1] == pytest.approx(1.0)


def test_render_controller_unpremultiplies_readback_before_transparent_png(
    qapp, tmp_path
):
    class PremultipliedAdapter(FakeRenderAdapter):
        def capture_frame(self, width=None, height=None, camera_pose=None):
            frame = np.zeros((height, width, 4), dtype=np.uint8)
            frame[:, :, :3] = (64, 32, 16)
            frame[:, :, 3] = 128
            return frame

    project = ViewerProject(
        camera=CameraPose(position=(0.0, 0.0, 5.0)),
        appearance=AppearanceSettings(
            tone_mapping="none",
            exposure=0.0,
            contrast=1.0,
            saturation=1.0,
            vignette=0.0,
            sharpening=0.0,
        ),
        render=RenderSettings(
            width=3,
            height=2,
            output_kind=OutputKind.PNG,
            transparent_background=True,
        ),
    )
    output = tmp_path / "premultiplied.png"
    controller = ViewerRenderController(PremultipliedAdapter())

    controller.start(RenderPlan.from_project(project, output))
    deadline = time.monotonic() + 5.0
    while controller.is_running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)

    assert not controller.is_running
    from PIL import Image

    with Image.open(output) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0)) == (128, 64, 32, 128)


def test_render_dialog_exposes_frozen_output_summary_and_cancel(qapp, tmp_path):
    project = _project()
    project = ViewerProject(
        camera=project.camera,
        timeline=project.timeline,
        display=DisplaySettings(mode=DisplayMode.OVERLAY),
        appearance=project.appearance,
        render=project.render,
    )
    dialog = ViewerRenderDialog(
        RenderPlan.from_project(project, tmp_path / "frames"),
        metrics={
            "gaussians": 123456,
            "estimated_gpu_bytes": 987654321,
            "sort_gpu_ms": 4.5,
        },
    )
    assert "3 × 2" in dialog.resolution_label.text()
    assert "3" in dialog.frame_count_label.text()
    assert "1.00" in dialog.duration_label.text()
    assert "Gaussian + 球体" in dialog.mode_label.text()
    assert "123,456" in dialog.gaussian_count_label.text()
    assert "941.9 MiB" in dialog.gpu_memory_label.text()
    assert "framebuffer" in dialog.memory_budget_label.text()
    assert dialog.progress_bar.value() == 0
    dialog.set_progress(0.5)
    assert "1 / 3" in dialog.frame_progress_label.text()
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
