"""Embedded 3D Gaussian-splat workspace."""

from __future__ import annotations

import os
import sys
import logging
from math import radians
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from multiwebcam.ui.fluent import check_box

logger = logging.getLogger(__name__)

LIGHTWEIGHT_MAX_GAUSSIANS = 80_000
HIGH_QUALITY_MAX_GAUSSIANS = 240_000
HIGH_QUALITY_FRAME_INTERVAL_MS = 100


class GaussianModelView(QWidget):
    """Hosts q3dviewer's OpenGL widget inside the capture application."""

    model_loaded = Signal(str)
    load_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("gaussianModelSurface")
        self._gl_widget = None
        self._gaussian_item = None
        self._axis_item = None
        self._load_worker = None
        self._current_model_path = None
        self._reload_after_worker = False
        self._shutting_down = False
        self._active = False
        self._interacting = False
        self._warmup_frames = 0
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(50)
        self._render_timer.timeout.connect(self._render_frame)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._placeholder = QLabel("从左侧选择一个 3DGS .ply 模型")
        self._placeholder.setObjectName("modelPlaceholder")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._placeholder)

        self._overlay = QFrame(self)
        self._overlay.setObjectName("modelViewportControls")
        overlay_layout = QHBoxLayout(self._overlay)
        overlay_layout.setContentsMargins(10, 7, 10, 7)
        overlay_layout.setSpacing(12)
        self._orbit_checkbox = check_box("自动 360°")
        self._axis_checkbox = check_box("显示坐标系")
        self._axis_checkbox.setChecked(True)
        self._high_quality_checkbox = check_box("高质量预览")
        self._high_quality_checkbox.setChecked(False)
        self._high_quality_checkbox.setToolTip(
            "启用最多 24 万个 Gaussian、最高 3 阶球谐颜色和视深排序；加载与交互会更慢"
        )
        overlay_layout.addWidget(self._orbit_checkbox)
        overlay_layout.addWidget(self._axis_checkbox)
        overlay_layout.addWidget(self._high_quality_checkbox)
        self._orbit_checkbox.toggled.connect(self.set_auto_orbit)
        self._axis_checkbox.toggled.connect(self.set_axis_visible)
        self._high_quality_checkbox.toggled.connect(self.set_high_quality_preview)
        self._overlay.adjustSize()
        self._overlay.raise_()

    def load_model(self, path: Path) -> None:
        """Load a model off the GUI thread using the selected quality mode."""
        if self._shutting_down:
            return
        path = Path(path)
        self._current_model_path = path
        if self._load_worker is not None and self._load_worker.isRunning():
            self._reload_after_worker = True
            self._load_worker.requestInterruption()
            return
        try:
            self._ensure_renderer()
        except Exception as exc:
            logger.exception("Failed to initialize the 3DGS renderer")
            self.load_failed.emit(str(exc))
            return
        high_quality = self._high_quality_checkbox.isChecked()
        worker = _ModelLoadWorker(
            path,
            max_gaussians=(
                HIGH_QUALITY_MAX_GAUSSIANS
                if high_quality else LIGHTWEIGHT_MAX_GAUSSIANS
            ),
            full_sh=high_quality,
            parent=self,
        )
        self._load_worker = worker
        worker.loaded.connect(self._apply_loaded_model)
        worker.failed.connect(self.load_failed.emit)
        worker.finished.connect(lambda worker=worker: self._release_load_worker(worker))
        worker.start()

    def _apply_loaded_model(self, gs_data: object, center: object, distance: float, name: str) -> None:
        if self._shutting_down:
            return
        self._gaussian_item.set_data(gs_data=gs_data)
        self._gl_widget.set_cam_position(center=center, distance=distance)
        self._axis_item.set_size(max(distance * 0.2, 0.1))
        axis_transform = np.eye(4, dtype=np.float32)
        axis_transform[:3, 3] = center
        self._axis_item.set_transform(axis_transform)
        self._gl_widget.show_center = False
        # Upload happens in paintGL. A few coalesced updates are sufficient;
        # repeatedly preprocessing a large model only keeps the GPU saturated.
        self._warmup_frames = 4
        if self._active:
            self._render_timer.start()
        logger.info("3DGS model loaded: %s (%s gaussians)", name, len(gs_data))
        self.model_loaded.emit(name)

    def _release_load_worker(self, worker: QThread) -> None:
        if self._load_worker is worker:
            self._load_worker = None
        worker.deleteLater()
        if self._reload_after_worker and not self._shutting_down:
            self._reload_after_worker = False
            path = self._current_model_path
            if path is not None:
                QTimer.singleShot(0, lambda path=path: self.load_model(path))

    def set_active(self, active: bool) -> None:
        """Run the renderer only while its workspace is visible."""
        self._active = active
        if active and self._gl_widget is not None:
            self._warmup_frames = max(self._warmup_frames, 3)
            self._render_timer.start()
        else:
            self._render_timer.stop()

    def set_auto_orbit(self, enabled: bool) -> None:
        self._ensure_renderer()
        self._gl_widget.auto_orbit = enabled
        high_quality = self._high_quality_checkbox.isChecked()
        self._render_timer.setInterval(
            HIGH_QUALITY_FRAME_INTERVAL_MS if enabled and high_quality else 50
        )
        if not enabled and self._gaussian_item.sort_enabled:
            self._gaussian_item.request_sort()
        if self._active and enabled:
            self._render_timer.start()
        else:
            self._render_timer.stop()
        self._gl_widget.update()

    def set_axis_visible(self, visible: bool) -> None:
        self._ensure_renderer()
        self._axis_item.set_visible(visible)
        self._warmup_frames = max(self._warmup_frames, 2)
        if self._active:
            self._render_timer.start()

    def set_high_quality_preview(self, enabled: bool) -> None:
        """Switch between the lightweight preview and the full-quality path."""
        if self._gaussian_item is not None:
            self._gaussian_item.sort_enabled = enabled
            self._gaussian_item.request_sort()
        if self._interacting or (self._gl_widget is not None and self._gl_widget.auto_orbit):
            self._render_timer.setInterval(
                HIGH_QUALITY_FRAME_INTERVAL_MS if enabled else 33
            )

        path = self._current_model_path
        if path is not None:
            worker = self._load_worker
            if worker is not None and worker.isRunning():
                self._reload_after_worker = True
                worker.requestInterruption()
            else:
                self.load_model(path)
        elif self._gaussian_item is not None:
            self._warmup_frames = max(self._warmup_frames, 2)
            if self._active:
                self._render_timer.start()

    def _begin_interaction(self) -> None:
        self._interacting = True
        self._gl_widget.auto_orbit = False
        if self._gaussian_item is not None:
            self._gaussian_item.sort_suspended = True
        if self._orbit_checkbox.isChecked():
            self._orbit_checkbox.blockSignals(True)
            self._orbit_checkbox.setChecked(False)
            self._orbit_checkbox.blockSignals(False)
        self._render_timer.setInterval(
            HIGH_QUALITY_FRAME_INTERVAL_MS
            if self._high_quality_checkbox.isChecked() else 33
        )
        if self._active:
            self._render_timer.start()

    def _end_interaction(self) -> None:
        self._interacting = False
        if self._gaussian_item is not None:
            self._gaussian_item.sort_suspended = False
            if self._gaussian_item.sort_enabled:
                self._gaussian_item.request_sort()
        self._warmup_frames = max(self._warmup_frames, 2)
        self._render_timer.setInterval(50)
        if self._active:
            self._render_timer.start()

    def _render_frame(self) -> None:
        if self._active and self._gl_widget is not None:
            self._gl_widget.update()
            if self._warmup_frames > 0:
                self._warmup_frames -= 1
            if self._warmup_frames == 0 and not self._gl_widget.auto_orbit and not self._interacting:
                self._render_timer.stop()

    def _ensure_renderer(self) -> None:
        if self._gl_widget is not None:
            return

        q3dviewer_root = _find_q3dviewer_root()
        if q3dviewer_root is None:
            raise FileNotFoundError("未找到 3DGSviewer/q3dviewer")
        # q3dviewer must use the same Qt objects as the host application.
        # On Jetson the local PySide6 compatibility shim exports PyQt5 types;
        # on desktop these objects come from the real PySide6 package.
        qt_binding = QWidget.__module__.split(".", 1)[0]
        if qt_binding not in {"PyQt5", "PySide6"}:
            raise RuntimeError(f"无法识别当前 Qt 绑定: {QWidget.__module__}")
        os.environ["Q3D_QT_IMPL"] = qt_binding
        sys.path.insert(0, str(q3dviewer_root))

        from q3dviewer.custom_items.gaussian_item import GaussianItem
        from q3dviewer.custom_items.axis_item import AxisItem
        from OpenGL.GL import GL_DEPTH_TEST, glDisable, glEnable
        from q3dviewer.tools.gaussian_viewer import GaussianGLWidget
        from q3dviewer.utils.maths import euler_to_matrix
        owner = self

        class InteractiveGaussianGLWidget(GaussianGLWidget):
            def mousePressEvent(self, event):
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                super().mousePressEvent(event)

            def mouseMoveEvent(self, event):
                position = event.localPos()
                buttons = event.buttons()
                if not buttons & (
                    Qt.MouseButton.LeftButton
                    | Qt.MouseButton.RightButton
                    | Qt.MouseButton.MiddleButton
                ):
                    return
                start = self._drag_start_pos
                if start is None:
                    start = position
                    self._drag_start_pos = start
                if not self._drag_started:
                    delta = position - start
                    if (
                        abs(delta.x()) + abs(delta.y())
                        < self._drag_threshold
                    ):
                        return
                    self._drag_started = True
                    owner._begin_interaction()
                else:
                    delta = position - self.mousePos
                self.mousePos = position

                if buttons & Qt.MouseButton.LeftButton:
                    # Conventional orbit control: horizontal drag changes yaw,
                    # vertical drag changes pitch, including top/bottom views.
                    self.rotate(
                        radians(-delta.y() * 0.25),
                        0.0,
                        radians(-delta.x() * 0.25),
                    )
                elif buttons & (Qt.MouseButton.RightButton | Qt.MouseButton.MiddleButton):
                    rotation = euler_to_matrix(self.euler)
                    inverse_intrinsics = np.linalg.inv(self.get_K())
                    distance = max(self.dist, 0.5)
                    self.translate(
                        rotation @ inverse_intrinsics @ np.array([-delta.x(), delta.y(), 0.0]) * distance
                    )
                self.update()

            def mouseReleaseEvent(self, event):
                had_drag = self._drag_started
                super().mouseReleaseEvent(event)
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                if had_drag:
                    owner._end_interaction()

            def wheelEvent(self, event):
                owner._begin_interaction()
                super().wheelEvent(event)
                self.update()
                QTimer.singleShot(150, owner._end_interaction)

        self._gl_widget = InteractiveGaussianGLWidget()
        self._gl_widget.setCursor(Qt.CursorShape.OpenHandCursor)
        self._gl_widget.set_color(np.array([0.05, 0.07, 0.09, 1.0]))
        self._gl_widget.enable_show_center = False
        self._gl_widget.enable_depth_picking = False
        self._gaussian_item = GaussianItem(
            sort_enabled=self._high_quality_checkbox.isChecked(),
            sort_backend="opengl",
            sort_min_interval=0.3,
            sort_direction_threshold=0.05,
        )
        class VisibleAxisItem(AxisItem):
            def paint(self):
                glDisable(GL_DEPTH_TEST)
                super().paint()
                glEnable(GL_DEPTH_TEST)

        self._axis_item = VisibleAxisItem(size=1.0, width=5)
        self._gl_widget.add_item_with_name("gaussian", self._gaussian_item)
        self._gl_widget.add_item_with_name("world_axis", self._axis_item)
        self._layout.replaceWidget(self._placeholder, self._gl_widget)
        self._placeholder.deleteLater()
        self._overlay.raise_()
        if self._active and self._gl_widget.auto_orbit:
            self._render_timer.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._overlay.adjustSize()
        self._overlay.move(12, 12)
        self._overlay.raise_()

    def shutdown(self) -> None:
        """Stop timers and finish the loader before this widget is destroyed."""
        if self._shutting_down:
            return
        self._shutting_down = True
        self._render_timer.stop()
        worker = self._load_worker
        if worker is not None:
            if worker.isRunning():
                worker.requestInterruption()
                worker.wait()
            if self._load_worker is worker:
                self._load_worker = None
                worker.deleteLater()

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)


