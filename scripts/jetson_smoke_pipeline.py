"""End-to-end Jetson smoke test for capture, inference, and recording."""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

from multiwebcam.pipeline.session import CaptureSession
from multiwebcam.profiles import ProfileRepository
from multiwebcam.recognition import create_detector
from multiwebcam.sources.config import FrameSourceConfig
from multiwebcam.sources.device import FrameSource
from multiwebcam.sources.discovery import discover_frame_sources


def _build_sources(project: Path) -> tuple[list[FrameSource], dict[str, int]]:
    repo = ProfileRepository(project)
    profiles = [profile for profile in repo.load_all() if not profile.ignore]
    discovered = {options.bus_info: options for options in discover_frame_sources()}
    sources: list[FrameSource] = []
    cam_ids: dict[str, int] = {}

    for profile in profiles:
        options = discovered.get(profile.bus_info)
        if options is None:
            raise RuntimeError(f"Active profile missing from discovery: {profile.bus_info}")
        config = FrameSourceConfig(
            resolution=profile.resolution,
            fps=profile.capture_fps,
            pixel_format=profile.pixel_format,
            capture_backend=profile.capture_backend,
            gstreamer_pipeline=profile.gstreamer_pipeline,
        )
        source = FrameSource(options.path, config)
        sources.append(source)
        cam_ids[options.path] = profile.source_id

    if not sources:
        raise RuntimeError("No active sources in multiwebcam.toml")
    return sources, cam_ids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--warmup-seconds", type=float, default=3.0)
    parser.add_argument("--record-seconds", type=float, default=3.0)
    parser.add_argument("--run-inference", action="store_true")
    args = parser.parse_args()

    repo = ProfileRepository(args.project)
    settings = repo.load_settings()
    sources, cam_ids = _build_sources(args.project)
    detector = None
    if args.run_inference:
        detector = create_detector(settings.inference)

    session = CaptureSession(
        sources,
        enable_monitoring=False,
        recording_buffer_seconds=5.0,
        alignment_window_seconds=1.0,
        recording_settings=settings.recording,
    )

    try:
        session.start()
        deadline = time.monotonic() + args.warmup_seconds
        latest_packets = {}
        while time.monotonic() < deadline:
            for path, packet in session.get_latest_frames().items():
                if packet is not None:
                    latest_packets[path] = packet
            time.sleep(0.02)

        if set(latest_packets) != set(cam_ids):
            missing = sorted(set(cam_ids) - set(latest_packets))
            raise RuntimeError(f"Missing frames from: {missing}")

        print("[capture] OK")
        for path, packet in latest_packets.items():
            print(f"  {path}: frame_index={packet.frame_index} fps={packet.fps:.1f}")

        if detector is not None:
            print(f"[inference] backend={detector.backend_name}")
            for path, packet in latest_packets.items():
                result = detector.detect(packet.frame, packet.frame_index)
                region = result.object_region
                if region is None:
                    region_text = "none"
                else:
                    region_text = (
                        f"x={region.x} y={region.y} w={region.width} h={region.height} "
                        f"conf={region.confidence:.2f}"
                    )
                print(f"  {path}: latency_ms={result.latency_ms:.1f} region={region_text}")

        output_dir = Path(tempfile.mkdtemp(prefix="mwc_jetson_smoke_"))
        session.start_recording(output_dir, cam_ids=cam_ids)
        time.sleep(args.record_seconds)
        recording = session.stop_recording()
        if recording is None:
            raise RuntimeError("Recording stop returned no result")

        print(f"[recording] output={output_dir}")
        for cam_id, frames_written in sorted(recording.frames_per_camera.items()):
            path = output_dir / f"cam_{cam_id}.mp4"
            print(f"  cam_{cam_id}: frames={frames_written} exists={path.exists()}")
            if frames_written <= 0 or not path.exists():
                raise RuntimeError(f"Recording failed for cam_{cam_id}")
        print(f"  timestamps={recording.timestamps_path.exists()}")
        if not recording.timestamps_path.exists():
            raise RuntimeError("timestamps.csv missing")
    finally:
        session.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
