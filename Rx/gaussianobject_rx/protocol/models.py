"""Validated models shared by the task producer and future receiver."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

TASK_ANGLES = [0, 45, 90, 135, 180, 225, 270, 315]
TASK_FILENAMES = [f"{index}.jpg" for index in range(8)]


class StrictModel(BaseModel):
    """Protocol base model that rejects undeclared fields."""

    model_config = ConfigDict(extra="forbid")


class TaskStatus(str, Enum):
    WAITING = "waiting"
    UPLOADING = "uploading"
    READY = "ready"
    RUNNING_COLMAP = "running_colmap"
    RUNNING_3DGS = "running_3dgs"
    FINISHED = "finished"
    FAILED = "failed"


class TaskImage(StrictModel):
    index: int = Field(ge=0, le=7)
    angle: int
    filename: str
    source_filename: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_fixed_mapping(self) -> "TaskImage":
        expected_angle = TASK_ANGLES[self.index]
        expected_filename = TASK_FILENAMES[self.index]
        if self.angle != expected_angle:
            raise ValueError(f"index {self.index} requires angle {expected_angle}")
        if self.filename != expected_filename:
            raise ValueError(f"index {self.index} requires filename {expected_filename}")
        return self


class TaskFile(StrictModel):
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_relative_path(self) -> "TaskFile":
        path = PurePosixPath(self.relative_path)
        if path.is_absolute() or ".." in path.parts or self.relative_path.startswith("./"):
            raise ValueError("relative_path must be a safe normalized relative path")
        return self


class TaskManifest(StrictModel):
    schema_version: str = Field(min_length=1)
    capture_id: str = Field(min_length=1)
    image_count: int
    angles: List[int]
    images: List[TaskImage]
    files: List[TaskFile]
    created_at: datetime
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_complete_task(self) -> "TaskManifest":
        if self.image_count != 8:
            raise ValueError("image_count must equal 8")
        if self.angles != TASK_ANGLES:
            raise ValueError(f"angles must equal {TASK_ANGLES}")
        if len(self.images) != 8:
            raise ValueError("images must contain exactly 8 entries")

        indexes = [image.index for image in self.images]
        angles = [image.angle for image in self.images]
        filenames = [image.filename for image in self.images]
        if len(set(indexes)) != 8:
            raise ValueError("image indexes must be unique")
        if len(set(angles)) != 8:
            raise ValueError("image angles must be unique")
        if len(set(filenames)) != 8:
            raise ValueError("image filenames must be unique")
        if set(filenames) != set(TASK_FILENAMES):
            raise ValueError(f"image filenames must cover {TASK_FILENAMES}")
        if sorted(indexes) != list(range(8)):
            raise ValueError("image indexes must cover 0 through 7")

        file_paths = [item.relative_path for item in self.files]
        if len(file_paths) != len(set(file_paths)):
            raise ValueError("file relative paths must be unique")
        return self


class StatusResponse(StrictModel):
    message_type: str = Field(
        default="upload_received",
        pattern=(
            r"^(upload_received|reconstruction_queued|reconstruction_running|"
            r"reconstruction_progress|reconstruction_failed|result_sending|result_ready)$"
        )
    )
    task_id: str = Field(min_length=1)
    capture_id: Optional[str] = None
    status: TaskStatus
    stage: str = ""
    progress: int = Field(ge=0, le=100)
    current_step: int = Field(default=0, ge=0)
    total_steps: int = Field(default=0, ge=0)
    message: str
    output_ply: Optional[str] = None
    error: Optional[str] = None
    log_summary: str = ""
    created_at: datetime
    updated_at: datetime


class ResultMetadata(StrictModel):
    magic: str = Field(default="GOBJ", pattern=r"^GOBJ$")
    version: str = Field(default="1.0", pattern=r"^1\.0$")
    message_type: str = Field(default="ply_result", pattern=r"^ply_result$")
    task_id: str = Field(min_length=1)
    capture_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    file_size: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunk_size: int = Field(ge=1)
    chunk_count: int = Field(ge=1)
    created_at: datetime


class ReconstructionRequest(StrictModel):
    task_id: str = Field(min_length=1)


class ResultAck(StrictModel):
    magic: str = Field(default="GOBJ", pattern=r"^GOBJ$")
    version: str = Field(default="1.0", pattern=r"^1\.0$")
    message_type: str = Field(default="result_received", pattern=r"^result_received$")
    task_id: str = Field(pattern=r"^task-[0-9a-f]{64}$")
    capture_id: str = Field(min_length=1, max_length=128)
    filename: str = Field(default="3DGS.ply", pattern=r"^3DGS\.ply$")
    file_size: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
