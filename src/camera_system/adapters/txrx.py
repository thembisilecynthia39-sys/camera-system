"""Adapters around the existing Tx_Rx client; no protocol logic is duplicated."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..domain import (
    ReconstructionStatus,
    ReconstructionTask,
    ResultArtifact,
    TaskFile,
    TaskImage,
    TaskManifest,
    TaskState,
    TaskStateMachine,
    TransferReceipt,
)
from .errors import ServiceError, make_service_error


def task_manifest_from_txrx(source: Any) -> TaskManifest:
    """Translate the existing Pydantic manifest into the Qt-free domain model."""

    try:
        images = tuple(
            TaskImage(
                index=image.index,
                angle_deg=image.angle,
                filename=image.filename,
                source_filename=image.source_filename,
                sha256=image.sha256,
                size_bytes=image.size_bytes,
            )
            for image in sorted(source.images, key=lambda item: item.index)
        )
        files = tuple(
            TaskFile(
                relative_path=item.relative_path,
                sha256=item.sha256,
                size_bytes=item.size_bytes,
            )
            for item in source.files
        )
        return TaskManifest(
            schema_version=source.schema_version,
            capture_id=source.capture_id,
            images=images,
            files=files,
            created_at=source.created_at,
            checksum=source.checksum,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise make_service_error(
            "manifest_translation_failed",
            f"cannot translate Tx_Rx task manifest: {exc}",
            "manifest_translation",
            exc,
        ) from exc


class TxRxReconstructionAdapter:
    """Use Tx_Rx's public upload/reconstruct and status APIs unchanged."""

    def submit(
        self,
        task: ReconstructionTask,
        *,
        config_path: Optional[Path] = None,
        session: Any = None,
    ) -> ReconstructionTask:
        if task.state is not TaskState.READY:
            raise ServiceError(
                code_error(
                    "invalid_submit_state",
                    f"task must be ready before submit, got {task.state.value}",
                    "submit",
                )
            )
        try:
            from tx_rx.config import load_config
            from tx_rx.jetson_client.uploader import upload_staged_task

            config = load_config(config_path)
            uploaded = upload_staged_task(task.staging_dir, config_path, session)
        except ImportError as exc:
            raise make_service_error(
                "txrx_unavailable",
                "Tx_Rx client is not importable",
                "submit",
                exc,
            ) from exc
        except Exception as exc:
            raise make_service_error(
                "reconstruction_submit_failed",
                f"cannot upload task or request reconstruction: {exc}",
                "submit",
                exc,
                recoverable=True,
            ) from exc

        receipt = TransferReceipt(
            task_id=uploaded.task_id,
            capture_id=task.capture_id,
            checksum=uploaded.checksum,
            server_url=config.server_url,
            status=uploaded.upload_response.status,
            duplicate=uploaded.upload_response.duplicate,
        )
        # The current Tx_Rx public function intentionally performs both
        # POST /upload and POST /reconstruct.  Preserve that semantic boundary
        # instead of reimplementing either HTTP validation path here.
        TaskStateMachine(task.state).transition(TaskState.UPLOADING).transition(
            TaskState.RECONSTRUCTING
        )
        return replace(
            task,
            task_id=uploaded.task_id,
            receipt=receipt,
            state=TaskState.RECONSTRUCTING,
        )

    def poll(
        self,
        task: ReconstructionTask,
        *,
        config_path: Optional[Path] = None,
        session: Any = None,
        cancel_check: Any = None,
        progress_callback: Any = None,
    ) -> ReconstructionStatus:
        if not task.task_id:
            raise ServiceError(
                code_error("task_id_missing", "cannot poll a task without task_id", "poll")
            )
        try:
            from tx_rx.config import load_config
            from tx_rx.jetson_client.transfer import poll_status

            config = load_config(config_path)
            status = poll_status(
                task.task_id,
                task.capture_id,
                config,
                session,
                cancel_check,
                progress_callback,
            )
        except Exception as exc:
            message = str(exc)
            code = "reconstruction_cancelled" if "cancel" in message.lower() else "status_poll_failed"
            raise make_service_error(
                code,
                f"cannot poll reconstruction status: {message}",
                "poll",
                exc,
                recoverable=code == "status_poll_failed",
            ) from exc

        remote_status = status.status.value
        workflow_state = TaskState.DOWNLOADING if remote_status == "finished" else TaskState.RECONSTRUCTING
        return ReconstructionStatus(
            task_id=status.task_id,
            capture_id=status.capture_id,
            remote_status=remote_status,
            progress=float(status.progress),
            stage=status.stage,
            current_step=status.current_step,
            total_steps=status.total_steps,
            message=status.message,
            output_ply=status.output_ply,
            error=status.error,
            workflow_state=workflow_state,
            updated_at=status.updated_at or datetime.now(timezone.utc),
        )