class _ModelLoadWorker(QThread):
    loaded = Signal(object, object, float, str)
    failed = Signal(str)

    def __init__(self, path: Path, max_gaussians: int, full_sh: bool, parent=None):
        super().__init__(parent)
        self._path = path
        self._max_gaussians = max_gaussians
        self._full_sh = full_sh

    def run(self) -> None:
        try:
            gs_data, center, distance = _load_binary_ply_preview(
                self._path,
                self._max_gaussians,
                full_sh=self._full_sh,
                cancelled=self.isInterruptionRequested,
            )
            if self.isInterruptionRequested():
                return
            self.loaded.emit(gs_data, center, distance, self._path.name)
        except Exception as exc:
            if self.isInterruptionRequested():
                return
            logger.exception("Failed to load 3DGS model %s", self._path)
            self.failed.emit(str(exc))


def _load_binary_ply_preview(
    path: Path,
    max_gaussians: int,
    full_sh: bool = False,
    cancelled=None,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Load a lightweight DC sample or a full-resolution SH payload."""
    type_map = {
        "char": "i1", "uchar": "u1", "short": "<i2", "ushort": "<u2",
        "int": "<i4", "uint": "<u4", "float": "<f4", "double": "<f8",
    }
    properties = []
    vertex_count = None
    with path.open("rb") as stream:
        while True:
            raw = stream.readline()
            if not raw:
                raise ValueError("PLY 文件缺少 end_header")
            line = raw.decode("ascii").strip()
            if line.startswith("format ") and line != "format binary_little_endian 1.0":
                raise ValueError("当前快速预览仅支持 binary_little_endian PLY")
            if line.startswith("element vertex "):
                vertex_count = int(line.rsplit(" ", 1)[1])
            elif line.startswith("property "):
                parts = line.split()
                if len(parts) == 3 and parts[1] in type_map:
                    properties.append((parts[2], type_map[parts[1]]))
            elif line == "end_header":
                data_offset = stream.tell()
                break
    if not vertex_count:
        raise ValueError("PLY 文件没有 Gaussian 顶点")
    if cancelled is not None and cancelled():
        raise InterruptedError("模型加载已取消")

    required = {"x", "y", "z", "rot_0", "rot_1", "rot_2", "rot_3",
                "scale_0", "scale_1", "scale_2", "opacity", "f_dc_0", "f_dc_1", "f_dc_2"}
    names = {name for name, _dtype in properties}
    missing = sorted(required - names)
    if missing:
        raise ValueError(f"PLY 缺少字段: {', '.join(missing)}")

    mapped = np.memmap(path, dtype=np.dtype(properties), mode="r", offset=data_offset, shape=(vertex_count,))
    sample_count = vertex_count if max_gaussians <= 0 else min(vertex_count, max_gaussians)
    if sample_count == vertex_count:
        sample = mapped
    else:
        indices = np.linspace(0, vertex_count - 1, sample_count, dtype=np.int64)
        sample = mapped[indices]
    if cancelled is not None and cancelled():
        raise InterruptedError("模型加载已取消")

    points = np.column_stack((sample["x"], sample["y"], sample["z"])).astype(np.float32)
    rotations = np.column_stack(tuple(sample[f"rot_{i}"] for i in range(4))).astype(np.float32)
    norms = np.linalg.norm(rotations, axis=1, keepdims=True)
    rotations /= np.maximum(norms, 1e-8)
    scales = np.exp(np.column_stack(tuple(sample[f"scale_{i}"] for i in range(3)))).astype(np.float32)
    opacity = (1.0 / (1.0 + np.exp(-sample["opacity"]))).astype(np.float32)[:, None]
    colors = np.column_stack(tuple(sample[f"f_dc_{i}"] for i in range(3))).astype(np.float32)
    spherical_harmonics = colors
    if full_sh:
        rest_names = sorted(
            (name for name in names if name.startswith("f_rest_")),
            key=lambda name: int(name.rsplit("_", 1)[1]),
        )
        if len(rest_names) not in {0, 9, 24, 45}:
            raise ValueError(
                "PLY 球谐字段数量无效；应包含 0、9、24 或 45 个 f_rest_* 字段"
            )
        if rest_names:
            rest = np.column_stack(tuple(sample[name] for name in rest_names)).astype(np.float32)
            rest = rest.reshape(-1, 3, len(rest_names) // 3)
            rest = rest.transpose(0, 2, 1).reshape(-1, len(rest_names))
            spherical_harmonics = np.column_stack((colors, rest))

    gs_data = np.ascontiguousarray(
        np.column_stack((points, rotations, scales, opacity, spherical_harmonics)),
        dtype=np.float32,
    )

    finite_points = points[np.isfinite(points).all(axis=1)]
    if not finite_points.size:
        raise ValueError("PLY 中没有有效坐标")
    lower = np.percentile(finite_points, 1, axis=0)
    upper = np.percentile(finite_points, 99, axis=0)
    center = ((lower + upper) * 0.5).astype(np.float32)
    distance = max(float(np.linalg.norm(upper - lower) * 1.25), 1.0)
    return gs_data, center, distance


def _find_q3dviewer_root() -> Path | None:
    configured = os.environ.get("MULTIWEBCAM_Q3DVIEWER_ROOT")
    candidates = [Path(configured).expanduser()] if configured else []
    camera_system = Path(__file__).resolve().parents[5]
    candidates.append(camera_system / "3DGSviewer" / "q3dviewer")
    return next((path for path in candidates if (path / "q3dviewer").is_dir()), None)
