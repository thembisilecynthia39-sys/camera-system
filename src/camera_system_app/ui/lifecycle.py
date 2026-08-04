"""Coordinate bounded, pre-close cleanup outside MainWindow."""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

_QUIT_EVENT = getattr(QEvent, "Quit", QEvent.Type(20))


class LifecycleCoordinator(QObject):
    def __init__(self, window, components, parent=None) -> None:
        super().__init__(parent)
        self.window = window
        self.components = tuple(components)
        self._closing = False
        self._completed = False
        self._close_attempts = 0
        self._logger = logging.getLogger("camera_system_app.lifecycle")
        window._close_coordinator_attached = True
        window.close_requested.connect(self._on_close_requested)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == _QUIT_EVENT and not self._completed:
            QTimer.singleShot(0, self.window.close)
            return True
        return super().eventFilter(watched, event)

    def _on_close_requested(self, _event) -> None:
        if self._closing:
            return
        self._closing = True
        self._close_attempts += 1
        failed = []
        for component in self.components:
            try:
                if component.shutdown() is False:
                    failed.append(type(component).__name__)
            except Exception:
                failed.append(type(component).__name__)
                self._logger.exception(
                    "Shutdown failed for %s", type(component).__name__
                )
        self._closing = False
        if failed:
            message = (
                "以下组件仍在安全停止：{}。窗口暂时保持打开。".format(
                    "、".join(failed)
                )
            )
            self.window.statusBar().showMessage("● " + message)
            if self._close_attempts < 3:
                QTimer.singleShot(500, self.window.close)
            else:
                box = QMessageBox(
                    QMessageBox.Warning,
                    "后台任务仍在停止",
                    message + "\n请稍后再次关闭。",
                    QMessageBox.Ok,
                    self.window,
                )
                box.setModal(False)
                box.open()
                self._warning_box = box
            return
        self._completed = True
        self.window._close_coordinator_attached = False
        self.window.close_requested.disconnect(self._on_close_requested)
        QTimer.singleShot(0, self.window.close)

    def shutdown(self) -> bool:
        if self._completed:
            return True
        ok = True
        for component in self.components:
            try:
                ok = component.shutdown() is not False and ok
            except Exception:
                ok = False
                self._logger.exception(
                    "Fallback shutdown failed for %s", type(component).__name__
                )
        self._completed = ok
        return ok
