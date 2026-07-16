"""Probe concurrent OpenCV capture with an explicit FOURCC."""

from __future__ import annotations

import argparse
import threading
import time
from dataclasses import dataclass

import cv2

from multiwebcam.sources.discovery import discover_frame_sources


def discover_devices(max_devices: int) -> list[str]:
    return [source.path for source in discover_frame_sources()[:max_devices]]


@dataclass
class OpenCVResult:
    frames: int = 0
    first_frame_seconds: float | None = None
    opened: bool = False
    actual_fourcc: str = ""
    actual_width: float = 0.0
    actual_height: float = 0.0
    actual_fps: float = 0.0
    error: str | None = None


def device_index(path: str) -> int:
    return int(path.rsplit("video", 1)[1])


def fourcc_string(value: float) -> str:
    code = int(value)
    chars = [chr((code >> 8 * i) & 0xFF) for i in range(4)]
    return "".join(chars)


def capture_worker(
    path: str,
    width: int,
    height: int,
    fps: int,
    fourcc: str,
    duration: float,
    results: dict[str, OpenCVResult],
) -> None:
    result = OpenCVResult()
    started_at = time.perf_counter()
    cap = None
    try:
        cap = cv2.VideoCapture(device_index(path), cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)

        result.opened = cap.isOpened()
        result.actual_fourcc = fourcc_string(cap.get(cv2.CAP_PROP_FOURCC))
        result.actual_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        result.actual_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        result.actual_fps = cap.get(cv2.CAP_PROP_FPS)

        deadline = time.perf_counter() + duration
        while time.perf_counter() < deadline:
            ok, _frame = cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            if result.first_frame_seconds is None:
                result.first_frame_seconds = time.perf_counter() - started_at
            result.frames += 1
    except Exception as exc:
        result.error = repr(exc)
    finally:
        if cap is not None:
            cap.release()
        results[path] = result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", action="append", dest="devices")
    parser.add_argument("--max-devices", type=int, default=4)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--fourcc", default="MJPG")
    parser.add_argument("--duration", type=float, default=8.0)
    args = parser.parse_args()

    devices = args.devices or discover_devices(args.max_devices)
    if not devices:
        print("No capture devices discovered")
        return 1
    print(f"devices={' '.join(devices)}")
    results: dict[str, OpenCVResult] = {}
    threads = [
        threading.Thread(
            target=capture_worker,
            args=(path, args.width, args.height, args.fps, args.fourcc, args.duration, results),
        )
        for path in devices
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(args.duration + 8.0)

    print("OpenCV explicit FOURCC concurrent capture results")
    print(f"config={args.width}x{args.height}@{args.fps} {args.fourcc}")
    for path in devices:
        result = results.get(path, OpenCVResult(error="timeout"))
        first = "none" if result.first_frame_seconds is None else f"{result.first_frame_seconds:.3f}s"
        print(
            f"{path}: opened={result.opened} frames={result.frames} first_frame={first} "
            f"actual={result.actual_width:.0f}x{result.actual_height:.0f}@{result.actual_fps:.1f} "
            f"fourcc={result.actual_fourcc!r} error={result.error}"
        )

    failed = [path for path in devices if results.get(path, OpenCVResult()).frames == 0]
    if failed:
        print(f"FAILED_NO_FRAMES={','.join(failed)}")
        return 2
    print("ALL_DEVICES_DELIVERED_FRAMES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
