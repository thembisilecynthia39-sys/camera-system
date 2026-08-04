"""V4L2 device discovery and capability query."""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from multiwebcam.sources.config import FrameSourceConfig

logger = logging.getLogger(__name__)

# V4L2 fourcc codes to FFmpeg format names
_V4L2_TO_FFMPEG: dict[str, str] = {
    "MJPG": "mjpeg",
    "YUYV": "yuyv422",
    "NV12": "nv12",
    "H264": "h264",
}

_FFMPEG_TO_V4L2: dict[str, str] = {v: k for k, v in _V4L2_TO_FFMPEG.items()}
CancelCheck = Callable[[], bool]


def usb_root_bus(bus_info: str) -> str:
    """Return the USB root-controller path used for bandwidth planning.

    V4L2 exposes the physical USB route in ``bus_info``.  Port segments are
    appended after the root port (for example, ``usb-...xhci-2.1.1.4``), so
    removing those segments gives the controller shared by the cameras.  The
    fallback keeps non-USB and synthetic test identifiers stable.
    """
    match = re.match(r"^(.*-\d+)(?:\.\d+)*$", bus_info)
    return match.group(1) if match else bus_info


def _normalize_format(fmt: str) -> str:
    """Normalize pixel format to lowercase FFmpeg name."""
    upper = fmt.upper()
    if upper in _V4L2_TO_FFMPEG:
        return _V4L2_TO_FFMPEG[upper]
    return fmt.lower()


@dataclass(frozen=True)
class VideoMode:
    """A specific capture mode: format + resolution + framerate."""

    pixel_format: str  # e.g., "MJPG", "YUYV"
    width: int
    height: int
    fps: float

    def __str__(self) -> str:
        return f"{self.pixel_format} {self.width}x{self.height}@{self.fps:.0f}fps"


@dataclass(frozen=True)
class FrameSourceOptions:
    """Available options for a V4L2 capture device.

    Queried via v4l2-ctl before opening the device. Use this to:
    - Check what modes a device supports
    - Validate a config before creating a FrameSource
    - Get a suggested config for immediate preview
    """

    path: str  # e.g., "/dev/video0"
    model: str  # e.g., "HD Pro Webcam C920" (hardware name from V4L2)
    driver: str  # e.g., "uvcvideo"
    bus_info: str  # e.g., "usb-0000:00:14.0-2"
    modes: tuple[VideoMode, ...]

    def supports(self, config: FrameSourceConfig) -> bool:
        """Check if this device supports the given configuration."""
        w, h = config.resolution
        config_fmt = _normalize_format(config.pixel_format)
        # Allow small fps tolerance (some cameras report 29.97 vs 30)
        return any(
            _normalize_format(mode.pixel_format) == config_fmt
            and mode.width == w
            and mode.height == h
            and abs(mode.fps - config.fps) < 1.0
            for mode in self.modes
        )

    @property
    def root_bus(self) -> str:
        """USB root controller shared by this camera."""
        return usb_root_bus(self.bus_info)

    def suggested_config(self) -> FrameSourceConfig:
        """Pick a sensible config for immediate use.

        Heuristics:
        - Prefer MJPEG (lower bandwidth than YUYV)
        - Prefer 720p if available
        - Prefer 30fps if available
        - Fall back to whatever is available
        """
        if not self.modes:
            # No modes available, return default and let it fail at open time
            return FrameSourceConfig()

        # Score each mode: higher is better
        def score(mode: VideoMode) -> tuple[int, int, int, int]:
            format_score = 2 if mode.pixel_format == "MJPG" else 1
            # Prefer 720p, then 1080p, then other resolutions by size
            if mode.height == 720:
                res_score = 10_000_000
            elif mode.height == 1080:
                res_score = 9_000_000
            else:
                res_score = mode.width * mode.height
            # Prefer 30fps, then higher, then lower
            if abs(mode.fps - 30) < 1:
                fps_score = 1000
            else:
                fps_score = int(mode.fps)
            return (format_score, res_score, fps_score, mode.width)

        best = max(self.modes, key=score)
        return FrameSourceConfig(
            resolution=(best.width, best.height),
            fps=int(best.fps),
            pixel_format=_normalize_format(best.pixel_format),
        )

    def formats(self) -> set[str]:
        """All supported pixel formats."""
        return {mode.pixel_format for mode in self.modes}

    def resolutions(self, pixel_format: str) -> set[tuple[int, int]]:
        """Resolutions available for a pixel format."""
        fmt = _normalize_format(pixel_format)
        return {(mode.width, mode.height) for mode in self.modes if _normalize_format(mode.pixel_format) == fmt}

    def framerates(self, pixel_format: str, width: int, height: int) -> list[float]:
        """Framerates available for a format + resolution."""
        fmt = _normalize_format(pixel_format)
        return sorted(
            mode.fps
            for mode in self.modes
            if _normalize_format(mode.pixel_format) == fmt and mode.width == width and mode.height == height
        )

    @property
    def max_resolution(self) -> tuple[int, int]:
        """Highest resolution by pixel count."""
        if not self.modes:
            return (0, 0)
        best = max(self.modes, key=lambda m: m.width * m.height)
        return (best.width, best.height)


