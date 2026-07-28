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
        "01  采集工作台",
        "02  传输与重建",
        "03  结果查看",
        "04  历史任务",
        "05  设置",
        "06  日志和环境诊断",
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

        navigation_section = QLabel("主流程 · 采集 → 重建 → 查看")
        navigation_section.setObjectName("navigationSection")
        sidebar_layout.addWidget(navigation_section)

        self.navigation = QListWidget()
        self.navigation.setObjectName("primaryNavigation")
        self.navigation.setAccessibleName("主功能导航")
        for label in self.NAVIGATION_LABELS:
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(194, 50))
            self.navigation.addItem(item)
        sidebar_layout.addWidget(self.navigation, 1)

        workstation_status = QLabel("● 本机工作站\n摄像头与服务按需连接")
        workstation_status.setObjectName("workstationStatus")
        workstation_status.setWordWrap(True)
        workstation_status.setAccessibleName(
            "本机工作站，摄像头与服务按需连接"
        )
        sidebar_layout.addWidget(workstation_status)

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
        self.capture_page.open_diagnostics_requested.connect(
            lambda: self.navigation.setCurrentRow(5)
        )
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
