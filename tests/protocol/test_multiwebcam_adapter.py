import csv
from pathlib import Path

import pytest

from camera_system.adapters import MultiWebcamCaptureAdapter, ServiceError
from camera_system.domain import TASK_ANGLES, TaskState


def _create_multicamera_capture(root: Path, cameras=("1", "2")) -> Path:
    capture = root / "capture_001"
    images = capture / "images"
    images.mkdir(parents=True)
    rows = []
    for angle_index, angle in enumerate(TASK_ANGLES):
        for camera_id in cameras:
            name = f"frame_{camera_id}_{angle_index:02d}.jpg"
            (images / name).write_bytes(f"camera={camera_id},angle={angle}".encode())
            rows.append(
                {
                    "frame_id": str(angle_index + 1),
                    "camera_id": camera_id,
                    "label": f"camera-{camera_id}",
                    "device_path": f"/dev/video{camera_id}",
                    "bus_info": f"usb-{camera_id}",
                    "image_name": name,
                    "angle_deg": str(angle),
                }
            )
    with (capture / "metadata.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return capture


def test_adapter_reports_multi_camera_eight_angle_progress(tmp_path):
    capture = _create_multicamera_capture(tmp_path)
    adapter = MultiWebcamCaptureAdapter()

    session = adapter.inspect_capture(capture)
    progress = adapter.get_progress(capture)

    assert session.camera_ids == ("1", "2")
    assert session.captured_angles == TASK_ANGLES
    assert session.state is TaskState.READY
    assert progress.progress_percent == 100
    assert progress.camera_count == 2


def test_adapter_selects_one_complete_camera_and_delegates_packaging(tmp_path):
    capture = _create_multicamera_capture(tmp_path)
    adapter = MultiWebcamCaptureAdapter()

    task = adapter.prepare_task(capture, staging_root=tmp_path / "staging")

    assert task.source_camera_id == "1"
    assert task.manifest.image_count == 8
    assert [image.angle_deg for image in task.manifest.images] == list(TASK_ANGLES)
    assert [image.source_filename for image in task.manifest.images] == [
        f"frame_1_{index:02d}.jpg" for index in range(8)
    ]
    assert {item.relative_path for item in task.manifest.files} >= {"metadata.csv", "metadata.json"}
    assert task.staging_dir.is_dir()


def test_adapter_allows_explicit_camera_selection(tmp_path):
    capture = _create_multicamera_capture(tmp_path)

    task = MultiWebcamCaptureAdapter().prepare_task(
        capture,
        staging_root=tmp_path / "staging",
        camera_id="2",
    )

    assert task.source_camera_id == "2"
    assert task.manifest.images[0].source_filename == "frame_2_00.jpg"


def test_adapter_rejects_a_capture_without_complete_camera_angles(tmp_path):
    capture = _create_multicamera_capture(tmp_path, cameras=("1",))
    metadata = capture / "metadata.csv"
    lines = metadata.read_text(encoding="utf-8").splitlines()
    metadata.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

    with pytest.raises(ServiceError) as raised:
        MultiWebcamCaptureAdapter().prepare_task(capture, staging_root=tmp_path / "staging")

    assert raised.value.error.code == "camera_angle_mismatch"
