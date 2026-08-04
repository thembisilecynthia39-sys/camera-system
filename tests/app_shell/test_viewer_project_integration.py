"""Integration tests for sidecar restoration and presentation mode."""

from __future__ import annotations

from pathlib import Path
import time

import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QFrame, QMessageBox, QWidget

from camera_system_app.bootstrap import build_context
from camera_system_app.application.viewer_session import ViewerSession
from camera_system_app.application.viewer_timeline import sample_timeline
from camera_system_app.domain.viewer import (
    CameraMode,
    CameraPose,
    DisplayMode,
    DisplaySettings,
    OutputKind,
    RenderSettings,
    ViewerProject,
)
from camera_system_app.infrastructure.viewer_project_store import ViewerProjectStore
from camera_system_app.ui.main_window import MainWindow
from camera_system_app.ui.viewer_bindings import ViewerBindings


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _binding(tmp_path, qapp, monkeypatch):
    for name in ("CONFIG", "DATA", "STATE", "CACHE"):
        monkeypatch.setenv("XDG_{}_HOME".format(name), str(tmp_path / name.lower()))
    context = build_context(project_root=str(PROJECT_ROOT))
    window = MainWindow(context.paths, context.settings)
    window.show()
    qapp.processEvents()
    binding = ViewerBindings(window, PROJECT_ROOT, window)
    return binding, window


def test_bindings_restore_matching_sidecar_state(tmp_path, qapp, monkeypatch):
    binding, window = _binding(tmp_path, qapp, monkeypatch)
    source = tmp_path / "room.ply"
    source.write_bytes(b"ply-source")
    store = ViewerProjectStore()
    project = ViewerProject(
        source_path=str(source.resolve()),
        source_size=source.stat().st_size,
        source_sha256=store.sha256_file(source),
        camera=CameraPose(position=(1.0, 2.0, 3.0)),
        display=DisplaySettings(mode=DisplayMode.OVERLAY),
    )
    store.save(project)

    restored = binding._load_project_state(source, project)

    assert restored == project
    window.deleteLater()


def test_bindings_reset_stale_sidecar_instead_of_silently_applying_it(
    tmp_path, qapp, monkeypatch
):
    binding, window = _binding(tmp_path, qapp, monkeypatch)
    source = tmp_path / "room.ply"
    source.write_bytes(b"original")
    store = ViewerProjectStore()
    stale = ViewerProject(
        source_path=str(source.resolve()),
        source_size=source.stat().st_size,
        source_sha256=store.sha256_file(source),
        display=DisplaySettings(mode=DisplayMode.SPHERE_SOLID),
    )
    store.save(stale)
    source.write_bytes(b"changed")
    fallback = ViewerProject(source_path=str(source.resolve()))

    restored = binding._load_project_state(source, fallback, allow_stale=False)

    assert restored == fallback
    window.deleteLater()


def test_presentation_mode_hides_chrome_and_is_reversible(qapp, tmp_path, monkeypatch):
    binding, window = _binding(tmp_path, qapp, monkeypatch)
    sidebar = window.findChild(QFrame, "sidebar")
    assert sidebar is not None
    assert sidebar.isVisible()

    binding.set_presentation_mode(True)
    assert binding.is_presentation_mode
    assert not sidebar.isVisible()
    assert not window.statusBar().isVisible()

    binding.set_presentation_mode(False)
    assert not binding.is_presentation_mode
    assert sidebar.isVisible()
    assert window.statusBar().isVisible()
    window.deleteLater()


def test_presentation_escape_from_viewer_child_exits_mode(qapp, tmp_path, monkeypatch):
    binding, window = _binding(tmp_path, qapp, monkeypatch)
    binding.set_presentation_mode(True)

    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Escape,
        Qt.KeyboardModifier.NoModifier,
    )

    assert binding.eventFilter(window.result_page, event) is True
    assert binding.is_presentation_mode is False
    window.deleteLater()