def discover_frame_sources(
    cancel_check: CancelCheck | None = None,
) -> list[FrameSourceOptions]:
    """Discover all V4L2 video capture devices.

    Queries each /dev/video* device, filters out metadata nodes,
    and returns options with supported modes.

    Uses v4l2-ctl when available. On minimal Jetson installs without
    v4l-utils, falls back to sysfs identity data and conservative UVC modes.

    Returns:
        List of FrameSourceOptions for each capture device.

    """
    logger.info("Discovering V4L2 devices")
    devices = []
    seen_bus_info: set[str] = set()
    for path in sorted(Path("/dev").glob("video*")):
        _check_cancel(cancel_check)
        options = get_frame_source_options(
            str(path),
            cancel_check=cancel_check,
        )
        if options is not None:
            if options.bus_info in seen_bus_info:
                logger.debug(
                    "Skipping duplicate capture node %s for bus %s",
                    options.path,
                    options.bus_info,
                )
                continue
            seen_bus_info.add(options.bus_info)
            devices.append(options)
            logger.debug(f"Found capture device: {path} ({options.model})")
    logger.info(f"Discovery complete: {len(devices)} capture device(s) found")
    return devices


def get_frame_source_options(
    device_path: str,
    cancel_check: CancelCheck | None = None,
) -> FrameSourceOptions | None:
    """Get options for a specific device.

    Args:
        device_path: Path to V4L2 device (e.g., "/dev/video0")

    Returns:
        FrameSourceOptions if device is a valid capture device, None otherwise.
    """
    _check_cancel(cancel_check)
    info = _query_device_info(device_path, cancel_check)
    if info is None:
        logger.debug(f"{device_path}: Failed to query device info")
        return None

    model, driver, bus_info, is_capture = info
    if not is_capture:
        logger.debug(f"{device_path}: Not a capture device")
        return None

    modes = _query_modes(device_path, cancel_check)
    if not modes:
        # No modes means it's likely a metadata node
        logger.debug(f"{device_path}: No capture modes available (likely metadata node)")
        return None

    return FrameSourceOptions(
        path=device_path,
        model=model,
        driver=driver,
        bus_info=bus_info,
        modes=tuple(modes),
    )


def _query_device_info(
    device_path: str,
    cancel_check: CancelCheck | None = None,
) -> tuple[str, str, str, bool] | None:
    """Query basic device info via v4l2-ctl --info, with sysfs fallback."""
    try:
        result = _run_command(
            ["v4l2-ctl", "-d", device_path, "--info"],
            timeout=5,
            cancel_check=cancel_check,
        )
        if result.returncode != 0:
            return None

        name = ""
        driver = ""
        bus_info = ""
        is_capture = False

        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Card type"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("Driver name"):
                driver = line.split(":", 1)[1].strip()
            elif line.startswith("Bus info"):
                bus_info = line.split(":", 1)[1].strip()
            elif "Video Capture" in line:
                is_capture = True

        return (name, driver, bus_info, is_capture)

    except subprocess.TimeoutExpired:
        logger.warning(f"{device_path}: v4l2-ctl query timed out")
        return None
    except FileNotFoundError:
        logger.warning("v4l2-ctl not found; using sysfs fallback for V4L2 discovery")
        return _query_device_info_from_sysfs(device_path)


def _query_modes(
    device_path: str,
    cancel_check: CancelCheck | None = None,
) -> list[VideoMode]:
    """Query supported modes via v4l2-ctl --list-formats-ext."""
    try:
        result = _run_command(
            ["v4l2-ctl", "-d", device_path, "--list-formats-ext"],
            timeout=10,
            cancel_check=cancel_check,
        )
        if result.returncode != 0:
            return []

        return _parse_formats_output(result.stdout)

    except subprocess.TimeoutExpired:
        return []
    except FileNotFoundError:
        return _default_uvc_modes()


