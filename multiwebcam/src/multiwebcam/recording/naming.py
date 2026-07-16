from __future__ import annotations
"""Utilities for auto-generating readable recording names."""

from datetime import datetime
from pathlib import Path


def next_recording_name(recordings_dir: Path) -> str:
    """Return a readable, time-based name for the next capture.

    A numeric suffix is added only when multiple captures are created in the
    same second. Existing legacy ``recording_NNN`` folders remain untouched.

    Args:
        recordings_dir: Path to the recordings directory to scan.

    Returns:
        A string like ``采集_20260711_153045``.
    """
    stem = datetime.now().strftime("采集_%Y%m%d_%H%M%S")
    candidate = stem
    suffix = 2
    while (recordings_dir / candidate).exists():
        candidate = f"{stem}_{suffix}"
        suffix += 1
    return candidate
