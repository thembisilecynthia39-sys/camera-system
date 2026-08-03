"""Immutable render snapshots for deterministic stills and camera tours."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from camera_system_app.application.viewer_timeline import (
    sample_timeline,
    timeline_frame_count,
)
from camera_system_app.domain.viewer import (
    AppearanceSettings,
    CameraPose,
    CameraTimeline,
    DisplaySettings,
    OutputKind,
    RenderSettings,
    ViewerProject,
    ViewerValidationError,
    validate_render_settings,
)


class RenderPlanError(ViewerValidationError):
    """The frozen project state cannot be rendered as requested."""


@dataclass(frozen=True)
class RenderPlan:
    """All inputs needed by a render, captured before its first frame."""

    output_path: Path
    camera: CameraPose
    timeline: CameraTimeline
    display: DisplaySettings
    appearance: AppearanceSettings
    render: RenderSettings

    def __post_init__(self) -> None:
        if not isinstance(self.output_path, Path):
            object.__setattr__(self, "output_path", Path(self.output_path))
        if not isinstance(self.camera, CameraPose):
            raise RenderPlanError("render camera must be a CameraPose value")
        if not isinstance(self.timeline, CameraTimeline):
            raise RenderPlanError("render timeline must be a CameraTimeline value")
        if not isinstance(self.display, DisplaySettings):
            raise RenderPlanError("render display must be a DisplaySettings value")
        if not isinstance(self.appearance, AppearanceSettings):
            raise RenderPlanError("render appearance must be an AppearanceSettings value")
        if not isinstance(self.render, RenderSettings):
            raise RenderPlanError("render settings must be a RenderSettings value")
        try:
            validate_render_settings(self.render)
        except ViewerValidationError as exc:
            raise RenderPlanError(str(exc)) from exc
        if self.render.output_kind in (OutputKind.MP4, OutputKind.PNG_SEQUENCE) and not self.timeline.shots:
            raise RenderPlanError("视频或 PNG 序列输出需要至少一个相机镜头段")
        object.__setattr__(self, "output_path", Path(self.output_path).expanduser())

    @classmethod
    def from_project(cls, project: ViewerProject, output_path) -> "RenderPlan":
        if not isinstance(project, ViewerProject):
            raise RenderPlanError("project must be a ViewerProject value")
        return cls(
            output_path=Path(output_path),
            camera=project.camera,
            timeline=project.timeline,
            display=project.display,
            appearance=project.appearance,
            render=project.render,
        )

    @property
    def frame_count(self) -> int:
        if self.render.output_kind is OutputKind.PNG:
            return 1
        return timeline_frame_count(self.timeline)

    @property
    def duration_seconds(self) -> float:
        """Duration represented by the frozen camera tour, excluding encoding time."""

        if self.render.output_kind is OutputKind.PNG:
            return 0.0
        return self.timeline.duration_seconds

    def frame_pose(self, frame_index: int) -> CameraPose:
        if isinstance(frame_index, bool):
            raise RenderPlanError("frame_index must be a non-negative integer")
        try:
            index = int(frame_index)
        except (TypeError, ValueError):
            raise RenderPlanError("frame_index must be a non-negative integer")
        if index != frame_index or index < 0 or index >= self.frame_count:
            raise RenderPlanError("frame_index is outside the render plan")
        if self.render.output_kind is OutputKind.PNG:
            return self.camera
        return sample_timeline(self.timeline, index)

    def progress_for_frame(self, frame_index: int) -> float:
        if self.frame_count <= 0:
            return 1.0
        if frame_index < 0 or frame_index >= self.frame_count:
            raise RenderPlanError("frame_index is outside the render plan")
        return float(frame_index + 1) / float(self.frame_count)


__all__ = ["RenderPlan", "RenderPlanError"]
