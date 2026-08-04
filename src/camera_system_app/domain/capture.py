"""Capture runtime events shared between the adapter and application layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from camera_system.domain import TASK_ANGLES


class CaptureRuntimeStatus(str, Enum):
    IDLE = "idle"
    DISCOVERING = "discovering"
    READY = "ready"
    RECORDING = "recording"
    STOPPING = "stopping"
    UNAVAILABLE = "unavailable"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass(frozen=True)
class CaptureRuntimeState:
    status: CaptureRuntimeStatus
    message: str
    camera_count: int = 0
    completed_angles: Tuple[int, ...] = ()
    current_angle_deg: Optional[int] = None
    progress_percent: float = 0.0
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaptureCompletedEvent:
    capture_dir: Path
    object_name: str
    completed_angles: Tuple[int, ...] = TASK_ANGLES
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(self, "capture_dir", Path(self.capture_dir).resolve())
        object.__setattr__(self, "completed_angles", tuple(self.completed_angles))
        if self.completed_angles != TASK_ANGLES:
            raise ValueError("capture completion requires all fixed eight angles")

