"""HTTP uploader that accepts only complete, validated staging tasks."""

from __future__ import annotations

import logging
import json
import os
import tempfile
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

import requests

from tx_rx.config import TxRxConfig, load_config
from tx_rx.jetson_client.http_client import direct_session, network_timeout
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


UploadProgressCallback = Callable[[int, int], None]
CancelCheck = Callable[[], bool]


def check_health(
    config: TxRxConfig,
    session: Optional[Any] = None,
    cancel_check: Optional[CancelCheck] = None,
) -> None:
    """Fail unless the configured reconstruction service is reachable and healthy."""

    client = session or direct_session()
    deadline = time.monotonic() + config.request_timeout_seconds
    while True:
        _check_cancel(cancel_check)
        remaining = max(0.1, deadline - time.monotonic())
        try:
            response = client.get(
                f"{config.server_url}/health",
                timeout=network_timeout(min(2.0, remaining), read_cap=2.0),
            )
            response.raise_for_status()
            return
        except requests.Timeout as exc:
            if time.monotonic() < deadline:
                continue
            raise TaskUploadError(
                f"health check failed for {config.server_url}: {exc}"
            ) from exc
        except requests.RequestException as exc:
            raise TaskUploadError(f"health check failed for {config.server_url}: {exc}") from exc


def upload_task_package(
    package: TaskPackageResult,
    config: TxRxConfig,
    session: Optional[Any] = None,
    progress_callback: Optional[UploadProgressCallback] = None,
    cancel_check: Optional[CancelCheck] = None,
) -> UploadResponse:
    """Upload one validated package and persist its reusable server receipt."""

    client = session or direct_session()
    archive_path: Optional[Path] = None
    try:
        archive_path = _create_task_archive(package, cancel_check)
        _check_cancel(cancel_check)
        if progress_callback is None:
            with archive_path.open("rb") as stream:
                response = client.post(
                    f"{config.server_url}/upload",
                    files={"file": (f"{package.capture_id}.zip", stream, "application/zip")},
                    data={"checksum": package.checksum},
                    timeout=network_timeout(config.upload_timeout_seconds),
                )
        else:
            body = _StreamingMultipart(
                archive_path,
                f"{package.capture_id}.zip",
                package.checksum,
                progress_callback,
                cancel_check,
            )
            response = client.post(
                f"{config.server_url}/upload",
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={body.boundary}",
                    "Content-Length": str(body.content_length),
                },
                timeout=network_timeout(config.upload_timeout_seconds),
            )
        response.raise_for_status()
        parsed = _validate_upload_response(response.json(), package)
        _write_upload_receipt(package, config.server_url, response.json())
        return parsed
    except TaskUploadError:
        raise
    except (OSError, ValueError, requests.RequestException) as exc:
        raise TaskUploadError(
            f"staging task {package.staging_dir}: upload failed: {exc}"
        ) from exc
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)


def request_reconstruction(
    package: TaskPackageResult,
    task_id: str,
    config: TxRxConfig,
    session: Optional[Any] = None,
) -> ReconstructResponse:
    """Ask the remote service to start reconstruction for an uploaded task."""

    client = session or direct_session()
    try:
        response = client.post(
            f"{config.server_url}/reconstruct",
            json={"task_id": task_id},
            headers={"Idempotency-Key": task_id},
            timeout=network_timeout(config.request_timeout_seconds),
        )
        response.raise_for_status()
        return _validate_reconstruct_response(response.json(), package, task_id)
    except TaskUploadError:
        raise
    except (ValueError, TypeError, requests.RequestException) as exc:
        raise TaskUploadError(
            f"staging task {package.staging_dir}: reconstruct request failed: {exc}"
        ) from exc


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
        check_health(config, client)
        upload_response = upload_task_package(package, config, client)
        task_id = upload_response.task_id
        reconstruct_response = request_reconstruction(package, task_id, config, client)
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


def _create_task_archive(
    package: TaskPackageResult,
    cancel_check: Optional[CancelCheck] = None,
) -> Path:
    with tempfile.NamedTemporaryFile(prefix=f"{package.capture_id}-", suffix=".zip", delete=False) as temp:
        archive_path = Path(temp.name)
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(package.manifest_path, "task.json")
            for item in sorted(package.manifest.files, key=lambda file: file.relative_path):
                _check_cancel(cancel_check)
                archive.write(package.staging_dir / item.relative_path, item.relative_path)
        return archive_path
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise


class _StreamingMultipart:
    """Small requests-compatible multipart iterator with byte progress."""

    def __init__(
        self,
        archive_path: Path,
        filename: str,
        checksum: str,
        callback: UploadProgressCallback,
        cancel_check: Optional[CancelCheck] = None,
    ) -> None:
        self.archive_path = archive_path
        self.callback = callback
        self.cancel_check = cancel_check
        self.boundary = "camera-system-" + package_token(checksum)
        self._prefix = (
            f"--{self.boundary}\r\n"
            'Content-Disposition: form-data; name="checksum"\r\n\r\n'
            f"{checksum}\r\n"
            f"--{self.boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/zip\r\n\r\n"
        ).encode("utf-8")
        self._suffix = f"\r\n--{self.boundary}--\r\n".encode("ascii")
        self.content_length = (
            len(self._prefix) + archive_path.stat().st_size + len(self._suffix)
        )

    def __len__(self) -> int:
        return self.content_length

    def __iter__(self) -> Iterator[bytes]:
        sent = 0
        for data in self._parts():
            _check_cancel(self.cancel_check)
            sent += len(data)
            self.callback(sent, self.content_length)
            yield data

    def _parts(self) -> Iterator[bytes]:
        yield self._prefix
        with self.archive_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                yield chunk
        yield self._suffix


def package_token(checksum: str) -> str:
    """Return a safe deterministic multipart boundary suffix."""

    return checksum[:24]


def _check_cancel(cancel_check: Optional[CancelCheck]) -> None:
    if cancel_check and cancel_check():
        raise TaskUploadError("upload cancelled")


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
