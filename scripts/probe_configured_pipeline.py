"""Probe the active camera profiles from multiwebcam.toml.

The script discovers current V4L2 devices, matches active profiles by bus_info,
then starts the project CaptureSession with each profile's own resolution/FPS.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from multiwebcam.pipeline.session import CaptureSession
from multiwebcam.profiles import ProfileRepository
from multiwebcam.sources.config import FrameSourceConfig
from multiwebcam.sources.device import FrameSource
from multiwebcam.sources.discovery import discover_frame_sources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--duration", type=float, default=5.0)
    args = parser.parse_args()

    repo = ProfileRepository(args.project)
    profiles = [profile for profile in repo.load_all() if not profile.ignore]
    if not profiles:
        print("No active profiles in multiwebcam.toml")
        return 1

    discovered = {options.bus_info: options for options in discover_frame_sources()}

    sources: list[FrameSource] = []
    labels: dict[str, str] = {}
    for profile in profiles:
        options = discovered.get(profile.bus_info)
        if options is None:
            print(f"MISSING source_id={profile.source_id} bus={profile.bus_info}")
            return 2

        config = FrameSourceConfig(
            resolution=profile.resolution,
            fps=profile.capture_fps,
            pixel_format=profile.pixel_format,
            capture_backend=profile.capture_backend,
            gstreamer_pipeline=profile.gstreamer_pipeline,
        )
        sources.append(FrameSource(options.path, config))
        labels[options.path] = (
            f"source_id={profile.source_id} bus={profile.bus_info} "
            f"config={profile.resolution[0]}x{profile.resolution[1]}@{profile.capture_fps} {profile.pixel_format}"
        )

    print("Configured active devices:")
    for source in sources:
        print(f"{source.device_path}: {labels[source.device_path]}")

    session = CaptureSession(
        sources,
        enable_monitoring=False,
        recording_buffer_seconds=2.0,
        alignment_window_seconds=1.0,
    )
    counts = {source.device_path: 0 for source in sources}
    first_frame = {source.device_path: None for source in sources}
    last_fps = {source.device_path: 0.0 for source in sources}

    started_at = time.perf_counter()
    try:
        try:
            session.start()
        except Exception as exc:
            print(f"START_FAILED={exc}")
            return 2

        deadline = time.perf_counter() + args.duration
        while time.perf_counter() < deadline:
            for path, packet in session.get_latest_frames().items():
                if packet is None:
                    continue
                counts[path] += 1
                last_fps[path] = packet.fps
                if first_frame[path] is None:
                    first_frame[path] = time.perf_counter() - started_at
            time.sleep(0.02)
    finally:
        session.stop()

    print("CaptureSession configured-profile results")
    for source in sources:
        path = source.device_path
        first = "none" if first_frame[path] is None else f"{first_frame[path]:.3f}s"
        print(f"{path}: frames_seen={counts[path]} first_frame={first} source_reported_fps={last_fps[path]:.1f}")

    failed = [path for path, count in counts.items() if count == 0]
    if failed:
        print(f"FAILED_NO_FRAMES={','.join(failed)}")
        return 2

    print("ALL_DEVICES_DELIVERED_FRAMES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