class TxRxTransferAdapter:
    """Use Tx_Rx's validated metadata, Range download and ACK functions."""

    def download_result(
        self,
        task: ReconstructionTask,
        *,
        config_path: Optional[Path] = None,
        session: Any = None,
        cancel_check: Any = None,
        progress_callback: Any = None,
    ) -> ResultArtifact:
        if not task.task_id:
            raise ServiceError(
                code_error("task_id_missing", "cannot download a task without task_id", "download_result")
            )
        try:
            from tx_rx.config import load_config
            from tx_rx.jetson_client.transfer import download_ply, get_ply_metadata

            config = load_config(config_path)
            metadata = get_ply_metadata(task.task_id, task.capture_id, config, session)
            path = download_ply(metadata, config, session, cancel_check, progress_callback)
        except Exception as exc:
            raise make_service_error(
                "result_download_failed",
                f"cannot download or verify reconstruction result: {exc}",
                "download_result",
                exc,
                recoverable=True,
            ) from exc
        return ResultArtifact(
            task_id=metadata.task_id,
            capture_id=metadata.capture_id,
            path=path,
            filename=metadata.filename,
            size_bytes=metadata.file_size,
            sha256=metadata.sha256,
            protocol_magic=metadata.magic,
            protocol_version=metadata.version,
            protocol_message_type=metadata.message_type,
            chunk_size=metadata.chunk_size,
            chunk_count=metadata.chunk_count,
            created_at=metadata.created_at,
            metadata={"output_ply": metadata.filename},
        )

    def acknowledge_result(
        self,
        task: ReconstructionTask,
        artifact: ResultArtifact,
        *,
        config_path: Optional[Path] = None,
        session: Any = None,
    ) -> None:
        if task.task_id != artifact.task_id or task.capture_id != artifact.capture_id:
            raise ServiceError(
                code_error(
                    "result_identity_mismatch",
                    "task and artifact identity do not match",
                    "acknowledge_result",
                )
            )
        if artifact.chunk_size is None or artifact.chunk_count is None:
            raise ServiceError(
                code_error(
                    "result_metadata_missing",
                    "result artifact lacks Tx_Rx chunk metadata needed for ACK",
                    "acknowledge_result",
                )
            )
        try:
            from tx_rx.config import load_config
            from tx_rx.jetson_client.transfer import acknowledge_result
            from tx_rx.protocol.models import PlyMetadata

            config = load_config(config_path)
            metadata = PlyMetadata(
                magic=artifact.protocol_magic,
                version=artifact.protocol_version,
                message_type=artifact.protocol_message_type,
                task_id=artifact.task_id,
                capture_id=artifact.capture_id,
                filename=artifact.filename,
                file_size=artifact.size_bytes,
                sha256=artifact.sha256,
                chunk_size=artifact.chunk_size,
                chunk_count=artifact.chunk_count,
                created_at=artifact.created_at,
            )
            acknowledge_result(metadata, artifact.path, config, session)
        except Exception as exc:
            raise make_service_error(
                "result_ack_failed",
                f"cannot acknowledge reconstruction result: {exc}",
                "acknowledge_result",
                exc,
                recoverable=True,
            ) from exc


def code_error(code: str, message: str, operation: str) -> "AppError":
    from ..domain import AppError

    return AppError(code=code, message=message, operation=operation, recoverable=True)
