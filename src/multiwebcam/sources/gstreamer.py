from __future__ import annotations
"""Helpers for Jetson-friendly GStreamer capture pipelines."""


from pathlib import Path

from multiwebcam.sources.config import FrameSourceConfig


def build_jetson_capture_pipeline(device_path: str, config: FrameSourceConfig) -> str:
    """Build a Jetson-oriented GStreamer pipeline for USB camera capture."""
    width, height = config.resolution
    fps = max(1, int(config.fps))
    pixel_format = config.pixel_format.lower()

    common_sink = "appsink drop=true max-buffers=1 sync=false"
    if pixel_format in {"mjpeg", "mjpe"}:
        return (
            f"v4l2src device={device_path} do-timestamp=true io-mode=2 ! "
            f"image/jpeg,width={width},height={height},framerate={fps}/1 ! "
            "jpegparse ! nvv4l2decoder mjpeg=1 ! "
            "nvvidconv ! video/x-raw,format=BGRx ! "
            "videoconvert ! video/x-raw,format=BGR ! "
            f"{common_sink}"
        )

    if pixel_format in {"yuyv", "yuyv422"}:
        return (
            f"v4l2src device={device_path} do-timestamp=true io-mode=2 ! "
            f"video/x-raw,format=YUY2,width={width},height={height},framerate={fps}/1 ! "
            "videoconvert ! video/x-raw,format=BGR ! "
            f"{common_sink}"
        )

    return (
        f"v4l2src device={device_path} do-timestamp=true io-mode=2 ! "
        f"video/x-raw,width={width},height={height},framerate={fps}/1 ! "
        "videoconvert ! video/x-raw,format=BGR ! "
        f"{common_sink}"
    )


def quote_gstreamer_location(path: str | Path) -> str:
    """Quote a filesystem path for use in a pipeline property."""
    return "'" + str(path).replace("'", "\\'") + "'"
