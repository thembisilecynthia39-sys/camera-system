"""Qt-free reconstruction task state."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional


class ReconstructionState(str, Enum):
    READY = "ready"
    VALIDATING = "validating"
    PACKAGING = "packaging"
    HEALTH_CHECK = "health_check"
    UPLOADING = "uploading"
    STARTING = "starting"
    RECONSTRUCTING = "reconstructing"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    ACKNOWLEDGING = "acknowledging"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


ACTIVE_STATES = {
    ReconstructionState.VALIDATING,
    ReconstructionState.PACKAGING,
    ReconstructionState.HEALTH_CHECK,
    ReconstructionState.UPLOADING,
    ReconstructionState.STARTING,
    ReconstructionState.RECONSTRUCTING,
    ReconstructionState.DOWNLOADING,
    ReconstructionState.VERIFYING,
    ReconstructionState.ACKNOWLEDGING,
}


@dataclass(frozen=True)
class ReconstructionJob:
    job_id: str
    capture_id: str
    capture_dir: Path
    state: ReconstructionState = ReconstructionState.READY
    stage_message: str = "八角度采集已完成"
    staging_dir: Optional[Path] = None
    server_task_id: Optional[str] = None
    server_url: Optional[str] = None
    reconstruct_requested: bool = False
    result_path: Optional[Path] = None
    result_sha256: Optional[str] = None
    result_size: int = 0
    upload_sent: int = 0
    upload_total: int = 0
    reconstruction_progress: float = 0.0
    download_received: int = 0
    download_total: int = 0
    attempts: int = 0
    error: Optional[str] = None
    error_code: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        object.__setattr__(self, "capture_dir", Path(self.capture_dir).resolve())
        for field_name in ("staging_dir", "result_path"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, Path(value).resolve())
        if not self.created_at:
            object.__setattr__(self, "created_at", now)
        if not self.updated_at:
            object.__setattr__(self, "updated_at", now)

    def changed(self, **values: Any) -> "ReconstructionJob":
        values.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
        return replace(self, **values)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        for key in ("capture_dir", "staging_dir", "result_path"):
            value = payload[key]
            payload[key] = str(value) if value is not None else None
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ReconstructionJob":
        allowed = set(cls.__dataclass_fields__)
        values = {key: value for key, value in payload.items() if key in allowed}
        values["state"] = ReconstructionState(values["state"])
        return cls(**values)


@dataclass(frozen=True)
class ResultAvailableEvent:
    job_id: str
    capture_id: str
    local_path: Path
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "local_path", Path(self.local_path).resolve())
