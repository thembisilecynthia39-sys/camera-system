import csv
import json

import numpy as np

from multiwebcam.quality.metrics import evaluate_capture_set
from multiwebcam.snapshot import SnapshotCameraInfo, save_snapshot_set
from multiwebcam.sources.frame_packet import FramePacket


def make_packet(path: str, frame_index: int, frame_time: float) -> FramePacket:
    rng = np.random.default_rng(frame_index)
    frame = rng.integers(40, 215, size=(80, 100, 3), dtype=np.uint8)
    return FramePacket(
        device_path=path,
        device_id=frame_index,
        frame_index=frame_index,
        frame_time=frame_time,
        timestamp_source="wall_clock",
        frame=frame,
        fps=30.0,
    )


def test_save_snapshot_set_writes_images_and_metadata(tmp_path):
    packets = {
        "/dev/video0": make_packet("/dev/video0", 0, 1.0),
        "/dev/video2": make_packet("/dev/video2", 1, 1.02),
    }
    camera_info = {
        "/dev/video0": SnapshotCameraInfo(0, "cam0", "usb-a", "/dev/video0", (1280, 720), 30, "mjpeg"),
        "/dev/video2": SnapshotCameraInfo(2, "cam2", "usb-b", "/dev/video2", (640, 480), 30, "mjpeg"),
    }
    quality = evaluate_capture_set(packets)

    result = save_snapshot_set(
        tmp_path / "captures",
        packets,
        camera_info,
        quality,
        angle_deg=45,
        readiness_percent=82.0,
        progress_percent=38.0,
        readiness_label="READY",
    )

    assert result.frame_id == 1
    assert result.output_dir.name == "capture_001"
    assert result.image_paths[0].exists()
    assert result.image_paths[2].exists()

    metadata_rows = list(csv.DictReader((result.output_dir / "metadata.csv").open()))
    assert {row["camera_id"] for row in metadata_rows} == {"0", "2"}
    assert metadata_rows[0]["image_name"].startswith("frame_000001_cam_")
    assert metadata_rows[0]["angle_deg"] == "45"
    assert metadata_rows[0]["readiness_label"] == "READY"

    quality_rows = list(csv.DictReader((result.output_dir / "quality.csv").open()))
    assert len(quality_rows) == 2
    assert "timestamp_spread_ms" in quality_rows[0]
    assert quality_rows[0]["capture_readiness_percent"] == "82.00"

    cameras = json.loads((result.output_dir / "cameras.json").read_text())
    assert [camera["camera_id"] for camera in cameras] == [0, 2]


def test_save_snapshot_set_increments_frame_id(tmp_path):
    packets = {"/dev/video0": make_packet("/dev/video0", 0, 1.0)}
    camera_info = {
        "/dev/video0": SnapshotCameraInfo(0, "cam0", "usb-a", "/dev/video0", (1280, 720), 30, "mjpeg")
    }
    quality = evaluate_capture_set(packets)

    first = save_snapshot_set(tmp_path / "captures", packets, camera_info, quality)
    second = save_snapshot_set(tmp_path / "captures", packets, camera_info, quality)

    assert first.frame_id == 1
    assert second.frame_id == 2
    assert (second.output_dir / "images" / "frame_000002_cam_0.jpg").exists()