def test_presentation_button_reflects_active_state(qapp, tmp_path, monkeypatch):
    binding, window = _binding(tmp_path, qapp, monkeypatch)

    binding.set_presentation_mode(True)

    assert window.result_page._toolbar.presentation_button.text() == "退出演示"
    assert window.result_page._toolbar.presentation_button.toolTip() == "退出全屏演示模式"

    binding.set_presentation_mode(False)
    assert window.result_page._toolbar.presentation_button.text() == "演示"
    window.deleteLater()


def test_presentation_forces_camera_xyz_readout_and_restores_visibility(
    qapp, tmp_path, monkeypatch
):
    binding, window = _binding(tmp_path, qapp, monkeypatch)
    window.result_page.set_camera_info_visible(False)

    binding.set_presentation_mode(True)

    assert not window.result_page._camera_info_label.isHidden()

    binding.set_presentation_mode(False)
    assert window.result_page._camera_info_label.isHidden()
    window.deleteLater()


def test_left_arrow_orbits_without_timeline(qapp, tmp_path, monkeypatch):
    binding, window = _binding(tmp_path, qapp, monkeypatch)

    class OrbitAdapter:
        def __init__(self):
            self.calls = []
            self.pose = CameraPose(position=(0.0, 0.0, 5.0))

        def orbit(self, delta_yaw=0.0, delta_pitch=0.0):
            self.calls.append((delta_yaw, delta_pitch))
            return self.pose

    adapter = OrbitAdapter()
    binding._adapter = adapter
    binding._session = ViewerSession(adapter, ViewerProject())
    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Left,
        Qt.KeyboardModifier.NoModifier,
    )

    assert binding.eventFilter(window.result_page, event) is True
    assert adapter.calls
    assert adapter.calls[-1][0] < 0.0
    assert binding._session.project.camera == adapter.pose
    assert binding._session.is_dirty
    window.deleteLater()


def test_presentation_arrow_orbits_even_with_timeline(
    qapp, tmp_path, monkeypatch
):
    binding, window = _binding(tmp_path, qapp, monkeypatch)

    class OrbitAdapter:
        def __init__(self):
            self.calls = []

        def orbit(self, delta_yaw=0.0, delta_pitch=0.0):
            self.calls.append((delta_yaw, delta_pitch))

    from camera_system_app.domain.viewer import CameraShot, CameraTimeline

    adapter = OrbitAdapter()
    timeline = CameraTimeline(
        shots=(
            CameraShot(
                "shot",
                "镜头",
                CameraPose(position=(0.0, 0.0, 5.0)),
                CameraPose(position=(2.0, 0.0, 5.0)),
                duration_seconds=1.0,
            ),
        ),
        fps=2.0,
    )
    binding._adapter = adapter
    binding._session = ViewerSession(adapter, ViewerProject(timeline=timeline))
    binding._playback.set_timeline(timeline)
    binding.set_presentation_mode(True)

    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Right,
        Qt.KeyboardModifier.NoModifier,
    )

    assert binding.eventFilter(window.result_page, event) is True
    assert adapter.calls
    assert adapter.calls[-1][0] > 0.0
    assert binding._playback.current_frame == 0
    binding.set_presentation_mode(False)
    window.deleteLater()


def test_panorama_control_drives_timer_and_commits_once_on_stop(
    qapp, tmp_path, monkeypatch
):
    binding, window = _binding(tmp_path, qapp, monkeypatch)

    class OrbitAdapter:
        def __init__(self):
            self.calls = []
            self.end_calls = 0
            self.pose = CameraPose(position=(0.0, 0.0, 5.0))

        def orbit(self, delta_yaw=0.0, delta_pitch=0.0):
            self.calls.append((delta_yaw, delta_pitch))
            return self.pose

        def get_camera_pose(self):
            return self.pose

        def set_camera_pose(self, pose):
            self.pose = pose
            return pose

        def end_interaction(self):
            self.end_calls += 1

    adapter = OrbitAdapter()
    binding._adapter = adapter
    binding._session = ViewerSession(adapter, ViewerProject())
    button = getattr(window.result_page._toolbar, "panorama_button", None)
    assert button is not None
    window.result_page._toolbar.setEnabled(True)

    button.click()
    assert binding._panorama_active is True
    assert binding._panorama_timer.isActive()

    binding._on_panorama_tick()
    assert adapter.calls
    assert adapter.calls[-1][0] > 0.0

    button.click()
    assert binding._panorama_active is False
    assert not binding._panorama_timer.isActive()
    assert adapter.end_calls == 1
    window.deleteLater()


