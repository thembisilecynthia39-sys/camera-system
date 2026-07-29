from datetime import datetime, timezone
from pathlib import Path

import pytest

from camera_system.domain import (
    AppError,
    CaptureProgress,
    CaptureSession,
    ReconstructionStatus,
    ReconstructionTask,
    ResultArtifact,
    TASK_ANGLES,
    TaskFile,
    TaskImage,
    TaskManifest,
    TaskState,
    TransferReceipt,
)


HASH = "a" * 64


def _manifest() -> TaskManifest:
    images = tuple(
        TaskImage(
            index=index,
            angle_deg=angle,
            filename=f"{index}.jpg",
            source_filename=f"source_{index}.jpg",
            sha256=HASH,
            size_bytes=index + 1,
        )
        for index, angle in enumerate(TASK_ANGLES)
    )
    files = tuple(
        TaskFile(
            relative_path=f"images/{index}.jpg",
            sha256=HASH,
            size_bytes=index + 1,
        )
        for index in range(8)
    )
    return TaskManifest(
        schema_version="1.0",
        capture_id="capture_001",
        images=images,
        files=files,
        created_at=datetime.now(timezone.utc),
        checksum="b" * 64,
    )


def test_manifest_is_exactly_the_existing_eight_angle_contract():
    manifest = _manifest()

    assert manifest.image_count == 8
    assert manifest.angles == TASK_ANGLES
    assert [manifest.image_for_index(index).angle_deg for index in range(8)] == list(TASK_ANGLES)


def test_task_image_rejects_wrong_fixed_mapping():
    with pytest.raises(ValueError, match="requires angle 45"):
        TaskImage(
            index=1,
            angle_deg=90,
            filename="1.jpg",
            source_filename="source.jpg",
            sha256=HASH,
            size_bytes=1,
        )


@pytest.mark.parametrize(
    "relative_path",
    ["/tmp/image.jpg", "../image.jpg", "./image.jpg", ""],
)
def test_task_file_rejects_unsafe_paths(relative_path):
    with pytest.raises(ValueError):
        TaskFile(relative_path=relative_path, sha256=HASH, size_bytes=1)


def test_task_manifest_rejects_incomplete_images():
    valid = _manifest()
    with pytest.raises(ValueError, match="exactly 8"):
        TaskManifest(
            schema_version=valid.schema_version,
            capture_id=valid.capture_id,
            images=valid.images[:-1],
            files=valid.files,
            created_at=valid.created_at,
            checksum=valid.checksum,
        )


def test_capture_models_use_only_serializable_python_types():
    capture = CaptureSession(
        session_id="capture_001",
        capture_id="capture_001",
        capture_dir=Path("captures/capture_001"),
        camera_ids=("1", "2"),
        captured_angles=TASK_ANGLES,
        state=TaskState.READY,
    )
    progress = CaptureProgress(
        session_id=capture.session_id,
        state=TaskState.READY,
        completed_angles=TASK_ANGLES,
        progress_percent=100,
        readiness_percent=100,
        camera_count=2,
    )

    assert capture.capture_dir == Path("captures/capture_001")
    assert progress.progress_percent == 100
    assert not any(type(value).__module__.startswith("PySide") for value in vars(progress).values())


def test_reconstruction_and_result_models_preserve_identity():
    manifest = _manifest()
    receipt = TransferReceipt(
        task_id="task-capture_001",
        capture_id="capture_001",
        checksum=manifest.checksum,
        server_url="http://127.0.0.1:8000",
        status="ready",
        duplicate=False,
    )
    task = ReconstructionTask(
        capture_id="capture_001",
        manifest=manifest,
        staging_dir=Path("staging/capture_001"),
        task_id=receipt.task_id,
        receipt=receipt,
        state=TaskState.RECONSTRUCTING,
    )
    status = ReconstructionStatus(
        task_id=task.task_id,
        capture_id=task.capture_id,
        remote_status="finished",
        progress=100,
        workflow_state=TaskState.DOWNLOADING,
    )
    artifact = ResultArtifact(
        task_id=task.task_id,
        capture_id=task.capture_id,
        path=Path("result/3DGS.ply"),
        filename="3DGS.ply",
        size_bytes=1,
        sha256=HASH,
        chunk_size=1,
        chunk_count=1,
    )

    assert task.receipt == receipt
    assert status.workflow_state is TaskState.DOWNLOADING
    assert artifact.protocol_message_type == "ply_result"


def test_app_error_is_a_plain_serializable_value():
    error = AppError(
        code="capture_incomplete",
        message="eight angles are required",
        operation="prepare_task",
        recoverable=True,
        details={"completed": 7},
    )

    assert error.details == {"completed": 7}
    assert error.recoverable is True
