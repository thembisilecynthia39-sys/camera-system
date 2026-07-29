from __future__ import annotations
"""Project-level runtime settings for recording and inference."""


from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RecordingSettings:
    """Recording backend configuration."""

    backend: Literal["pyav", "gstreamer"] = "gstreamer"
    codec: str = "h264"
    fps: int = 30
    jetson_encoder: str = "nvv4l2h264enc"
    bitrate: int = 8_000_000
    preset_level: int = 1
    insert_sps_pps: bool = True
    maxperf_enable: bool = True


@dataclass(frozen=True)
class InferenceSettings:
    """Realtime recognition backend configuration."""

    backend: Literal["heuristic", "ultralytics_tensorrt", "subprocess"] = "heuristic"
    engine_path: str | None = None
    device: int | str = 0
    input_size: tuple[int, int] = (640, 640)
    confidence_threshold: float = 0.25
    interval_ms: int = 100
    target_class_ids: tuple[int, ...] | None = None
    service_conda_env: str | None = None
    service_python: str | None = None
    service_backend: Literal["heuristic", "ultralytics_tensorrt"] | None = None
    service_script: str | None = None


@dataclass(frozen=True)
class AppSettings:
    """Top-level project runtime settings."""

    recording: RecordingSettings = RecordingSettings()
    inference: InferenceSettings = InferenceSettings()
