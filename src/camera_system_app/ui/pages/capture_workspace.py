"""Host page for the existing multiwebcam GridView and FocusView."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from camera_system_app.domain import (
    CaptureCompletedEvent,
    CaptureRuntimeState,
    CaptureRuntimeStatus,
)
from camera_system_app.ui.widgets import EmptyState, StatusBanner


class CaptureWorkspacePage(QWidget):
    """Presentation-only container for views supplied by CaptureAdapter."""

    open_diagnostics_requested = Signal()

    def __init__(self, capture_root: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("capturePageSurface")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._capture_root = capture_root
        layout = QVBoxLayout(self)
        # The embedded capture console is one connected operational surface.
        # Outer gutters belong on light document pages, not around a video wall.
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._status = StatusBanner("正在准备采集服务…", "warning")
        layout.addWidget(self._status)

        self._host = QStackedWidget()
        self._host.setObjectName("captureHost")
        self._empty_state = EmptyState(
            "◎",
            "等待摄像头画面",
            "采集服务正在发现设备。若长时间没有画面，请检查 USB 连接并查看环境诊断。",
            "打开环境诊断",
        )
        self._empty_state.action_requested.connect(
            self.open_diagnostics_requested.emit
        )
        self._placeholder = self._empty_state
        self._host.addWidget(self._placeholder)
        layout.addWidget(self._host, 1)

    def set_capture_widget(self, widget) -> None:
        current = self._host.currentWidget()
        if current is not None and current is not self._placeholder:
            self._host.removeWidget(current)
        if widget is None:
            self._host.setCurrentWidget(self._placeholder)
            return
        if self._host.indexOf(widget) < 0:
            self._host.addWidget(widget)
        self._host.setCurrentWidget(widget)

    def set_runtime_state(self, state: CaptureRuntimeState) -> None:
        successful = state.status in {
            CaptureRuntimeStatus.READY,
            CaptureRuntimeStatus.RECORDING,
        }
        self._status.set_status(
            "{}  摄像头：{} 路".format(state.message, state.camera_count),
            "success" if successful else "warning",
        )

    def show_capture_completed(self, event: CaptureCompletedEvent) -> None:
        self._status.set_status(
            "✓ 八个固定视角采集完成：{}".format(event.capture_dir),
            "success",
        )

    def show_connection_warning(self, message: str) -> None:
        self._status.set_status("摄像头断开提示：" + message, "warning")
