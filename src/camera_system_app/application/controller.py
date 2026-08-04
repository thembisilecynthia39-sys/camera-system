"""Qt-independent application facade used by UI bindings."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from camera_system_app.application.diagnostics import DiagnosticService
from camera_system_app.config.settings import AppSettings, SettingsManager
from camera_system_app.domain import (
    CaptureCompletedEvent,
    CaptureRuntimeState,
    user_message,
)
from camera_system_app.domain.diagnostics import DiagnosticReport
from camera_system_app.infrastructure.logging import LogService
from camera_system_app.infrastructure.paths import AppPaths


class ApplicationController:
    """Coordinate shell use cases without depending on Qt widgets."""

    def __init__(
        self,
        paths: AppPaths,
        settings_manager: SettingsManager,
        settings: AppSettings,
        logs: LogService,
    ) -> None:
        self.paths = paths
        self.settings_manager = settings_manager
        self.settings = settings
        self.logs = logs
        self.capture_state = None
        self.latest_capture = None
        self._logger = logging.getLogger("camera_system_app.controller")

    def diagnose(self) -> DiagnosticReport:
        return DiagnosticService(self.paths, self.settings).run()

    def save_settings(self, values: Mapping[str, Any]) -> AppSettings:
        self.settings = self.settings_manager.save(values)
        self._logger.info("Unified settings saved to %s", self.paths.config_file)
        return self.settings

    def read_log_tail(self, max_lines: int = 300) -> str:
        try:
            return self.logs.tail(max_lines)
        except OSError as exc:
            return user_message(exc, "读取日志")

    def on_capture_state_changed(self, state: CaptureRuntimeState) -> None:
        self.capture_state = state
        self._logger.info(
            "Capture state=%s cameras=%s message=%s",
            state.status.value,
            state.camera_count,
            state.message,
        )

    def on_capture_completed(self, event: CaptureCompletedEvent) -> None:
        self.latest_capture = event
        self._logger.info(
            "Eight-angle capture completed: object=%s path=%s",
            event.object_name,
            event.capture_dir,
        )
