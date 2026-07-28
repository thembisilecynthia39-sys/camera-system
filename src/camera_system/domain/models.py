"""Qt-independent models for capture, reconstruction, transfer and results."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Mapping, Optional, Tuple

from .state import TaskState


TASK_ANGLES: Tuple[int, ...] = (0, 45, 90, 135, 180, 225, 270, 315)
TASK_FILENAMES: Tuple[str, ...] = tuple(f"{index}.jpg" for index in range(8))
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CAPTURE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _require_sha256(value: str, field_name: str) -> None:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")


def _require_capture_id(value: str) -> None:
    if not _CAPTURE_ID_RE.fullmatch(value):
        raise ValueError(
            "capture_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}"
        )


def _require_safe_relative_path(value: str) -> None:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or value.startswith("./"):
        raise ValueError("relative_path must be a safe normalized relative path")


@dataclass(frozen=True)
class AppError:
    """Serializable application error, with no dependency on Qt exceptions."""

    code: str
    message: str
    operation: Optional[str] = None
    recoverable: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("error code cannot be empty")
        if not self.message.strip():
            raise ValueError("error message cannot be empty")
        object.__setattr__(self, "details", dict(self.details))


@dataclass(frozen=True)
class TaskImage:
    """One source image mapped to one fixed reconstruction angle."""

    index: int
    angle_deg: int
    filename: str
    source_filename: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if self.index < 0 or self.index >= len(TASK_ANGLES):
            raise ValueError("image index must be between 0 and 7")
        if self.angle_deg != TASK_ANGLES[self.index]:
            raise ValueError(
                f"index {self.index} requires angle {TASK_ANGLES[self.index]}"
            )
        if self.filename != TASK_FILENAMES[self.index]:
            raise ValueError(
                f"index {self.index} requires filename {TASK_FILENAMES[self.index]}"
            )
        if not self.source_filename or Path(self.source_filename).name != self.source_filename:
            raise ValueError("source_filename must be a filename, not a path")
        if self.size_bytes < 0:
            raise ValueError("image size cannot be negative")
        _require_sha256(self.sha256, "image sha256")


@dataclass(frozen=True)
class TaskFile:
    """One file included in the Tx_Rx task archive."""

    relative_path: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        _require_safe_relative_path(self.relative_path)
        _require_sha256(self.sha256, "file sha256")
        if self.size_bytes < 0:
            raise ValueError("file size cannot be negative")


@dataclass(frozen=True)
class TaskManifest:
    """Qt-free representation of the existing Tx_Rx eight-image manifest."""

    schema_version: str
    capture_id: str
    images: Tuple[TaskImage, ...]
    files: Tuple[TaskFile, ...]
    created_at: datetime
    checksum: str

    def __post_init__(self) -> None:
        if not self.schema_version.strip():
            raise ValueError("schema_version cannot be empty")
        _require_capture_id(self.capture_id)
        if len(self.images) != 8:
            raise ValueError("manifest must contain exactly 8 images")
        indexes = [image.index for image in self.images]
        if sorted(indexes) != list(range(8)) or len(set(indexes)) != 8:
            raise ValueError("manifest image indexes must cover 0 through 7")
        if len({item.relative_path for item in self.files}) != len(self.files):
            raise ValueError("manifest file paths must be unique")
        _require_sha256(self.checksum, "manifest checksum")

    @property
    def image_count(self) -> int:
        return len(self.images)

    @property
    def angles(self) -> Tuple[int, ...]:
        return TASK_ANGLES

    def image_for_index(self, index: int) -> TaskImage:
        for image in self.images:
            if image.index == index:
                return image
        raise KeyError(index)


@dataclass(frozen=True)
class CaptureSession:
    """Description of a capture directory and its fixed-angle coverage."""

    session_id: str
    capture_id: str
    capture_dir: Path
    camera_ids: Tuple[str, ...] = ()
    captured_angles: Tuple[int, ...] = ()
    state: TaskState = TaskState.IDLE
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        _require_capture_id(self.capture_id)
        normalized_angles = tuple(self.captured_angles)
        if any(angle not in TASK_ANGLES for angle in normalized_angles):
            raise ValueError("captured_angles must use the fixed eight angles")
        if len(set(normalized_angles)) != len(normalized_angles):
            raise ValueError("captured_angles must be unique")
        object.__setattr__(self, "capture_dir", Path(self.capture_dir))
        object.__setattr__(self, "camera_ids", tuple(str(item) for item in self.camera_ids))
        object.__setattr__(self, "captured_angles", normalized_angles)


@dataclass(frozen=True)
class CaptureProgress:
    """Progress emitted by capture adapters and safe to serialize or log."""

    session_id: str
    state: TaskState
    completed_angles: Tuple[int, ...] = ()
    current_angle_deg: Optional[int] = None
    readiness_percent: float = 0.0
    progress_percent: float = 0.0
    camera_count: int = 0
    message: Optional[str] = None
    updated_at: datetime = field(default_factory=_now_utc)

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if any(angle not in TASK_ANGLES for angle in self.completed_angles):
            raise ValueError("completed_angles must use the fixed eight angles")
        if len(set(self.completed_angles)) != len(self.completed_angles):
            raise ValueError("completed_angles must be unique")
        if self.current_angle_deg is not None and self.current_angle_deg not in TASK_ANGLES:
            raise ValueError("current_angle_deg must use the fixed eight angles")
        if not 0.0 <= float(self.readiness_percent) <= 100.0:
            raise ValueError("readiness_percent must be between 0 and 100")
        if not 0.0 <= float(self.progress_percent) <= 100.0:
            raise ValueError("progress_percent must be between 0 and 100")
        if self.camera_count < 0:
            raise ValueError("camera_count cannot be negative")
        object.__setattr__(self, "completed_angles", tuple(self.completed_angles))


@dataclass(frozen=True)
class TransferReceipt:
    """The upload response needed to continue the reconstruction workflow."""

    task_id: str
    capture_id: str
    checksum: str
    server_url: str
    status: str
    duplicate: bool

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.capture_id.strip():
            raise ValueError("task_id and capture_id cannot be empty")
        _require_capture_id(self.capture_id)
        _require_sha256(self.checksum, "task checksum")
        if not self.server_url.strip():
            raise ValueError("server_url cannot be empty")


@dataclass(frozen=True)
class ReconstructionTask:
    """A prepared task plus its local workflow state and optional remote ID."""

    capture_id: str
    manifest: TaskManifest
    staging_dir: Path
    capture_dir: Optional[Path] = None
    task_id: Optional[str] = None
    state: TaskState = TaskState.READY
    source_camera_id: Optional[str] = None
    receipt: Optional[TransferReceipt] = None
    created_at: datetime = field(default_factory=_now_utc)

    def __post_init__(self) -> None:
        _require_capture_id(self.capture_id)
        if self.manifest.capture_id != self.capture_id:
            raise ValueError("task capture_id must match manifest capture_id")
        object.__setattr__(self, "staging_dir", Path(self.staging_dir))
        if self.capture_dir is not None:
            object.__setattr__(self, "capture_dir", Path(self.capture_dir))
        if self.receipt is not None and self.receipt.capture_id != self.capture_id:
            raise ValueError("upload receipt capture_id must match task capture_id")
        if self.task_id is not None and not self.task_id.strip():
            raise ValueError("task_id cannot be blank")


@dataclass(frozen=True)
class ReconstructionStatus:
    """Remote Tx_Rx status while retaining the local workflow interpretation."""

    task_id: str
    capture_id: str
    remote_status: str
    progress: float = 0.0
    stage: Optional[str] = None
    current_step: Optional[int] = None
    total_steps: Optional[int] = None
    message: Optional[str] = None
    output_ply: Optional[str] = None
    error: Optional[str] = None
    workflow_state: TaskState = TaskState.RECONSTRUCTING
    updated_at: datetime = field(default_factory=_now_utc)

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.capture_id.strip():
            raise ValueError("task_id and capture_id cannot be empty")
        _require_capture_id(self.capture_id)
        if not self.remote_status.strip():
            raise ValueError("remote_status cannot be empty")
        if not 0.0 <= float(self.progress) <= 100.0:
            raise ValueError("progress must be between 0 and 100")
        if self.current_step is not None and self.current_step < 0:
            raise ValueError("current_step cannot be negative")
        if self.total_steps is not None and self.total_steps < 0:
            raise ValueError("total_steps cannot be negative")


@dataclass(frozen=True)
class ResultArtifact:
    """A verified local result and the protocol metadata needed for ACK."""

    task_id: str
    capture_id: str
    path: Path
    filename: str
    size_bytes: int
    sha256: str
    media_type: str = "application/octet-stream"
    protocol_magic: str = "GOBJ"
    protocol_version: str = "1.0"
    protocol_message_type: str = "ply_result"
    chunk_size: Optional[int] = None
    chunk_count: Optional[int] = None
    created_at: Optional[datetime] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.capture_id.strip():
            raise ValueError("task_id and capture_id cannot be empty")
        _require_capture_id(self.capture_id)
        object.__setattr__(self, "path", Path(self.path))
        if not self.filename.strip():
            raise ValueError("artifact filename cannot be empty")
        if self.size_bytes <= 0:
            raise ValueError("artifact size must be positive")
        _require_sha256(self.sha256, "artifact sha256")
        if self.chunk_size is not None and self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_count is not None and self.chunk_count <= 0:
            raise ValueError("chunk_count must be positive")
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ViewerDocument:
    """Qt-free description returned after a viewer adapter accepts an artifact."""

    artifact: ResultArtifact
    format: str
    point_count: Optional[int] = None
    capabilities: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.format.strip():
            raise ValueError("viewer format cannot be empty")
        if self.point_count is not None and self.point_count < 0:
            raise ValueError("point_count cannot be negative")
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(self, "metadata", dict(self.metadata))
