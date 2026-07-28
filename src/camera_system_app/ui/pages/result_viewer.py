"""Embedded local Gaussian Splat result viewer page."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from camera_system_app.ui.pages.base import BasePage
from camera_system_app.ui.widgets import StatusBanner


class ResultViewerPage(BasePage):
    open_local_result_requested = Signal(str)
    select_local_result_requested = Signal()
    reset_view_requested = Signal()

    def __init__(self, result_root: str, viewer_root: str, parent=None) -> None:
        super().__init__(
            "结果查看",
            "使用现有 q3dviewer 查看 Jetson 本地 Gaussian Splat PLY。",
            parent,
        )
        self.setObjectName("resultPageSurface")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._local_path = None
        self.result_root = Path(result_root).resolve()
        self._viewer_widget = None
        self._banner = StatusBanner("当前没有已完成的本地重建结果。")
        self.layout.addWidget(self._banner)

        card = self.add_card()
        self._result = QLabel("结果目录：" + result_root)
        self._result.setWordWrap(True)
        viewer = QLabel("q3dviewer 源码：" + viewer_root)
        viewer.setObjectName("mutedText")
        viewer.setWordWrap(True)
        controls = QHBoxLayout()
        self._select = QPushButton("选择本地 PLY")
        self._select.clicked.connect(self.select_local_result_requested.emit)
        self._action = QPushButton("加载当前 PLY")
        self._action.setObjectName("primaryButton")
        self._action.setEnabled(False)
        self._action.clicked.connect(self.open_current_result)
        self._reset = QPushButton("重置视角")
        self._reset.setEnabled(False)
        self._reset.clicked.connect(self.reset_view_requested.emit)
        hint = QLabel(
            "右键拖动 360° 环视 · 左键拖动平移 · 滚轮缩放 · "
            "移动时快速预览，停下后恢复高质量"
        )
        hint.setObjectName("mutedText")
        controls.addWidget(self._select)
        controls.addWidget(self._action)
        controls.addWidget(self._reset)
        controls.addStretch(1)
        controls.addWidget(hint)
        card.addWidget(self._result)
        card.addWidget(viewer)
        card.addLayout(controls)

        self._viewer_frame = QFrame()
        self._viewer_frame.setObjectName("contentCard")
        self._viewer_layout = QVBoxLayout(self._viewer_frame)
        self._viewer_layout.setContentsMargins(2, 2, 2, 2)
        self._empty = QLabel("重建完成后，可在此处打开本地 3DGS.ply。")
        self._empty.setObjectName("mutedText")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._viewer_layout.addWidget(self._empty, 1)
        self.layout.addWidget(self._viewer_frame, 1)

    def set_result_available(self, local_path: str) -> None:
        path = Path(local_path).resolve()
        self._local_path = path
        self._result.setText("Jetson 本地结果：" + str(path))
        if path.is_file():
            self._banner.set_status("本地结果文件可用，可以加载。", "success")
            self._action.setEnabled(True)
        else:
            self.show_load_error("结果文件不存在：{}".format(path))

    def open_current_result(self) -> None:
        if self._local_path:
            self.open_local_result_requested.emit(str(self._local_path))

    def show_loading(self, path: str) -> None:
        self._banner.set_status("正在后台解析 PLY：{}".format(path), "success")
        self._action.setEnabled(False)
        self._reset.setEnabled(False)

    def set_viewer_widget(self, widget, path: str, gaussian_count: int) -> None:
        if self._viewer_widget is None:
            self._viewer_layout.removeWidget(self._empty)
            self._empty.hide()
            self._viewer_widget = widget
            self._viewer_layout.addWidget(widget, 1)
        self._viewer_widget.show()
        self._banner.set_status(
            "已加载 {:,} 个 Gaussian：{}".format(gaussian_count, path),
            "success",
        )
        self._action.setEnabled(True)
        self._action.setText("重新加载")
        self._reset.setEnabled(True)

    def show_load_error(self, message: str) -> None:
        self._banner.set_status("结果加载失败：{}".format(message), "warning")
        self._action.setEnabled(bool(self._local_path and self._local_path.is_file()))
        self._reset.setEnabled(self._viewer_widget is not None)
