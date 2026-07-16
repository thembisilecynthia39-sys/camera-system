from __future__ import annotations
"""Lightweight per-frame metadata for monitoring-only pipeline paths."""


from dataclasses import dataclass


@dataclass(frozen=True)
class FrameMetadata:
    """Frame identity and timing without the image payload."""

    device_path: str
    frame_index: int
    frame_time: float
