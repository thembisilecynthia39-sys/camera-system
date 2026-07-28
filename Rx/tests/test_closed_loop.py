from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import socket
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from typing import Optional

import requests

from gaussianobject_tx.config import TxRxConfig
from gaussianobject_tx.client.result_client import ResultDownloadError, ResultReceiver
from gaussianobject_tx.client.simulate import _fragmented_pipelined_upload
from gaussianobject_tx.client.task_manifest import prepare_manual_task
from gaussianobject_tx.client.uploader import _create_task_archive, upload_staged_task
from gaussianobject_rx.protocol.models import TaskStatus
from gaussianobject_rx.server.application import ReceiverApplication
from gaussianobject_rx.server.config import ReceiverConfig
from gaussianobject_rx.server.files import sha256_file


def _jpeg(width: int = 16, height: int = 12, marker: int = 0) -> bytes:
    component_data = bytes([1, 0x11, 0, 2, 0x11, 0, 3, 0x11, marker & 0xFF])
    sof_data = bytes([8]) + height.to_bytes(2, "big") + width.to_bytes(2, "big") + bytes([3]) + component_data
    return b"\xff\xd8\xff\xc0" + (len(sof_data) + 2).to_bytes(2, "big") + sof_data + b"\xff\xd9"


def _make_task(root: Path, capture_id: str, marker: int = 0) -> Path:
    images = root / capture_id / "images"
    images.mkdir(parents=True)
    for index in range(8):
        (images / f"{index}.jpg").write_bytes(_jpeg(marker=marker + index))
    return prepare_manual_task(images.parent).staging_dir


def _write_fake_baseline(path: Path, sleep_seconds: float = 0.0) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import os
import pathlib
import sys
import time

print('running sparse-view SfM', flush=True)
time.sleep(float(os.environ.get('FAKE_BASELINE_SLEEP', '0')))
print('training one baseline model', flush=True)
if int(os.environ.get('FAKE_BASELINE_EXIT', '0')):
    print('simulated baseline failure', flush=True)
    sys.exit(int(os.environ['FAKE_BASELINE_EXIT']))
