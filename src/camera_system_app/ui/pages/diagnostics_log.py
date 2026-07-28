"""Combined logs and environment diagnostics page."""

from PySide6.QtCore import QAbstractTableModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableView,
)

from camera_system_app.domain.diagnostics import DiagnosticReport, DiagnosticStatus
from camera_system_app.ui.pages.base import BasePage


class DiagnosticTableModel(QAbstractTableModel):
    """Expose diagnostics without item-owned objects on the JetPack Qt shim."""

    HEADERS = ("状态", "检查项", "摘要", "详情")
    STATUS_LABELS = {
        DiagnosticStatus.PASS: "✓ 通过",
        DiagnosticStatus.WARNING: "△ 提示",
        DiagnosticStatus.FAILURE: "✕ 失败",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._checks = ()

    def rowCount(self, _parent=None) -> int:
        return len(self._checks)

    def columnCount(self, _parent=None) -> int:
        return len(self.HEADERS)

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole or not index.isValid():
            return None
        check = self._checks[index.row()]
        values = (
            self.STATUS_LABELS[check.status],
            check.name,
            check.summary,
            check.detail,
        )
        return values[index.column()]

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if (
            role == Qt.DisplayRole
            and orientation == Qt.Horizontal
            and 0 <= section < len(self.HEADERS)
        ):
            return self.HEADERS[section]
        return None

    def set_report(self, report: DiagnosticReport) -> None:
        self.beginResetModel()
        self._checks = report.checks
        self.endResetModel()


class DiagnosticsLogPage(BasePage):
    refresh_diagnostics_requested = Signal()
    refresh_logs_requested = Signal()

    def __init__(self, log_file: str, parent=None) -> None:
        super().__init__(
            "日志和环境诊断",
            "检查本机运行条件。诊断不会打开摄像头，也不会请求 WSL 服务。",
            parent,
        )
        actions = QHBoxLayout()
        refresh_diagnostics = QPushButton("刷新环境诊断")
        refresh_logs = QPushButton("刷新日志")
        refresh_diagnostics.clicked.connect(self.refresh_diagnostics_requested.emit)
        refresh_logs.clicked.connect(self.refresh_logs_requested.emit)
        actions.addWidget(refresh_diagnostics)
        actions.addWidget(refresh_logs)
        actions.addStretch(1)
        self.layout.addLayout(actions)

        self._table = QTableView()
        self._table_model = DiagnosticTableModel(self._table)
        self._table.setModel(self._table_model)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setAccessibleName("环境诊断结果")
        self.layout.addWidget(self._table, 1)

        log_label = QLabel("应用日志：" + log_file)
        log_label.setObjectName("sectionTitle")
        log_label.setWordWrap(True)
        self.layout.addWidget(log_label)
        self._logs = QPlainTextEdit()
        self._logs.setReadOnly(True)
        self._logs.setAccessibleName("应用日志内容")
        self.layout.addWidget(self._logs, 1)

    def set_report(self, report: DiagnosticReport) -> None:
        self._table_model.set_report(report)
        self._table.resizeRowsToContents()

    def set_log_text(self, text: str) -> None:
        self._logs.setPlainText(text)
        cursor = self._logs.textCursor()
        cursor.movePosition(cursor.End)
        self._logs.setTextCursor(cursor)
