"""Host page for the existing multiwebcam GridView and FocusView."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

from camera_system_app.domain import (
    CaptureCompletedEvent,
    CaptureRuntimeState,
    CaptureRuntimeStatus,
)
from camera_system_app.ui.widgets import StatusBanner


class CaptureWorkspacePage(QWidget):
    """Presentation-only container for views supplied by CaptureAdapter."""

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
        self._placeholder = QLabel(
            "采集画面尚未载入。\n未连接摄像头时，仍可进入本页面检查连接并重新扫描。"
        )
        self._placeholder.setObjectName("mutedText")
        self._placeholder.setWordWrap(True)
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