def test_bindings_drive_adapter_from_exact_timeline_frames(qapp, tmp_path, monkeypatch):
    binding, window = _binding(tmp_path, qapp, monkeypatch)

    class FakeAdapter:
        def __init__(self):
            self.poses = []

        def set_camera_pose(self, pose):
            self.poses.append(pose)

    from camera_system_app.domain.viewer import CameraShot, CameraTimeline

    adapter = FakeAdapter()
    timeline = CameraTimeline(
        shots=(
            CameraShot(
                "shot",
                "镜头",
                CameraPose(position=(0.0, 0.0, 5.0)),
                CameraPose(position=(2.0, 0.0, 5.0)),
                duration_seconds=1.0,
            ),
        ),
        fps=2.0,
    )
    binding._adapter = adapter
    binding._session = ViewerSession(adapter, ViewerProject(timeline=timeline))
    binding._playback.set_timeline(timeline)

    binding._on_frame_selected(1)

    assert adapter.poses[-1] == sample_timeline(timeline, 1)
    assert binding._playback.current_frame == 1
    window.deleteLater()


def test_bindings_display_adapter_canonical_camera_pose_after_edit(
    qapp, tmp_path, monkeypatch
):
    binding, window = _binding(tmp_path, qapp, monkeypatch)

    requested = CameraPose(
        position=(1.0, 0.0, 0.0),
        target=(0.0, 0.0, 0.0),
    )
    canonical = CameraPose(
        position=(1.0, 0.0, 0.0),
        target=(0.0, 0.0, 0.0),
        rotation_xyzw=(0.0, 0.7071067812, 0.0, 0.7071067812),
    )

    class CanonicalAdapter:
        def set_camera_pose(self, _pose):
            return canonical

    adapter = CanonicalAdapter()
    binding._adapter = adapter
    binding._session = ViewerSession(adapter, ViewerProject())
    poses = []
    window.result_page.set_current_camera_pose = poses.append

    binding._on_camera_pose_changed(requested)

    assert binding._session.project.camera == canonical
    assert poses == [canonical]
    window.deleteLater()


def test_failed_loaded_project_keeps_previous_adapter_scene(
    qapp, tmp_path, monkeypatch
):
    binding, window = _binding(tmp_path, qapp, monkeypatch)

    class FailingAdapter:
        def __init__(self, data):
            self.data = np.asarray(data).copy()
            self.pose = CameraPose(position=(0.0, 0.0, 5.0))

        def set_gaussians(self, data, bounds=None):
            self.data = np.asarray(data).copy()
            return int(self.data.shape[0])

        def get_camera_pose(self):
            return self.pose

        def snapshot_scene(self):
            return {"data": self.data.copy()}

        def restore_scene(self, snapshot):
            self.data = snapshot["data"].copy()

        def set_display_settings(self, _settings):
            raise RuntimeError("display setup failed")

    old_data = np.array([[1.0, 2.0]], dtype=np.float32)
    adapter = FailingAdapter(old_data)
    old_project = ViewerProject(source_path=str(tmp_path / "old.ply"))
    binding._adapter = adapter
    binding._session = ViewerSession(adapter, old_project)
    old_viewer = QWidget()
    window.result_page.set_viewer_widget(old_viewer, "old.ply", 1)
    qapp.processEvents()
    window.result_page.show_loading("new.ply")

    payload = (
        np.array([[9.0, 8.0]], dtype=np.float32),
        (np.zeros(3, dtype=np.float32), np.ones(3, dtype=np.float32)),
        12,
        "b" * 64,
    )
    binding._on_loaded(payload, str(tmp_path / "new.ply"))
    qapp.processEvents()

    assert np.array_equal(adapter.data, old_data)
    assert window.result_page._viewer_widget is old_viewer
    window.deleteLater()


