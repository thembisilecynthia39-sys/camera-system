import cgi
import hashlib
import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import requests

from tx_rx.config import TxRxConfig
from tx_rx.jetson_client import prepare_manual_task, upload_staged_task
from tx_rx.jetson_client.transfer import (
    TransferError,
    acknowledge_result,
    download_ply,
    get_ply_metadata,
    poll_status,
)


class _State:
    ply = b"ply\n" + bytes(range(256)) * 5
    chunk_size = 257
    task_id = "task-" + "1" * 64
    capture_id = "manual_001"
    uploaded_zip = b""
    multipart_checksum = ""
    reconstruct_called = False
    ack_payload = None
    bad_chunk_hash = False
    bad_file_hash = False
    bad_file_size = False
    bad_capture_id = False
    bad_task_id = False
    truncate_chunk = False
    reconstruct_error = False
    upload_count = 0
    reconstruct_count = 0
    ranges = []
    if_ranges = []


def _handler(state):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, payload, status=200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            task_id = state.task_id
            capture_id = "wrong" if state.bad_capture_id else state.capture_id
            response_task_id = "task-wrong" if state.bad_task_id else task_id
            if self.path == "/health":
                return self._json({"status": "ok"})
            if self.path == f"/status/{task_id}":
                return self._json({
                    "message_type": "status_response", "task_id": response_task_id,
                    "capture_id": capture_id, "status": "finished", "stage": "finished",
                    "progress": 100.0, "extra_server_field": True,
                })
            if self.path == f"/result/{task_id}/metadata":
                digest = hashlib.sha256(state.ply).hexdigest()
                if state.bad_file_hash:
                    digest = "0" * 64
                size = len(state.ply) + (1 if state.bad_file_size else 0)
                return self._json({
                    "magic": "GOBJ", "version": "1.0", "message_type": "ply_result",
                    "task_id": response_task_id, "capture_id": capture_id, "filename": "3DGS.ply",
                    "file_size": size, "sha256": digest, "chunk_size": state.chunk_size,
                    "chunk_count": (size + state.chunk_size - 1) // state.chunk_size,
                    "created_at": "2026-01-01T00:00:00Z",
                })
            if self.path == f"/result/{task_id}":
                raw_range = self.headers["Range"]
                state.ranges.append(raw_range)
                state.if_ranges.append(self.headers["If-Range"])
                start, end = map(int, raw_range[len("bytes="):].split("-"))
                body = state.ply[start:end + 1]
                if state.truncate_chunk and start == 0:
                    body = body[:-1]
                digest = hashlib.sha256(body).hexdigest()
                if state.bad_chunk_hash and start == 0:
                    digest = "f" * 64
                file_hash = hashlib.sha256(state.ply).hexdigest()
                index = start // state.chunk_size
                count = (len(state.ply) + state.chunk_size - 1) // state.chunk_size
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(state.ply)}")
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("X-GO-Task-ID", task_id)
                self.send_header("X-GO-Capture-ID", state.capture_id)
                self.send_header("X-GO-Chunk-Index", str(index))
                self.send_header("X-GO-Chunk-Count", str(count))
                self.send_header("X-GO-Chunk-SHA256", digest)
                self.send_header("X-GO-File-Size", str(len(state.ply)))
                self.send_header("X-GO-SHA256", file_hash)
                self.end_headers()
                self.wfile.write(body)
                return
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            if self.path == "/upload":
                state.upload_count += 1
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers["Content-Type"]},
                )
                state.uploaded_zip = form["file"].file.read()
                state.multipart_checksum = form.getvalue("checksum")
                return self._json({
                    "message_type": "upload_received", "task_id": state.task_id,
                    "capture_id": state.capture_id, "status": "ready", "duplicate": False,
                })
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/reconstruct":
                state.reconstruct_count += 1
                state.reconstruct_called = True
                if state.reconstruct_error:
                    return self._json({"error": "simulated"}, 500)
                return self._json({
                    "message_type": "reconstruction_started", "task_id": state.task_id,
                    "capture_id": state.capture_id, "status": "queued",
                })
            if self.path == f"/result/{state.task_id}/ack":
                state.ack_payload = payload
                return self._json({
                    "message_type": "result_acknowledged", "task_id": state.task_id,
                    "capture_id": state.capture_id,
                })
            self._json({"error": "not found"}, 404)
    return Handler


