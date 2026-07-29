"""Connect page signals to application use cases outside MainWindow."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject

from camera_system_app.application.controller import ApplicationController
from camera_system_app.domain import user_message
from camera_system_app.ui.main_window import MainWindow


class ApplicationBindings(QObject):
    """Own UI-to-application signal bindings for the shell."""

    def __init__(
        self,
        window: MainWindow,
        controller: ApplicationController,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.window = window
        self.controller = controller
        self._logger = logging.getLogger("camera_system_app.ui.bindings")

        window.settings_page.save_requested.connect(self._save_settings)
        window.diagnostics_page.refresh_diagnostics_requested.connect(
            self.refresh_diagnostics
        )
        window.diagnostics_page.refresh_logs_requested.connect(self.refresh_logs)

    def initialize(self) -> None:
        self.refresh_diagnostics()
        self.refresh_logs()

    def refresh_diagnostics(self) -> None:
        report = self.controller.diagnose()
        self.window.diagnostics_page.set_report(report)

    def refresh_logs(self) -> None:
        self.window.diagnostics_page.set_log_text(self.controller.read_log_tail())

    def _save_settings(self, values) -> None:
        try:
            settings = self.controller.save_settings(values)
        except Exception as exc:
            self._logger.exception("Failed to save settings")
            self.window.settings_page.show_save_result(
                user_message(exc, "保存设置"),
                False,
            )
            return
        self.window.settings_page.show_save_result(
            "设置已保存：{}".format(self.controller.paths.config_file),
            True,
        )
        self._logger.info("Active WSL endpoint is %s", settings.wsl_service_url or "unset")
        self.refresh_diagnostics()
        self.refresh_logs()
