from __future__ import annotations
"""Still-image capture helpers for COLMAP/3DGS datasets."""


import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

import cv2

from multiwebcam.quality.metrics import CaptureSetQuality
from multiwebcam.sources.frame_packet import FramePacket


@dataclass(frozen=True)
class SnapshotCameraInfo:
    source_id: int
    label: str
    bus_info: str
    device_path: str
    resolution: tuple[int, int]
    fps: int
    pixel_format: str


@dataclass(frozen=True)
class SnapshotResult:
    frame_id: int
    output_dir: Path
    image_paths: dict[int, Path]
    ok_to_capture: bool


def save_snapshot_set(
    output_root: Path,
    packets: dict[str, FramePacket],
    camera_info: dict[str, SnapshotCameraInfo],
    quality: CaptureSetQuality,
    ok_to_capture: bool | None = None,
    angle_deg: int | None = None,
    readiness_percent: float | None = None,
    progress_percent: float | None = None,
    readiness_label: str | None = None,
) -> SnapshotResult:
    """Save one synchronized still-image set."""
    output_dir = output_root / "capture_001"
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    frame_id = _next_frame_id(images_dir)
    image_paths: dict[int, Path] = {}

    for device_path, packet in sorted(packets.items(), key=lambda item: camera_info[item[0]].source_id):
        info = camera_info[device_path]
        image_path = images_dir / f"frame_{frame_id:06d}_cam_{info.source_id}.jpg"
        if not cv2.imwrite(str(image_path), packet.frame):
            raise OSError(f"Failed to write image: {image_path}")
        image_paths[info.source_id] = image_path

    _append_metadata(
        output_dir / "metadata.csv",
        frame_id,
        packets,
        camera_info,
        angle_deg=angle_deg,
        readiness_percent=readiness_percent,
        progress_percent=progress_percent,
        readiness_label=readiness_label,
    )
    _append_quality(
        output_dir / "quality.csv",
        frame_id,
        quality,
        camera_info,
        angle_deg=angle_deg,
        readiness_percent=readiness_percent,
        progress_percent=progress_percent,
    )
    _write_cameras_json(output_dir / "cameras.json", camera_info)

    return SnapshotResult(
        frame_id=frame_id,
        output_dir=output_dir,
        image_paths=image_paths,
        ok_to_capture=quality.ok_to_capture if ok_to_capture is None else ok_to_capture,
    )


def _next_frame_id(images_dir: Path) -> int:
    pattern = re.compile(r"^frame_(\d+)_cam_\d+\.jpg$")
    highest = 0
    for path in images_dir.glob("frame_*_cam_*.jpg"):
        match = pattern.match(path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def _append_metadata(
    path: Path,
    frame_id: int,
    packets: dict[str, FramePacket],
    camera_info: dict[str, SnapshotCameraInfo],
    *,
    angle_deg: int | None,
    readiness_percent: float | None,
    progress_percent: float | None,
    readiness_label: str | None,
) -> None:
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
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
            ],
        )
        if is_new:
            writer.writeheader()
        for device_path, packet in sorted(packets.items(), key=lambda item: camera_info[item[0]].source_id):
            info = camera_info[device_path]
            writer.writerow(
                {
                    "frame_id": frame_id,
                    "camera_id": info.source_id,
                    "label": info.label,
                    "device_path": device_path,
                    "bus_info": info.bus_info,
                    "image_name": f"frame_{frame_id:06d}_cam_{info.source_id}.jpg",
                    "resolution": f"{info.resolution[0]}x{info.resolution[1]}",
                    "frame_index": packet.frame_index,
                    "frame_time": f"{packet.frame_time:.6f}",
                    "fps": f"{packet.fps:.2f}",
                    "angle_deg": "" if angle_deg is None else angle_deg,
                    "readiness_percent": "" if readiness_percent is None else f"{readiness_percent:.2f}",
                    "progress_percent": "" if progress_percent is None else f"{progress_percent:.2f}",
                    "readiness_label": "" if readiness_label is None else readiness_label,
                }
            )


def _append_quality(
    path: Path,
    frame_id: int,
    quality: CaptureSetQuality,
    camera_info: dict[str, SnapshotCameraInfo],
    *,
    angle_deg: int | None,
    readiness_percent: float | None,
    progress_percent: float | None,
) -> None:
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "frame_id",
                "camera_id",
                "level",
                "sharpness",
                "brightness",
                "underexposed_pct",
                "overexposed_pct",
                "feature_count",
                "timestamp_spread_ms",
                "capture_readiness_percent",
                "capture_progress_percent",
                "angle_deg",
                "reasons",
            ],
        )
        if is_new:
            writer.writeheader()
        for device_path, frame_quality in sorted(
            quality.frame_qualities.items(),
            key=lambda item: camera_info[item[0]].source_id,
        ):
            info = camera_info[device_path]
            writer.writerow(
                {
                    "frame_id": frame_id,
                    "camera_id": info.source_id,
                    "level": frame_quality.level.value,
                    "sharpness": f"{frame_quality.sharpness:.3f}",
                    "brightness": f"{frame_quality.brightness:.3f}",
                    "underexposed_pct": f"{frame_quality.underexposed_pct:.3f}",
                    "overexposed_pct": f"{frame_quality.overexposed_pct:.3f}",
                    "feature_count": frame_quality.feature_count,
                    "timestamp_spread_ms": f"{quality.timestamp_spread_ms:.3f}",
                    "capture_readiness_percent": (
                        "" if readiness_percent is None else f"{readiness_percent:.2f}"
                    ),
                    "capture_progress_percent": "" if progress_percent is None else f"{progress_percent:.2f}",
                    "angle_deg": "" if angle_deg is None else angle_deg,
                    "reasons": ";".join((*quality.reasons, *frame_quality.reasons)),
                }
            )


def _write_cameras_json(path: Path, camera_info: dict[str, SnapshotCameraInfo]) -> None:
    payload = [
        {
            "camera_id": info.source_id,
            "label": info.label,
            "bus_info": info.bus_info,
            "device_path": info.device_path,
            "resolution": list(info.resolution),
            "fps": info.fps,
            "pixel_format": info.pixel_format,
        }
        for info in sorted(camera_info.values(), key=lambda item: item.source_id)
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
