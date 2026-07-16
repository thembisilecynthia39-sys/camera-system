"""Configuration for local reconstruction task staging."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


class TxRxConfigError(Exception):
    """The Tx_Rx configuration is missing or invalid."""


class TxRxConfig(BaseModel):
    """Validated local Tx_Rx settings."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1)
    staging_root: Path
    server_url: str = Field(default="http://10.150.14.62:8000", min_length=1)
    remote_task_root: str = Field(default="/home/yp/GaussianObject/rx_tasks", min_length=1)
    upload_timeout_seconds: int = Field(default=300, ge=1, le=86400)
    result_root: Path = Path("/home/jetson/3DGS/results")
    result_layout: Literal["task_nested", "capture_flat"] = "task_nested"
    request_timeout_seconds: int = Field(default=300, ge=1, le=86400)
    status_poll_interval_seconds: float = Field(default=2.0, gt=0, le=3600)
    reconstruction_timeout_seconds: int = Field(default=21600, ge=1, le=604800)
    download_timeout_seconds: int = Field(default=600, ge=1, le=86400)
    max_ply_size_bytes: int = Field(default=2147483648, ge=1)

    @field_validator("staging_root")
    @classmethod
    def validate_staging_root(cls, value: Path) -> Path:
        expanded = value.expanduser()
        if not expanded.is_absolute():
            raise ValueError("staging_root must be an absolute path")
        return expanded

    @field_validator("result_root")
    @classmethod
    def validate_result_root(cls, value: Path) -> Path:
        expanded = value.expanduser()
        if not expanded.is_absolute():
            raise ValueError("result_root must be an absolute path")
        return expanded

    @field_validator("server_url")
    @classmethod
    def validate_server_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("server_url must start with http:// or https://")
        return normalized

    @field_validator("remote_task_root")
    @classmethod
    def validate_remote_task_root(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith("/"):
            raise ValueError("remote_task_root must be an absolute WSL path")
        return normalized


def load_config(config_path: Optional[Path] = None) -> TxRxConfig:
    """Load the fixed staging location from YAML configuration."""

    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    try:
        payload: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("configuration root must be a mapping")
        return TxRxConfig.model_validate(payload)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        raise TxRxConfigError(f"cannot load Tx_Rx configuration {path}: {exc}") from exc
