"""Adapter embedding the existing q3dviewer Gaussian renderer."""

from __future__ import annotations

import os
import sys
from math import isfinite, pi
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal

from camera_system_app.domain.viewer import (
    AppearanceSettings,
    CameraMode,
    CameraPose,
    DisplaySettings,
)


class ViewerLoadError(Exception):
    """A local result cannot be loaded as a Gaussian Splat PLY."""


def prepare_q3dviewer(project_root: Path) -> Path:
    """Select the main application's Qt binding and expose q3dviewer source."""

    root = Path(project_root).resolve() / "3DGSviewer" / "q3dviewer"
    package = root / "q3dviewer"
    if not package.is_dir():
        raise ViewerLoadError("找不到 q3dviewer 源码目录：{}".format(package))
    os.environ["Q3D_QT_IMPL"] = "PySide6"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def load_gaussian_ply(
    path: Path,
    project_root: Path,
    cancel_check: Callable[[], bool] | None = None,
):
    """Load and validate one local 3DGS PLY without creating a Qt widget."""

    if cancel_check is not None and cancel_check():
        raise InterruptedError("Gaussian PLY loading cancelled")
    local_path = Path(path).expanduser().resolve()
    if not local_path.exists():
        raise ViewerLoadError("结果文件不存在：{}".format(local_path))
    if not local_path.is_file():
        raise ViewerLoadError("结果路径不是文件：{}".format(local_path))
    if local_path.suffix.lower() != ".ply":
        raise ViewerLoadError("结果格式不支持，仅支持 .ply：{}".format(local_path.name))
    prepare_q3dviewer(project_root)
    try:
        from q3dviewer.utils.cloud_io import load_gs_ply

        gaussians = load_gs_ply(
            str(local_path),
            cancel_check=cancel_check,
        )
    except InterruptedError:
        raise
    except Exception as exc:
        raise ViewerLoadError(
            "PLY 格式错误或 Gaussian 数据加载失败：{}".format(exc)
        ) from exc
    required = {"pw", "rot", "scale", "alpha", "sh"}
    names = set(gaussians.dtype.names or ())
    if not required.issubset(names):
        raise ViewerLoadError(
            "PLY 缺少 Gaussian 属性：{}".format(
                ", ".join(sorted(required - names))
            )
        )
    if gaussians.shape[0] == 0:
        raise ViewerLoadError("PLY 不包含任何 Gaussian 点")
    flat = gaussians.view(np.float32).reshape(gaussians.shape[0], -1)
    for start in range(0, flat.shape[0], 65536):
        if cancel_check is not None and cancel_check():
            raise InterruptedError("Gaussian PLY loading cancelled")
        if not np.isfinite(flat[start : start + 65536]).all():
            raise ViewerLoadError("PLY 包含无效的 NaN 或无穷数值")
    return gaussians


