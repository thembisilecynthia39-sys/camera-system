"""Transfer/reconstruction workflow presentation only."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton

from camera_system_app.domain import ReconstructionState
from camera_system_app.ui.pages.base import BasePage
from camera_system_app.ui.widgets import StatusBanner


class TransferReconstructionPage(BasePage):
    start_requested = Signal(str)
    open_result_requested = Signal(str)
    select_images_requested = Signal()

    def __init__(self, service_url: str, staging_root: str, parent=None) -> None:
        super().__init__(
            "传输与重建",
            "任务校验、上传、WSL 重建、状态轮询和校验下载均在后台执行。",
            parent,
        )
        self._job = None
        self._selection_busy = False
        status = (
            "服务地址已配置；仅在用户启动任务后连接。"
            if service_url
            else "WSL 地址和端口尚未配置，应用仍可离线使用。"
        )
        self._banner = StatusBanner(status)
        self.layout.addWidget(self._banner)
        card = self.add_card()
        title = QLabel("当前任务")
        title.setObjectName("sectionTitle")
        self._identity = QLabel("等待八角度采集完成，或手动选择八张照片")
        self._identity.setWordWrap(True)
        self._stage = QLabel("状态：未就绪")
        self._stage.setWordWrap(True)
        endpoint = QLabel("服务地址和端口：" + (service_url or "未配置"))
        endpoint.setObjectName("mutedText")
        endpoint.setWordWrap(True)
        staging = QLabel("Jetson 暂存目录：" + staging_root)
        staging.setObjectName("mutedText")
        staging.setWordWrap(True)

        self._upload_label = QLabel("上传进度")
        self._upload = QProgressBar()
        self._upload.setRange(0, 100)
        self._reconstruction_label = QLabel("重建进度")
        self._reconstruction = QProgressBar()
        self._reconstruction.setRange(0, 100)
        self._download_label = QLabel("下载进度")
        self._download = QProgressBar()
        self._download.setRange(0, 100)
        self._action = QPushButton("等待八角度采集")
        self._action.setObjectName("primaryButton")
        self._action.setEnabled(False)
        self._action.clicked.connect(self._activate)
        self._select_images = QPushButton("选择八张照片")
        self._select_images.setObjectName("secondaryButton")
        self._select_images.clicked.connect(self.select_images_requested.emit)
        selection_hint = QLabel(
            "文件名无需包含角度，例如 01.jpg～08.jpg。系统按文件名的"
            "自然数字顺序映射到固定八个视角。"
        )
        selection_hint.setObjectName("mutedText")
        selection_hint.setWordWrap(True)

        for widget in (
            title,
            self._identity,
            self._stage,
            endpoint,
            staging,
            self._upload_label,
            self._upload,
            self._reconstruction_label,
            self._reconstruction,
            self._download_label,
            self._download,
            self._select_images,
            selection_hint,
            self._action,
        ):
            card.addWidget(widget)
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
        self._reconstruction.setValue(int(job.reconstruction_progress))
        self.set_download_progress(job.download_received, job.download_total)
        if job.state is ReconstructionState.COMPLETED:
            self._action.setText("打开结果")
            self._action.setEnabled(bool(job.result_path))
            self._banner.set_status("任务完成，结果已在 Jetson 本地校验。", "success")
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
        self._upload.setValue(self._percent(sent, total))
        self._upload_label.setText("上传进度：{} / {} 字节".format(sent, total))

    def set_reconstruction_progress(self, progress: float, stage: str) -> None:
        self._reconstruction.setValue(int(progress))
        self._reconstruction_label.setText("重建进度：{} · {:.1f}%".format(stage, progress))

    def set_download_progress(self, received: int, total: int) -> None:
        self._download.setValue(self._percent(received, total))
        self._download_label.setText(
            "下载进度：{} / {} 字节".format(received, total)
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
                "success",
            )
        elif self._job is not None:
            self.set_job(self._job)

    def show_selection_error(self, message: str) -> None:
        self._banner.set_status("照片选择失败：{}".format(message), "warning")

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
