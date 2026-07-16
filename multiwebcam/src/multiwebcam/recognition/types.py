from __future__ import annotations
"""Recognition backend types."""


from dataclasses import dataclass
from typing import Protocol

import numpy as np

from multiwebcam.quality.metrics import ObjectRegion


@dataclass(frozen=True)
class DetectionResult:
    """Recognition result for one frame."""

    frame_index: int
    object_region: ObjectRegion | None
    backend: str
    latency_ms: float


@dataclass(frozen=True)
class InferenceStatus:
    """Realtime summary of object-recognition health across active sources."""

    backend: str
    active_count: int
    detected_count: int
    latency_ms: float | None
    warming: bool = False


class ObjectDetector(Protocol):
    """Protocol for region detectors."""

    backend_name: str

    def detect(self, frame: np.ndarray, frame_index: int) -> DetectionResult:
        """Return the best object region for this frame."""