task_id = os.environ['SCENE_NAME']
iterations = int(sys.argv[3])
run_name = os.environ['RUN_NAME']
output = pathlib.Path(os.environ['OUT_ROOT']) / task_id / (run_name + '_shsharp_scale101') / 'point_cloud' / ('iteration_' + str(iterations)) / 'point_cloud.ply'
output.parent.mkdir(parents=True, exist_ok=True)
size = int(os.environ.get('FAKE_PLY_SIZE', '4096'))
header = b'ply\\nformat binary_little_endian 1.0\\ncomment fake reconstruction\\nend_header\\n'
with output.open('wb') as stream:
    stream.write(header)
    remaining = max(0, size - len(header))
    block = bytes(range(256)) * 256
    while remaining:
        chunk = block[:min(len(block), remaining)]
        stream.write(chunk)
        remaining -= len(chunk)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _wait_for_status(server_url: str, task_id: str, status: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        response = requests.get(f"{server_url}/status/{task_id}", timeout=2)
        response.raise_for_status()
        last = response.json()
        if last["status"] == status:
            return last
        if last["status"] == TaskStatus.FAILED.value:
            raise AssertionError(last)
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {status}: {last}")


class _InterruptedResponse:
    def __init__(self, response, truncate: bool = False):
        self._response = response
        self.status_code = response.status_code
        self.headers = response.headers
        self._truncate = truncate

    def raise_for_status(self):
        return self._response.raise_for_status()

    def json(self):
        return self._response.json()

    def iter_content(self, chunk_size=1):
        iterator = self._response.iter_content(chunk_size=chunk_size)
        first = next(iterator)
        if not self._truncate:
            yield first
        self._response.close()
        raise requests.ConnectionError("simulated transfer interruption")


class _InterruptingSession:
    def __init__(self, truncate_every_time: bool = False):
        self.inner = requests.Session()
        self.interrupted = False
        self.truncate_every_time = truncate_every_time

    def get(self, url, **kwargs):
        response = self.inner.get(url, **kwargs)
        if "/result/" in url and not url.endswith("/metadata"):
            if self.truncate_every_time or not self.interrupted:
                self.interrupted = True
                return _InterruptedResponse(response, truncate=self.truncate_every_time)
        return response

    def close(self):
        self.inner.close()


class ClosedLoopTests(unittest.TestCase):
    def setUp(self):
        self.previous_no_proxy = os.environ.get("NO_PROXY")
        self.previous_no_proxy_lower = os.environ.get("no_proxy")
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.baseline = self.root / "fake_baseline"
        _write_fake_baseline(self.baseline)
        self.application = self._application()
        self.application.start()

    def tearDown(self):
        os.environ.pop("FAKE_PLY_SIZE", None)
        os.environ.pop("FAKE_BASELINE_SLEEP", None)
        os.environ.pop("FAKE_BASELINE_EXIT", None)
        if self.application is not None:
            self.application.stop()
        self.temp.cleanup()
        if self.previous_no_proxy is None:
            os.environ.pop("NO_PROXY", None)
        else:
            os.environ["NO_PROXY"] = self.previous_no_proxy
        if self.previous_no_proxy_lower is None:
            os.environ.pop("no_proxy", None)
        else:
            os.environ["no_proxy"] = self.previous_no_proxy_lower

    def _application(self, queue_size: int = 4) -> ReceiverApplication:
        return ReceiverApplication(
            ReceiverConfig(
                listen_host="127.0.0.1",
                listen_port=0,
                task_root=self.root / "rx_tasks",
                baseline_path=self.baseline,
                baseline_iterations=500,
                reconstruction_queue_size=queue_size,
                max_upload_size_bytes=8 * 1024 * 1024,
                max_extracted_size_bytes=16 * 1024 * 1024,
                max_ply_size_bytes=16 * 1024 * 1024,
                result_chunk_size_bytes=64 * 1024,
                request_timeout_seconds=5,
                reconstruction_timeout_seconds=20,
                process_stop_timeout_seconds=2,
            )
        )

    def _tx_config(self, result_root: Optional[Path] = None) -> TxRxConfig:
        return TxRxConfig(
            schema_version="1.0",
            staging_root=self.root / "staging",
            server_url=self.application.server_url,
            upload_timeout_seconds=5,
            result_root=result_root or self.root / "jetson_results",
            status_poll_interval_seconds=0.05,
            result_timeout_seconds=10,
            result_chunk_size_bytes=64 * 1024,
            max_result_size_bytes=16 * 1024 * 1024,
        )

    def _upload(self, capture_id: str, marker: int = 0):
        staging = _make_task(self.root / "staging", capture_id, marker)
        config_path = self.root / f"{capture_id}.yaml"
        config = self._tx_config()
        config_path.write_text(
            "\n".join(
                [
                    'schema_version: "1.0"',
                    f"staging_root: {config.staging_root}",
                    f"server_url: {config.server_url}",
                    "upload_timeout_seconds: 5",
                    f"result_root: {config.result_root}",
                    "status_poll_interval_seconds: 0.05",
                    "result_timeout_seconds: 10",
                    "result_chunk_size_bytes: 65536",
                    "max_result_size_bytes: 16777216",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return staging, upload_staged_task(staging, config_path)

    def _upload_only(self, capture_id: str, marker: int = 0, source: str = "upload_only") -> dict:
        staging = _make_task(self.root / source, capture_id, marker)
        package = prepare_manual_task(staging)
        archive = _create_task_archive(package)
        try:
            with archive.open("rb") as stream:
                response = requests.post(
                    f"{self.application.server_url}/upload",
                    files={"file": (f"{capture_id}.zip", stream, "application/zip")},
                    data={"checksum": package.checksum},
                    timeout=5,
                )
            response.raise_for_status()
            return response.json()
        finally:
            archive.unlink(missing_ok=True)

    def test_tx_upload_baseline_input_small_result_and_atomic_receive(self):
        staging, uploaded = self._upload("capture_001")
        record = self.application.service.registry.get(uploaded.task_id)
        self.assertEqual(record.capture_id, "capture_001")
        self.assertEqual(Path(record.task_dir).name, "capture_001")
        self.assertEqual(sorted(path.name for path in Path(record.input_dir).iterdir()), [f"{i}.jpg" for i in range(8)])

        receiver = ResultReceiver(self._tx_config())
        result = receiver.wait_and_download(uploaded.task_id, "capture_001")
        self.assertEqual(result.ply_path.name, "capture_0013DGS.ply")
        self.assertTrue(result.ply_path.is_file())
        self.assertFalse(result.ply_path.with_suffix(".ply.part").exists())
        self.assertEqual(result.sha256, sha256_file(result.ply_path))
        self.assertTrue((staging / "upload.json").is_file())
        ack = requests.post(
            f"{self.application.server_url}/result/{uploaded.task_id}/ack",
            json={
                "magic": "GOBJ",
                "version": "1.0",
                "message_type": "result_received",
                "task_id": uploaded.task_id,
                "capture_id": "capture_001",
                "filename": "3DGS.ply",
                "file_size": result.size_bytes,
                "sha256": result.sha256,
            },
            timeout=5,
        )
        self.assertEqual(ack.status_code, 200, ack.text)
        self.assertEqual(ack.json()["message_type"], "result_acknowledged")
        self.assertTrue(self.application.service.registry.get(uploaded.task_id).result_acknowledged_at)

    def test_upload_automatically_starts_reconstruction_without_reconstruct_request(self):
        uploaded = self._upload_only("capture_auto")
        status = _wait_for_status(
            self.application.server_url,
            uploaded["task_id"],
            TaskStatus.FINISHED.value,
        )
        self.assertEqual(status["capture_id"], "capture_auto")
        self.assertTrue(Path(status["output_ply"]).is_file())

    def test_same_capture_id_uses_readable_numbered_task_directories(self):
        first = self._upload_only("book", marker=1)
        second = self._upload_only("book", marker=2, source="upload_only_second")

        first_record = self.application.service.registry.get(first["task_id"])
        second_record = self.application.service.registry.get(second["task_id"])
        self.assertEqual(Path(first_record.task_dir).name, "book")
        self.assertEqual(Path(second_record.task_dir).name, "book-2")

    def test_result_callback_runs_only_after_verified_ply_is_published(self):
        _, uploaded = self._upload("capture_callback")
        callbacks = []

        def result_ready(result):
            callbacks.append((result.task_id, result.ply_path, result.ply_path.is_file()))

        receiver = ResultReceiver(self._tx_config(), result_callback=result_ready)
        result = receiver.wait_and_download(uploaded.task_id, "capture_callback")
        self.assertEqual(callbacks, [(uploaded.task_id, result.ply_path, True)])

    def test_two_consecutive_capture_ids_and_same_filename_are_isolated(self):
        _, first = self._upload("capture_A", marker=1)
        _, second = self._upload("capture_B", marker=50)
        receiver = ResultReceiver(self._tx_config())
        result_a = receiver.wait_and_download(first.task_id, "capture_A")
        result_b = receiver.wait_and_download(second.task_id, "capture_B")
        self.assertNotEqual(result_a.ply_path, result_b.ply_path)
        self.assertEqual(result_a.ply_path.name, "capture_A3DGS.ply")
        self.assertEqual(result_b.ply_path.name, "capture_B3DGS.ply")
        self.assertTrue(result_a.ply_path.is_file())
        self.assertTrue(result_b.ply_path.is_file())

    def test_large_result_is_downloaded_in_multiple_ranges(self):
        os.environ["FAKE_PLY_SIZE"] = str(320 * 1024 + 17)
        _, uploaded = self._upload("capture_large")
        session = requests.Session()
        calls = []
        original_get = session.get

        def recording_get(url, **kwargs):
            if "/result/" in url and not url.endswith("/metadata"):
                calls.append(kwargs.get("headers", {}).get("Range"))
            return original_get(url, **kwargs)

        session.get = recording_get
        result = ResultReceiver(self._tx_config(), session=session).wait_and_download(
            uploaded.task_id, "capture_large"
        )
        self.assertEqual(result.size_bytes, 320 * 1024 + 17)
        self.assertGreater(len(calls), 1)
        self.assertTrue(all(value and value.startswith("bytes=") for value in calls))

    def test_interrupted_result_chunk_is_retried_without_publishing_part(self):
        os.environ["FAKE_PLY_SIZE"] = str(160 * 1024)
        _, uploaded = self._upload("capture_resume")
        session = _InterruptingSession()
        result = ResultReceiver(self._tx_config(), session=session).wait_and_download(
            uploaded.task_id, "capture_resume"
        )
        self.assertTrue(session.interrupted)
        self.assertTrue(result.ply_path.is_file())
        self.assertFalse(result.ply_path.with_suffix(".ply.part").exists())

    def test_repeated_truncation_fails_and_never_creates_ply(self):
        _, uploaded = self._upload("capture_truncated")
        _wait_for_status(self.application.server_url, uploaded.task_id, TaskStatus.FINISHED.value)
        result_root = self.root / "truncated_results"
        receiver = ResultReceiver(
            self._tx_config(result_root),
            session=_InterruptingSession(truncate_every_time=True),
        )
        with self.assertRaises(ResultDownloadError):
            receiver.download(uploaded.task_id, "capture_truncated")
        self.assertFalse(any(result_root.rglob("*.ply")))

    def test_sha_mismatch_marks_part_corrupt(self):
        _, uploaded = self._upload("capture_bad_hash")
        _wait_for_status(self.application.server_url, uploaded.task_id, TaskStatus.FINISHED.value)
        record = self.application.service.registry.get(uploaded.task_id)
        result_path = Path(record.result_path)
        data = bytearray(result_path.read_bytes())
        data[-1] ^= 0xFF
        result_path.write_bytes(data)
        result_root = self.root / "bad_hash_results"
        with self.assertRaises(ResultDownloadError):
            ResultReceiver(self._tx_config(result_root)).download(uploaded.task_id, "capture_bad_hash")
        self.assertFalse(any(result_root.rglob("capture_bad_hash3DGS.ply")))
        self.assertTrue(any(result_root.rglob("*.corrupt-*")))

    def test_existing_same_name_corrupt_result_is_preserved_then_replaced(self):
        _, uploaded = self._upload("capture_existing")
        _wait_for_status(self.application.server_url, uploaded.task_id, TaskStatus.FINISHED.value)
        config = self._tx_config()
        destination = config.result_root / "capture_existing3DGS.ply"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"old corrupt result")
        result = ResultReceiver(config).download(uploaded.task_id, "capture_existing")
        self.assertTrue(result.ply_path.is_file())
        self.assertTrue(any(destination.parent.glob("capture_existing3DGS.ply.corrupt-*")))

    def test_missing_image_archive_is_rejected(self):
        staging = _make_task(self.root / "missing", "capture_missing")
        package = prepare_manual_task(staging)
        original = _create_task_archive(package)
        broken = self.root / "missing.zip"
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(broken, "w") as output:
            for info in source.infolist():
                if info.filename != "images/7.jpg":
                    output.writestr(info, source.read(info.filename))
        with broken.open("rb") as stream:
            response = requests.post(
                f"{self.application.server_url}/upload",
                files={"file": ("missing.zip", stream, "application/zip")},
                data={"checksum": package.checksum},
                timeout=5,
            )
        self.assertEqual(response.status_code, 400)
        original.unlink()

    def test_shuffled_manifest_and_zip_order_are_aggregated_by_index(self):
        staging = _make_task(self.root / "shuffled", "capture_shuffled")
        package = prepare_manual_task(staging)
        manifest = package.manifest.model_dump(mode="json")
        manifest["images"] = list(reversed(manifest["images"]))
        archive_path = self.root / "shuffled.zip"
        paths = list(reversed(package.manifest.files))
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in paths:
                archive.write(staging / item.relative_path, item.relative_path)
            archive.writestr("task.json", json.dumps(manifest))
        with archive_path.open("rb") as stream:
            response = requests.post(
                f"{self.application.server_url}/upload",
                files={"file": ("shuffled.zip", stream, "application/zip")},
                data={"checksum": package.checksum},
                timeout=5,
            )
        self.assertEqual(response.status_code, 200, response.text)
        record = self.application.service.registry.get(response.json()["task_id"])
        self.assertEqual(sorted(path.name for path in Path(record.input_dir).iterdir()), [f"{i}.jpg" for i in range(8)])

    def test_fragmented_raw_http_upload_handles_tcp_packet_boundaries(self):
        staging = _make_task(self.root / "fragmented", "capture_fragmented")
        package = prepare_manual_task(staging)
        archive = _create_task_archive(package)
        boundary = "fragment-boundary-123"
        body = io.BytesIO()
        body.write(f"--{boundary}\r\n".encode())
        body.write(b'Content-Disposition: form-data; name="checksum"\r\n\r\n')
        body.write(package.checksum.encode())
        body.write(f"\r\n--{boundary}\r\n".encode())
        body.write(b'Content-Disposition: form-data; name="file"; filename="capture.zip"\r\n')
        body.write(b"Content-Type: application/zip\r\n\r\n")
        body.write(archive.read_bytes())
        body.write(f"\r\n--{boundary}--\r\n".encode())
        payload = body.getvalue()
        host, port = self.application.address[:2]
        with socket.create_connection((host, port), timeout=5) as connection:
            headers = (
                "POST /upload HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode()
            wire = headers + payload
            positions = [1, 2, 7, 31, 3, 4096, 13, 65536]
            offset = 0
            index = 0
            while offset < len(wire):
                size = positions[index % len(positions)]
                connection.sendall(wire[offset : offset + size])
                offset += size
                index += 1
            response = bytearray()
            while True:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)
        self.assertIn(b"HTTP/1.1 200", response)
        archive.unlink()

    def test_fragmented_upload_and_pipelined_reconstruct_are_framed_independently(self):
        staging = _make_task(self.root / "pipelined", "capture_pipelined")
        package = prepare_manual_task(staging)
        archive = _create_task_archive(package)
        try:
            upload, reconstruct = _fragmented_pipelined_upload(
                self.application.server_url,
                archive,
                package.checksum,
            )
        finally:
            archive.unlink(missing_ok=True)
        self.assertEqual(upload["message_type"], "upload_received")
        self.assertEqual(reconstruct["message_type"], "reconstruction_queued")
        self.assertEqual(upload["task_id"], reconstruct["task_id"])

    def test_duplicate_listener_reports_address_in_use_and_keeps_first_server_alive(self):
        host, port = self.application.address[:2]
        conflicting = ReceiverConfig(
            **{
                **self.application.config.model_dump(),
                "listen_host": host,
                "listen_port": port,
                "task_root": self.root / "conflicting_tasks",
            }
        )
        with self.assertRaises(OSError) as raised:
            ReceiverApplication(conflicting)
        self.assertIn(raised.exception.errno, {48, 98, 10048})
        health = requests.get(f"{self.application.server_url}/health", timeout=2)
        self.assertEqual(health.status_code, 200)

    def test_stop_releases_http_thread_worker_process_and_port(self):
        os.environ["FAKE_BASELINE_SLEEP"] = "30"
        _, uploaded = self._upload("capture_stop")
        _wait_for_status(self.application.server_url, uploaded.task_id, TaskStatus.RUNNING_COLMAP.value)
        host, port = self.application.address[:2]
        application = self.application
        self.application = None
        application.stop()
        self.assertFalse(application._thread.is_alive())
        self.assertFalse(application.service.reconstruction._thread.is_alive())
        with self.assertRaises(OSError):
            socket.create_connection((host, port), timeout=0.2)

    def test_restart_automatically_resumes_interrupted_reconstruction(self):
        os.environ["FAKE_BASELINE_SLEEP"] = "30"
        uploaded = self._upload_only("capture_restart")
        _wait_for_status(
            self.application.server_url,
            uploaded["task_id"],
            TaskStatus.RUNNING_COLMAP.value,
        )
        self.application.stop()
        os.environ.pop("FAKE_BASELINE_SLEEP", None)
        self.application = self._application()
        self.application.start()
        status = _wait_for_status(
            self.application.server_url,
            uploaded["task_id"],
            TaskStatus.FINISHED.value,
        )
        self.assertTrue(Path(status["output_ply"]).is_file())

    def test_reconstruction_failure_returns_capture_id_and_short_error(self):
        os.environ["FAKE_BASELINE_EXIT"] = "7"
        _, uploaded = self._upload("capture_failure")
        status = _wait_for_status(
            self.application.server_url,
            uploaded.task_id,
            TaskStatus.FAILED.value,
        )
        self.assertEqual(status["capture_id"], "capture_failure")
        self.assertIn("baseline exited with code 7", status["error"])
        self.assertLessEqual(len(status["log_summary"].encode("utf-8")), 16 * 1024)

    def test_bounded_queue_rejects_third_waiting_task(self):
        self.application.stop()
        self.application = self._application(queue_size=1)
        self.application.start()
        os.environ["FAKE_BASELINE_SLEEP"] = "30"
        first = self._upload_only("capture_queue_1", marker=1)
        _wait_for_status(
            self.application.server_url,
            first["task_id"],
            TaskStatus.RUNNING_COLMAP.value,
        )
        second = self._upload_only("capture_queue_2", marker=20)
        self.assertTrue(second["reconstruction_queued"])
        with self.assertRaises(requests.HTTPError) as raised:
            self._upload_only("capture_queue_3", marker=40)
        self.assertEqual(raised.exception.response.status_code, 503)
        self.assertEqual(raised.exception.response.json()["error"], "queue_full")


if __name__ == "__main__":
    unittest.main()
