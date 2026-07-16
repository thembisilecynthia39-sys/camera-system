from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from tx_rx.protocol.models import (
    TASK_ANGLES,
    StatusResponse,
    TaskFile,
    TaskImage,
    TaskManifest,
    TaskStatus,
)

HASH = "a" * 64


def _images():
    return [
        TaskImage(
            index=index,
            angle=angle,
            filename=f"{index}.jpg",
            source_filename=f"source_{index}.jpg",
            sha256=HASH,
            size_bytes=index + 1,
        )
        for index, angle in enumerate(TASK_ANGLES)
    ]


def _manifest_data():
    return {
        "schema_version": "1.0",
        "capture_id": "capture_001",
        "image_count": 8,
        "angles": TASK_ANGLES,
        "images": [image.model_dump() for image in _images()],
        "files": [
            TaskFile(relative_path=f"images/{index}.jpg", sha256=HASH, size_bytes=index + 1).model_dump()
            for index in range(8)
        ],
        "created_at": datetime.now(timezone.utc),
        "checksum": "b" * 64,
    }


def test_valid_task_manifest():
    manifest = TaskManifest.model_validate(_manifest_data())
    assert manifest.image_count == 8
    assert [image.filename for image in manifest.images] == [f"{index}.jpg" for index in range(8)]


def test_image_count_must_be_eight():
    data = _manifest_data()
    data["image_count"] = 7
    with pytest.raises(ValidationError, match="image_count must equal 8"):
        TaskManifest.model_validate(data)


def test_angles_must_be_complete():
    data = _manifest_data()
    data["angles"] = TASK_ANGLES[:-1]
    with pytest.raises(ValidationError, match="angles must equal"):
        TaskManifest.model_validate(data)


def test_duplicate_image_index_is_rejected():
    data = _manifest_data()
    data["images"][1] = dict(data["images"][0])
    with pytest.raises(ValidationError, match="indexes must be unique"):
        TaskManifest.model_validate(data)


def test_duplicate_image_angle_is_rejected():
    data = _manifest_data()
    data["images"][1]["angle"] = 0
    with pytest.raises(ValidationError):
        TaskManifest.model_validate(data)


def test_missing_seven_jpg_is_rejected():
    data = _manifest_data()
    data["images"] = data["images"][:-1]
    with pytest.raises(ValidationError, match="exactly 8"):
        TaskManifest.model_validate(data)


@pytest.mark.parametrize("progress", [-1, 101])
def test_status_progress_range(progress):
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        StatusResponse(
            task_id="task-1",
            status=TaskStatus.WAITING,
            progress=progress,
            message="waiting",
            created_at=now,
            updated_at=now,
        )


def test_models_reject_undeclared_camera_fields():
    data = _manifest_data()
    data["camera_selection"] = "anything"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TaskManifest.model_validate(data)

    image = _images()[0].model_dump()
    image["camera_id"] = 1
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TaskImage.model_validate(image)


def test_task_image_requires_index_filename_and_angle_mapping():
    with pytest.raises(ValidationError, match="requires filename 0.jpg"):
        TaskImage(
            index=0,
            angle=0,
            filename="1.jpg",
            source_filename="source.jpg",
            sha256=HASH,
            size_bytes=1,
        )

