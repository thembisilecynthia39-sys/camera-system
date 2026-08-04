"""Bind the multiwebcam adapter to the capture page and application layer."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

from camera_system_app.application.controller import ApplicationController
from camera_system_app.infrastructure.adapters import MultiWebcamCaptureAdapter
from camera_system_app.ui.main_window import MainWindow


class CaptureBindings(QObject):
    def __init__(
        self,
        window: MainWindow,
        controller: ApplicationController,
        adapter: MultiWebcamCaptureAdapter,
        capture_completed_callback=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.window = window
        self.controller = controller
        self.adapter = adapter
        self.capture_completed_callback = capture_completed_callback
        self._shutdown = False
        self._last_camera_count = 0

        adapter.view_changed.connect(window.capture_page.set_capture_widget)
        adapter.state_changed.connect(self._on_state_changed)
        adapter.capture_completed.connect(self._on_capture_completed)
        window.navigation.currentRowChanged.connect(self._on_page_changed)

    def initialize(self) -> None:
        self.adapter.initialize_view()
        self._on_page_changed(self.window.navigation.currentRow())
        QTimer.singleShot(0, self.adapter.start)

    def shutdown(self) -> bool:
        if self._shutdown:
            return True
        stopped = self.adapter.stop()
        self._shutdown = stopped is not False
        return self._shutdown

    def _on_state_changed(self, state) -> None:
        disconnected = (
            self._last_camera_count > 0
            and state.camera_count < self._last_camera_count
        )
        self._last_camera_count = state.camera_count
        self.controller.on_capture_state_changed(state)
        self.window.capture_page.set_runtime_state(state)
        if disconnected:
            message = "摄像头连接已变化：当前 {} 路，请检查 USB 连接后继续。".format(
                state.camera_count
            )
            self.window.statusBar().showMessage("● " + message)
            self.window.capture_page.show_connection_warning(message)
        else:
            self.window.statusBar().showMessage(
                "● 采集：{} · {} 路摄像头".format(state.message, state.camera_count)
            )

    def _on_capture_completed(self, event) -> None:
        self.controller.on_capture_completed(event)
        self.window.capture_page.show_capture_completed(event)
        if self.capture_completed_callback:
            self.capture_completed_callback(event)

    def _on_page_changed(self, index: int) -> None:
        active_page = (
            self.window.pages[index]
            if 0 <= index < len(self.window.pages)
            else None
        )
        transferred = self.adapter.set_result_review_active(
            active_page is self.window.result_page
        )
        if not transferred and active_page is self.window.result_page:
            self.window.statusBar().showMessage(
                "● 正在录制，无法将 GPU 完全切换到结果查看。请先停止录制。"
            )
