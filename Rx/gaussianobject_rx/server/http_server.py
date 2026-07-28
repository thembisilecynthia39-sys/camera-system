"""Standard-library HTTP transport compatible with the existing Tx uploader."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import tempfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import unquote, urlsplit

from pydantic import ValidationError

from gaussianobject_rx.protocol.models import ReconstructionRequest, ResultAck, ResultMetadata, TaskStatus
from gaussianobject_rx.server.archive_validator import ArchiveValidationError
from gaussianobject_rx.server.multipart import MultipartError, parse_multipart_upload
from gaussianobject_rx.server.reconstruction import ReconstructionQueueFull
from gaussianobject_rx.server.service import ReceiverService
from gaussianobject_rx.server.task_registry import utc_now

logger = logging.getLogger(__name__)


class ReceiverHTTPServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True

    def __init__(self, address: Tuple[str, int], service: ReceiverService) -> None:
        super().__init__(address, ReceiverRequestHandler)
        self.service = service


class ReceiverRequestHandler(BaseHTTPRequestHandler):
    server: ReceiverHTTPServer
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(self.server.service.config.request_timeout_seconds)

    def log_message(self, format_string: str, *args: object) -> None:
        logger.info("%s - %s", self.client_address[0], format_string % args)

    def do_GET(self) -> None:
        self._safe_route(include_body=True)

    def do_HEAD(self) -> None:
        self._safe_route(include_body=False)

    def _safe_route(self, include_body: bool) -> None:
        try:
            self._route(include_body)
        except (ValidationError, ValueError) as exc:
            self._json(409, {"error": "result_not_ready", "message": str(exc)}, include_body=include_body)
        except KeyError as exc:
            self._json(404, {"error": "task_not_found", "message": str(exc)}, include_body=include_body)
        except Exception as exc:
            logger.exception("request failed")
            self._json(500, {"error": "internal_error", "message": str(exc)}, include_body=include_body)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path == "/upload":
                self._upload()
            elif path == "/reconstruct":
                self._reconstruct()
            elif match := re.fullmatch(r"/result/(task-[0-9a-f]{64})/ack", path):
                self._result_ack(match.group(1))
            else:
                self._json(404, {"error": "not_found"})
        except (MultipartError, ArchiveValidationError, ValidationError, ValueError) as exc:
            self._json(400, {"error": "invalid_request", "message": str(exc)})
        except ReconstructionQueueFull as exc:
            self._json(503, {"error": "queue_full", "message": str(exc)})
        except KeyError as exc:
            self._json(404, {"error": "task_not_found", "message": str(exc)})
        except Exception as exc:
            logger.exception("request failed")
            self._json(500, {"error": "internal_error", "message": str(exc)})

    def _route(self, include_body: bool) -> None:
        path = unquote(urlsplit(self.path).path)
        if path == "/health":
            self._json(200, {"status": "ok"}, include_body=include_body)
            return
        match = re.fullmatch(r"/status/(task-[0-9a-f]{64})", path)
        if match:
            self._status(match.group(1), include_body)
            return
        match = re.fullmatch(r"/result/(task-[0-9a-f]{64})/metadata", path)
        if match:
            self._result_metadata(match.group(1), include_body)
            return
        match = re.fullmatch(r"/result/(task-[0-9a-f]{64})", path)
        if match:
            self._result(match.group(1), include_body)
            return
        self._json(404, {"error": "not_found"}, include_body=include_body)

    def _upload(self) -> None:
        content_length = _content_length(self.headers.get("Content-Length"))
        config = self.server.service.config
        incoming = config.task_root / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="upload-", suffix=".zip.part", dir=str(incoming), delete=False) as temp:
            archive_path = Path(temp.name)
        try:
            checksum, _ = parse_multipart_upload(
                self.rfile,
                self.headers.get("Content-Type", ""),
                content_length,
                archive_path,
                config.max_upload_size_bytes,
            )
            record, duplicate = self.server.service.ingest_archive(archive_path, checksum)
        finally:
            archive_path.unlink(missing_ok=True)
        self._json(
            200,
            {
                "message_type": "upload_received",
                "task_id": record.task_id,
                "capture_id": record.capture_id,
                "status": record.status,
                "reconstruction_queued": record.status in {
                    TaskStatus.READY.value,
                    TaskStatus.RUNNING_COLMAP.value,
                    TaskStatus.RUNNING_3DGS.value,
                    TaskStatus.FINISHED.value,
                },
                "duplicate": duplicate,
            },
        )

    def _reconstruct(self) -> None:
        length = _content_length(self.headers.get("Content-Length"))
        if length > 1024 * 1024:
            raise ValueError("JSON request body is too large")
        payload = self.rfile.read(length)
        if len(payload) != length:
            raise ValueError("JSON request body is incomplete")
        request = ReconstructionRequest.model_validate_json(payload)
        record = self.server.service.reconstruction.submit(request.task_id)
        self._json(
            202,
            {
                "message_type": "reconstruction_queued",
                "task_id": record.task_id,
                "capture_id": record.capture_id,
                "status": record.status,
            },
        )

    def _status(self, task_id: str, include_body: bool) -> None:
        record = self.server.service.registry.get(task_id)
        if record is None:
            self._json(404, {"error": "task_not_found"}, include_body=include_body)
            return
        self._json(
            200,
            {
                "message_type": _status_message_type(record),
                "task_id": record.task_id,
                "capture_id": record.capture_id,
                "status": record.status,
                "stage": record.status,
                "progress": record.progress,
                "current_step": 0,
                "total_steps": 0,
                "message": record.message,
                "output_ply": record.result_path or None,
                "error": record.error or None,
                "log_summary": record.log_summary if record.status == TaskStatus.FAILED.value else "",
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            },
            include_body=include_body,
        )

    def _result_ack(self, task_id: str) -> None:
        length = _content_length(self.headers.get("Content-Length"))
        if length > 1024 * 1024:
            raise ValueError("ACK request body is too large")
        payload = self.rfile.read(length)
        if len(payload) != length:
            raise ValueError("ACK request body is incomplete")
        ack = ResultAck.model_validate_json(payload)
        if ack.task_id != task_id:
            raise ValueError("ACK task_id does not match URL")
        record = self._finished_record(task_id)
        if (
            ack.capture_id != record.capture_id
            or ack.file_size != record.result_size
            or ack.sha256 != record.result_sha256
        ):
            raise ValueError("ACK result identity does not match registered result")
        record = self.server.service.registry.update(
            task_id,
            result_acknowledged_at=utc_now(),
        )
        self._json(
            200,
            {
                "message_type": "result_acknowledged",
                "task_id": record.task_id,
                "capture_id": record.capture_id,
                "acknowledged_at": record.result_acknowledged_at,
            },
        )

    def _result_metadata(self, task_id: str, include_body: bool) -> None:
        record = self._finished_record(task_id)
        chunk_size = self.server.service.config.result_chunk_size_bytes
        metadata = ResultMetadata(
            task_id=record.task_id,
            capture_id=record.capture_id,
            filename="3DGS.ply",
            file_size=record.result_size,
            sha256=record.result_sha256,
            chunk_size=chunk_size,
            chunk_count=math.ceil(record.result_size / chunk_size),
            created_at=datetime.fromisoformat(record.updated_at),
        )
        self._json(200, metadata.model_dump(mode="json"), include_body=include_body)

    def _result(self, task_id: str, include_body: bool) -> None:
        record = self._finished_record(task_id)
        path = Path(record.result_path)
        total = record.result_size
        if_range = self.headers.get("If-Range")
        if if_range and if_range != f'"{record.result_sha256}"':
            raise ValueError("If-Range does not match immutable result")
        byte_range = _parse_range(self.headers.get("Range"), total)
        if byte_range is None:
            start, end, status = 0, total - 1, 200
        else:
            start, end, status = byte_range[0], byte_range[1], 206
        length = end - start + 1
        config = self.server.service.config
        chunk_index = start // config.result_chunk_size_bytes
        chunk_count = math.ceil(total / config.result_chunk_size_bytes)
        chunk_sha = _sha256_range(path, start, length)

        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", f'"{record.result_sha256}"')
        self.send_header("Content-Disposition", 'attachment; filename="3DGS.ply"')
        self.send_header("X-GO-Magic", "GOBJ")
        self.send_header("X-GO-Protocol-Version", "1.0")
        self.send_header("X-GO-Message-Type", "ply_result")
        self.send_header("X-GO-Transfer-State", "result_sending")
        self.send_header("X-GO-Task-ID", record.task_id)
        self.send_header("X-GO-Capture-ID", record.capture_id)
        self.send_header("X-GO-Filename", "3DGS.ply")
        self.send_header("X-GO-File-Size", str(total))
        self.send_header("X-GO-SHA256", record.result_sha256)
        self.send_header("X-GO-Chunk-Index", str(chunk_index))
        self.send_header("X-GO-Chunk-Count", str(chunk_count))
        self.send_header("X-GO-Chunk-SHA256", chunk_sha)
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.end_headers()
        if include_body:
            with path.open("rb") as stream:
                stream.seek(start)
                remaining = length
                while remaining:
                    chunk = stream.read(min(64 * 1024, remaining))
                    if not chunk:
                        raise ConnectionError("result file became truncated while sending")
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

    def _finished_record(self, task_id: str):
        record = self.server.service.registry.get(task_id)
        if record is None:
            raise KeyError(task_id)
        if record.status != TaskStatus.FINISHED.value:
            raise ValueError(f"task result is not ready: {record.status}")
        path = Path(record.result_path)
        if not path.is_file() or path.stat().st_size != record.result_size:
            raise ValueError("registered result is missing or changed")
        return record

    def _json(self, status: int, payload: Dict[str, Any], include_body: bool = True) -> None:
        if status >= 400 and "message_type" not in payload:
            payload = {"message_type": "error", **payload}
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)


def _content_length(value: Optional[str]) -> int:
    if value is None:
        raise ValueError("Content-Length is required")
    try:
        length = int(value)
    except ValueError as exc:
        raise ValueError("Content-Length is invalid") from exc
    if length < 0:
        raise ValueError("Content-Length is invalid")
    return length


def _parse_range(value: Optional[str], total: int) -> Optional[Tuple[int, int]]:
    if not value:
        return None
    match = re.fullmatch(r"bytes=(\d+)-(\d*)", value.strip())
    if not match:
        raise ValueError("unsupported Range header")
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else total - 1
    if start < 0 or end < start or start >= total or end >= total:
        raise ValueError("Range is outside result file")
    return start, end


def _sha256_range(path: Path, start: int, length: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(start)
        remaining = length
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError("result is shorter than registered size")
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def _status_message_type(record) -> str:
    if record.status == TaskStatus.FAILED.value:
        return "reconstruction_failed"
    if record.status == TaskStatus.FINISHED.value:
        return "result_ready"
    if record.status in {TaskStatus.RUNNING_COLMAP.value, TaskStatus.RUNNING_3DGS.value}:
        return "reconstruction_running"
    if record.status == TaskStatus.READY.value and record.message == "queued for reconstruction":
        return "reconstruction_queued"
    return "upload_received"
