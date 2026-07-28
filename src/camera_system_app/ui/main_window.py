"""Top-level window responsible only for navigation and page composition."""

from __future__ import annotations

from typing import List

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from camera_system_app.config.settings import AppSettings
from camera_system_app import __version__
from camera_system_app.infrastructure.paths import AppPaths
from camera_system_app.ui.pages import (
    CaptureWorkspacePage,
    DiagnosticsLogPage,
    HistoryPage,
    ResultViewerPage,
    SettingsPage,
    TransferReconstructionPage,
)


class MainWindow(QMainWindow):
    """Compose the six top-level pages and connect primary navigation."""

    close_requested = Signal(object)
    NAVIGATION_LABELS = (
        "采集工作台",
        "传输与重建",
        "结果查看",
        "历史任务",
        "设置",
        "日志和环境诊断",
    )

    def __init__(self, paths: AppPaths, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("边端 3DGS 重建")
        self._close_coordinator_attached = False
        self.setMinimumSize(1024, 680)
        self.resize(1600, 900)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(224)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 18, 14, 16)
        sidebar_layout.setSpacing(14)

        brand_block = QFrame()
        brand_block.setObjectName("brandBlock")
        brand_layout = QVBoxLayout(brand_block)
        brand_layout.setContentsMargins(14, 12, 14, 12)
        brand_layout.setSpacing(3)
        brand = QLabel("Camera System")
        brand.setObjectName("brandTitle")
        subtitle = QLabel("Jetson 3DGS 工作站")
        subtitle.setObjectName("brandSubtitle")
        brand_layout.addWidget(brand)
        brand_layout.addWidget(subtitle)
        sidebar_layout.addWidget(brand_block)

        self.navigation = QListWidget()
        self.navigation.setObjectName("primaryNavigation")
        self.navigation.setAccessibleName("主功能导航")
        for label in self.NAVIGATION_LABELS:
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(194, 50))
            self.navigation.addItem(item)
        sidebar_layout.addWidget(self.navigation, 1)

        version = QLabel("版本 " + __version__)
        version.setObjectName("sidebarVersion")
        sidebar_layout.addWidget(version)

        self.stack = QStackedWidget()
        self.capture_page = CaptureWorkspacePage(settings.capture_root)
        self.transfer_page = TransferReconstructionPage(
            settings.wsl_service_url,
            settings.transfer_staging_root,
        )
        self.result_page = ResultViewerPage(settings.result_root, settings.viewer_root)
        self.history_page = HistoryPage()
        self.settings_page = SettingsPage(settings, str(paths.config_file))
        self.diagnostics_page = DiagnosticsLogPage(str(paths.log_file))

        self.pages: List[QWidget] = [
            self.capture_page,
            self.transfer_page,
            self.result_page,
            self.history_page,
            self.settings_page,
            self.diagnostics_page,
        ]
        for page in self.pages:
            self.stack.addWidget(page)

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.navigation.currentRowChanged.connect(self._show_page)
        self.navigation.setCurrentRow(0)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().showMessage("● 应用就绪 · 摄像头与 WSL 服务按需连接")

    def _show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        status_bar = self.statusBar()
        status_bar.setProperty(
            "mode",
            "operational" if index in {0, 2} else "standard",
        )
        status_bar.style().unpolish(status_bar)
        status_bar.style().polish(status_bar)

    def closeEvent(self, event) -> None:
        """Delegate pre-close coordination; MainWindow owns no services."""

        if self._close_coordinator_attached:
            event.ignore()
            self.close_requested.emit(event)
            return
        event.accept()
