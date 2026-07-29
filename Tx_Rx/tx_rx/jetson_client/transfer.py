"""Pure Python Jetson-to-WSL reconstruction transfer workflow."""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import time
from pathlib import Path
from typing import Any, Callable, List, Optional
from urllib.parse import quote

import requests

from tx_rx.config import TxRxConfig, load_config
from tx_rx.jetson_client.http_client import direct_session, network_timeout
from tx_rx.jetson_client.task_manifest import TaskPackageResult, build_configured_task_package
from tx_rx.jetson_client.uploader import TaskUploadResult, upload_staged_task
from tx_rx.protocol.models import AckResponse, PlyMetadata, StatusResponse, TaskStatus

CancelCheck = Callable[[], bool]
ProgressCallback = Callable[[str], None]


class TransferError(Exception):
    """The server response or result transfer violated the agreed protocol."""


def poll_status(
    task_id: str,
    capture_id: str,
    config: TxRxConfig,
    session: Optional[Any] = None,
    cancel_check: Optional[CancelCheck] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> StatusResponse:
    """Poll until reconstruction finishes, fails, times out, or is cancelled."""

    client = session or direct_session()
    deadline = time.monotonic() + config.reconstruction_timeout_seconds
    while True:
        _check_cancel(cancel_check)
        if time.monotonic() >= deadline:
            raise TransferError(f"status polling timed out for task {task_id}")
        remaining = max(0.1, deadline - time.monotonic())
        status = get_status(
            task_id,
            capture_id,
            config,
            client,
            timeout_seconds=min(config.request_timeout_seconds, remaining),
        )
        if progress_callback:
            progress_callback(f"stage={status.stage or status.status.value} progress={status.progress}")
        if status.status is TaskStatus.FINISHED:
            return status
        if status.status is TaskStatus.FAILED:
            raise TransferError(f"reconstruction failed for task {task_id}: {status.error or status.message}")
        _interruptible_wait(
            min(config.status_poll_interval_seconds, max(0.0, deadline - time.monotonic())),
            cancel_check,
        )


def get_status(
    task_id: str,
    capture_id: str,
    config: TxRxConfig,
    session: Optional[Any] = None,
    timeout_seconds: Optional[float] = None,
) -> StatusResponse:
    """Query and validate one remote task status without polling."""

    client = session or direct_session()
    try:
        response = client.get(
            f"{config.server_url}/status/{quote(task_id, safe='')}",
            timeout=network_timeout(
                timeout_seconds or config.request_timeout_seconds
            ),
        )
        response.raise_for_status()
        status = StatusResponse.model_validate(response.json())
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise TransferError(f"cannot query status for task {task_id}: {exc}") from exc
    _require_identity(status.task_id, status.capture_id, task_id, capture_id, "status")
    return status


def get_ply_metadata(
    task_id: str,
    capture_id: str,
    config: TxRxConfig,
    session: Optional[Any] = None,
    cancel_check: Optional[CancelCheck] = None,
) -> PlyMetadata:
    """Fetch and strictly validate result metadata."""

    client = session or direct_session()
    try:
        response = _cancellable_request(
            client,
            "get",
            f"{config.server_url}/result/{quote(task_id, safe='')}/metadata",
            config.request_timeout_seconds,
            cancel_check,
        )
        response.raise_for_status()
        metadata = PlyMetadata.model_validate(response.json())
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise TransferError(f"cannot obtain PLY metadata for task {task_id}: {exc}") from exc
    _require_identity(metadata.task_id, metadata.capture_id, task_id, capture_id, "PLY metadata")
    if (metadata.magic, metadata.version, metadata.message_type, metadata.filename) != (
        "GOBJ", "1.0", "ply_result", "3DGS.ply"
    ):
        raise TransferError(f"invalid PLY metadata constants for task {task_id}")
    if metadata.file_size > config.max_ply_size_bytes:
        raise TransferError(f"PLY size {metadata.file_size} exceeds configured limit {config.max_ply_size_bytes}")
    expected_count = math.ceil(metadata.file_size / metadata.chunk_size)
    if metadata.chunk_count != expected_count:
        raise TransferError(
            f"PLY chunk_count {metadata.chunk_count} does not match file_size/chunk_size {expected_count}"
        )
    return metadata


def download_ply(
    metadata: PlyMetadata,
    config: TxRxConfig,
    session: Optional[Any] = None,
    cancel_check: Optional[CancelCheck] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> Path:
    """Stream validated HTTP ranges to .part and atomically publish 3DGS.ply."""

    client = session or direct_session()
    if config.result_layout == "capture_flat":
        result_dir = config.result_root
        final_filename = f"{metadata.capture_id}3DGS.ply"
    else:
        result_dir = config.result_root / metadata.capture_id / metadata.task_id
        final_filename = metadata.filename
    result_dir.mkdir(parents=True, exist_ok=True)
    final_path = result_dir / final_filename
    part_path = result_dir / f"{final_filename}.part"
    deadline = time.monotonic() + config.download_timeout_seconds
    if final_path.is_file():
        if final_path.stat().st_size == metadata.file_size and _sha256_file(final_path) == metadata.sha256:
            return final_path
        raise TransferError(f"existing result file does not match metadata: {final_path}")

    try:
        with part_path.open("wb") as output:
            for chunk_index in range(metadata.chunk_count):
                _check_cancel(cancel_check)
                if time.monotonic() >= deadline:
                    raise TransferError(
                        f"PLY download timed out for task {metadata.task_id}"
                    )
                start = chunk_index * metadata.chunk_size
                end = min(start + metadata.chunk_size, metadata.file_size) - 1
                headers = {
                    "Range": f"bytes={start}-{end}",
                    "If-Range": f'"{metadata.sha256}"',
                }
                response = client.get(
                    f"{config.server_url}/result/{quote(metadata.task_id, safe='')}",
                    headers=headers,
                    stream=True,
                    timeout=network_timeout(
                        max(0.1, deadline - time.monotonic()),
                        read_cap=5.0,
                    ),
                )
                try:
                    if response.status_code != 206:
                        raise TransferError(f"chunk {chunk_index}: expected HTTP 206, got {response.status_code}")
                    expected_length = end - start + 1
                    _validate_chunk_headers(response.headers, metadata, chunk_index, start, end, expected_length)
                    digest = hashlib.sha256()
                    received = 0
                    for data in response.iter_content(chunk_size=1024 * 1024):
                        _check_cancel(cancel_check)
                        if time.monotonic() >= deadline:
                            raise TransferError(
                                f"PLY download timed out for task {metadata.task_id}"
                            )
                        if not data:
                            continue
                        received += len(data)
                        if received > expected_length:
                            raise TransferError(f"chunk {chunk_index}: response exceeds requested range")
                        digest.update(data)
                        output.write(data)
                    if received != expected_length:
                        raise TransferError(f"chunk {chunk_index}: received {received} bytes, expected {expected_length}")
                    if digest.hexdigest() != response.headers["X-GO-Chunk-SHA256"]:
                        raise TransferError(f"chunk {chunk_index}: SHA-256 mismatch")
                finally:
                    close = getattr(response, "close", None)
                    if callable(close):
                        close()
                if progress_callback:
                    progress_callback(f"download={end + 1}/{metadata.file_size}")
            output.flush()
            os.fsync(output.fileno())
        if part_path.stat().st_size != metadata.file_size:
            raise TransferError(f"downloaded PLY size mismatch for task {metadata.task_id}")
        if _sha256_file(part_path) != metadata.sha256:
            raise TransferError(f"downloaded PLY SHA-256 mismatch for task {metadata.task_id}")
        os.replace(str(part_path), str(final_path))
        return final_path
    except TransferError:
        raise
    except (OSError, requests.RequestException) as exc:
        raise TransferError(f"PLY download failed for task {metadata.task_id}: {exc}") from exc


def acknowledge_result(
    metadata: PlyMetadata,
    final_path: Path,
    config: TxRxConfig,
    session: Optional[Any] = None,
    cancel_check: Optional[CancelCheck] = None,
) -> AckResponse:
    """Acknowledge a completely validated and published PLY result."""

    _check_cancel(cancel_check)
    if not final_path.is_file() or final_path.stat().st_size != metadata.file_size:
        raise TransferError(f"cannot ACK missing or invalid result file: {final_path}")
    payload = {
        "magic": "GOBJ",
        "version": "1.0",
        "message_type": "result_received",
        "task_id": metadata.task_id,
        "capture_id": metadata.capture_id,
        "filename": metadata.filename,
        "file_size": metadata.file_size,
        "sha256": metadata.sha256,
    }
    client = session or direct_session()
    try:
        response = _cancellable_request(
            client,
            "post",
            f"{config.server_url}/result/{quote(metadata.task_id, safe='')}/ack",
            config.request_timeout_seconds,
            cancel_check,
            json=payload,
            headers={"Idempotency-Key": metadata.task_id},
        )
        response.raise_for_status()
        ack = AckResponse.model_validate(response.json())
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise TransferError(f"cannot ACK result for task {metadata.task_id}: {exc}") from exc
    _require_identity(ack.task_id, ack.capture_id, metadata.task_id, metadata.capture_id, "ACK")
    if ack.message_type != "result_acknowledged":
        raise TransferError(f"unexpected ACK message_type {ack.message_type!r}")
    return ack


def run_transfer(
    capture_dir: Path,
    config_path: Path,
    session: Optional[Any] = None,
    cancel_check: Optional[CancelCheck] = None,
    progress_callback: Optional[ProgressCallback] = print,
    selected_images: Optional[List[str]] = None,
) -> Path:
    """Run the complete package, upload, reconstruction, download, and ACK flow."""

    config = load_config(config_path)
    if "127.0.0.1" in config.server_url or "localhost" in config.server_url:
        raise TransferError("server_url must contain the actual WSL IP, not localhost")
    package: TaskPackageResult = build_configured_task_package(
        capture_dir,
        config_path,
        selected_images,
        cancel_check=cancel_check,
    )
    if progress_callback:
        progress_callback(f"capture_id={package.capture_id}")
    uploaded: TaskUploadResult = upload_staged_task(
        package.staging_dir,
        config_path,
        session,
        cancel_check=cancel_check,
    )
    if progress_callback:
        progress_callback(f"task_id={uploaded.task_id} upload_status={uploaded.upload_response.status}")
    poll_status(uploaded.task_id, package.capture_id, config, session, cancel_check, progress_callback)
    metadata = get_ply_metadata(
        uploaded.task_id,
        package.capture_id,
        config,
        session,
        cancel_check,
    )
    final_path = download_ply(metadata, config, session, cancel_check, progress_callback)
    ack = acknowledge_result(
        metadata,
        final_path,
        config,
        session,
        cancel_check,
    )
    if progress_callback:
        progress_callback(f"final_path={final_path} sha256={metadata.sha256} ack={ack.message_type}")
    return final_path


def _validate_chunk_headers(
    headers: Any, metadata: PlyMetadata, chunk_index: int, start: int, end: int, length: int
) -> None:
    expected = {
        "Content-Range": f"bytes {start}-{end}/{metadata.file_size}",
        "Content-Length": str(length),
        "X-GO-Task-ID": metadata.task_id,
        "X-GO-Capture-ID": metadata.capture_id,
        "X-GO-Chunk-Index": str(chunk_index),
        "X-GO-Chunk-Count": str(metadata.chunk_count),
        "X-GO-File-Size": str(metadata.file_size),
        "X-GO-SHA256": metadata.sha256,
    }
    for name, value in expected.items():
        if headers.get(name) != value:
            raise TransferError(f"chunk {chunk_index}: invalid {name}: {headers.get(name)!r}, expected {value!r}")
    chunk_hash = headers.get("X-GO-Chunk-SHA256", "")
    if len(chunk_hash) != 64 or any(char not in "0123456789abcdef" for char in chunk_hash):
        raise TransferError(f"chunk {chunk_index}: invalid X-GO-Chunk-SHA256")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_identity(
    actual_task_id: str, actual_capture_id: str, task_id: str, capture_id: str, context: str
) -> None:
    if actual_task_id != task_id:
        raise TransferError(f"{context} task_id mismatch: {actual_task_id!r} != {task_id!r}")
    if actual_capture_id != capture_id:
        raise TransferError(f"{context} capture_id mismatch: {actual_capture_id!r} != {capture_id!r}")


def _check_cancel(cancel_check: Optional[CancelCheck]) -> None:
    if cancel_check and cancel_check():
        raise TransferError("transfer cancelled")


def _cancellable_request(
    client: Any,
    method: str,
    url: str,
    timeout_seconds: float,
    cancel_check: Optional[CancelCheck],
    **kwargs,
):
    """Retry timeout observation windows inside one overall deadline."""

    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    request = getattr(client, method)
    while True:
        _check_cancel(cancel_check)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise requests.Timeout(
                f"{method.upper()} {url} exceeded {timeout_seconds}s"
            )
        try:
            return request(
                url,
                timeout=network_timeout(
                    min(1.0, remaining),
                    read_cap=1.0,
                ),
                **kwargs,
            )
        except requests.Timeout:
            _check_cancel(cancel_check)
            if time.monotonic() >= deadline:
                raise


def _interruptible_wait(seconds: float, cancel_check: Optional[CancelCheck]) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _check_cancel(cancel_check)
        time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))


def main() -> int:
    """Command-line entry point for the pure Python transfer workflow."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--image",
        action="append",
        dest="selected_images",
        metavar="FILENAME",
        help="selected .jpg/.jpeg filename in the image pool; repeat exactly 8 times in index order",
    )
    args = parser.parse_args()
    try:
        run_transfer(args.capture_dir, args.config, selected_images=args.selected_images)
    except Exception as exc:
        parser.exit(1, f"transfer failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
