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
        overlay_layout.addWidget(self._orbit_checkbox)
        overlay_layout.addWidget(self._axis_checkbox)
        self._orbit_checkbox.toggled.connect(self.set_auto_orbit)
        self._axis_checkbox.toggled.connect(self.set_axis_visible)
        self._overlay.adjustSize()
        self._overlay.raise_()

    def load_model(self, path: Path) -> None:
        """Load and decimate a model off the GUI thread."""
        if self._load_worker is not None and self._load_worker.isRunning():
            return
        self._ensure_renderer()
        self._load_worker = _ModelLoadWorker(path, max_gaussians=80_000, parent=self)
        self._load_worker.loaded.connect(self._apply_loaded_model)
        self._load_worker.failed.connect(self.load_failed.emit)
        self._load_worker.finished.connect(self._release_load_worker)
        self._load_worker.start()

    def _apply_loaded_model(self, gs_data: object, center: object, distance: float, name: str) -> None:
        self._gaussian_item.set_data(gs_data=gs_data)
        self._gl_widget.set_cam_position(center=center, distance=distance)
        self._axis_item.set_size(max(distance * 0.2, 0.1))
        axis_transform = np.eye(4, dtype=np.float32)
        axis_transform[:3, 3] = center
        self._axis_item.set_transform(axis_transform)
        self._gl_widget.show_center = False
        # Upload happens in paintGL. Keep a bounded one-second render window so
        # the first frame survives stacked-page and GPU scheduling delays.
        self._warmup_frames = 20
        if self._active:
            self._render_timer.start()
        logger.info("3DGS model loaded: %s (%s preview gaussians)", name, len(gs_data))
        self.model_loaded.emit(name)

    def _release_load_worker(self) -> None:
        worker = self._load_worker
        self._load_worker = None
        if worker is not None:
            worker.deleteLater()

    def set_active(self, active: bool) -> None:
        """Run the renderer only while its workspace is visible."""
        self._active = active
        if active and self._gl_widget is not None:
            self._warmup_frames = max(self._warmup_frames, 8)
            self._render_timer.start()
        elif self._warmup_frames == 0:
            self._render_timer.stop()

    def set_auto_orbit(self, enabled: bool) -> None:
        self._ensure_renderer()
        self._gl_widget.auto_orbit = enabled
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

    def _begin_interaction(self) -> None:
        self._interacting = True
        self._gl_widget.auto_orbit = False
        if self._orbit_checkbox.isChecked():
            self._orbit_checkbox.blockSignals(True)
            self._orbit_checkbox.setChecked(False)
            self._orbit_checkbox.blockSignals(False)
        self._render_timer.setInterval(33)
        if self._active:
            self._render_timer.start()

    def _end_interaction(self) -> None:
        self._interacting = False
        self._warmup_frames = max(self._warmup_frames, 4)
        self._render_timer.setInterval(50)

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
        os.environ.setdefault("Q3D_QT_IMPL", "PyQt5")
        sys.path.insert(0, str(q3dviewer_root))

        from q3dviewer.custom_items.gaussian_item import GaussianItem
        from q3dviewer.custom_items.axis_item import AxisItem
        from OpenGL.GL import GL_DEPTH_TEST, glDisable, glEnable
        from q3dviewer.tools.gaussian_viewer import GaussianGLWidget
        from q3dviewer.utils.maths import euler_to_matrix
        owner = self

        class InteractiveGaussianGLWidget(GaussianGLWidget):
            def mousePressEvent(self, event):
                owner._begin_interaction()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                super().mousePressEvent(event)

            def mouseMoveEvent(self, event):
                position = event.localPos()
                if not hasattr(self, "mousePos"):
                    self.mousePos = position
                delta = position - self.mousePos
                self.mousePos = position

                if event.buttons() & Qt.MouseButton.LeftButton:
                    # Conventional orbit control: horizontal drag changes yaw,
                    # vertical drag changes pitch, including top/bottom views.
                    self.rotate(
                        radians(-delta.y() * 0.25),
                        0.0,
                        radians(-delta.x() * 0.25),
                    )
                elif event.buttons() & (Qt.MouseButton.RightButton | Qt.MouseButton.MiddleButton):
                    rotation = euler_to_matrix(self.euler)
                    inverse_intrinsics = np.linalg.inv(self.get_K())
                    distance = max(self.dist, 0.5)
                    self.translate(
                        rotation @ inverse_intrinsics @ np.array([-delta.x(), delta.y(), 0.0]) * distance
                    )
                self.update()

            def mouseReleaseEvent(self, event):
                super().mouseReleaseEvent(event)
                self.setCursor(Qt.CursorShape.OpenHandCursor)
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
        self._gaussian_item = GaussianItem(sort_enabled=False, sort_backend="opengl")
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


class _ModelLoadWorker(QThread):
    loaded = Signal(object, object, float, str)
    failed = Signal(str)

    def __init__(self, path: Path, max_gaussians: int, parent=None):
        super().__init__(parent)
        self._path = path
        self._max_gaussians = max_gaussians

    def run(self) -> None:
        try:
            gs_data, center, distance = _load_binary_ply_preview(self._path, self._max_gaussians)
            self.loaded.emit(gs_data, center, distance, self._path.name)
        except Exception as exc:
            logger.exception("Failed to load 3DGS model %s", self._path)
            self.failed.emit(str(exc))


def _load_binary_ply_preview(path: Path, max_gaussians: int) -> tuple[np.ndarray, np.ndarray, float]:
    """Memory-map a binary GS PLY and materialize only a uniform preview sample."""
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

    required = {"x", "y", "z", "rot_0", "rot_1", "rot_2", "rot_3",
                "scale_0", "scale_1", "scale_2", "opacity", "f_dc_0", "f_dc_1", "f_dc_2"}
    names = {name for name, _dtype in properties}
    missing = sorted(required - names)
    if missing:
        raise ValueError(f"PLY 缺少字段: {', '.join(missing)}")

    mapped = np.memmap(path, dtype=np.dtype(properties), mode="r", offset=data_offset, shape=(vertex_count,))
    sample_count = min(vertex_count, max_gaussians)
    indices = np.linspace(0, vertex_count - 1, sample_count, dtype=np.int64)
    sample = mapped[indices]

    points = np.column_stack((sample["x"], sample["y"], sample["z"])).astype(np.float32)
    rotations = np.column_stack(tuple(sample[f"rot_{i}"] for i in range(4))).astype(np.float32)
    norms = np.linalg.norm(rotations, axis=1, keepdims=True)
    rotations /= np.maximum(norms, 1e-8)
    scales = np.exp(np.column_stack(tuple(sample[f"scale_{i}"] for i in range(3)))).astype(np.float32)
    opacity = (1.0 / (1.0 + np.exp(-sample["opacity"]))).astype(np.float32)[:, None]
    colors = np.column_stack(tuple(sample[f"f_dc_{i}"] for i in range(3))).astype(np.float32)
    gs_data = np.ascontiguousarray(np.column_stack((points, rotations, scales, opacity, colors)), dtype=np.float32)

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
