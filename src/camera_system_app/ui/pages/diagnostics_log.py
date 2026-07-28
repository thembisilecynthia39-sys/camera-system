"""Combined logs and environment diagnostics page."""

from PySide6.QtCore import QAbstractTableModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
)

from camera_system_app.domain.diagnostics import DiagnosticReport, DiagnosticStatus
from camera_system_app.ui.pages.base import BasePage
from camera_system_app.ui.widgets import MetricCard


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
            "检查本机运行条件；诊断不会打开摄像头，也不会请求 WSL 服务。",
            parent,
            eyebrow="系统 · 运行状态",
        )
        actions = QHBoxLayout()
        refresh_diagnostics = QPushButton("刷新环境诊断")
        refresh_diagnostics.setAccessibleName("刷新环境诊断")
        refresh_logs = QPushButton("刷新应用日志")
        refresh_logs.setAccessibleName("刷新应用日志")
        refresh_diagnostics.clicked.connect(
            self.refresh_diagnostics_requested.emit
        )
        refresh_logs.clicked.connect(self.refresh_logs_requested.emit)
        actions.addWidget(refresh_diagnostics)
        actions.addWidget(refresh_logs)
        actions.addStretch(1)
        self.layout.addLayout(actions)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self._passed_metric = MetricCard("通过", "0", "success")
        self._warning_metric = MetricCard("提示", "0", "warning")
        self._failure_metric = MetricCard("失败", "0", "danger")
        for metric in (
            self._passed_metric,
            self._warning_metric,
            self._failure_metric,
        ):
            metrics.addWidget(metric, 1)
        self.layout.addLayout(metrics)

        self._table = QTableView()
        self._table_model = DiagnosticTableModel(self._table)
        self._table.setModel(self._table_model)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.setAccessibleName("环境诊断结果")

        diagnostic_frame = QFrame()
        diagnostic_frame.setObjectName("contentCard")
        diagnostic_layout = QVBoxLayout(diagnostic_frame)
        diagnostic_layout.setContentsMargins(16, 14, 16, 14)
        diagnostic_title = QLabel("环境检查")
        diagnostic_title.setObjectName("sectionTitle")
        diagnostic_layout.addWidget(diagnostic_title)
        diagnostic_layout.addWidget(self._table, 1)

        log_frame = QFrame()
        log_frame.setObjectName("contentCard")
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(16, 14, 16, 14)
        log_label = QLabel("应用日志：" + log_file)
        log_label.setObjectName("sectionTitle")
        log_label.setWordWrap(True)
        self._logs = QPlainTextEdit()
        self._logs.setReadOnly(True)
        self._logs.setAccessibleName("应用日志内容")
        log_layout.addWidget(log_label)
        log_layout.addWidget(self._logs, 1)

        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.setAccessibleName("诊断结果和应用日志分栏")
        self._splitter.addWidget(diagnostic_frame)
        self._splitter.addWidget(log_frame)
        self._splitter.setSizes([360, 260])
        self.layout.addWidget(self._splitter, 1)

    def set_report(self, report: DiagnosticReport) -> None:
        self._table_model.set_report(report)
        self._passed_metric.set_value(
            sum(
                check.status is DiagnosticStatus.PASS
                for check in report.checks
            )
        )
        self._warning_metric.set_value(report.warning_count)
        self._failure_metric.set_value(report.failure_count)
        self._table.resizeRowsToContents()

    def set_log_text(self, text: str) -> None:
        self._logs.setPlainText(text)
        cursor = self._logs.textCursor()
        cursor.movePosition(cursor.End)
        self._logs.setTextCursor(cursor)