def _run_command(
    args: list[str],
    timeout: float,
    cancel_check: CancelCheck | None = None,
) -> subprocess.CompletedProcess:
    """Run and reap one command while observing cooperative cancellation."""

    _check_cancel(cancel_check)
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        if cancel_check is not None and cancel_check():
            _terminate_process(process)
            raise InterruptedError("camera discovery cancelled")
        returncode = process.poll()
        if returncode is not None:
            stdout, stderr = process.communicate()
            return subprocess.CompletedProcess(
                args,
                returncode,
                stdout,
                stderr,
            )
        if time.monotonic() >= deadline:
            _terminate_process(process)
            raise subprocess.TimeoutExpired(args, timeout)
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


def _terminate_process(process) -> None:
    process.terminate()
    try:
        process.communicate(timeout=0.25)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()


def _check_cancel(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise InterruptedError("camera discovery cancelled")


def _query_device_info_from_sysfs(device_path: str) -> tuple[str, str, str, bool] | None:
    video_name = Path(device_path).name
    sysfs_path = Path("/sys/class/video4linux") / video_name
    if not sysfs_path.exists():
        return None

    name = _read_text(sysfs_path / "name") or video_name
    index = _read_text(sysfs_path / "index")
    device_realpath = (sysfs_path / "device").resolve()
    uevent = _read_uevent(device_realpath / "uevent")
    driver = uevent.get("DRIVER", "uvcvideo")
    bus_info = _bus_info_from_sysfs_device(device_realpath)

    # UVC devices commonly expose index 0 as the capture node and index 1 as
    # metadata. Without v4l2-ctl capability data, keep only index 0.
    is_capture = index in ("", "0")
    return (name, driver, bus_info, is_capture)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _read_uevent(path: Path) -> dict[str, str]:
    values = {}
    for line in _read_text(path).splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _bus_info_from_sysfs_device(device_realpath: Path) -> str:
    parts = device_realpath.parts
    controller = ""
    port = ""

    for index, part in enumerate(parts):
        if part.endswith(".xhci"):
            controller = part
            for descendant in parts[index + 1 :]:
                if re.match(r"\d+-\d+(?:\.\d+)*$", descendant):
                    port = descendant
            break

    if controller and port:
        normalized_port = port.split("-", 1)[1] if "-" in port else port
        return f"usb-{controller}-{normalized_port}"

    return f"usb-{device_realpath.name}"


def _default_uvc_modes() -> list[VideoMode]:
    return [
        VideoMode("MJPG", 1280, 720, 30.0),
        VideoMode("MJPG", 640, 480, 30.0),
        VideoMode("YUYV", 640, 480, 30.0),
    ]


def _parse_formats_output(output: str) -> list[VideoMode]:
    """Parse v4l2-ctl --list-formats-ext output into VideoMode list."""
    modes: list[VideoMode] = []
    current_format: str | None = None
    current_width: int | None = None
    current_height: int | None = None

    # Pattern for format line: [0]: 'MJPG' (Motion-JPEG, ...)
    format_pattern = re.compile(r"\[\d+\]:\s+'(\w+)'")

    # Pattern for size line: Size: Discrete 1920x1080
    size_pattern = re.compile(r"Size:\s+\w+\s+(\d+)x(\d+)")

    # Pattern for interval line: Interval: Discrete 0.033s (30.000 fps)
    interval_pattern = re.compile(r"Interval:.*\((\d+\.?\d*)\s*fps\)")

    # Alternative pattern for fraction intervals: Interval: Discrete 1/30
    fraction_pattern = re.compile(r"Interval:\s+\w+\s+(\d+)/(\d+)")

    for line in output.splitlines():
        line = line.strip()

        # New format
        match = format_pattern.search(line)
        if match:
            current_format = match.group(1)
            current_width = None
            current_height = None
            continue

        # New resolution
        match = size_pattern.search(line)
        if match and current_format:
            current_width = int(match.group(1))
            current_height = int(match.group(2))
            continue

        # Framerate (fps form)
        match = interval_pattern.search(line)
        if match and current_format and current_width and current_height:
            fps = float(match.group(1))
            modes.append(
                VideoMode(
                    pixel_format=current_format,
                    width=current_width,
                    height=current_height,
                    fps=fps,
                )
            )
            continue

        # Framerate (fraction form)
        match = fraction_pattern.search(line)
        if match and current_format and current_width and current_height:
            num = int(match.group(1))
            denom = int(match.group(2))
            fps = denom / num if num else 0
            modes.append(
                VideoMode(
                    pixel_format=current_format,
                    width=current_width,
                    height=current_height,
                    fps=fps,
                )
            )
            continue

    return modes
