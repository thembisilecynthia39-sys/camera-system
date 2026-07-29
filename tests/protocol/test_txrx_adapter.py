from datetime import datetime, timezone
from pathlib import Path

from tx_rx.protocol.models import ReconstructResponse, StatusResponse, TaskStatus, UploadResponse

from camera_system.adapters import TxRxReconstructionAdapter
from camera_system.domain import (
    TASK_ANGLES,
    TaskFile,
    TaskImage,
    TaskManifest,
    TaskState,
    ReconstructionTask,
)


HASH = "a" * 64


def _task(tmp_path: Path) -> ReconstructionTask:
    manifest = TaskManifest(
        schema_version="1.0",
        capture_id="capture_001",
        images=tuple(
            TaskImage(
                index=index,
                angle_deg=angle,
                filename=f"{index}.jpg",
                source_filename=f"source_{index}.jpg",
                sha256=HASH,
                size_bytes=1,
            )
            for index, angle in enumerate(TASK_ANGLES)
        ),
        files=tuple(
            TaskFile(relative_path=f"images/{index}.jpg", sha256=HASH, size_bytes=1)
            for index in range(8)
        ),
        created_at=datetime.now(timezone.utc),
        checksum=HASH,
    )
    return ReconstructionTask(
        capture_id="capture_001",
        manifest=manifest,
        staging_dir=tmp_path / "staging",
    )


class _Config:
    server_url = "http://wsl.example:8000"


def test_reconstruction_adapter_delegates_upload_and_preserves_receipt(monkeypatch, tmp_path):
    import tx_rx.config
    import tx_rx.jetson_client.uploader

    upload_response = UploadResponse(
        message_type="upload_received",
        task_id="task-capture_001",
        capture_id="capture_001",
        status="ready",
        duplicate=False,
    )
    reconstruct_response = ReconstructResponse(
        message_type="reconstruction_queued",
        task_id="task-capture_001",
        capture_id="capture_001",
        status="queued",
    )

    class UploadResult:
        def __init__(self):
            self.task_id = "task-capture_001"
            self.checksum = HASH
            self.upload_response = upload_response
            self.reconstruct_response = reconstruct_response

    monkeypatch.setattr(tx_rx.config, "load_config", lambda _path=None: _Config())
    monkeypatch.setattr(
        tx_rx.jetson_client.uploader,
        "upload_staged_task",
        lambda *_args, **_kwargs: UploadResult(),
    )

    submitted = TxRxReconstructionAdapter().submit(_task(tmp_path))

    assert submitted.task_id == "task-capture_001"
    assert submitted.state is TaskState.RECONSTRUCTING
    assert submitted.receipt is not None
    assert submitted.receipt.server_url == "http://wsl.example:8000"


def test_reconstruction_adapter_maps_remote_finished_status(monkeypatch, tmp_path):
    import tx_rx.config
    import tx_rx.jetson_client.transfer

    now = datetime.now(timezone.utc)
    remote = StatusResponse(
        message_type="status",
        task_id="task-capture_001",
        capture_id="capture_001",
        status=TaskStatus.FINISHED,
        progress=100,
        stage="finished",
        output_ply="3DGS.ply",
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(tx_rx.config, "load_config", lambda _path=None: _Config())
    monkeypatch.setattr(tx_rx.jetson_client.transfer, "poll_status", lambda *_args, **_kwargs: remote)

    task = _task(tmp_path)
    task = ReconstructionTask(
        capture_id=task.capture_id,
        manifest=task.manifest,
        staging_dir=task.staging_dir,
        task_id="task-capture_001",
        state=TaskState.RECONSTRUCTING,
    )
    status = TxRxReconstructionAdapter().poll(task)

    assert status.remote_status == "finished"
    assert status.workflow_state is TaskState.DOWNLOADING
    assert status.output_ply == "3DGS.ply"