def test_bindings_render_a_single_png_and_restore_scene_controls(qapp, tmp_path, monkeypatch):
    binding, window = _binding(tmp_path, qapp, monkeypatch)

    class FakeAdapter:
        def set_display_settings(self, _settings):
            pass

        def set_appearance_settings(self, _settings):
            pass

        def set_quality(self, _quality):
            pass

        def set_camera_pose(self, _pose):
            pass

        def capture_frame(self, width=None, height=None, camera_pose=None):
            return np.zeros((height, width, 3), dtype=np.uint8)

    project = ViewerProject(
        source_path="scene.ply",
        render=RenderSettings(
            width=3,
            height=2,
            output_kind=OutputKind.PNG,
        ),
    )
    binding._adapter = FakeAdapter()
    binding._session = ViewerSession(binding._adapter, project)
    window.result_page.set_viewer_widget(QWidget(), "scene.ply", 1)
    output = tmp_path / "still.png"
    binding.start_render(output)

    deadline = time.monotonic() + 5.0
    while binding._render_controller.is_running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)

    assert output.exists()
    assert binding._render_dialog is not None
    assert window.result_page._toolbar.isEnabled()
    window.deleteLater()


def test_bindings_keyboard_orbits_without_timeline_controls(
    qapp, tmp_path, monkeypatch
):
    binding, window = _binding(tmp_path, qapp, monkeypatch)

    class FakeAdapter:
        def __init__(self):
            self.calls = []

        def orbit(self, delta_yaw=0.0, delta_pitch=0.0):
            self.calls.append((delta_yaw, delta_pitch))

    adapter = FakeAdapter()
    binding._adapter = adapter
    binding._session = ViewerSession(adapter, ViewerProject())

    event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    assert binding.eventFilter(window, event) is True
    assert adapter.calls[-1][0] > 0.0
    window.deleteLater()


def test_toolbar_save_action_publishes_sidecar_and_clears_dirty_state(
    qapp, tmp_path, monkeypatch
):
    binding, window = _binding(tmp_path, qapp, monkeypatch)
    source = tmp_path / "scene.ply"
    source.write_bytes(b"scene")

    class FakeAdapter:
        def set_display_settings(self, _settings):
            pass

        def set_appearance_settings(self, _settings):
            pass

        def set_camera_pose(self, _pose):
            pass

    adapter = FakeAdapter()
    project = ViewerProject(
        source_path=str(source.resolve()),
        source_size=source.stat().st_size,
        source_sha256=ViewerProjectStore.sha256_file(source),
    )
    binding._adapter = adapter
    binding._session = ViewerSession(adapter, project)
    binding._session.set_timeline(project.timeline)
    window.result_page.set_viewer_widget(QWidget(), str(source), 1)
    binding._mark_project_dirty()

    window.result_page._toolbar.save_button.click()

    sidecar = source.with_suffix(".splatview.json")
    assert sidecar.is_file()
    assert binding._session.is_dirty is False
    assert window.result_page._toolbar.save_button.text() == "保存"
    window.deleteLater()


