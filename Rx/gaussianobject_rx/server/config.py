"""Configuration for the WSL/server receiver."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_RECEIVER_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


class ReceiverConfigError(Exception):
    """Receiver configuration is missing or invalid."""


class ReceiverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.0", min_length=1)
    listen_host: str = Field(default="0.0.0.0", min_length=1)
    listen_port: int = Field(default=8000, ge=0, le=65535)
    task_root: Path
    baseline_path: Path
    baseline_iterations: int = Field(default=2000, ge=500, le=10000)
    reconstruction_queue_size: int = Field(default=8, ge=1, le=1024)
    max_upload_size_bytes: int = Field(default=512 * 1024 * 1024, ge=1)
    max_extracted_size_bytes: int = Field(default=1024 * 1024 * 1024, ge=1)
    max_ply_size_bytes: int = Field(default=2 * 1024 * 1024 * 1024, ge=1)
    result_chunk_size_bytes: int = Field(default=8 * 1024 * 1024, ge=64 * 1024)
    request_timeout_seconds: int = Field(default=300, ge=1, le=86400)
    reconstruction_timeout_seconds: int = Field(default=21600, ge=1, le=604800)
    process_stop_timeout_seconds: int = Field(default=15, ge=1, le=300)

    @field_validator("task_root", "baseline_path")
    @classmethod
    def validate_absolute_path(cls, value: Path) -> Path:
        expanded = value.expanduser()
        if not expanded.is_absolute():
            raise ValueError("receiver paths must be absolute")
        return expanded

    @field_validator("baseline_iterations")
    @classmethod
    def validate_iterations(cls, value: int) -> int:
        if value % 500:
            raise ValueError("baseline_iterations must be a multiple of 500")
        return value


def load_receiver_config(config_path: Optional[Path] = None) -> ReceiverConfig:
    path = Path(config_path) if config_path is not None else DEFAULT_RECEIVER_CONFIG_PATH
    try:
        payload: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("configuration root must be a mapping")
        return ReceiverConfig.model_validate(payload)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        raise ReceiverConfigError(f"cannot load receiver configuration {path}: {exc}") from exc