@pytest.fixture
def wsl_server():
    state = _State()
    for name in ("uploaded_zip", "multipart_checksum", "ack_payload"):
        setattr(state, name, b"" if name != "ack_payload" else None)
    state.ranges = []
    state.if_ranges = []
    state.upload_count = 0
    state.reconstruct_count = 0
    for name in ("reconstruct_called", "reconstruct_error", "bad_chunk_hash", "bad_file_hash", "bad_file_size", "bad_capture_id", "bad_task_id", "truncate_chunk"):
        setattr(state, name, False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def _config(tmp_path, server_url):
    return TxRxConfig(
        schema_version="1.0", staging_root=tmp_path / "staging", server_url=server_url,
        result_root=tmp_path / "results", request_timeout_seconds=2,
        status_poll_interval_seconds=0.01, reconstruction_timeout_seconds=2,
        download_timeout_seconds=2,
    )


def _config_file(tmp_path, server_url):
    path = tmp_path / "config.yaml"
    path.write_text(
        f'schema_version: "1.0"\nstaging_root: {tmp_path / "staging"}\nserver_url: {server_url}\n'
        f'result_root: {tmp_path / "results"}\nrequest_timeout_seconds: 2\n'
        'status_poll_interval_seconds: 0.01\nreconstruction_timeout_seconds: 2\n'
        'download_timeout_seconds: 2\nmax_ply_size_bytes: 2147483648\n', encoding="utf-8"
    )
    return path


def _manual(tmp_path):
    images = tmp_path / "staging" / "manual_001" / "images"
    images.mkdir(parents=True)
    for index in range(8):
        (images / f"{index}.jpg").write_bytes(f"jpeg-{index}".encode())
    return prepare_manual_task(images.parent)


def test_real_http_upload_uses_package_checksum_and_persists_task_id(wsl_server, tmp_path):
    state, url = wsl_server
    package = _manual(tmp_path)
    result = upload_staged_task(package.staging_dir, _config_file(tmp_path, url))
    assert state.multipart_checksum == package.checksum
    with zipfile.ZipFile(io.BytesIO(state.uploaded_zip)) as archive:
        assert set(archive.namelist()) == {"task.json", "metadata.json", *(f"images/{i}.jpg" for i in range(8))}
        assert json.loads(archive.read("task.json"))["checksum"] == package.checksum
    receipt = json.loads((package.staging_dir / "upload.json").read_text())
    assert receipt["task_id"] == state.task_id
    assert state.reconstruct_called


def test_real_http_status_metadata_multirange_and_ack(wsl_server, tmp_path):
    state, url = wsl_server
    config = _config(tmp_path, url)
    status = poll_status(state.task_id, state.capture_id, config)
    assert status.progress == 100
    metadata = get_ply_metadata(state.task_id, state.capture_id, config)
    final = download_ply(metadata, config)
    assert final.read_bytes() == state.ply
    assert not final.with_suffix(".ply.part").exists()
    ack = acknowledge_result(metadata, final, config)
    assert ack.message_type == "result_acknowledged"
    assert state.ack_payload["file_size"] == len(state.ply)


def test_capture_flat_result_uses_capture_name(wsl_server, tmp_path):
    state, url = wsl_server
    config = _config(tmp_path, url).model_copy(update={"result_layout": "capture_flat"})
    metadata = get_ply_metadata(state.task_id, state.capture_id, config)

    final = download_ply(metadata, config)

    assert final == config.result_root / f"{state.capture_id}3DGS.ply"
    assert final.read_bytes() == state.ply
    assert not (config.result_root / f"{state.capture_id}3DGS.ply.part").exists()
    assert len(state.ranges) > 1
    assert state.ranges[0] == f"bytes=0-{state.chunk_size - 1}"
    assert all(value == f'"{metadata.sha256}"' for value in state.if_ranges)


def test_single_range_download(wsl_server, tmp_path):
    state, url = wsl_server
    state.chunk_size = len(state.ply) + 100
    config = _config(tmp_path, url)
    metadata = get_ply_metadata(state.task_id, state.capture_id, config)
    assert download_ply(metadata, config).read_bytes() == state.ply
    assert state.ranges == [f"bytes=0-{len(state.ply) - 1}"]


def test_upload_receipt_survives_reconstruct_failure(wsl_server, tmp_path):
    state, url = wsl_server
    state.reconstruct_error = True
    package = _manual(tmp_path)
    with pytest.raises(Exception):
        upload_staged_task(package.staging_dir, _config_file(tmp_path, url))
    receipt = json.loads((package.staging_dir / "upload.json").read_text())
    assert receipt["task_id"] == state.task_id


def test_bad_chunk_hash_keeps_only_part(wsl_server, tmp_path):
    state, url = wsl_server
    state.bad_chunk_hash = True
    metadata = get_ply_metadata(state.task_id, state.capture_id, _config(tmp_path, url))
    with pytest.raises(TransferError, match="SHA-256 mismatch"):
        download_ply(metadata, _config(tmp_path, url))
    directory = tmp_path / "results" / state.capture_id / state.task_id
    assert (directory / "3DGS.ply.part").exists()
    assert not (directory / "3DGS.ply").exists()


def test_bad_whole_file_hash_rejected(wsl_server, tmp_path):
    state, url = wsl_server
    state.bad_file_hash = True
    config = _config(tmp_path, url)
    metadata = get_ply_metadata(state.task_id, state.capture_id, config)
    with pytest.raises(TransferError):
        download_ply(metadata, config)
    assert not (config.result_root / state.capture_id / state.task_id / "3DGS.ply").exists()


def test_bad_file_size_rejected(wsl_server, tmp_path):
    state, url = wsl_server
    state.bad_file_size = True
    config = _config(tmp_path, url)
    metadata = get_ply_metadata(state.task_id, state.capture_id, config)
    with pytest.raises(TransferError):
        download_ply(metadata, config)


@pytest.mark.parametrize("field", ["bad_capture_id", "bad_task_id"])
def test_metadata_identity_mismatch_rejected(wsl_server, tmp_path, field):
    state, url = wsl_server
    setattr(state, field, True)
    with pytest.raises(TransferError, match="mismatch"):
        get_ply_metadata(state.task_id, state.capture_id, _config(tmp_path, url))


def test_cancelled_download_keeps_part(wsl_server, tmp_path):
    state, url = wsl_server
    config = _config(tmp_path, url)
    metadata = get_ply_metadata(state.task_id, state.capture_id, config)
    calls = iter([False, False, True])
    with pytest.raises(TransferError, match="cancelled"):
        download_ply(metadata, config, cancel_check=lambda: next(calls, True))
    assert not (config.result_root / state.capture_id / state.task_id / "3DGS.ply").exists()


def test_truncated_download_rejected(wsl_server, tmp_path):
    state, url = wsl_server
    state.truncate_chunk = True
    config = _config(tmp_path, url)
    metadata = get_ply_metadata(state.task_id, state.capture_id, config)
    with pytest.raises(TransferError):
        download_ply(metadata, config)
    assert not (config.result_root / state.capture_id / state.task_id / "3DGS.ply").exists()


def test_status_request_timeout_has_clear_error(tmp_path):
    class TimeoutSession:
        def get(self, *args, **kwargs):
            raise requests.Timeout("simulated timeout")

    config = _config(tmp_path, "http://wsl-host:8000")
    with pytest.raises(TransferError, match="cannot query status"):
        poll_status(_State.task_id, _State.capture_id, config, TimeoutSession())


def test_status_cancelled_before_request(tmp_path):
    config = _config(tmp_path, "http://wsl-host:8000")
    with pytest.raises(TransferError, match="cancelled"):
        poll_status(_State.task_id, _State.capture_id, config, cancel_check=lambda: True)


def test_repeat_download_is_idempotent(wsl_server, tmp_path):
    state, url = wsl_server
    config = _config(tmp_path, url)
    metadata = get_ply_metadata(state.task_id, state.capture_id, config)
    first = download_ply(metadata, config)
    second = download_ply(metadata, config, cancel_check=lambda: True)
    assert first == second
