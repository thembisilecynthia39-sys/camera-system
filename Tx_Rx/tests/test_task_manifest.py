import csv
import hashlib
import json
from pathlib import Path

import pytest

from tx_rx.jetson_client.task_manifest import (
    CaptureDataError,
    InvalidImageCountError,
    MissingCaptureFileError,
    TaskPackageError,
    build_configured_task_package,
    build_task_package,
    load_staged_task_package,
)
from tx_rx.protocol.models import TASK_ANGLES, TaskManifest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_capture(root: Path, angles=TASK_ANGLES, prefix="shot") -> Path:
    capture = root / "capture_001"
    images = capture / "images"
    images.mkdir(parents=True)
    rows = []
    for index, angle in enumerate(angles):
        source_name = f"{prefix}_{index:02d}.jpg"
        (images / source_name).write_bytes(f"jpeg-content-{prefix}-{index}-{angle}".encode())
        rows.append(
            {
                "frame_id": str(index + 1),
                "camera_id": "ignored-by-task-builder",
                "label": "source",
                "device_path": "/dev/null",
                "bus_info": "none",
                "image_name": source_name,
                "resolution": "640x480",
                "frame_index": str(index),
                "frame_time": f"{index}.0",
                "fps": "30.0",
                "angle_deg": str(angle),
                "readiness_percent": "90.0",
                "progress_percent": "100.0" if index == 7 else "50.0",
                "readiness_label": "READY",
            }
        )
    _write_metadata(capture / "metadata.csv", rows)
    (capture / "quality.csv").write_text("frame_id,angle_deg\n1,0\n", encoding="utf-8")
    (capture / "cameras.json").write_text('[{"label": "source"}]\n', encoding="utf-8")
    return capture


