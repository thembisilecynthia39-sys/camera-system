"""Configure this project to run three active USB cameras.

The script discovers V4L2 capture devices, writes multiwebcam.toml with the
first N cameras active, and marks any remaining discovered cameras ignored.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import rtoml

from multiwebcam.sources.discovery import discover_frame_sources


def build_source_entry(
    source_id: int,
    bus_info: str,
    label: str,
    ignore: bool,
    resolution: tuple[int, int],
    fps: int,
    pixel_format: str,
) -> dict:
    return {
        "source_id": source_id,
        "label": label,
        "bus_info": bus_info,
        "ignore": ignore,
        "pixel_format": pixel_format,
        "capture_fps": fps,
        "resolution": list(resolution),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-path", type=Path, default=Path.cwd())
    parser.add_argument("--active-count", type=int, default=3)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--pixel-format", default="mjpeg")
    args = parser.parse_args()

    if args.active_count < 1:
        raise SystemExit("--active-count must be at least 1")

    sources = discover_frame_sources()
    if len(sources) < args.active_count:
        raise SystemExit(f"Only discovered {len(sources)} capture device(s); need {args.active_count}")

    resolution = (args.width, args.height)
    entries = []
    for index, source in enumerate(sources):
        active = index < args.active_count
        entries.append(
            build_source_entry(
                source_id=index,
                bus_info=source.bus_info,
                label=f"camera_{index}",
                ignore=not active,
                resolution=resolution,
                fps=args.fps,
                pixel_format=args.pixel_format,
            )
        )

    output_path = args.project_path / "multiwebcam.toml"
    args.project_path.mkdir(parents=True, exist_ok=True)
    rtoml.dump({"sources": entries}, output_path)

    print(f"Wrote {output_path}")
    for source, entry in zip(sources, entries, strict=True):
        state = "active" if not entry["ignore"] else "ignored"
        print(
            f"{state}: source_id={entry['source_id']} path={source.path} "
            f"bus={entry['bus_info']} resolution={args.width}x{args.height}@{args.fps} {args.pixel_format}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
