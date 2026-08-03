"""Tests for the application-owned viewer session boundary."""

from __future__ import annotations

from camera_system_app.application.viewer_session import ViewerSession
from camera_system_app.domain.viewer import (
    AppearanceSettings,
    CameraPose,
    CameraShot,
    CameraTimeline,
    DisplayMode,
    DisplaySettings,
    RenderSettings,
    ViewerProject,
)


class FakeViewerAdapter:
    def __init__(self):
        self.display = None
        self.appearance = None
        self.camera = None
        self.calls = []

    def set_display_settings(self, settings):
        self.calls.append("display")
        self.display = settings

    def set_appearance_settings(self, settings):
        self.calls.append("appearance")
        self.appearance = settings

    def set_camera_pose(self, pose):
        self.calls.append("camera")
        self.camera = pose


def test_session_updates_adapter_and_marks_project_dirty_for_display_changes():
    adapter = FakeViewerAdapter()
    session = ViewerSession(adapter)
    settings = DisplaySettings(mode=DisplayMode.SPHERE_WIREFRAME)

    session.set_display_settings(settings)

    assert adapter.display == settings
    assert session.project.display == settings
    assert session.is_dirty
    assert adapter.calls == ["display"]


def test_session_can_apply_a_complete_project_once_and_remain_clean():
    adapter = FakeViewerAdapter()
    session = ViewerSession(adapter)
    pose = CameraPose(position=(1.0, 2.0, 3.0))
    project = ViewerProject(
        camera=pose,
        display=DisplaySettings(mode=DisplayMode.OVERLAY),
        appearance=AppearanceSettings(exposure=1.0),
        timeline=CameraTimeline(
            shots=(CameraShot("shot", "Shot", pose, pose, duration_seconds=1.0),)
        ),
        render=RenderSettings(width=640, height=480),
    )

    session.apply_project(project)

    assert session.project == project
    assert not session.is_dirty
    assert adapter.camera == pose
    assert adapter.display == project.display
    assert adapter.appearance == project.appearance
    assert adapter.calls == ["display", "appearance", "camera"]


def test_session_camera_and_appearance_changes_are_independent_updates():
    adapter = FakeViewerAdapter()
    session = ViewerSession(adapter)
    pose = CameraPose(position=(2.0, 0.0, 4.0))
    appearance = AppearanceSettings(contrast=1.2)

    session.set_camera_pose(pose)
    session.set_appearance_settings(appearance)

    assert session.project.camera == pose
    assert session.project.appearance == appearance
    assert adapter.calls == ["camera", "appearance"]
    assert session.is_dirty


def test_mark_clean_clears_only_edit_state_without_resetting_project():
    adapter = FakeViewerAdapter()
    session = ViewerSession(adapter)
    settings = DisplaySettings(mode=DisplayMode.SPHERE_SOLID)
    session.set_display_settings(settings)

    session.mark_clean()

    assert not session.is_dirty
    assert session.project.display == settings