def _write_metadata(path: Path, rows) -> None:
    fieldnames = [
        "frame_id",
        "camera_id",
        "label",
        "device_path",
        "bus_info",
        "image_name",
        "resolution",
        "frame_index",
        "frame_time",
        "fps",
        "angle_deg",
        "readiness_percent",
        "progress_percent",
        "readiness_label",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_builds_complete_eight_image_task_package(tmp_path):
    capture = _create_capture(tmp_path / "input")
    original_files = {path.relative_to(capture): _sha256(path) for path in capture.rglob("*") if path.is_file()}

    result = build_task_package(capture, tmp_path / "staging")

    assert result.capture_id == "capture_001"
    assert result.image_count == 8
    assert result.staging_dir == tmp_path / "staging" / "capture_001"
    assert result.manifest_path.is_file()
    assert result.metadata_json_path.is_file()
    assert {path.name for path in result.images_dir.iterdir()} == {f"{index}.jpg" for index in range(8)}
    assert len(list(result.images_dir.glob("*.jpg"))) == 8

    for index, angle in enumerate(TASK_ANGLES):
        image = result.manifest.images[index]
        assert image.index == index
        assert image.angle == angle
        assert image.filename == f"{index}.jpg"
        assert image.source_filename == f"shot_{index:02d}.jpg"
        assert (result.images_dir / image.filename).read_bytes() == (
            capture / "images" / image.source_filename
        ).read_bytes()

    assert {path.relative_to(capture): _sha256(path) for path in capture.rglob("*") if path.is_file()} == original_files
    for filename in ("metadata.csv", "quality.csv", "cameras.json"):
        assert (result.staging_dir / filename).read_bytes() == (capture / filename).read_bytes()


def test_task_json_and_metadata_json_are_valid(tmp_path):
    capture = _create_capture(tmp_path / "input")
    result = build_task_package(capture, tmp_path / "staging")

    parsed = TaskManifest.model_validate_json(result.manifest_path.read_text(encoding="utf-8"))
    assert parsed == result.manifest
    metadata = json.loads(result.metadata_json_path.read_text(encoding="utf-8"))
    assert metadata["capture_id"] == "capture_001"
    assert metadata["image_count"] == 8
    assert metadata["angles"] == TASK_ANGLES
    assert [entry["filename"] for entry in metadata["images"]] == [f"{index}.jpg" for index in range(8)]


def test_all_manifest_file_hashes_are_correct(tmp_path):
    result = build_task_package(_create_capture(tmp_path / "input"), tmp_path / "staging")
    assert "task.json" not in {item.relative_path for item in result.manifest.files}
    for item in result.manifest.files:
        path = result.staging_dir / item.relative_path
        assert item.sha256 == _sha256(path)
        assert item.size_bytes == path.stat().st_size


def test_same_input_produces_same_task_checksum(tmp_path):
    capture = _create_capture(tmp_path / "input")
    first = build_task_package(capture, tmp_path / "staging-a")
    second = build_task_package(capture, tmp_path / "staging-b")
    assert first.checksum == second.checksum


def test_missing_one_photo_record_fails(tmp_path):
    capture = _create_capture(tmp_path / "input", angles=TASK_ANGLES[:-1])
    with pytest.raises(InvalidImageCountError, match="8 are required"):
        build_task_package(capture, tmp_path / "staging")


@pytest.mark.parametrize("filename", ["metadata.csv", "quality.csv", "cameras.json"])
def test_optional_capture_metadata_files_can_be_absent_for_eight_images(tmp_path, filename):
    capture = _create_capture(tmp_path / "input")
    (capture / filename).unlink()
    result = build_task_package(capture, tmp_path / "staging")
    assert result.image_count == 8


def test_exactly_eight_images_do_not_require_metadata_angles(tmp_path):
    angles = list(TASK_ANGLES)
    angles[-1] = angles[-2]
    capture = _create_capture(tmp_path / "input", angles=angles)
    result = build_task_package(capture, tmp_path / "staging")
    assert [image.angle for image in result.manifest.images] == TASK_ANGLES


def test_arbitrary_eight_jpgs_are_stably_mapped_without_angle_records(tmp_path):
    capture = _create_capture(tmp_path / "input")
    images_dir = capture / "images"
    for path in list(images_dir.iterdir()):
        path.unlink()
    names = ["zebra.jpg", "apple.jpg", "p8.jpg", "hello.jpg", "x.jpg", "03.jpg", "view.jpg", "mid.jpg"]
    for name in names:
        (images_dir / name).write_bytes(f"content-{name}".encode())
    (capture / "metadata.csv").write_text("frame_id,angle_deg,image_name\n", encoding="utf-8")

    result = build_task_package(capture, tmp_path / "staging")

    assert [image.source_filename for image in result.manifest.images] == sorted(names)
    assert [image.index for image in result.manifest.images] == list(range(8))
    assert [image.angle for image in result.manifest.images] == TASK_ANGLES


def test_user_can_select_eight_images_from_larger_pool_in_given_order(tmp_path):
    capture = _create_capture(tmp_path / "input")
    images_dir = capture / "images"
    for index in range(12):
        (images_dir / f"pool_{index:02d}.jpg").write_bytes(f"pool-{index}".encode())
    selected = ["pool_07.jpg", "shot_03.jpg", "pool_01.jpg", "shot_00.jpg",
                "pool_11.jpg", "shot_06.jpg", "pool_04.jpg", "shot_02.jpg"]

    result = build_task_package(capture, tmp_path / "staging", selected)

    assert [image.source_filename for image in result.manifest.images] == selected
    assert [image.index for image in result.manifest.images] == list(range(8))
    assert [image.angle for image in result.manifest.images] == TASK_ANGLES


def test_selected_images_must_be_exactly_eight_unique_jpg_names(tmp_path):
    capture = _create_capture(tmp_path / "input")
    with pytest.raises(InvalidImageCountError, match="exactly 8 selected"):
        build_task_package(capture, tmp_path / "staging", ["shot_00.jpg"])
    with pytest.raises(CaptureDataError, match="must be unique"):
        build_task_package(capture, tmp_path / "staging", ["shot_00.jpg"] * 8)


def test_eight_jpgs_directly_in_capture_directory_need_no_metadata(tmp_path):
    capture = tmp_path / "book"
    capture.mkdir()
    for index in range(8):
        (capture / f"book_{index}.jpg").write_bytes(f"book-{index}".encode())

    result = build_task_package(capture, tmp_path / "staging")

    assert result.capture_id == "book"
    assert [image.source_filename for image in result.manifest.images] == [
        f"book_{index}.jpg" for index in range(8)
    ]
    assert [image.angle for image in result.manifest.images] == TASK_ANGLES


def test_eight_jpeg_inputs_are_normalized_to_jpg_protocol_names(tmp_path):
    capture = tmp_path / "book"
    capture.mkdir()
    for index in range(8):
        (capture / f"source_{index}.jpeg").write_bytes(f"jpeg-{index}".encode())

    result = build_task_package(capture, tmp_path / "staging")

    assert [image.source_filename for image in result.manifest.images] == [
        f"source_{index}.jpeg" for index in range(8)
    ]
    assert [image.filename for image in result.manifest.images] == [f"{index}.jpg" for index in range(8)]


def test_source_image_missing_fails_with_path(tmp_path):
    capture = _create_capture(tmp_path / "input")
    missing = capture / "images" / "shot_07.jpg"
    missing.unlink()
    with pytest.raises(MissingCaptureFileError, match="shot_07.jpg"):
        build_task_package(capture, tmp_path / "staging")


def test_uses_metadata_mapping_not_sorted_first_eight_images(tmp_path):
    capture = _create_capture(tmp_path / "input")
    images_dir = capture / "images"
    for index in range(12):
        (images_dir / f"000-decoy-{index}.jpg").write_bytes(b"decoy")

    result = build_task_package(capture, tmp_path / "staging")
    assert all(image.source_filename.startswith("shot_") for image in result.manifest.images)
    assert all((result.images_dir / f"{index}.jpg").read_bytes() != b"decoy" for index in range(8))


def test_latest_complete_metadata_round_is_used_and_staging_stays_at_eight(tmp_path):
    capture = _create_capture(tmp_path / "input", prefix="old")
    metadata_path = capture / "metadata.csv"
    with metadata_path.open("r", newline="", encoding="utf-8") as stream:
        old_rows = list(csv.DictReader(stream))
    new_rows = []
    for index, angle in enumerate(TASK_ANGLES):
        source_name = f"new_{index:02d}.jpg"
        (capture / "images" / source_name).write_bytes(f"new-{index}".encode())
        row = dict(old_rows[index])
        row.update(frame_id=str(index + 9), image_name=source_name, angle_deg=str(angle))
        new_rows.append(row)
    _write_metadata(metadata_path, old_rows + new_rows)

    result = build_task_package(capture, tmp_path / "staging")
    assert len(list(result.images_dir.glob("*.jpg"))) == 8
    assert [image.source_filename for image in result.manifest.images] == [f"new_{index:02d}.jpg" for index in range(8)]


def test_existing_incomplete_staging_directory_fails(tmp_path):
    capture = _create_capture(tmp_path / "input")
    incomplete = tmp_path / "staging" / "capture_001"
    incomplete.mkdir(parents=True)
    with pytest.raises(CaptureDataError, match="already exists but is incomplete"):
        build_task_package(capture, tmp_path / "staging")


def test_configured_builder_uses_only_configured_staging_root(tmp_path):
    capture = _create_capture(tmp_path / "input")
    configured_root = tmp_path / "visible-staging"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f'schema_version: "1.0"\nstaging_root: {configured_root}\n',
        encoding="utf-8",
    )

    result = build_configured_task_package(capture, config_path)

    assert result.staging_dir == configured_root / "capture_001"
    assert result.staging_dir.is_dir()


def test_staged_package_can_be_revalidated_for_future_upload(tmp_path):
    result = build_task_package(_create_capture(tmp_path / "input"), tmp_path / "staging")

    loaded = load_staged_task_package(result.staging_dir)

    assert loaded.staging_dir == result.staging_dir
    assert loaded.checksum == result.checksum


def test_cancelled_package_removes_temporary_staging_directory(tmp_path):
    capture = _create_capture(tmp_path / "input")
    staging_root = tmp_path / "staging"

    def cancel_after_temporary_directory_exists():
        return bool(list(staging_root.glob(".capture_001-*")))

    with pytest.raises(TaskPackageError, match="task packaging cancelled"):
        build_task_package(
            capture,
            staging_root,
            cancel_check=cancel_after_temporary_directory_exists,
        )

    assert not (staging_root / "capture_001").exists()
    assert list(staging_root.glob(".capture_001-*")) == []
