"""Readable task history with compact, non-overlapping row actions."""

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from camera_system_app.domain import ReconstructionState
from camera_system_app.ui.pages.base import BasePage


class HistoryPage(BasePage):
    select_requested = Signal(str)
    retry_requested = Signal(str)
    open_result_requested = Signal(str)
    open_task_directory_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(
            "历史任务",
            "集中查看采集、上传、重建、下载和结果状态。",
            parent,
            eyebrow="工作区 · 任务记录",
        )
        summary = QFrame()
        summary.setObjectName("historySummary")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(16, 11, 16, 11)
        summary_layout.setSpacing(12)
        self._count_label = QLabel("共 0 个任务")
        self._count_label.setObjectName("historyCount")
        hint = QLabel("双击任意行可查看详情；常用操作直接显示，其余操作位于“更多”菜单。")
        hint.setObjectName("historyHint")
        hint.setWordWrap(True)
        summary_layout.addWidget(self._count_label)
        summary_layout.addWidget(hint, 1)
        self.layout.addWidget(summary)

        self.table = QTableWidget(0, 6)
        self.table.setObjectName("historyTable")
        self.table.setHorizontalHeaderLabels(
            ["任务 ID", "创建时间", "状态", "结果", "说明", "操作"]
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideMiddle)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(58)

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setMinimumSectionSize(88)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 190)
        self.table.setColumnWidth(1, 168)
        self.table.setColumnWidth(2, 112)
        self.table.setColumnWidth(5, 180)
        self.table.setAccessibleName("历史任务列表")
        self.table.cellDoubleClicked.connect(self._select_row)
        self._empty_state = QLabel(
            "<h2>◇ 还没有历史任务</h2>"
            "<p>完成八视角采集或手动选择照片后，任务会显示在这里。</p>"
        )
        self._empty_state.setObjectName("historyEmptyState")
        self._empty_state.setAlignment(Qt.AlignCenter)
        self._empty_state.setWordWrap(True)
        self._empty_state.setAccessibleName(
            "还没有历史任务。完成八视角采集或手动选择照片后，任务会显示在这里。"
        )
        self.layout.addWidget(self._empty_state, 1)
        self.table.setHidden(True)
        self.layout.addWidget(self.table, 1)

    def set_jobs(self, jobs) -> None:
        self._count_label.setText("共 {} 个任务".format(len(jobs)))
        self._empty_state.setHidden(bool(jobs))
        self.table.setHidden(not bool(jobs))
        self.table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            task_item = self._text_item(job.job_id, job.job_id)
            created_item = self._text_item(
                _display_datetime(job.created_at),
                job.created_at,
            )
            result_text = job.result_path.name if job.result_path else "—"
            result_item = self._text_item(
                result_text,
                str(job.result_path) if job.result_path else "尚无结果文件",
            )
            message = job.error or job.stage_message or "—"
            message_item = self._text_item(message, message)
            self.table.setItem(row, 0, task_item)
            self.table.setItem(row, 1, created_item)
            self.table.setCellWidget(row, 2, self._state_badge(job.state))
            self.table.setItem(row, 3, result_item)
            self.table.setItem(row, 4, message_item)

            actions = QWidget()
            actions.setObjectName("historyActions")
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(8, 8, 8, 8)
            action_layout.setSpacing(6)

            primary = QPushButton()
            primary.setObjectName("tablePrimaryAction")
            if job.state in {
                ReconstructionState.FAILED,
                ReconstructionState.CANCELLED,
                ReconstructionState.INTERRUPTED,
            }:
                primary.setText("重试")
                primary.clicked.connect(
                    lambda _checked=False, value=job.job_id: self.retry_requested.emit(value)
                )
            elif (
                job.state is ReconstructionState.COMPLETED
                and job.result_path
                and job.result_path.is_file()
            ):
                primary.setText("打开结果")
                primary.clicked.connect(
                    lambda _checked=False, value=str(job.result_path):
                    self.open_result_requested.emit(value)
                )
            else:
                primary.setText("查看详情")
                primary.clicked.connect(
                    lambda _checked=False, value=job.job_id:
                    self.select_requested.emit(value)
                )
            action_layout.addWidget(primary, 1)

            more = QToolButton()
            more.setObjectName("tableMoreAction")
            more.setText("⋯")
            more.setToolTip("更多操作")
            more.setAccessibleName("{} 的更多操作".format(job.job_id))
            menu = QMenu(more)
            detail_action = menu.addAction("查看详情")
            detail_action.triggered.connect(
                lambda _checked=False, value=job.job_id:
                self.select_requested.emit(value)
            )
            folder_action = menu.addAction("打开任务目录")
            folder_action.triggered.connect(
                lambda _checked=False, value=job.job_id:
                self.open_task_directory_requested.emit(value)
            )
            more.setMenu(menu)
            more.setPopupMode(QToolButton.InstantPopup)
            action_layout.addWidget(more)
            self.table.setCellWidget(row, 5, actions)
            self.table.setRowHeight(row, 58)

    def _select_row(self, row: int, _column: int) -> None:
        item = self.table.item(row, 0)
        if item is not None:
            self.select_requested.emit(item.text())

    @staticmethod
    def _text_item(text: str, tooltip: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setToolTip(tooltip)
        item.setTextAlignment(int(Qt.AlignVCenter | Qt.AlignLeft))
        return item

    @staticmethod
    def _state_badge(state: ReconstructionState) -> QWidget:
        container = QWidget()
        container.setObjectName("historyActions")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 10, 8, 10)
        badge = QLabel(_STATE_LABELS.get(state, state.value))
        badge.setObjectName("taskStateBadge")
        badge.setProperty("state", _state_colour(state))
        badge.setAlignment(Qt.AlignCenter)
        layout.addWidget(badge)
        return container


_STATE_LABELS = {
    ReconstructionState.READY: "待上传",
    ReconstructionState.VALIDATING: "校验中",
    ReconstructionState.PACKAGING: "打包中",
    ReconstructionState.HEALTH_CHECK: "连接检查",
    ReconstructionState.UPLOADING: "上传中",
    ReconstructionState.STARTING: "启动重建",
    ReconstructionState.RECONSTRUCTING: "重建中",
    ReconstructionState.DOWNLOADING: "下载中",
    ReconstructionState.VERIFYING: "校验结果",
    ReconstructionState.ACKNOWLEDGING: "确认完成",
    ReconstructionState.COMPLETED: "已完成",
    ReconstructionState.FAILED: "失败",
    ReconstructionState.CANCELLED: "已取消",
    ReconstructionState.INTERRUPTED: "已中断",
}


def _state_colour(state: ReconstructionState) -> str:
    if state is ReconstructionState.COMPLETED:
        return "success"
    if state is ReconstructionState.FAILED:
        return "danger"
    if state in {
        ReconstructionState.CANCELLED,
        ReconstructionState.INTERRUPTED,
    }:
        return "warning"
    if state is ReconstructionState.READY:
        return "neutral"
    return "active"


def _display_datetime(value: str) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
