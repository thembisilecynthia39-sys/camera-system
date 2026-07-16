"""HTTP uploader that accepts only complete, validated staging tasks."""

from __future__ import annotations

import logging
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from tx_rx.config import load_config
from tx_rx.jetson_client.http_client import direct_session
from tx_rx.jetson_client.task_manifest import TaskPackageResult, load_staged_task_package
from tx_rx.protocol.models import ReconstructResponse, UploadResponse

logger = logging.getLogger(__name__)


class TaskUploadError(Exception):
    """A staged task could not be uploaded or started."""


@dataclass(frozen=True)
class TaskUploadResult:
    task_id: str
    staging_dir: Path
    checksum: str
    upload_response: UploadResponse
    reconstruct_response: ReconstructResponse


def upload_staged_task(
    staging_dir: Path,
    config_path: Optional[Path] = None,
    session: Optional[Any] = None,
) -> TaskUploadResult:
    """Validate, upload, and request reconstruction for one staging task."""

    package = load_staged_task_package(staging_dir)
    config = load_config(config_path)
    client = session or direct_session()
    archive_path: Optional[Path] = None
    try:
        health = client.get(f"{config.server_url}/health", timeout=config.upload_timeout_seconds)
        health.raise_for_status()
        archive_path = _create_task_archive(package)
        with archive_path.open("rb") as stream:
            response = client.post(
                f"{config.server_url}/upload",
                files={"file": (f"{package.capture_id}.zip", stream, "application/zip")},
                data={"checksum": package.checksum},
                timeout=config.upload_timeout_seconds,
            )
        response.raise_for_status()
        upload_response = _validate_upload_response(response.json(), package)
        task_id = upload_response.task_id
        _write_upload_receipt(package, config.server_url, response.json())
        reconstruct = client.post(
            f"{config.server_url}/reconstruct",
            json={"task_id": task_id},
            timeout=config.upload_timeout_seconds,
        )
        reconstruct.raise_for_status()
        reconstruct_response = _validate_reconstruct_response(reconstruct.json(), package, task_id)
    except TaskUploadError:
        raise
    except (OSError, ValueError, requests.RequestException) as exc:
        raise TaskUploadError(f"staging task {staging_dir}: upload failed: {exc}") from exc
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)
    logger.info("Uploaded staged task %s as %s", staging_dir, task_id)
    return TaskUploadResult(
        task_id,
        package.staging_dir,
        package.checksum,
        upload_response,
        reconstruct_response,
    )


def _write_upload_receipt(
    package: TaskPackageResult,
    server_url: str,
    upload_response: Any,
) -> None:
    path = package.staging_dir / "upload.json"
    temporary_path = path.with_name(".upload.json.tmp")
    payload = {
        "task_id": upload_response["task_id"],
        "capture_id": package.capture_id,
        "server_url": server_url,
        "checksum": package.checksum,
        "upload_response": upload_response,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with temporary_path.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary_path), str(path))
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        raise TaskUploadError(f"staging task {package.staging_dir}: cannot save upload receipt: {exc}") from exc


def _create_task_archive(package: TaskPackageResult) -> Path:
    with tempfile.NamedTemporaryFile(prefix=f"{package.capture_id}-", suffix=".zip", delete=False) as temp:
        archive_path = Path(temp.name)
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(package.manifest_path, "task.json")
            for item in sorted(package.manifest.files, key=lambda file: file.relative_path):
                archive.write(package.staging_dir / item.relative_path, item.relative_path)
        return archive_path
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise


def _validate_upload_response(payload: Any, package: TaskPackageResult) -> UploadResponse:
    try:
        parsed = UploadResponse.model_validate(payload)
    except (ValueError, TypeError) as exc:
        raise TaskUploadError(f"staging task {package.staging_dir}: invalid /upload response: {exc}") from exc
    if parsed.message_type != "upload_received":
        raise TaskUploadError(f"staging task {package.staging_dir}: unexpected upload message_type {parsed.message_type!r}")
    if parsed.capture_id != package.capture_id:
        raise TaskUploadError(f"staging task {package.staging_dir}: upload capture_id mismatch")
    reusable_duplicate_statuses = {
        "ready",
        "queued",
        "preprocessing",
        "running_colmap",
        "running_3dgs",
        "finished",
    }
    status_is_valid = parsed.status == "ready" or (
        parsed.duplicate and parsed.status in reusable_duplicate_statuses
    )
    if not status_is_valid:
        raise TaskUploadError(f"staging task {package.staging_dir}: unexpected upload status {parsed.status!r}")
    if not parsed.task_id.startswith("task-"):
        raise TaskUploadError(f"staging task {package.staging_dir}: invalid server task_id {parsed.task_id!r}")
    return parsed


def _validate_reconstruct_response(
    payload: Any, package: TaskPackageResult, task_id: str
) -> ReconstructResponse:
    try:
        parsed = ReconstructResponse.model_validate(payload)
    except (ValueError, TypeError) as exc:
        raise TaskUploadError(f"staging task {package.staging_dir}: invalid /reconstruct response: {exc}") from exc
    if parsed.task_id != task_id or parsed.capture_id != package.capture_id:
        raise TaskUploadError(f"staging task {package.staging_dir}: /reconstruct identity mismatch")
    if not parsed.message_type:
        raise TaskUploadError(f"staging task {package.staging_dir}: /reconstruct message_type is empty")
    return parsed
