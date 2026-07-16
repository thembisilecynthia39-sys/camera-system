"""Probe four-camera capture through the multiwebcam pipeline.

This is a hardware diagnostic script. It starts the project's FrameSource and
CaptureSession path and prints per-device frame counts over a short window.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass

from multiwebcam.pipeline.session import CaptureSession
from multiwebcam.sources.config import FrameSourceConfig
from multiwebcam.sources.device import FrameSource
from multiwebcam.sources.discovery import discover_frame_sources


def discover_devices(max_devices: int) -> list[str]:
    return [source.path for source in discover_frame_sources()[:max_devices]]


def device_args(devices: list[str]) -> str:
    return " ".join(devices)


@dataclass
class DeviceResult:
    frames: int = 0
    first_frame_seconds: float | None = None
    last_fps: float = 0.0


def run_session(devices: list[str], config: FrameSourceConfig, duration: float) -> int:
    sources = [FrameSource(path, config) for path in devices]
    session = CaptureSession(
        sources,
        enable_monitoring=False,
        recording_buffer_seconds=2.0,
        alignment_window_seconds=1.0,
    )
    results = {path: DeviceResult() for path in devices}

    started_at = time.perf_counter()
    try:
        try:
            session.start()
        except Exception as exc:
            print("CaptureSession results")
            print(f"config={config.resolution[0]}x{config.resolution[1]}@{config.fps} {config.pixel_format}")
            print(f"START_FAILED={exc}")
            return 2

        deadline = time.perf_counter() + duration
        while time.perf_counter() < deadline:
            for path, packet in session.get_latest_frames().items():
                if packet is None:
                    continue
                result = results[path]
                result.frames += 1
                result.last_fps = packet.fps
                if result.first_frame_seconds is None:
                    result.first_frame_seconds = time.perf_counter() - started_at
            time.sleep(0.02)
    finally:
        session.stop()

    print("CaptureSession results")
    print(f"config={config.resolution[0]}x{config.resolution[1]}@{config.fps} {config.pixel_format}")
    for path in devices:
        result = results[path]
        first = "none" if result.first_frame_seconds is None else f"{result.first_frame_seconds:.3f}s"
        print(f"{path}: frames_seen={result.frames} first_frame={first} source_reported_fps={result.last_fps:.1f}")

    failed = [path for path, result in results.items() if result.frames == 0]
    if failed:
        print(f"FAILED_NO_FRAMES={','.join(failed)}")
        return 2

    print("ALL_DEVICES_DELIVERED_FRAMES")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", action="append", dest="devices")
    parser.add_argument("--max-devices", type=int, default=4)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--pixel-format", default="mjpeg")
    parser.add_argument("--duration", type=float, default=8.0)
    args = parser.parse_args()

    devices = args.devices or discover_devices(args.max_devices)
    if not devices:
        print("No capture devices discovered")
        return 1
    print(f"devices={device_args(devices)}")
    config = FrameSourceConfig(
        resolution=(args.width, args.height),
        fps=args.fps,
        pixel_format=args.pixel_format,
    )
    return run_session(devices, config, args.duration)


if __name__ == "__main__":
    raise SystemExit(main())
