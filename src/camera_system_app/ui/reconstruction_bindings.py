"""Bind persisted reconstruction jobs and background workers to the shell."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QMessageBox

from camera_system_app.domain import ErrorCode, ReconstructionState, user_message
from camera_system_app.workers import ManualImportWorker, TransferWorker


class ReconstructionBindings(QObject):
    def __init__(self, window, workflow, settings_manager=None, parent=None) -> None:
        super().__init__(parent)
        self.window = window
        self.workflow = workflow
        self.settings_manager = settings_manager
        self._worker = None
        self._import_worker = None
        self._history_timer = QTimer(self)
        self._history_timer.setSingleShot(True)
        self._history_timer.setInterval(250)
        self._history_timer.timeout.connect(self._refresh_history_now)
        self._logger = logging.getLogger("camera_system_app.ui.reconstruction")
        window.transfer_page.start_requested.connect(self.start)
        window.transfer_page.open_result_requested.connect(self.open_result)
        window.transfer_page.select_images_requested.connect(
            self.select_manual_images
        )
        window.history_page.retry_requested.connect(self.start)
        window.history_page.open_result_requested.connect(self.open_result)
        window.history_page.select_requested.connect(self.select_job)
        window.history_page.open_task_directory_requested.connect(
            self.open_task_directory
        )
        if settings_manager is not None:
            window.settings_page.save_requested.connect(self._reload_settings)

    def initialize(self) -> None:
        jobs = self.workflow.restore()
        self.window.history_page.set_jobs(jobs)
        invalid = self.workflow.repository.invalid_task_directories
        if invalid:
            self.window.statusBar().showMessage(
                "● 有 {} 个本地任务状态损坏，详情已写入日志。".format(len(invalid))
            )
        if jobs:
            self.window.transfer_page.set_job(jobs[0])
        completed = next(
            (
                job
                for job in jobs
                if job.state is ReconstructionState.COMPLETED
                and job.result_path
                and job.result_path.is_file()
            ),
            None,
        )
        if completed:
            self.window.result_page.set_result_available(str(completed.result_path))

    def register_capture(self, event) -> None:
        job = self.workflow.register_capture(event)
        self.window.transfer_page.set_job(job)
        self._refresh_history()
        self.window.statusBar().showMessage("● 八角度采集已就绪，可上传并重建")

    def start(self, job_id: str) -> None:
        if self._worker is not None:
            return
        try:
            job = self.workflow.repository.get(job_id)
        except Exception as exc:
            self._logger.exception("Cannot load task %s", job_id)
            QMessageBox.warning(
                self.window, "无法启动任务", user_message(exc, "读取任务")
            )
            return
        self.window.transfer_page.set_job(
            job.changed(
                state=ReconstructionState.VALIDATING,
                stage_message="后台任务正在启动",
            )
        )
        worker = TransferWorker(self.workflow, job_id, self)
        worker.job_changed.connect(self._on_job_changed)
        worker.upload_progress.connect(self.window.transfer_page.set_upload_progress)
        worker.reconstruction_progress.connect(
            self.window.transfer_page.set_reconstruction_progress
        )
        worker.download_progress.connect(
            self.window.transfer_page.set_download_progress
        )
        worker.result_available.connect(self._on_result_available)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(lambda current=worker: self._on_finished(current))
        self._worker = worker
        worker.start()

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        workers = (self._import_worker, self._worker)
        for worker in workers:
            if worker is None or not worker.isRunning():
                continue
            cancel = getattr(worker, "cancel", None)
            if callable(cancel):
                cancel()
            else:
                worker.requestInterruption()
            if not worker.wait(timeout_ms):
                self._logger.error(
                    "%s did not stop within %sms",
                    type(worker).__name__,
                    timeout_ms,
                )
                return False
        return True

    def select_manual_images(self) -> None:
        if self._worker is not None or self._import_worker is not None:
            return
        initial_dir = str(Path(self.workflow.settings.capture_root))
        selected, _ = QFileDialog.getOpenFileNames(
            self.window,
            "选择八张照片（按文件名顺序对应八个角度）",
            initial_dir,
            "JPEG 照片 (*.jpg *.jpeg *.JPG *.JPEG)",
        )
        if not selected:
            return
        if len(selected) != 8:
            message = "必须且只能选择八张照片，当前选择了 {} 张。".format(
                len(selected)
            )
            self.window.transfer_page.show_selection_error(message)
            QMessageBox.warning(self.window, "照片数量不正确", message)
            return
        self.window.transfer_page.set_selection_busy(True)
        worker = ManualImportWorker(self.workflow, selected, self)
        worker.imported.connect(self._on_manual_imported)
        worker.failed.connect(self._on_manual_import_failed)
        worker.finished.connect(
            lambda current=worker: self._on_import_finished(current)
        )
        self._import_worker = worker
        worker.start()

    def select_job(self, job_id: str) -> None:
        try:
            job = self.workflow.repository.get(job_id)
        except Exception as exc:
            QMessageBox.warning(self.window, "任务不可用", str(exc))
            return
        self.window.transfer_page.set_job(job)
        self.window.navigation.setCurrentRow(1)

    def open_result(self, local_path: str) -> None:
        self.window.result_page.set_result_available(local_path)
        self.window.navigation.setCurrentRow(2)
        self.window.result_page.open_current_result()

    def open_task_directory(self, job_id: str) -> None:
        directory = self.workflow.repository.task_dir(job_id)
        if not directory.is_dir():
            QMessageBox.warning(self.window, "任务目录不存在", str(directory))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(directory))))

    def _on_job_changed(self, job) -> None:
        self.window.transfer_page.set_job(job)
        self._refresh_history()
        self.window.statusBar().showMessage(
            "● 任务 {}：{}".format(job.capture_id, job.stage_message)
        )

    def _on_result_available(self, event) -> None:
        self.window.result_page.set_result_available(str(event.local_path))
        self.window.transfer_page.set_job(self.workflow.repository.get(event.job_id))
        self._refresh_history()
        self.window.statusBar().showMessage(
            "● 重建完成：{}".format(event.local_path)
        )

    def _on_failed(self, error) -> None:
        message = user_message(error, "传输与重建")
        self._logger.error("Transfer worker failed: %s", message)
        if self._worker:
            try:
                self.window.transfer_page.set_job(
                    self.workflow.repository.get(self._worker.job_id)
                )
            except Exception:
                pass
        self._refresh_history()
        self.window.transfer_page._banner.set_status(message, "error")
        if getattr(error, "code", None) in {
            ErrorCode.SERVICE_UNAVAILABLE,
            ErrorCode.TIMEOUT,
            ErrorCode.REMOTE_FAILURE,
        }:
            self.window.statusBar().showMessage("● WSL 服务连接异常：" + message)

    def _on_manual_imported(self, job) -> None:
        self.window.transfer_page.set_job(job)
        self._refresh_history()
        self.window.statusBar().showMessage(
            "● 已校验八张照片，可上传并重建"
        )

    def _on_manual_import_failed(self, error) -> None:
        message = user_message(error, "导入八张照片")
        self._logger.error("Manual image import failed: %s", message)
        self.window.transfer_page.show_selection_error(message)

    def _on_import_finished(self, worker) -> None:
        if self._import_worker is worker:
            self._import_worker = None
        self.window.transfer_page.set_selection_busy(False)
        worker.deleteLater()

    def _on_finished(self, worker) -> None:
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

    def _refresh_history(self) -> None:
        if not self._history_timer.isActive():
            self._history_timer.start()

    def _refresh_history_now(self) -> None:
        self.window.history_page.set_jobs(self.workflow.repository.all())

    def _reload_settings(self, _values) -> None:
        if self.settings_manager is not None:
            self.workflow.settings = self.settings_manager.load()
