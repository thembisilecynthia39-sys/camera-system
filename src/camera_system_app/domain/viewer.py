"""Qt-free state models for the 3DGS roaming and presentation viewer.

The viewer keeps its editable state in small, JSON-safe value objects.  The
models deliberately do not import Qt, NumPy, or the renderer so that timeline,
validation, and project persistence can be tested without a graphics context.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Sequence, Tuple


Vector3 = Tuple[float, float, float]
Quaternion = Tuple[float, float, float, float]
Color3 = Tuple[float, float, float]


class ViewerValidationError(ValueError):
    """Raised when viewer state cannot be rendered or persisted safely."""


class DisplayMode(str, Enum):
    STANDARD = "standard"
    SPHERE_WIREFRAME = "sphere_wireframe"
    SPHERE_SOLID = "sphere_solid"
    OVERLAY = "overlay"


class SphereStyle(str, Enum):
    WIREFRAME = "wireframe"
    SOLID = "solid"
    OVERLAY = "overlay"


class QualityPreset(str, Enum):
    PREVIEW = "preview"
    HIGH = "high"
    FINAL = "final"


class OutputKind(str, Enum):
    PNG = "png"
    PNG_SEQUENCE = "png_sequence"
    MP4 = "mp4"


def _finite_float(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ViewerValidationError("{} must be a number".format(label))
    if not math.isfinite(result):
        raise ViewerValidationError("{} must be finite".format(label))
    return result


def _vector3(value: Sequence[Any], label: str) -> Vector3:
    if isinstance(value, (str, bytes)) or len(value) != 3:
        raise ViewerValidationError("{} must contain exactly three values".format(label))
    return tuple(_finite_float(component, label) for component in value)  # type: ignore


def _color3(value: Sequence[Any], label: str) -> Color3:
    color = _vector3(value, label)
    if any(component < 0.0 or component > 1.0 for component in color):
        raise ViewerValidationError("{} values must be between 0 and 1".format(label))
    return color


def _quaternion(value: Sequence[Any]) -> Quaternion:
    if isinstance(value, (str, bytes)) or len(value) != 4:
        raise ViewerValidationError("rotation_xyzw must contain exactly four values")
    raw = tuple(_finite_float(component, "rotation_xyzw") for component in value)
    norm = math.sqrt(sum(component * component for component in raw))
    if norm <= 1e-12:
        raise ViewerValidationError("rotation_xyzw cannot be a zero quaternion")
    normalized = tuple(round(component / norm, 12) for component in raw)
    return normalized  # type: ignore


def _enum(value: Any, enum_type: Any, label: str) -> Any:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError):
        raise ViewerValidationError("unsupported {}: {}".format(label, value))


@dataclass(frozen=True)
class CameraPose:
    """A renderer-independent camera pose."""

    position: Vector3 = (0.0, 0.0, 5.0)
    target: Vector3 = (0.0, 0.0, 0.0)
    rotation_xyzw: Quaternion = (0.0, 0.0, 0.0, 1.0)
    fov_degrees: float = 45.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "position", _vector3(self.position, "position"))
        object.__setattr__(self, "target", _vector3(self.target, "target"))
        object.__setattr__(self, "rotation_xyzw", _quaternion(self.rotation_xyzw))
        fov = _finite_float(self.fov_degrees, "fov_degrees")
        if not 1.0 <= fov <= 179.0:
            raise ViewerValidationError("fov_degrees must be between 1 and 179")
        object.__setattr__(self, "fov_degrees", fov)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": list(self.position),
            "target": list(self.target),
            "rotation_xyzw": list(self.rotation_xyzw),
            "fov_degrees": self.fov_degrees,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CameraPose":
        return cls(
            position=value.get("position", (0.0, 0.0, 5.0)),
            target=value.get("target", (0.0, 0.0, 0.0)),
            rotation_xyzw=value.get("rotation_xyzw", (0.0, 0.0, 0.0, 1.0)),
            fov_degrees=value.get("fov_degrees", 45.0),
        )


@dataclass(frozen=True)
class CameraShot:
    """One camera move and its optional holds."""

    shot_id: str
    name: str
    start: CameraPose
    end: CameraPose
    duration_seconds: float = 3.0
    hold_start_seconds: float = 0.0
    hold_end_seconds: float = 0.0
    easing: str = "smoothstep"

    def __post_init__(self) -> None:
        if not str(self.shot_id).strip():
            raise ViewerValidationError("shot_id cannot be empty")
        if not str(self.name).strip():
            raise ViewerValidationError("shot name cannot be empty")
        object.__setattr__(self, "shot_id", str(self.shot_id))
        object.__setattr__(self, "name", str(self.name))
        if not isinstance(self.start, CameraPose) or not isinstance(self.end, CameraPose):
            raise ViewerValidationError("shot start and end must be CameraPose values")
        duration = _finite_float(self.duration_seconds, "duration_seconds")
        hold_start = _finite_float(self.hold_start_seconds, "hold_start_seconds")
        hold_end = _finite_float(self.hold_end_seconds, "hold_end_seconds")
        if duration <= 0.0:
            raise ViewerValidationError("duration_seconds must be positive")
        if hold_start < 0.0 or hold_end < 0.0:
            raise ViewerValidationError("shot hold durations cannot be negative")
        easing = str(self.easing).lower()
        if easing not in ("linear", "smoothstep"):
            raise ViewerValidationError("unsupported shot easing: {}".format(self.easing))
        object.__setattr__(self, "duration_seconds", duration)
        object.__setattr__(self, "hold_start_seconds", hold_start)
        object.__setattr__(self, "hold_end_seconds", hold_end)
        object.__setattr__(self, "easing", easing)

    @property
    def total_seconds(self) -> float:
        return self.hold_start_seconds + self.duration_seconds + self.hold_end_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "name": self.name,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "duration_seconds": self.duration_seconds,
            "hold_start_seconds": self.hold_start_seconds,
            "hold_end_seconds": self.hold_end_seconds,
            "easing": self.easing,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CameraShot":
        return cls(
            shot_id=value.get("shot_id", "shot"),
            name=value.get("name", "Shot"),
            start=CameraPose.from_dict(value.get("start", {})),
            end=CameraPose.from_dict(value.get("end", {})),
            duration_seconds=value.get("duration_seconds", 3.0),
            hold_start_seconds=value.get("hold_start_seconds", 0.0),
            hold_end_seconds=value.get("hold_end_seconds", 0.0),
            easing=value.get("easing", "smoothstep"),
        )


@dataclass(frozen=True)
class CameraTimeline:
    """Ordered camera shots sampled at a deterministic frame rate."""

    shots: Tuple[CameraShot, ...] = ()
    fps: float = 30.0
    loop: bool = False

    def __post_init__(self) -> None:
        shots = tuple(self.shots)
        if any(not isinstance(shot, CameraShot) for shot in shots):
            raise ViewerValidationError("timeline shots must be CameraShot values")
        fps = _finite_float(self.fps, "timeline fps")
        if not 1.0 <= fps <= 240.0:
            raise ViewerValidationError("timeline fps must be between 1 and 240")
        object.__setattr__(self, "shots", shots)
        object.__setattr__(self, "fps", fps)
        object.__setattr__(self, "loop", bool(self.loop))

    @property
    def duration_seconds(self) -> float:
        return sum(shot.total_seconds for shot in self.shots)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shots": [shot.to_dict() for shot in self.shots],
            "fps": self.fps,
            "loop": self.loop,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CameraTimeline":
        return cls(
            shots=tuple(CameraShot.from_dict(item) for item in value.get("shots", ())),
            fps=value.get("fps", 30.0),
            loop=value.get("loop", False),
        )


@dataclass(frozen=True)
class DisplaySettings:
    """Realtime Gaussian display and sphere-overlay settings."""

    mode: DisplayMode = DisplayMode.STANDARD
    quality: QualityPreset = QualityPreset.HIGH
    sphere_style: SphereStyle = SphereStyle.WIREFRAME
    sphere_sigma_multiplier: float = 3.0
    sphere_opacity: float = 0.5
    sphere_line_width: float = 1.0
    sphere_color_mode: str = "gaussian"
    sphere_color: Color3 = (0.35, 0.78, 1.0)
    background_color: Color3 = (0.025, 0.035, 0.055)
    show_grid: bool = False
    show_camera_guides: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", _enum(self.mode, DisplayMode, "display mode"))
        object.__setattr__(self, "quality", _enum(self.quality, QualityPreset, "quality"))
        object.__setattr__(self, "sphere_style", _enum(self.sphere_style, SphereStyle, "sphere style"))
        multiplier = _finite_float(self.sphere_sigma_multiplier, "sphere_sigma_multiplier")
        opacity = _finite_float(self.sphere_opacity, "sphere_opacity")
        line_width = _finite_float(self.sphere_line_width, "sphere_line_width")
        if multiplier <= 0.0:
            raise ViewerValidationError("sphere_sigma_multiplier must be positive")
        if not 0.0 <= opacity <= 1.0:
            raise ViewerValidationError("sphere_opacity must be between 0 and 1")
        if line_width <= 0.0:
            raise ViewerValidationError("sphere_line_width must be positive")
        object.__setattr__(self, "sphere_sigma_multiplier", multiplier)
        object.__setattr__(self, "sphere_opacity", opacity)
        object.__setattr__(self, "sphere_line_width", line_width)
        object.__setattr__(self, "sphere_color_mode", str(self.sphere_color_mode))
        object.__setattr__(self, "sphere_color", _color3(self.sphere_color, "sphere_color"))
        object.__setattr__(self, "background_color", _color3(self.background_color, "background_color"))
        object.__setattr__(self, "show_grid", bool(self.show_grid))
        object.__setattr__(self, "show_camera_guides", bool(self.show_camera_guides))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "quality": self.quality.value,
            "sphere_style": self.sphere_style.value,
            "sphere_sigma_multiplier": self.sphere_sigma_multiplier,
            "sphere_opacity": self.sphere_opacity,
            "sphere_line_width": self.sphere_line_width,
            "sphere_color_mode": self.sphere_color_mode,
            "sphere_color": list(self.sphere_color),
            "background_color": list(self.background_color),
            "show_grid": self.show_grid,
            "show_camera_guides": self.show_camera_guides,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DisplaySettings":
        return cls(
            mode=value.get("mode", DisplayMode.STANDARD.value),
            quality=value.get("quality", QualityPreset.HIGH.value),
            sphere_style=value.get("sphere_style", SphereStyle.WIREFRAME.value),
            sphere_sigma_multiplier=value.get("sphere_sigma_multiplier", 3.0),
            sphere_opacity=value.get("sphere_opacity", 0.5),
            sphere_line_width=value.get("sphere_line_width", 1.0),
            sphere_color_mode=value.get("sphere_color_mode", "gaussian"),
            sphere_color=value.get("sphere_color", (0.35, 0.78, 1.0)),
            background_color=value.get("background_color", (0.025, 0.035, 0.055)),
            show_grid=value.get("show_grid", False),
            show_camera_guides=value.get("show_camera_guides", False),
        )


@dataclass(frozen=True)
class AppearanceSettings:
    """Bounded presentation look applied to interactive and final output."""

    exposure: float = 0.0
    tone_mapping: str = "aces"
    contrast: float = 1.0
    saturation: float = 1.0
    vignette: float = 0.0
    sharpening: float = 0.0

    def __post_init__(self) -> None:
        exposure = _finite_float(self.exposure, "exposure")
        contrast = _finite_float(self.contrast, "contrast")
        saturation = _finite_float(self.saturation, "saturation")
        vignette = _finite_float(self.vignette, "vignette")
        sharpening = _finite_float(self.sharpening, "sharpening")
        if not -20.0 <= exposure <= 20.0:
            raise ViewerValidationError("exposure must be between -20 and 20")
        if contrast < 0.0 or saturation < 0.0:
            raise ViewerValidationError("contrast and saturation cannot be negative")
        if not 0.0 <= vignette <= 1.0 or not 0.0 <= sharpening <= 1.0:
            raise ViewerValidationError("vignette and sharpening must be between 0 and 1")
        object.__setattr__(self, "exposure", exposure)
        object.__setattr__(self, "tone_mapping", str(self.tone_mapping))
        object.__setattr__(self, "contrast", contrast)
        object.__setattr__(self, "saturation", saturation)
        object.__setattr__(self, "vignette", vignette)
        object.__setattr__(self, "sharpening", sharpening)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exposure": self.exposure,
            "tone_mapping": self.tone_mapping,
            "contrast": self.contrast,
            "saturation": self.saturation,
            "vignette": self.vignette,
            "sharpening": self.sharpening,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AppearanceSettings":
        return cls(
            exposure=value.get("exposure", 0.0),
            tone_mapping=value.get("tone_mapping", "aces"),
            contrast=value.get("contrast", 1.0),
            saturation=value.get("saturation", 1.0),
            vignette=value.get("vignette", 0.0),
            sharpening=value.get("sharpening", 0.0),
        )


@dataclass(frozen=True)
class RenderSettings:
    """Immutable-at-render-start output settings."""

    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    output_kind: OutputKind = OutputKind.MP4
    quality: QualityPreset = QualityPreset.FINAL
    transparent_background: bool = False
    background_color: Color3 = (0.025, 0.035, 0.055)
    max_dimension: int = 8192

    def __post_init__(self) -> None:
        try:
            width = int(self.width)
            height = int(self.height)
            max_dimension = int(self.max_dimension)
        except (TypeError, ValueError):
            raise ViewerValidationError("render dimensions must be integers")
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "max_dimension", max_dimension)
        object.__setattr__(self, "fps", _finite_float(self.fps, "render fps"))
        object.__setattr__(self, "output_kind", _enum(self.output_kind, OutputKind, "output kind"))
        object.__setattr__(self, "quality", _enum(self.quality, QualityPreset, "render quality"))
        object.__setattr__(self, "transparent_background", bool(self.transparent_background))
        object.__setattr__(self, "background_color", _color3(self.background_color, "background_color"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "output_kind": self.output_kind.value,
            "quality": self.quality.value,
            "transparent_background": self.transparent_background,
            "background_color": list(self.background_color),
            "max_dimension": self.max_dimension,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RenderSettings":
        return cls(
            width=value.get("width", 1920),
            height=value.get("height", 1080),
            fps=value.get("fps", 30.0),
            output_kind=value.get("output_kind", OutputKind.MP4.value),
            quality=value.get("quality", QualityPreset.FINAL.value),
            transparent_background=value.get("transparent_background", False),
            background_color=value.get("background_color", (0.025, 0.035, 0.055)),
            max_dimension=value.get("max_dimension", 8192),
        )


@dataclass(frozen=True)
class ViewerProject:
    """Complete sidecar-persisted state for one Gaussian source."""

    source_path: str = ""
    source_size: int = 0
    source_sha256: str = ""
    version: int = 1
    camera: CameraPose = field(default_factory=CameraPose)
    timeline: CameraTimeline = field(default_factory=CameraTimeline)
    display: DisplaySettings = field(default_factory=DisplaySettings)
    appearance: AppearanceSettings = field(default_factory=AppearanceSettings)
    render: RenderSettings = field(default_factory=RenderSettings)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_path", str(self.source_path))
        try:
            source_size = int(self.source_size)
            version = int(self.version)
        except (TypeError, ValueError):
            raise ViewerValidationError("source_size and version must be integers")
        if source_size < 0:
            raise ViewerValidationError("source_size cannot be negative")
        if version < 1:
            raise ViewerValidationError("unsupported viewer project version")
        object.__setattr__(self, "source_size", source_size)
        object.__setattr__(self, "version", version)
        digest = str(self.source_sha256).lower()
        if digest and not re.match(r"^[0-9a-f]{64}$", digest):
            raise ViewerValidationError("source_sha256 must be a 64-character hex digest")
        object.__setattr__(self, "source_sha256", digest)
        if not isinstance(self.camera, CameraPose):
            raise ViewerValidationError("camera must be a CameraPose value")
        if not isinstance(self.timeline, CameraTimeline):
            raise ViewerValidationError("timeline must be a CameraTimeline value")
        if not isinstance(self.display, DisplaySettings):
            raise ViewerValidationError("display must be a DisplaySettings value")
        if not isinstance(self.appearance, AppearanceSettings):
            raise ViewerValidationError("appearance must be an AppearanceSettings value")
        if not isinstance(self.render, RenderSettings):
            raise ViewerValidationError("render must be a RenderSettings value")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "source": {
                "path": self.source_path,
                "size": self.source_size,
                "sha256": self.source_sha256,
            },
            "camera": self.camera.to_dict(),
            "timeline": self.timeline.to_dict(),
            "display": self.display.to_dict(),
            "appearance": self.appearance.to_dict(),
            "render": self.render.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ViewerProject":
        source = value.get("source", {})
        return cls(
            version=value.get("version", 1),
            source_path=source.get("path", value.get("source_path", "")),
            source_size=source.get("size", value.get("source_size", 0)),
            source_sha256=source.get("sha256", value.get("source_sha256", "")),
            camera=CameraPose.from_dict(value.get("camera", {})),
            timeline=CameraTimeline.from_dict(value.get("timeline", {})),
            display=DisplaySettings.from_dict(value.get("display", {})),
            appearance=AppearanceSettings.from_dict(value.get("appearance", {})),
            render=RenderSettings.from_dict(value.get("render", {})),
        )


def validate_render_settings(settings: RenderSettings) -> None:
    """Validate settings at the boundary before allocating a render target."""

    if not isinstance(settings, RenderSettings):
        raise ViewerValidationError("render settings must be a RenderSettings value")
    if settings.width <= 0 or settings.height <= 0:
        raise ViewerValidationError("render width and height must be positive")
    if settings.max_dimension <= 0:
        raise ViewerValidationError("max_dimension must be positive")
    if settings.width > settings.max_dimension or settings.height > settings.max_dimension:
        raise ViewerValidationError("render dimensions exceed the configured safety limit")
    if not 1.0 <= settings.fps <= 240.0:
        raise ViewerValidationError("render fps must be between 1 and 240")
    if settings.output_kind is OutputKind.MP4 and settings.transparent_background:
        raise ViewerValidationError("transparent background is supported for PNG output only")
