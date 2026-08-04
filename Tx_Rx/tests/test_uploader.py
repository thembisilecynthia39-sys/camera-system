from pathlib import Path
import json
import zipfile

import pytest
import requests

from tx_rx.config import load_config
from tx_rx.jetson_client import (
    CaptureDataError,
    TaskUploadError,
    check_health,
    prepare_manual_task,
    upload_staged_task,
)


class _Response:
    def __init__(self, payload=None, error=None):
        self._payload = payload or {}
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error

    def json(self):
        return self._payload


class _Session:
    def __init__(self):
        self.calls = []
        self.archive_names = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return _Response({"status": "ok"})

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url.endswith("/upload"):
            stream = kwargs["files"]["file"][1]
            with zipfile.ZipFile(stream) as archive:
                self.archive_names = sorted(archive.namelist())
            return _Response({
                "message_type": "upload_received", "task_id": "task-server-1",
                "capture_id": "manual_001", "status": "ready", "duplicate": False,
            })
        return _Response({
            "message_type": "reconstruction_started", "task_id": "task-server-1",
            "capture_id": "manual_001", "status": "queued",
        })


def _task(root: Path) -> Path:
    images = root / "manual_001" / "images"
    images.mkdir(parents=True)
    for index in range(8):
        (images / f"{index}.jpg").write_bytes(f"image-{index}".encode())
    return prepare_manual_task(images.parent).staging_dir


def _config(path: Path, staging_root: Path) -> Path:
    path.write_text(
        f'schema_version: "1.0"\nstaging_root: {staging_root}\n'
        'server_url: http://wsl-host:8000\nupload_timeout_seconds: 30\n',
        encoding="utf-8",
    )
    return path


def test_uploader_accepts_validated_staging_and_starts_reconstruction(tmp_path):
    staging_dir = _task(tmp_path / "staging")
    config = _config(tmp_path / "config.yaml", tmp_path / "staging")
    session = _Session()

    result = upload_staged_task(staging_dir, config, session)

    assert result.task_id == "task-server-1"
    assert [(method, url) for method, url, _ in session.calls] == [
        ("GET", "http://wsl-host:8000/health"),
        ("POST", "http://wsl-host:8000/upload"),
        ("POST", "http://wsl-host:8000/reconstruct"),
    ]
    assert session.calls[-1][2]["json"] == {"task_id": "task-server-1"}
    assert session.archive_names == [
        "images/0.jpg",
        "images/1.jpg",
        "images/2.jpg",
        "images/3.jpg",
        "images/4.jpg",
        "images/5.jpg",
        "images/6.jpg",
        "images/7.jpg",
        "metadata.json",
        "task.json",
    ]
    receipt = json.loads((staging_dir / "upload.json").read_text(encoding="utf-8"))
    assert receipt["task_id"] == "task-server-1"
    assert receipt["checksum"] == result.checksum
    assert receipt["server_url"] == "http://wsl-host:8000"


def test_health_timeout_checks_cancellation_between_short_attempts(tmp_path):
    config_path = _config(tmp_path / "config.yaml", tmp_path / "staging")
    config = load_config(config_path)

    class TimeoutSession:
        def __init__(self):
            self.calls = 0

        def get(self, *_args, **_kwargs):
            self.calls += 1
            raise requests.Timeout("simulated timeout")

    session = TimeoutSession()
    checks = iter((False, True))

    with pytest.raises(TaskUploadError, match="cancelled"):
        check_health(
            config,
            session,
            cancel_check=lambda: next(checks, True),
        )

    assert session.calls == 1


def test_staged_upload_honors_cancellation_before_network(tmp_path):
    staging_dir = _task(tmp_path / "staging")
    config = _config(tmp_path / "config.yaml", tmp_path / "staging")
    session = _Session()

    with pytest.raises(TaskUploadError, match="upload cancelled"):
        upload_staged_task(
            staging_dir,
            config,
            session,
            cancel_check=lambda: True,
        )

    assert session.calls == []


def test_staged_upload_honors_cancellation_before_reconstruction(tmp_path):
    staging_dir = _task(tmp_path / "staging")
    config = _config(tmp_path / "config.yaml", tmp_path / "staging")
    cancelled = False

    class CancelAfterUploadSession(_Session):
        def post(self, url, **kwargs):
            nonlocal cancelled
            response = super().post(url, **kwargs)
            if url.endswith("/upload"):
                cancelled = True
            return response

    session = CancelAfterUploadSession()

    with pytest.raises(TaskUploadError, match="upload cancelled"):
        upload_staged_task(
            staging_dir,
            config,
            session,
            cancel_check=lambda: cancelled,
        )

    assert [(method, url) for method, url, _ in session.calls] == [
        ("GET", "http://wsl-host:8000/health"),
        ("POST", "http://wsl-host:8000/upload"),
    ]


def test_uploader_accepts_duplicate_task_that_is_already_finished(tmp_path):
    staging_dir = _task(tmp_path / "staging")
    config = _config(tmp_path / "config.yaml", tmp_path / "staging")

    class FinishedDuplicateSession(_Session):
        def post(self, url, **kwargs):
            if url.endswith("/upload"):
                return _Response({
                    "message_type": "upload_received",
                    "task_id": "task-server-1",
                    "capture_id": "manual_001",
                    "status": "finished",
                    "duplicate": True,
                })
            return _Response({
                "message_type": "result_ready",
                "task_id": "task-server-1",
                "capture_id": "manual_001",
                "status": "finished",
            })

    result = upload_staged_task(staging_dir, config, FinishedDuplicateSession())

    assert result.upload_response.duplicate is True
    assert result.upload_response.status == "finished"
    assert result.reconstruct_response.status == "finished"


def test_uploader_rejects_nonduplicate_finished_upload(tmp_path):
    staging_dir = _task(tmp_path / "staging")
    config = _config(tmp_path / "config.yaml", tmp_path / "staging")

    class InvalidFinishedSession(_Session):
        def post(self, url, **kwargs):
            if url.endswith("/upload"):
                return _Response({
                    "message_type": "upload_received",
                    "task_id": "task-server-1",
                    "capture_id": "manual_001",
                    "status": "finished",
                    "duplicate": False,
                })
            return super().post(url, **kwargs)

    with pytest.raises(TaskUploadError, match="unexpected upload status 'finished'"):
        upload_staged_task(staging_dir, config, InvalidFinishedSession())


def test_uploader_rejects_unprepared_directory_before_network(tmp_path):
    task_dir = tmp_path / "staging" / "manual_001"
    task_dir.mkdir(parents=True)
    session = _Session()
    config = _config(tmp_path / "config.yaml", tmp_path / "staging")

    with pytest.raises(CaptureDataError):
        upload_staged_task(task_dir, config, session)

    assert session.calls == []


def test_uploader_requires_server_task_id(tmp_path):
    staging_dir = _task(tmp_path / "staging")
    config = _config(tmp_path / "config.yaml", tmp_path / "staging")

    class MissingIdSession(_Session):
        def post(self, url, **kwargs):
            if url.endswith("/upload"):
                return _Response({})
            return super().post(url, **kwargs)

    with pytest.raises(TaskUploadError, match="invalid /upload response"):
        upload_staged_task(staging_dir, config, MissingIdSession())
