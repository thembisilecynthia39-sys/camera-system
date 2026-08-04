"""Unified settings editor with grouped, scrollable sections."""

from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from camera_system_app.config.settings import AppSettings
from camera_system_app.ui.pages.base import BasePage
from camera_system_app.ui.widgets import (
    SafeDoubleSpinBox,
    SafeSpinBox,
    StatusBanner,
)


class SettingsPage(BasePage):
    save_requested = Signal(object)

    def __init__(self, settings: AppSettings, config_file: str, parent=None) -> None:
        super().__init__(
            "设置",
            "统一管理服务连接、数据目录、任务超时和日志级别。",
            parent,
            eyebrow="系统 · 工作站配置",
        )
        self._status = StatusBanner(
            "配置来源：" + config_file,
            "info",
        )
        self.layout.addWidget(self._status)

        self._create_fields(settings)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setAccessibleName("设置分组")
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        connection = self._section(
            content_layout,
            "服务连接",
            "填写 Jetson 能访问的 WSL 或 Linux 重建服务地址。",
        )
        connection_form = QFormLayout()
        connection_form.setSpacing(12)
        connection_form.addRow("WSL 地址和端口", self._service_url)
        connection.addLayout(connection_form)

        storage = self._section(
            content_layout,
            "数据目录",
            "相对路径按项目根目录解析；保存设置不会立即访问目录。",
        )
        storage_form = QFormLayout()
        storage_form.setSpacing(12)
        storage_form.addRow("采集目录", self._capture_root)
        storage_form.addRow("传输暂存目录", self._staging_root)
        storage_form.addRow("结果目录", self._result_root)
        storage_form.addRow("查看器目录", self._viewer_root)
        storage.addLayout(storage_form)

        timeouts = self._section(
            content_layout,
            "网络与任务超时",
            "超时是底层阻塞调用和网络请求的最终退出边界。",
        )
        timeout_form = QFormLayout()
        timeout_form.setSpacing(12)
        timeout_form.addRow("上传超时（秒）", self._upload_timeout)
        timeout_form.addRow("请求超时（秒）", self._request_timeout)
        timeout_form.addRow("状态轮询间隔", self._poll_interval)
        timeout_form.addRow("重建总超时（秒）", self._reconstruction_timeout)
        timeout_form.addRow("下载超时（秒）", self._download_timeout)
        timeouts.addLayout(timeout_form)

        logging_section = self._section(
            content_layout,
            "日志",
            "INFO 适合日常运行；排查问题时可临时使用 DEBUG。",
        )
        logging_form = QFormLayout()
        logging_form.setSpacing(12)
        logging_form.addRow("日志级别", self._log_level)
        logging_section.addLayout(logging_form)
        content_layout.addStretch(1)
        self._scroll.setWidget(content)
        self.layout.addWidget(self._scroll, 1)

        note = QLabel(
            "保存只更新配置，不会在 Qt 主线程中启动采集、压缩、上传或下载。"
        )
        note.setObjectName("mutedText")
        note.setWordWrap(True)
        self._save_button = QPushButton("保存设置")
        self._save_button.setObjectName("primaryButton")
        self._save_button.setAccessibleName("保存工作站设置")
        self._save_button.clicked.connect(self._emit_save)
        self.layout.addWidget(note)
        self.layout.addWidget(self._save_button)

    def _create_fields(self, settings: AppSettings) -> None:
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
        self._upload_timeout = SafeSpinBox()
        self._upload_timeout.setRange(1, 86400)
        self._upload_timeout.setValue(settings.upload_timeout_seconds)
        self._request_timeout = SafeSpinBox()
        self._request_timeout.setRange(1, 86400)
        self._request_timeout.setValue(settings.request_timeout_seconds)
        self._poll_interval = SafeDoubleSpinBox()
        self._poll_interval.setRange(0.1, 3600.0)
        self._poll_interval.setValue(settings.status_poll_interval_seconds)
        self._poll_interval.setSuffix(" 秒")
        self._reconstruction_timeout = SafeSpinBox()
        self._reconstruction_timeout.setRange(1, 604800)
        self._reconstruction_timeout.setValue(
            settings.reconstruction_timeout_seconds
        )
        self._download_timeout = SafeSpinBox()
        self._download_timeout.setRange(1, 86400)
        self._download_timeout.setValue(settings.download_timeout_seconds)

    @staticmethod
    def _section(parent_layout, title: str, description: str) -> QVBoxLayout:
        card = QFrame()
        card.setObjectName("contentCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        description_label = QLabel(description)
        description_label.setObjectName("sectionDescription")
        description_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(description_label)
        parent_layout.addWidget(card)
        return layout

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
        self._status.set_status(
            message,
            "success" if successful else "danger",
        )
