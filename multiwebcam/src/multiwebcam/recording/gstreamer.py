from __future__ import annotations
"""GStreamer-based hardware recording helpers for Jetson."""


from pathlib import Path

from multiwebcam.profiles.settings import RecordingSettings
from multiwebcam.sources.gstreamer import quote_gstreamer_location


def build_jetson_writer_pipeline(
    output_path: Path,
    frame_size: tuple[int, int],
    fps: int,
    settings: RecordingSettings,
) -> str:
    """Build a Jetson hardware-encoder pipeline for OpenCV VideoWriter."""
    width, height = frame_size
    encoder_props = [
        f"bitrate={settings.bitrate}",
        f"preset-level={settings.preset_level}",
        f"insert-sps-pps={'true' if settings.insert_sps_pps else 'false'}",
        f"maxperf-enable={'true' if settings.maxperf_enable else 'false'}",
    ]
    encoder = f"{settings.jetson_encoder} " + " ".join(encoder_props)
    location = quote_gstreamer_location(output_path)
    return (
        "appsrc ! "
        f"video/x-raw,format=BGR,width={width},height={height},framerate={max(1, fps)}/1 ! "
        "queue ! videoconvert ! video/x-raw,format=I420 ! "
        "nvvidconv ! "
        f"{encoder} ! "
        "h264parse ! qtmux ! "
        f"filesink location={location} sync=false"
    )