def test_opening_another_source_can_cancel_when_project_is_dirty(
    qapp, tmp_path, monkeypatch
):
    binding, window = _binding(tmp_path, qapp, monkeypatch)

    class DirtySession:
        is_dirty = True

    binding._session = DirtySession()
    monkeypatch.setattr(
        "camera_system_app.ui.viewer_bindings.QMessageBox.warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )

    assert binding._confirm_dirty_before_open() is False
    window.deleteLater()


def test_bindings_persist_fly_navigation_and_recall_camera_bookmarks(
    qapp, tmp_path, monkeypatch
):
    binding, window = _binding(tmp_path, qapp, monkeypatch)

    class FakeAdapter:
        def __init__(self):
            self.pose = CameraPose(position=(0.0, 0.0, 5.0))
            self.modes = []
            self.speeds = []
            self.poses = []

        def set_camera_mode(self, mode):
            self.modes.append(mode)

        def set_fly_speed(self, speed):
            self.speeds.append(speed)

        def get_camera_pose(self):
            return self.pose

        def set_camera_pose(self, pose):
            self.pose = pose
            self.poses.append(pose)

    adapter = FakeAdapter()
    binding._adapter = adapter
    binding._session = ViewerSession(adapter, ViewerProject(camera=adapter.pose))

    binding._on_camera_mode_changed(CameraMode.FLY.value)
    binding._on_fly_speed_changed(2.5)
    binding._on_bookmark_add_requested("入口")
    bookmark = binding._session.project.bookmarks[0]
    binding._on_bookmark_load_requested(bookmark.bookmark_id)
    binding._on_bookmark_delete_requested(bookmark.bookmark_id)

    assert binding._session.project.camera_mode is CameraMode.FLY
    assert binding._session.project.fly_speed == 2.5
    assert adapter.modes == [CameraMode.FLY]
    assert adapter.speeds == [2.5]
    assert adapter.poses[-1] == adapter.pose
    assert binding._session.project.bookmarks == ()
    window.deleteLater()


def test_bindings_surface_sphere_shader_fallback_without_hiding_standard_view(
    qapp, tmp_path, monkeypatch
):
    binding, window = _binding(tmp_path, qapp, monkeypatch)

    binding._on_sphere_availability_changed(False, "shader unavailable")

    combo = window.result_page._toolbar.display_mode_combo
    sphere_index = combo.findData(DisplayMode.SPHERE_SOLID.value)
    assert combo.model().item(sphere_index).isEnabled() is False
    assert window.result_page._inspector.sphere_sigma_multiplier.isEnabled() is False
    assert "外接球显示不可用" in window.result_page._banner._text.text()
    assert "标准 Gaussian" in window.result_page._banner._text.text()
    window.deleteLater()


def test_bindings_apply_editable_camera_position_and_target(
    qapp, tmp_path, monkeypatch
):
    binding, window = _binding(tmp_path, qapp, monkeypatch)

    class FakeAdapter:
        def __init__(self):
            self.poses = []

        def set_camera_pose(self, pose):
            self.poses.append(pose)

    from camera_system_app.domain.viewer import CameraPose

    adapter = FakeAdapter()
    binding._adapter = adapter
    binding._session = ViewerSession(adapter, ViewerProject())
    pose = CameraPose(
        position=(4.0, 5.0, 6.0),
        target=(1.0, 2.0, 3.0),
        fov_degrees=61.0,
    )

    binding._on_camera_pose_changed(pose)

    assert binding._session.project.camera == pose
    assert adapter.poses[-1] == pose
    assert binding._session.is_dirty
    window.deleteLater()


def test_display_background_color_is_used_by_final_render_settings(
    qapp, tmp_path, monkeypatch
):
    binding, window = _binding(tmp_path, qapp, monkeypatch)

    class FakeAdapter:
        def set_display_settings(self, _settings):
            pass

    adapter = FakeAdapter()
    binding._adapter = adapter
    binding._session = ViewerSession(adapter, ViewerProject())
    settings = DisplaySettings(background_color=(0.2, 0.4, 0.6))

    binding.set_display_settings(settings)

    assert binding._session.project.display.background_color == (0.2, 0.4, 0.6)
    assert binding._session.project.render.background_color == (0.2, 0.4, 0.6)
    window.deleteLater()
