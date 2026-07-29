"""Adapter embedding the existing q3dviewer Gaussian renderer."""

from __future__ import annotations

import os
import sys
from math import pi
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal


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

    def __init__(self, project_root: Path, parent=None) -> None:
        super().__init__(parent)
        prepare_q3dviewer(project_root)
        from q3dviewer.custom_items.gaussian_item import GaussianItem
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
        self.widget.add_item_with_name("gaussian", self.item)
        self._default_center = np.zeros(3, dtype=np.float64)
        self._default_distance = 4.0
        self._default_euler = np.array([pi / 3, 0.0, pi / 4], dtype=np.float64)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self.widget.update)
        self.widget.interaction_started.connect(self._begin_interaction)
        self.widget.interaction_finished.connect(self._end_interaction)
        self._released = False
        self._active = True

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
        self._default_center = (lo + hi) * 0.5
        radius = float(np.linalg.norm(hi - lo) * 0.5)
        self._default_distance = max(radius * 2.5, 1.0)
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
