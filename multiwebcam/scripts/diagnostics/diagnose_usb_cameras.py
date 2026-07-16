"""Create a USB camera diagnostic report.

The report captures USB topology, UVC driver parameters, discovered V4L2
capture devices, and concurrent capture results through the supported probes.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from multiwebcam.sources.discovery import discover_frame_sources


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CommandResult:
    title: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def run_command(title: str, command: list[str], timeout: float = 30.0) -> CommandResult:
    try:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return CommandResult(title, command, result.returncode, result.stdout, result.stderr)
    except FileNotFoundError as exc:
        return CommandResult(title, command, 127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandResult(title, command, 124, stdout, stderr + f"\nTimed out after {timeout:.1f}s")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return f"unavailable: {exc}"


def discover_device_paths(max_devices: int) -> list[str]:
    return [source.path for source in discover_frame_sources()[:max_devices]]


def render_command_result(result: CommandResult) -> str:
    command = " ".join(result.command)
    parts = [
        f"## {result.title}",
        f"$ {command}",
        f"exit_code={result.returncode}",
    ]
    if result.stdout.strip():
        parts.append(result.stdout.rstrip())
    if result.stderr.strip():
        parts.append("stderr:")
        parts.append(result.stderr.rstrip())
    return "\n".join(parts)


def render_discovery(max_devices: int) -> str:
    try:
        sources = discover_frame_sources()
    except Exception as exc:
        return f"## multiwebcam discovery\nERROR: {exc}"

    lines = ["## multiwebcam discovery", f"capture_devices={len(sources)}"]
    for source in sources[:max_devices]:
        mode_preview = ", ".join(str(mode) for mode in source.modes[:6])
        if len(source.modes) > 6:
            mode_preview += f", ... ({len(source.modes)} total)"
        lines.append(f"{source.path}: model={source.model!r} driver={source.driver!r} bus={source.bus_info!r}")
        lines.append(f"  modes={mode_preview}")
    return "\n".join(lines)


def render_uvc_parameters() -> str:
    parameter_dir = Path("/sys/module/uvcvideo/parameters")
    lines = ["## uvcvideo parameters"]
    for name in ("quirks", "nodrop", "timeout", "hwtimestamps", "clock"):
        value = read_text(parameter_dir / name)
        if name == "quirks" and value == "4294967295":
            value += " (driver default table, not FIX_BANDWIDTH)"
        lines.append(f"{name}={value}")
    return "\n".join(lines)


def build_probe_command(
    script: str, devices: list[str], width: int, height: int, fps: int, duration: float
) -> list[str]:
    command = [
        sys.executable,
        f"scripts/{script}",
        "--width",
        str(width),
        "--height",
        str(height),
        "--fps",
        str(fps),
        "--duration",
        str(duration),
    ]
    for device in devices:
        command.extend(["--device", device])
    return command


def build_report(args: argparse.Namespace) -> str:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    devices = args.devices or discover_device_paths(args.max_devices)

    sections = [
        "# USB Camera Diagnostic Report",
        f"timestamp={timestamp}",
        f"host={platform.node()}",
        f"platform={platform.platform()}",
        f"python={sys.version.split()[0]}",
        f"requested_config={args.width}x{args.height}@{args.fps} mjpeg duration={args.duration}s",
        f"devices={' '.join(devices) if devices else 'none'}",
        "",
        render_uvc_parameters(),
        "",
        render_command_result(run_command("USB topology", ["lsusb", "-t"], timeout=10.0)),
        "",
        render_command_result(run_command("V4L2 device list", ["v4l2-ctl", "--list-devices"], timeout=10.0)),
        "",
        render_discovery(args.max_devices),
    ]

    if not devices:
        sections.append("## capture probes\nNo devices discovered; skipping capture probes.")
        return "\n\n".join(sections)

    timeout = args.duration + 20.0
    probes = [
        (
            "OpenCV explicit MJPG probe",
            build_probe_command("probe_opencv_fourcc.py", devices, args.width, args.height, args.fps, args.duration)
            + ["--fourcc", "MJPG"],
        ),
        (
            "PyAV V4L2 MJPEG probe",
            build_probe_command(
                "probe_pyav_four_cameras.py", devices, args.width, args.height, args.fps, args.duration
            ),
        ),
        (
            "multiwebcam CaptureSession probe",
            build_probe_command(
                "probe_four_camera_pipeline.py", devices, args.width, args.height, args.fps, args.duration
            ),
        ),
    ]
    for title, command in probes:
        sections.append("")
        sections.append(render_command_result(run_command(title, command, timeout=timeout)))

    return "\n\n".join(sections)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", action="append", dest="devices")
    parser.add_argument("--max-devices", type=int, default=4)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = build_report(args)
    print(report)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
        print(f"\nWrote report: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
