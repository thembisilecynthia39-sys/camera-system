"""Unified settings editor."""

from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
)

from camera_system_app.config.settings import AppSettings
from camera_system_app.ui.pages.base import BasePage
from camera_system_app.ui.widgets import StatusBanner


class SettingsPage(BasePage):
    save_requested = Signal(object)

    def __init__(self, settings: AppSettings, config_file: str, parent=None) -> None:
        super().__init__(
            "设置",
            "统一管理服务地址、数据目录和日志级别；相对路径按项目根目录解析。",
            parent,
        )
        self._status = StatusBanner("配置来源：" + config_file, "success")
        self.layout.addWidget(self._status)
        card = self.add_card()
        form = QFormLayout()
        form.setSpacing(12)

        self._service_url = QLineEdit(settings.wsl_service_url)
        self._service_url.setPlaceholderText("例如：http://WSL-IP:8000")
        self._capture_root = QLineEdit(settings.capture_root)
        self._staging_root = QLineEdit(settings.transfer_staging_root)
        self._result_root = QLineEdit(settings.result_root)
        self._viewer_root = QLineEdit(settings.viewer_root)
        self._log_level = QComboBox()
        self._log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self._log_level.setCurrentText(settings.log_level)
        self._max_ply_size_bytes = settings.max_ply_size_bytes
        self._start_maximized = settings.start_maximized
        self._upload_timeout = QSpinBox()
        self._upload_timeout.setRange(1, 86400)
        self._upload_timeout.setValue(settings.upload_timeout_seconds)
        self._request_timeout = QSpinBox()
        self._request_timeout.setRange(1, 86400)
        self._request_timeout.setValue(settings.request_timeout_seconds)
        self._poll_interval = QDoubleSpinBox()
        self._poll_interval.setRange(0.1, 3600.0)
        self._poll_interval.setValue(settings.status_poll_interval_seconds)
        self._poll_interval.setSuffix(" 秒")
        self._reconstruction_timeout = QSpinBox()
        self._reconstruction_timeout.setRange(1, 604800)
        self._reconstruction_timeout.setValue(settings.reconstruction_timeout_seconds)
        self._download_timeout = QSpinBox()
        self._download_timeout.setRange(1, 86400)
        self._download_timeout.setValue(settings.download_timeout_seconds)

        form.addRow("WSL 地址和端口", self._service_url)
        form.addRow("采集目录", self._capture_root)
        form.addRow("传输暂存目录", self._staging_root)
        form.addRow("结果目录", self._result_root)
        form.addRow("查看器目录", self._viewer_root)
        form.addRow("上传超时（秒）", self._upload_timeout)
        form.addRow("请求超时（秒）", self._request_timeout)
        form.addRow("状态轮询间隔", self._poll_interval)
        form.addRow("重建总超时（秒）", self._reconstruction_timeout)
        form.addRow("下载超时（秒）", self._download_timeout)
        form.addRow("日志级别", self._log_level)
        card.addLayout(form)

        note = QLabel("目录设置仅保存配置，不会在 Qt 主线程中启动采集、压缩、上传或下载。")
        note.setObjectName("mutedText")
        note.setWordWrap(True)
        save = QPushButton("保存设置")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._emit_save)
        card.addWidget(note)
        card.addWidget(save)
        self.finish()

    def _emit_save(self) -> None:
        self.save_requested.emit(self.values())

    def values(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "language": "zh_CN",
            "log_level": self._log_level.currentText(),
            "wsl_service_url": self._service_url.text(),
            "capture_root": self._capture_root.text(),
            "transfer_staging_root": self._staging_root.text(),
            "result_root": self._result_root.text(),
            "viewer_root": self._viewer_root.text(),
            "upload_timeout_seconds": self._upload_timeout.value(),
            "request_timeout_seconds": self._request_timeout.value(),
            "status_poll_interval_seconds": self._poll_interval.value(),
            "reconstruction_timeout_seconds": self._reconstruction_timeout.value(),
            "download_timeout_seconds": self._download_timeout.value(),
            "max_ply_size_bytes": self._max_ply_size_bytes,
            "start_maximized": self._start_maximized,
        }

    def show_save_result(self, message: str, successful: bool) -> None:
        self._status.set_status(message, "success" if successful else "warning")
