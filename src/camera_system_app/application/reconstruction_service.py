"""Recoverable application workflow around the existing Tx_Rx client."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

from camera_system_app.config.settings import AppSettings
from camera_system_app.domain import (
    ACTIVE_STATES,
    ApplicationError,
    CaptureCompletedEvent,
    ErrorCode,
    OperationCancelledError,
    ReconstructionJob,
    ReconstructionState,
    ResultAvailableEvent,
    TaskValidationError,
    normalize_error,
)
from camera_system_app.infrastructure.reconstruction_repository import (
    ReconstructionJobRepository,
)

JobCallback = Callable[[ReconstructionJob], None]
ByteProgressCallback = Callable[[int, int], None]

_DOWNLOAD_RE = re.compile(r"download=(\d+)/(\d+)")
_REMOTE_PROGRESS_RE = re.compile(r"progress=([0-9.]+)")
_PROGRESS_PERSIST_INTERVAL_SECONDS = 1.0


def _natural_filename_key(path: Path):
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in re.split(r"(\d+)", path.name.casefold())
        if part
    )


class ReconstructionWorkflow:
    """Synchronously execute one job; callers must run it outside the UI thread."""

    def __init__(
        self,
        project_root: Path,
        settings: AppSettings,
        repository: ReconstructionJobRepository,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.settings = settings
        self.repository = repository
        self._active = set()
        self._active_lock = threading.RLock()
        self._logger = logging.getLogger("camera_system_app.reconstruction")
        txrx_root = self.project_root / "Tx_Rx"
        if str(txrx_root) not in sys.path:
            sys.path.insert(0, str(txrx_root))

    def register_capture(self, event: CaptureCompletedEvent) -> ReconstructionJob:
        token = hashlib.sha256(str(event.capture_dir).encode("utf-8")).hexdigest()[:16]
        job = ReconstructionJob(
            job_id=f"{event.capture_dir.name}-{token}",
            capture_id=event.capture_dir.name,
            capture_dir=event.capture_dir,
        )
        return self.repository.register(job)

    def import_manual_images(self, image_paths) -> ReconstructionJob:
        """Persist and validate one user-selected fixed-angle image set.

        Callers must run this filesystem-heavy operation outside the Qt GUI
        thread. Files are ordered by filename and mapped to the fixed angles.
        """

        from tx_rx.jetson_client.task_manifest import prepare_manual_task

        images = sorted(
            (Path(path).expanduser().resolve() for path in image_paths),
            key=lambda path: (_natural_filename_key(path), str(path)),
        )
        if len(images) != 8:
            raise TaskValidationError("必须且只能选择八张照片。")
        if len(set(images)) != 8:
            raise TaskValidationError("八张照片不能包含重复文件。")
        for path in images:
            if path.suffix.lower() not in {".jpg", ".jpeg"}:
                raise TaskValidationError(
                    "只支持 JPG/JPEG 照片：{}".format(path.name)
                )
            if not path.is_file():
                raise TaskValidationError("照片不存在：{}".format(path))
            if path.stat().st_size <= 0:
                raise TaskValidationError("照片为空：{}".format(path))

        root = Path(self.settings.transfer_staging_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        job_id = "manual-{}-{}".format(stamp, uuid.uuid4().hex[:8])
        final_dir = root / job_id
        temporary_dir = Path(
            tempfile.mkdtemp(prefix=".{}-".format(job_id), dir=str(root))
        )
        try:
            images_dir = temporary_dir / "images"
            images_dir.mkdir()
            for index, source in enumerate(images):
                shutil.copy2(str(source), str(images_dir / "{}.jpg".format(index)))
            os.replace(str(temporary_dir), str(final_dir))
            package = prepare_manual_task(final_dir)
            job = ReconstructionJob(
                job_id=job_id,
                capture_id=package.capture_id,
                capture_dir=package.staging_dir,
                staging_dir=package.staging_dir,
                stage_message="手动选择的八张照片已校验，可上传并重建",
            )
            return self.repository.register(job)
        except Exception:
            shutil.rmtree(temporary_dir, ignore_errors=True)
            shutil.rmtree(final_dir, ignore_errors=True)
            raise

    def restore(self) -> List[ReconstructionJob]:
        restored = []
        for job in self.repository.all():
            if job.state in ACTIVE_STATES:
                job = job.changed(
                    state=ReconstructionState.INTERRUPTED,
                    stage_message="上次运行在传输期间中断，可安全重试",
                    error="应用退出前任务尚未完成",
                    error_code=ErrorCode.INTERRUPTED.value,
                )
                self.repository.save(job)
            restored.append(job)
        return restored

    def execute(
        self,
        job_id: str,
        *,
        job_callback: Optional[JobCallback] = None,
        upload_callback: Optional[ByteProgressCallback] = None,
        reconstruction_callback: Optional[Callable[[float, str], None]] = None,
        download_callback: Optional[ByteProgressCallback] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        session=None,
    ) -> ResultAvailableEvent:
        with self._active_lock:
            if job_id in self._active:
                raise RuntimeError("该任务已在传输或重建中")
            self._active.add(job_id)
        try:
            return self._execute(
                job_id,
                job_callback,
                upload_callback,
                reconstruction_callback,
                download_callback,
                cancel_check,
                session,
            )
        except Exception as exc:
            error = normalize_error(exc, "传输与重建")
            job = self.repository.get(job_id)
            interrupted = (
                isinstance(error, OperationCancelledError)
                and error.code is ErrorCode.INTERRUPTED
            )
            cancelled = error.code is ErrorCode.CANCELLED
            self._update(
                job,
                job_callback,
                state=(
                    ReconstructionState.INTERRUPTED
                    if interrupted
                    else ReconstructionState.CANCELLED
                    if cancelled
                    else ReconstructionState.FAILED
                ),
                stage_message=error.user_message,
                error=error.user_message,
                error_code=error.code.value,
            )
            self._logger.exception("Reconstruction job %s failed", job_id)
            raise error from exc
        finally:
            with self._active_lock:
                self._active.discard(job_id)

    def _execute(
        self,
        job_id,
        job_callback,
        upload_callback,
        reconstruction_callback,
        download_callback,
        cancel_check,
        session,
    ) -> ResultAvailableEvent:
        from tx_rx.config import TxRxConfig
        from tx_rx.jetson_client.http_client import direct_session
        from tx_rx.jetson_client.task_manifest import (
            build_task_package,
            load_staged_task_package,
        )
        from tx_rx.jetson_client.transfer import (
            acknowledge_result,
            download_ply,
            get_ply_metadata,
            get_status,
            poll_status,
        )
        from tx_rx.jetson_client.uploader import (
            check_health,
            request_reconstruction,
            upload_task_package,
        )
        from tx_rx.protocol.models import TaskStatus

        job = self.repository.get(job_id)
        if job.state is ReconstructionState.COMPLETED:
            if (
                job.result_path
                and job.result_path.is_file()
                and job.result_sha256
                and (not job.result_size or job.result_path.stat().st_size == job.result_size)
                and self._sha256_file(job.result_path) == job.result_sha256
            ):
                return ResultAvailableEvent(
                    job.job_id, job.capture_id, job.result_path, job.result_sha256
                )
            raise TaskValidationError("已完成任务的本地结果不存在或完整性校验失败。")
        if not self.settings.wsl_service_url:
            raise TaskValidationError("请先在设置中配置 WSL 服务地址和端口。")

        if job.server_task_id and job.server_url != self.settings.wsl_service_url:
            job = self._update(
                job,
                job_callback,
                server_task_id=None,
                server_url=None,
                reconstruct_requested=False,
                staging_dir=None,
                stage_message="服务地址已变更，将重新建立远端任务",
            )
        config = TxRxConfig(
            schema_version="1.0",
            staging_root=Path(self.settings.transfer_staging_root) / job.job_id,
            server_url=self.settings.wsl_service_url,
            result_root=Path(self.settings.result_root),
            result_layout="task_nested",
            upload_timeout_seconds=self.settings.upload_timeout_seconds,
            request_timeout_seconds=self.settings.request_timeout_seconds,
            status_poll_interval_seconds=self.settings.status_poll_interval_seconds,
            reconstruction_timeout_seconds=self.settings.reconstruction_timeout_seconds,
            download_timeout_seconds=self.settings.download_timeout_seconds,
            max_ply_size_bytes=self.settings.max_ply_size_bytes,
        )
        client = session or direct_session()
        job = self._update(
            job,
            job_callback,
            state=ReconstructionState.VALIDATING,
            stage_message="校验八角度采集任务",
            attempts=job.attempts + 1,
            error=None,
            error_code=None,
        )
        self._cancel(cancel_check)

        job = self._update(
            job,
            job_callback,
            state=ReconstructionState.PACKAGING,
            stage_message="生成 task.json 并打包任务",
        )
        package = (
            load_staged_task_package(
                job.staging_dir,
                cancel_check=cancel_check,
            )
            if job.staging_dir
            else build_task_package(
                job.capture_dir,
                config.staging_root,
                cancel_check=cancel_check,
            )
        )
        job = self._update(
            job,
            job_callback,
            capture_id=package.capture_id,
            staging_dir=package.staging_dir,
        )

        job = self._update(
            job,
            job_callback,
            state=ReconstructionState.HEALTH_CHECK,
            stage_message="检查 WSL 重建服务",
        )
        check_health(config, client, cancel_check=cancel_check)
        self._cancel(cancel_check)

        if not job.server_task_id:
            receipt = self._read_receipt(package.staging_dir, package.checksum, config.server_url)
            if receipt:
                job = self._update(
                    job,
                    job_callback,
                    server_task_id=receipt,
                    server_url=config.server_url,
                )
            else:
                job = self._update(
                    job,
                    job_callback,
                    state=ReconstructionState.UPLOADING,
                    stage_message="上传任务包",
                )
                last_upload_persist = 0.0

                def on_upload(sent: int, total: int) -> None:
                    nonlocal job, last_upload_persist
                    job = job.changed(upload_sent=sent, upload_total=total)
                    now = time.monotonic()
                    if (
                        sent >= total
                        or now - last_upload_persist
                        >= _PROGRESS_PERSIST_INTERVAL_SECONDS
                    ):
                        job = self.repository.save(job)
                        if job_callback:
                            job_callback(job)
                        last_upload_persist = now
                    if upload_callback:
                        upload_callback(sent, total)

                uploaded = upload_task_package(
                    package,
                    config,
                    client,
                    progress_callback=on_upload,
                    cancel_check=cancel_check,
                )
                job = self._update(
                    job,
                    job_callback,
                    server_task_id=uploaded.task_id,
                    server_url=config.server_url,
                )

        task_id = str(job.server_task_id)
        remote_status = None
        if job.reconstruct_requested:
            # A failed status query is intentionally not followed by another
            # reconstruct POST: we cannot prove that the first request failed.
            remote_status = get_status(task_id, package.capture_id, config, client)

        if not job.reconstruct_requested:
            job = self._update(
                job,
                job_callback,
                state=ReconstructionState.STARTING,
                stage_message="请求启动重建",
                reconstruct_requested=True,
            )
            request_reconstruction(package, task_id, config, client)

        if remote_status is None or remote_status.status is not TaskStatus.FINISHED:
            job = self._update(
                job,
                job_callback,
                state=ReconstructionState.RECONSTRUCTING,
                stage_message="WSL 正在重建",
            )

            def on_status(message: str) -> None:
                nonlocal job
                match = _REMOTE_PROGRESS_RE.search(message)
                progress = float(match.group(1)) if match else job.reconstruction_progress
                stage = message.split(" progress=", 1)[0].replace("stage=", "")
                job = self._update(
                    job,
                    job_callback,
                    reconstruction_progress=progress,
                    stage_message="重建：{}".format(stage),
                )
                if reconstruction_callback:
                    reconstruction_callback(progress, stage)

            poll_status(
                task_id,
                package.capture_id,
                config,
                client,
                cancel_check,
                on_status,
            )

        job = self._update(
            job,
            job_callback,
            state=ReconstructionState.DOWNLOADING,
            stage_message="下载 3DGS.ply 到 Jetson 临时文件",
            reconstruction_progress=100.0,
        )
        metadata = get_ply_metadata(
            task_id,
            package.capture_id,
            config,
            client,
            cancel_check,
        )
        last_download_persist = 0.0

        def on_download(message: str) -> None:
            nonlocal job, last_download_persist
            match = _DOWNLOAD_RE.search(message)
            if not match:
                return
            received, total = int(match.group(1)), int(match.group(2))
            job = job.changed(
                download_received=received,
                download_total=total,
            )
            now = time.monotonic()
            if (
                received >= total
                or now - last_download_persist
                >= _PROGRESS_PERSIST_INTERVAL_SECONDS
            ):
                job = self.repository.save(job)
                if job_callback:
                    job_callback(job)
                last_download_persist = now
            if download_callback:
                download_callback(received, total)

        final_path = download_ply(
            metadata, config, client, cancel_check, on_download
        )
        job = self._update(
            job,
            job_callback,
            state=ReconstructionState.VERIFYING,
            stage_message="SHA-256 校验成功，结果已原子保存",
            result_path=final_path,
            result_sha256=metadata.sha256,
            result_size=metadata.file_size,
            download_received=metadata.file_size,
            download_total=metadata.file_size,
        )
        job = self._update(
            job,
            job_callback,
            state=ReconstructionState.ACKNOWLEDGING,
            stage_message="确认结果接收",
        )
        acknowledge_result(
            metadata,
            final_path,
            config,
            client,
            cancel_check,
        )
        job = self._update(
            job,
            job_callback,
            state=ReconstructionState.COMPLETED,
            stage_message="重建结果已就绪",
            reconstruction_progress=100.0,
            error=None,
            error_code=None,
        )
        return ResultAvailableEvent(
            job.job_id, job.capture_id, final_path, metadata.sha256
        )

    def _update(self, job, callback, **values):
        updated = self.repository.save(job.changed(**values))
        if callback:
            callback(updated)
        return updated

    @staticmethod
    def _cancel(cancel_check) -> None:
        if cancel_check and cancel_check():
            raise OperationCancelledError(interrupted=True)

    @staticmethod
    def _read_receipt(staging_dir: Path, checksum: str, server_url: str) -> Optional[str]:
        path = staging_dir / "upload.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                payload.get("checksum") == checksum
                and payload.get("server_url") == server_url
                and str(payload.get("task_id", "")).startswith("task-")
            ):
                return str(payload["task_id"])
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
        return None

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
