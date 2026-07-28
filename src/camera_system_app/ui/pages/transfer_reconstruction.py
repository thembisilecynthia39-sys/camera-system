"""Transfer/reconstruction workflow presentation only."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from camera_system_app.domain import ReconstructionState
from camera_system_app.ui.pages.base import BasePage
from camera_system_app.ui.widgets import StatusBanner, WorkflowStage


class TransferReconstructionPage(BasePage):
    start_requested = Signal(str)
    open_result_requested = Signal(str)
    select_images_requested = Signal()

    _UPLOAD_ACTIVE = {
        ReconstructionState.VALIDATING,
        ReconstructionState.PACKAGING,
        ReconstructionState.HEALTH_CHECK,
        ReconstructionState.UPLOADING,
    }
    _RECONSTRUCTION_ACTIVE = {
        ReconstructionState.STARTING,
        ReconstructionState.RECONSTRUCTING,
    }
    _DOWNLOAD_ACTIVE = {
        ReconstructionState.DOWNLOADING,
        ReconstructionState.VERIFYING,
        ReconstructionState.ACKNOWLEDGING,
    }

    def __init__(self, service_url: str, staging_root: str, parent=None) -> None:
        super().__init__(
            "传输与重建",
            "从本地任务校验到结果下载，每一阶段都在后台执行并持续保存状态。",
            parent,
            eyebrow="工作流 02 · 处理与交付",
        )
        self._job = None
        self._selection_busy = False
        status = (
            "服务地址已配置；仅在用户启动任务后连接。"
            if service_url
            else "WSL 地址和端口尚未配置，应用仍可离线使用。"
        )
        self._banner = StatusBanner(
            status,
            "info" if service_url else "warning",
        )
        self.layout.addWidget(self._banner)

        summary = self.add_card(
            "当前任务",
            "确认任务身份和目标服务，再启动上传与重建。",
        )
        self._identity = QLabel("等待八角度采集完成，或手动选择八张照片")
        self._identity.setWordWrap(True)
        self._identity.setAccessibleName("当前任务身份")
        self._stage = QLabel("状态：未就绪")
        self._stage.setWordWrap(True)
        self._stage.setObjectName("mutedText")
        endpoint = QLabel("服务地址：" + (service_url or "未配置"))
        endpoint.setObjectName("mutedText")
        endpoint.setWordWrap(True)
        staging = QLabel("Jetson 暂存目录：" + staging_root)
        staging.setObjectName("mutedText")
        staging.setWordWrap(True)
        summary.addWidget(self._identity)
        summary.addWidget(self._stage)
        metadata = QHBoxLayout()
        metadata.setSpacing(20)
        metadata.addWidget(endpoint, 1)
        metadata.addWidget(staging, 2)
        summary.addLayout(metadata)

        stages = QWidget()
        stages.setAccessibleName("重建流程阶段")
        stage_layout = QHBoxLayout(stages)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        stage_layout.setSpacing(12)
        self._upload_stage = WorkflowStage("01", "上传任务")
        self._reconstruction_stage = WorkflowStage("02", "服务端重建")
        self._download_stage = WorkflowStage("03", "下载与校验")
        for stage in (
            self._upload_stage,
            self._reconstruction_stage,
            self._download_stage,
        ):
            stage_layout.addWidget(stage, 1)
        self.layout.addWidget(stages)

        # Compatibility aliases for code that reads the original progress bars.
        self._upload = self._upload_stage.progress
        self._reconstruction = self._reconstruction_stage.progress
        self._download = self._download_stage.progress

        actions = self.add_card(
            "任务操作",
            "照片按自然数字顺序映射到固定八个视角；主操作会根据任务状态自动变化。",
        )
        selection_hint = QLabel(
            "文件名无需包含角度，例如 01.jpg～08.jpg。"
        )
        selection_hint.setObjectName("mutedText")
        selection_hint.setWordWrap(True)
        actions.addWidget(selection_hint)
        action_row = QHBoxLayout()
        self._select_images = QPushButton("选择八张照片")
        self._select_images.setObjectName("secondaryButton")
        self._select_images.setAccessibleName("手动选择八张重建照片")
        self._select_images.clicked.connect(self.select_images_requested.emit)
        self._action = QPushButton("等待八角度采集")
        self._action.setObjectName("primaryButton")
        self._action.setAccessibleName("当前任务主操作")
        self._action.setEnabled(False)
        self._action.clicked.connect(self._activate)
        action_row.addWidget(self._select_images)
        action_row.addStretch(1)
        action_row.addWidget(self._action)
        actions.addLayout(action_row)
        self.finish()

    def set_job(self, job) -> None:
        self._job = job
        self._identity.setText(
            "采集：{}    本地任务：{}{}".format(
                job.capture_id,
                job.job_id,
                "    服务任务：{}".format(job.server_task_id)
                if job.server_task_id
                else "",
            )
        )
        self._stage.setText(
            "状态：{} · {}".format(job.state.value, job.stage_message)
            + ("\n错误：" + job.error if job.error else "")
        )
        self.set_upload_progress(job.upload_sent, job.upload_total)
        self.set_reconstruction_progress(
            job.reconstruction_progress,
            job.stage_message or "等待服务端进度",
        )
        self.set_download_progress(job.download_received, job.download_total)
        self._sync_stage_states(job)

        if job.state is ReconstructionState.COMPLETED:
            self._action.setText("打开结果")
            self._action.setEnabled(bool(job.result_path))
            self._banner.set_status(
                "任务完成，结果已在 Jetson 本地校验。",
                "success",
            )
        elif job.state in {
            ReconstructionState.READY,
            ReconstructionState.FAILED,
            ReconstructionState.CANCELLED,
            ReconstructionState.INTERRUPTED,
        }:
            self._action.setText(
                "上传并重建"
                if job.state is ReconstructionState.READY
                else "重试传输与重建"
            )
            self._action.setEnabled(True)
            if job.state in {
                ReconstructionState.FAILED,
                ReconstructionState.INTERRUPTED,
            }:
                self._banner.set_status(
                    "任务失败或被中断，可从本地持久化状态安全重试。",
                    "warning",
                )
        else:
            self._action.setText("传输与重建进行中")
            self._action.setEnabled(False)

        selectable_states = {
            ReconstructionState.READY,
            ReconstructionState.FAILED,
            ReconstructionState.CANCELLED,
            ReconstructionState.INTERRUPTED,
            ReconstructionState.COMPLETED,
        }
        self._select_images.setEnabled(
            not self._selection_busy and job.state in selectable_states
        )

    def set_upload_progress(self, sent: int, total: int) -> None:
        self._upload_stage.set_progress(
            self._percent(sent, total),
            "已发送 {:,} / {:,} 字节".format(sent, total),
        )

    def set_reconstruction_progress(self, progress: float, stage: str) -> None:
        self._reconstruction_stage.set_progress(
            int(progress),
            "{} · {:.1f}%".format(stage, progress),
        )

    def set_download_progress(self, received: int, total: int) -> None:
        self._download_stage.set_progress(
            self._percent(received, total),
            "已接收 {:,} / {:,} 字节".format(received, total),
        )

    def set_selection_busy(self, busy: bool) -> None:
        self._selection_busy = busy
        self._select_images.setEnabled(not busy)
        self._select_images.setText(
            "正在校验八张照片…" if busy else "选择八张照片"
        )
        if busy:
            self._action.setEnabled(False)
            self._banner.set_status(
                "正在后台复制、校验并生成本地任务。",
                "info",
            )
        elif self._job is not None:
            self.set_job(self._job)

    def show_selection_error(self, message: str) -> None:
        self._banner.set_status(
            "照片选择失败：{}".format(message),
            "danger",
        )

    def _sync_stage_states(self, job) -> None:
        state = job.state
        stages = (
            self._upload_stage,
            self._reconstruction_stage,
            self._download_stage,
        )
        for stage in stages:
            stage.set_state("pending")

        if state in self._UPLOAD_ACTIVE:
            self._upload_stage.set_state("active")
            return
        if state in self._RECONSTRUCTION_ACTIVE:
            self._complete_stage(self._upload_stage)
            self._reconstruction_stage.set_state("active")
            return
        if state in self._DOWNLOAD_ACTIVE:
            self._complete_stage(self._upload_stage)
            self._complete_stage(self._reconstruction_stage)
            self._download_stage.set_state("active")
            return
        if state is ReconstructionState.COMPLETED:
            for stage in stages:
                self._complete_stage(stage)
            return
        if state in {
            ReconstructionState.FAILED,
            ReconstructionState.CANCELLED,
            ReconstructionState.INTERRUPTED,
        }:
            presentation = (
                "failed"
                if state is ReconstructionState.FAILED
                else "warning"
            )
            if job.download_received or job.download_total:
                self._complete_stage(self._upload_stage)
                self._complete_stage(self._reconstruction_stage)
                self._download_stage.set_state(presentation)
            elif job.reconstruction_progress:
                self._complete_stage(self._upload_stage)
                self._reconstruction_stage.set_state(presentation)
            else:
                self._upload_stage.set_state(presentation)

    @staticmethod
    def _complete_stage(stage: WorkflowStage) -> None:
        stage.set_state("completed")
        stage.set_progress(100, "已完成")

    def _activate(self) -> None:
        if not self._job:
            return
        if self._job.state is ReconstructionState.COMPLETED:
            self.open_result_requested.emit(str(self._job.result_path))
        else:
            self.start_requested.emit(self._job.job_id)

    @staticmethod
    def _percent(value: int, total: int) -> int:
        return int(min(100, value * 100 / total)) if total else 0
