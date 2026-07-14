"""Probe concurrent V4L2 capture with PyAV.

This isolates the PyAV/FFmpeg V4L2 backend from the current OpenCV
FrameSource implementation.
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import time
from dataclasses import dataclass

import av

from multiwebcam.sources.discovery import discover_frame_sources


def discover_devices(max_devices: int) -> list[str]:
    return [source.path for source in discover_frame_sources()[:max_devices]]


@dataclass
class PyAVResult:
    device: str
    frames: int
    first_frame_seconds: float | None
    fps: float
    error: str | None = None


def capture_worker(
    device: str,
    width: int,
    height: int,
    fps: int,
    pixel_format: str,
    duration: float,
    queue: mp.Queue,
) -> None:
    started_at = time.perf_counter()
    frames = 0
    first_frame_seconds: float | None = None
    container = None
    try:
        options = {
            "input_format": pixel_format,
            "video_size": f"{width}x{height}",
            "framerate": str(fps),
            "use_wallclock_as_timestamps": "1",
            "fflags": "nobuffer",
            "flags": "low_delay",
            "probesize": "32",
            "analyzeduration": "0",
            "rtbufsize": "512k",
        }
        container = av.open(device, format="v4l2", options=options)
        deadline = time.perf_counter() + duration
        for _frame in container.decode(video=0):
            now = time.perf_counter()
            if first_frame_seconds is None:
                first_frame_seconds = now - started_at
            frames += 1
            if now >= deadline:
                break
        elapsed = max(time.perf_counter() - started_at, 0.001)
        queue.put(PyAVResult(device, frames, first_frame_seconds, frames / elapsed, None))
    except Exception as exc:
        elapsed = max(time.perf_counter() - started_at, 0.001)
        queue.put(PyAVResult(device, frames, first_frame_seconds, frames / elapsed, repr(exc)))
    finally:
        if container is not None:
            container.close()


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
    print(f"devices={' '.join(devices)}")
    queue: mp.Queue = mp.Queue()
    processes = [
        mp.Process(
            target=capture_worker,
            args=(
                device,
                args.width,
                args.height,
                args.fps,
                args.pixel_format,
                args.duration,
                queue,
            ),
        )
        for device in devices
    ]

    for process in processes:
        process.start()

    deadline = time.perf_counter() + args.duration + 8.0
    for process in processes:
        remaining = max(deadline - time.perf_counter(), 0.1)
        process.join(remaining)

    timed_out = []
    for device, process in zip(devices, processes, strict=True):
        if process.is_alive():
            timed_out.append(device)
            process.terminate()
            process.join(2.0)

    results: dict[str, PyAVResult] = {}
    while not queue.empty():
        result = queue.get()
        results[result.device] = result

    print("PyAV concurrent capture results")
    print(f"config={args.width}x{args.height}@{args.fps} {args.pixel_format}")
    for device in devices:
        result = results.get(device)
        if result is None:
            print(f"{device}: frames=0 first_frame=none fps=0.0 error=timeout")
            continue
        first = "none" if result.first_frame_seconds is None else f"{result.first_frame_seconds:.3f}s"
        error = "" if result.error is None else f" error={result.error}"
        print(f"{device}: frames={result.frames} first_frame={first} fps={result.fps:.1f}{error}")

    failed = [
        device for device in devices if device in timed_out or device not in results or results[device].frames == 0
    ]
    if failed:
        print(f"FAILED_NO_FRAMES_OR_TIMEOUT={','.join(failed)}")
        return 2

    print("ALL_DEVICES_DELIVERED_FRAMES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
