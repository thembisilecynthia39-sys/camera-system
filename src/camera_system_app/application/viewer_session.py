"""Application-owned state boundary for the 3DGS viewer."""

from __future__ import annotations

from dataclasses import replace

from camera_system_app.domain.viewer import (
    AppearanceSettings,
    CameraBookmark,
    CameraMode,
    CameraPose,
    CameraTimeline,
    DisplaySettings,
    RenderSettings,
    ViewerProject,
    ViewerValidationError,
)


class ViewerSession:
    """Keep editable project state in sync with a renderer adapter."""

    def __init__(self, adapter, project=None):
        if project is not None and not isinstance(project, ViewerProject):
            raise ViewerValidationError("viewer session project must be a ViewerProject value")
        self.adapter = adapter
        self._project = project if project is not None else ViewerProject()
        self._dirty = False

    @property
    def project(self):
        return self._project

    @property
    def is_dirty(self):
        return self._dirty

    def apply_project(self, project):
        if not isinstance(project, ViewerProject):
            raise ViewerValidationError("viewer session project must be a ViewerProject value")
        self.adapter.set_display_settings(project.display)
        self.adapter.set_appearance_settings(project.appearance)
        self.adapter.set_camera_pose(project.camera)
        set_camera_mode = getattr(self.adapter, "set_camera_mode", None)
        if callable(set_camera_mode):
            set_camera_mode(project.camera_mode)
        set_fly_speed = getattr(self.adapter, "set_fly_speed", None)
        if callable(set_fly_speed):
            set_fly_speed(project.fly_speed)
        self._project = project
        self._dirty = False

    def set_display_settings(self, settings):
        if not isinstance(settings, DisplaySettings):
            raise ViewerValidationError("display settings must be a DisplaySettings value")
        self.adapter.set_display_settings(settings)
        self._project = replace(self._project, display=settings)
        self._dirty = True

    def set_appearance_settings(self, settings):
        if not isinstance(settings, AppearanceSettings):
            raise ViewerValidationError("appearance settings must be an AppearanceSettings value")
        self.adapter.set_appearance_settings(settings)
        self._project = replace(self._project, appearance=settings)
        self._dirty = True

    def set_camera_pose(self, pose):
        if not isinstance(pose, CameraPose):
            raise ViewerValidationError("camera pose must be a CameraPose value")
        applied_pose = self.adapter.set_camera_pose(pose)
        if not isinstance(applied_pose, CameraPose):
            applied_pose = pose
        self._project = replace(self._project, camera=applied_pose)
        self._dirty = True
        return applied_pose

    def record_camera_pose(self, pose):
        """Record a pose that the adapter has already applied to its camera."""

        if not isinstance(pose, CameraPose):
            raise ViewerValidationError("camera pose must be a CameraPose value")
        self._project = replace(self._project, camera=pose)
        self._dirty = True
        return pose

    def set_camera_mode(self, mode):
        mode = mode if isinstance(mode, CameraMode) else CameraMode(mode)
        set_camera_mode = getattr(self.adapter, "set_camera_mode", None)
        if callable(set_camera_mode):
            set_camera_mode(mode)
        self._project = replace(self._project, camera_mode=mode)
        self._dirty = True

    def set_fly_speed(self, speed):
        project = replace(self._project, fly_speed=speed)
        set_fly_speed = getattr(self.adapter, "set_fly_speed", None)
        if callable(set_fly_speed):
            set_fly_speed(project.fly_speed)
        self._project = project
        self._dirty = True

    def set_bookmarks(self, bookmarks):
        bookmarks = tuple(bookmarks)
        if any(not isinstance(bookmark, CameraBookmark) for bookmark in bookmarks):
            raise ViewerValidationError("bookmarks must be CameraBookmark values")
        self._project = replace(self._project, bookmarks=bookmarks)
        self._dirty = True

    def set_timeline(self, timeline):
        if not isinstance(timeline, CameraTimeline):
            raise ViewerValidationError("timeline must be a CameraTimeline value")
        self._project = replace(self._project, timeline=timeline)
        self._dirty = True

    def set_render_settings(self, settings):
        if not isinstance(settings, RenderSettings):
            raise ViewerValidationError("render settings must be a RenderSettings value")
        self._project = replace(self._project, render=settings)
        self._dirty = True

    def fit_scene(self):
        self.adapter.fit_scene()
        pose = self.adapter.get_camera_pose()
        if isinstance(pose, CameraPose):
            self._project = replace(self._project, camera=pose)
            self._dirty = True
        return pose

    def capture_frame(self, width=None, height=None):
        return self.adapter.capture_frame(
            width=width,
            height=height,
            camera_pose=self._project.camera,
        )

    def performance_metrics(self):
        return self.adapter.performance_metrics()

    def mark_clean(self):
        self._dirty = False


__all__ = ["ViewerSession"]