class Q3DViewerAdapter(QObject):
    """Own one embedded q3dviewer GLWidget and its existing GaussianItem."""

    rendering_failed = Signal(str)
    sphere_availability_changed = Signal(bool, str)

    def __init__(self, project_root: Path, parent=None) -> None:
        super().__init__(parent)
        prepare_q3dviewer(project_root)
        from q3dviewer.custom_items.gaussian_item import GaussianItem
        from q3dviewer.custom_items.scene_overlay_item import SceneOverlayItem
        from q3dviewer.glwidget import GLWidget

        self.widget = GLWidget()
        # A result-view click must only focus the widget. Depth picking reads
        # back the framebuffer and recenters the camera, which looks like an
        # unexpected zoom and is too costly for large Gaussian models.
        self.widget.enable_depth_picking = False
        self.widget.setMinimumSize(480, 320)
        self.widget.set_color(np.array([0.04, 0.08, 0.11, 1.0], dtype=np.float32))
        self.widget.initialization_failed.connect(self.rendering_failed.emit)
        self.item = GaussianItem(
            sort_enabled=True,
            sort_backend="opengl",
            sort_min_interval=0.10,
        )
        self.item.render_controller.set_sphere_availability_callback(
            self._on_sphere_availability_changed
        )
        self.widget.add_item_with_name("gaussian", self.item)
        self.overlay_item = SceneOverlayItem()
        self.overlay_item.disable_setting()
        self.widget.add_item_with_name("scene_overlays", self.overlay_item)
        self._default_center = np.zeros(3, dtype=np.float64)
        self._default_distance = 4.0
        self._default_euler = np.array([pi / 3, 0.0, pi / 4], dtype=np.float64)
        self._bounds = None
        self._display_settings = DisplaySettings()
        self._appearance_settings = AppearanceSettings()
        self._background_alpha = 1.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self.widget.update)
        self.widget.interaction_started.connect(self._begin_interaction)
        self.widget.interaction_finished.connect(self._end_interaction)
        self._released = False
        self._active = True

    def _on_sphere_availability_changed(self, available: bool, error: str) -> None:
        self.sphere_availability_changed.emit(bool(available), str(error or ""))

    def set_gaussians(self, gaussians: Any, bounds=None) -> int:
        """Upload CPU Gaussian data on the GUI thread and fit the camera."""

        gs_data = gaussians.view(np.float32).reshape(gaussians.shape[0], -1)
        self.item.set_data(gs_data=gs_data, validated=True)
        if bounds is None:
            points = np.asarray(gaussians["pw"], dtype=np.float32)
            lo = np.percentile(points, 1, axis=0)
            hi = np.percentile(points, 99, axis=0)
        else:
            lo, hi = bounds
        lo = np.asarray(lo, dtype=np.float64)
        hi = np.asarray(hi, dtype=np.float64)
        if (
            lo.shape != (3,)
            or hi.shape != (3,)
            or not np.isfinite(lo).all()
            or not np.isfinite(hi).all()
            or np.any(hi < lo)
        ):
            raise ValueError("Gaussian bounds must be finite three-dimensional values")
        self._bounds = (lo.copy(), hi.copy())
        self._default_center = (lo + hi) * 0.5
        radius = float(np.linalg.norm(hi - lo) * 0.5)
        self._default_distance = max(radius * 2.5, 1.0)
        self.overlay_item.set_bounds(lo, hi)
        self.reset_view()
        return int(gaussians.shape[0])

    def _begin_interaction(self) -> None:
        if not self._active:
            return
        self.item.set_interactive_preview(True, max_gaussians=120000)
        if not self._timer.isActive():
            self._timer.start()
        self.widget.update()

    def _end_interaction(self) -> None:
        self._timer.stop()
        self.item.set_interactive_preview(False)
        # One final full-quality frame refreshes SH color and depth sorting.
        if self._active:
            self.widget.update()

    def set_active(self, active: bool) -> None:
        """Render only while the result page owns the visible GPU workload."""

        self._active = bool(active)
        if self._active:
            self.widget.update()
            return
        self._timer.stop()
        self.item.set_interactive_preview(False)

    def reset_view(self) -> None:
        self.widget.set_cam_position(
            center=self._default_center.copy(),
            distance=self._default_distance,
            euler=self._default_euler.copy(),
        )
        self.item.request_sort()
        self.widget.update()

    def fit_scene(self) -> None:
        self.reset_view()

    def set_view_preset(self, preset: str) -> None:
        presets = {
            "front": np.array([0.0, 0.0, 0.0], dtype=np.float64),
            "back": np.array([0.0, 0.0, pi], dtype=np.float64),
            "left": np.array([0.0, -pi / 2.0, 0.0], dtype=np.float64),
            "right": np.array([0.0, pi / 2.0, 0.0], dtype=np.float64),
            "top": np.array([-pi / 2.0, 0.0, 0.0], dtype=np.float64),
            "bottom": np.array([pi / 2.0, 0.0, 0.0], dtype=np.float64),
        }
        key = str(preset).lower().strip()
        if key not in presets:
            raise ValueError("unsupported view preset: {}".format(preset))
        self.widget.set_cam_position(
            center=self._default_center.copy(),
            distance=self._default_distance,
            euler=presets[key],
        )
        self.item.request_sort()
        self.widget.update()

    def set_display_settings(self, settings: DisplaySettings) -> None:
        if not isinstance(settings, DisplaySettings):
            raise ValueError("display settings must be a DisplaySettings value")
        self.item.set_display_mode(settings.mode.value)
        self.item.set_quality(settings.quality.value)
        self.item.set_sphere_settings(
            sigma_multiplier=settings.sphere_sigma_multiplier,
            opacity=settings.sphere_opacity,
            line_width=settings.sphere_line_width,
            color_mode=settings.sphere_color_mode,
            color=settings.sphere_color,
            all_instances=settings.sphere_all_instances,
        )
        self.overlay_item.set_options(
            grid=settings.show_grid,
            axis=settings.show_axis,
            bounds=settings.show_bounds,
            center=settings.show_center,
        )
        self.widget.set_color(
            np.asarray(
                (*settings.background_color, self._background_alpha),
                dtype=np.float32,
            )
        )
        self._display_settings = settings
        self.widget.update()

    def set_quality(self, quality: str) -> str:
        return self.item.set_quality(quality)

    def set_camera_mode(self, mode: CameraMode | str) -> None:
        mode = mode if isinstance(mode, CameraMode) else CameraMode(mode)
        self.widget.set_camera_mode(mode.value)

    def set_fly_speed(self, speed: float) -> None:
        self.widget.set_fly_speed(float(speed))

    @property
    def background_alpha(self) -> float:
        return self._background_alpha

    def set_background_alpha(self, alpha: float) -> None:
        try:
            value = float(alpha)
        except (TypeError, ValueError):
            raise ValueError("background alpha must be a number")
        if not isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("background alpha must be between 0 and 1")
        self._background_alpha = value
        color = np.asarray(self.widget.color, dtype=np.float32).copy()
        color[3] = value
        self.widget.set_color(color)

    @property
    def appearance_settings(self) -> AppearanceSettings:
        return self._appearance_settings

    def set_appearance_settings(self, settings: AppearanceSettings) -> None:
        if not isinstance(settings, AppearanceSettings):
            raise ValueError("appearance settings must be an AppearanceSettings value")
        set_sh_degree = getattr(self.item, "set_sh_degree", None)
        if callable(set_sh_degree):
            set_sh_degree(settings.sh_degree)
        set_appearance = getattr(self.item, "set_appearance_settings", None)
        if callable(set_appearance):
            set_appearance(settings)
        self._appearance_settings = settings

    def snapshot_scene(self) -> dict[str, Any]:
        """Capture the mutable renderer state before a scene replacement."""

        return {
            "gaussians": (
                None
                if self.item.gpu_data.count == 0
                else self.item.gs_data
            ),
            "bounds": (
                None
                if self._bounds is None
                else tuple(np.array(value, copy=True) for value in self._bounds)
            ),
            "camera_state": dict(self.get_camera_state()),
            "display_settings": self._display_settings,
            "appearance_settings": self._appearance_settings,
            "background_alpha": self._background_alpha,
        }

    def restore_scene(self, snapshot: dict[str, Any]) -> None:
        """Restore a scene snapshot after a failed GUI-thread replacement."""

        if not isinstance(snapshot, dict):
            raise ValueError("scene snapshot must be a dictionary")
        gaussians = snapshot.get("gaussians")
        if gaussians is not None:
            self.set_gaussians(gaussians, bounds=snapshot.get("bounds"))
        self.set_display_settings(snapshot["display_settings"])
        self.set_appearance_settings(snapshot["appearance_settings"])
        self.set_background_alpha(snapshot["background_alpha"])
        self.set_camera_state(snapshot["camera_state"])
        self.widget.update()

    def get_camera_state(self) -> dict[str, Any]:
        return self.widget.get_camera_state()

    def set_camera_state(self, state: dict[str, Any]) -> None:
        self.widget.set_camera_state(state)

    @staticmethod
    def _camera_state_for_pose(pose: CameraPose) -> dict[str, Any]:
        from q3dviewer.utils.maths import matrix_to_euler, quaternion_to_matrix

        position = np.asarray(pose.position, dtype=np.float64)
        target = np.asarray(pose.target, dtype=np.float64)
        offset = position - target
        distance = float(np.linalg.norm(offset))
        if not isfinite(distance) or distance <= 1e-8:
            raise ValueError("camera position and target must be different")

        direction = offset / distance
        rotation = quaternion_to_matrix(pose.rotation_xyzw)
        if not np.allclose(rotation[:, 2], direction, rtol=1e-6, atol=1e-6):
            world_up = np.array([0.0, 1.0, 0.0], dtype=np.float64)
            if abs(float(np.dot(world_up, direction))) > 0.98:
                world_up = np.array([0.0, 0.0, 1.0], dtype=np.float64)
            right = np.cross(world_up, direction)
            right /= np.linalg.norm(right)
            up = np.cross(direction, right)
            rotation = np.column_stack((right, up, direction))

        return {
            "center": target.tolist(),
            "euler": matrix_to_euler(rotation).tolist(),
            "distance": distance,
            "fov_degrees": pose.fov_degrees,
        }

    def get_camera_pose(self) -> CameraPose:
        from q3dviewer.utils.maths import euler_to_matrix, matrix_to_quaternion

        state = self.widget.get_camera_state()
        center = np.asarray(state["center"], dtype=np.float64)
        rotation = euler_to_matrix(np.asarray(state["euler"], dtype=np.float64))
        position = center + rotation.dot(np.array([0.0, 0.0, state["distance"]]))
        return CameraPose(
            position=position,
            target=center,
            rotation_xyzw=matrix_to_quaternion(rotation),
            fov_degrees=state["fov_degrees"],
        )

    def set_camera_pose(self, pose: CameraPose) -> CameraPose:
        if not isinstance(pose, CameraPose):
            raise ValueError("camera pose must be a CameraPose value")
        self.widget.set_camera_state(self._camera_state_for_pose(pose))
        return self.get_camera_pose()

    def orbit(self, delta_yaw=0.0, delta_pitch=0.0) -> CameraPose:
        """Apply one scene-centered orbit step and return the canonical pose."""

        self.widget.orbit(delta_yaw=delta_yaw, delta_pitch=delta_pitch)
        return self.get_camera_pose()

    def end_interaction(self) -> bool:
        """Immediately restore full-quality rendering after scripted orbiting."""

        was_interacting = self.widget.finish_interaction(notify=False)
        self._end_interaction()
        return bool(was_interacting)

    def capture_frame(self, width=None, height=None, camera_pose=None):
        if width is None and height is None and camera_pose is None:
            return self.widget.capture_frame()
        if width is None or height is None:
            raise ValueError("width and height must be supplied together")
        camera_state = None
        if camera_pose is not None:
            if not isinstance(camera_pose, CameraPose):
                raise ValueError("camera_pose must be a CameraPose value")
            camera_state = self._camera_state_for_pose(camera_pose)
        return self.widget.render_to_array(
            width,
            height,
            camera_state=camera_state,
        )

    def performance_metrics(self) -> dict[str, Any]:
        """Renderer timing plus Jetson unified-memory availability."""
        metrics = dict(self.item.performance_metrics())
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    metrics["unified_memory_available_bytes"] = (
                        int(line.split()[1]) * 1024
                    )
                    break
        except (OSError, ValueError, IndexError):
            pass
        return metrics

    def release(self) -> None:
        if self._released:
            return
        self._timer.stop()
        self.widget.cleanup_gl()
        self.widget.setting_window.close()
        self._released = True
