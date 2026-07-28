"""Integration tests for the unified application's Tx_Rx boundary."""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from camera_system_app.application.reconstruction_service import (
    ReconstructionWorkflow,
)
from camera_system_app.bootstrap import build_context
from camera_system_app.domain import (
    ACTIVE_STATES,
    CaptureCompletedEvent,
    ReconstructionState,
)
from camera_system_app.infrastructure.reconstruction_repository import (
    ReconstructionJobRepository,
)
from camera_system_app.workers import TransferWorker
from camera_system_app.ui.pages import TransferReconstructionPage
from Tx_Rx.tests.test_http_protocol import _State, _handler


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def mock_wsl():
    state = _State()
    state.uploaded_zip = b""
    state.multipart_checksum = ""
    state.ack_payload = None
    state.ranges = []
    state.if_ranges = []
    state.upload_count = 0
    state.reconstruct_count = 0
    for name in (
        "reconstruct_called",
        "reconstruct_error",
        "bad_chunk_hash",
        "bad_file_hash",
        "bad_file_size",
        "bad_capture_id",
        "bad_task_id",
        "truncate_chunk",
    ):
        setattr(state, name, False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, "http://127.0.0.1:{}".format(server.server_port)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def _workflow(tmp_path: Path, server_url: str):
    context = build_context(
        project_root=str(PROJECT_ROOT),
        config_file=str(tmp_path / "config" / "settings.json"),
    )
    settings = replace(
        context.settings,
        wsl_service_url=server_url,
        transfer_staging_root=str(tmp_path / "staging"),
        result_root=str(tmp_path / "results"),
        request_timeout_seconds=2,
        upload_timeout_seconds=2,
        status_poll_interval_seconds=0.01,
        reconstruction_timeout_seconds=2,
        download_timeout_seconds=2,
    )
    repository = ReconstructionJobRepository(tmp_path / "state")
    return ReconstructionWorkflow(PROJECT_ROOT, settings, repository), repository


def _capture(tmp_path: Path) -> CaptureCompletedEvent:
    capture = tmp_path / _State.capture_id
    images = capture / "images"
    images.mkdir(parents=True)
    for index in range(8):
        (images / "{}.jpg".format(index)).write_bytes(
            b"jpeg-" + bytes([index])
        )
    return CaptureCompletedEvent(capture, "manual")


def test_complete_flow_streams_progress_and_persists_local_result(
    mock_wsl, tmp_path
):
    state, url = mock_wsl
    workflow, repository = _workflow(tmp_path, url)
    job = workflow.register_capture(_capture(tmp_path))
    uploads, downloads = [], []

    event = workflow.execute(
        job.job_id,
        upload_callback=lambda sent, total: uploads.append((sent, total)),
        download_callback=lambda received, total: downloads.append((received, total)),
    )

    saved = repository.get(job.job_id)
    assert saved.state is ReconstructionState.COMPLETED
    assert event.local_path == saved.result_path
    assert event.local_path.read_bytes() == state.ply
    assert not Path(str(event.local_path) + ".part").exists()
    assert uploads and uploads[-1][0] == uploads[-1][1]
    assert downloads and downloads[-1] == (len(state.ply), len(state.ply))
    assert state.upload_count == 1
    assert state.reconstruct_count == 1
    assert state.ack_payload["sha256"] == event.sha256


def test_capture_registration_and_completed_execution_are_idempotent(
    mock_wsl, tmp_path
):
    state, url = mock_wsl
    workflow, repository = _workflow(tmp_path, url)
    capture = _capture(tmp_path)
    first = workflow.register_capture(capture)
    assert workflow.register_capture(capture).job_id == first.job_id

    workflow.execute(first.job_id)
    workflow.execute(first.job_id)

    assert state.upload_count == 1
    assert state.reconstruct_count == 1
    assert len(repository.all()) == 1


def test_manual_eight_image_selection_is_persisted_as_ready_task(tmp_path):
    workflow, repository = _workflow(tmp_path, "http://127.0.0.1:1")
    source = tmp_path / "manual"
    source.mkdir()
    selected = []
    for index in range(8):
        path = source / "view-{:02d}.jpg".format(7 - index)
        path.write_bytes(b"jpeg-" + bytes([index]))
        selected.append(path)

    job = workflow.import_manual_images(selected)

    saved = repository.get(job.job_id)
    manifest = json.loads((saved.staging_dir / "task.json").read_text())
    assert saved.state is ReconstructionState.READY
    assert saved.capture_dir == saved.staging_dir
    assert manifest["angles"] == [0, 45, 90, 135, 180, 225, 270, 315]
    assert [item["filename"] for item in manifest["images"]] == [
        "{}.jpg".format(index) for index in range(8)
    ]
    assert all(
        (saved.staging_dir / "images" / "{}.jpg".format(index)).is_file()
        for index in range(8)
    )
    assert (saved.staging_dir / "images" / "0.jpg").read_bytes() == b"jpeg-\x07"


def test_manual_image_names_use_natural_numeric_order(tmp_path):
    workflow, _ = _workflow(tmp_path, "http://127.0.0.1:1")
    source = tmp_path / "manual"
    source.mkdir()
    names = ("8.jpg", "1.jpg", "10.jpg", "2.jpg", "3.jpg", "4.jpg", "5.jpg", "6.jpg")
    selected = []
    for name in names:
        path = source / name
        path.write_bytes(name.encode("ascii"))
        selected.append(path)

    job = workflow.import_manual_images(selected)

    copied = [
        (job.staging_dir / "images" / "{}.jpg".format(index)).read_bytes().decode("ascii")
        for index in range(8)
    ]
    assert copied == [
        "1.jpg",
        "2.jpg",
        "3.jpg",
        "4.jpg",
        "5.jpg",
        "6.jpg",
        "8.jpg",
        "10.jpg",
    ]


def test_manual_selection_rejects_non_eight_image_count(tmp_path):
    workflow, repository = _workflow(tmp_path, "http://127.0.0.1:1")
    source = tmp_path / "manual"
    source.mkdir()
    selected = []
    for index in range(7):
        path = source / "{}.jpg".format(index)
        path.write_bytes(b"jpeg")
        selected.append(path)

    with pytest.raises(Exception, match="八张"):
        workflow.import_manual_images(selected)

    assert repository.all() == []


def test_completed_result_is_rehashed_before_fast_return(mock_wsl, tmp_path):
    _, url = mock_wsl
    workflow, repository = _workflow(tmp_path, url)
    job = workflow.register_capture(_capture(tmp_path))
    event = workflow.execute(job.job_id)
    event.local_path.write_bytes(b"tampered")

    with pytest.raises(Exception, match="完整性校验失败"):
        workflow.execute(job.job_id)

    assert repository.get(job.job_id).state is ReconstructionState.FAILED


def test_restart_marks_interrupted_job_retryable(mock_wsl, tmp_path):
    _, url = mock_wsl
    workflow, repository = _workflow(tmp_path, url)
    job = workflow.register_capture(_capture(tmp_path))
    repository.save(
        job.changed(
            state=next(iter(ACTIVE_STATES)),
            stage_message="running",
        )
    )

    restored = workflow.restore()

    assert restored[0].state is ReconstructionState.INTERRUPTED
    assert "重试" in restored[0].stage_message


def test_hash_failure_is_persisted_and_keeps_only_temporary_file(
    mock_wsl, tmp_path
):
    state, url = mock_wsl
    state.bad_chunk_hash = True
    workflow, repository = _workflow(tmp_path, url)
    job = workflow.register_capture(_capture(tmp_path))

    with pytest.raises(Exception, match="SHA-256"):
        workflow.execute(job.job_id)

    saved = repository.get(job.job_id)
    result_dir = Path(workflow.settings.result_root) / saved.capture_id / state.task_id
    assert saved.state is ReconstructionState.FAILED
    assert (result_dir / "3DGS.ply.part").exists()
    assert not (result_dir / "3DGS.ply").exists()


def test_failed_connection_can_retry_without_duplicate_remote_work(mock_wsl, tmp_path):
    state, url = mock_wsl
    workflow, repository = _workflow(tmp_path, "http://127.0.0.1:1")
    job = workflow.register_capture(_capture(tmp_path))

    with pytest.raises(Exception):
        workflow.execute(job.job_id)
    assert repository.get(job.job_id).state is ReconstructionState.FAILED

    workflow.settings = replace(workflow.settings, wsl_service_url=url)
    event = workflow.execute(job.job_id)

    assert event.local_path.is_file()
    assert repository.get(job.job_id).attempts == 2
    assert state.upload_count == 1
    assert state.reconstruct_count == 1


def test_transfer_worker_runs_complete_network_flow_off_main_thread(
    mock_wsl, tmp_path, qapp
):
    _, url = mock_wsl
    workflow, repository = _workflow(tmp_path, url)
    job = workflow.register_capture(_capture(tmp_path))
    results, errors = [], []
    worker = TransferWorker(workflow, job.job_id)
    worker.result_available.connect(results.append)
    worker.failed.connect(errors.append)
    worker.start()

    assert worker.wait(5000)
    qapp.processEvents()

    assert not errors
    assert results
    assert repository.get(job.job_id).state is ReconstructionState.COMPLETED


def test_transfer_page_prevents_repeat_click_and_exposes_completed_result(
    tmp_path, qapp
):
    page = TransferReconstructionPage("http://192.0.2.10:8000", str(tmp_path))
    selections = []
    page.select_images_requested.connect(lambda: selections.append(True))
    page._select_images.click()
    assert selections == [True]
    event = _capture(tmp_path)
    workflow, _ = _workflow(tmp_path, "http://192.0.2.10:8000")
    ready = workflow.register_capture(event)
    assert not page._action.isEnabled()

    page.set_job(ready)
    assert page._action.isEnabled()
    assert page._action.text() == "上传并重建"

    page.set_job(
        ready.changed(
            state=ReconstructionState.UPLOADING,
            stage_message="上传任务包",
        )
    )
    assert not page._action.isEnabled()

    result = tmp_path / "3DGS.ply"
    result.write_bytes(b"ply\n")
    page.set_job(
        ready.changed(
            state=ReconstructionState.COMPLETED,
            stage_message="done",
            result_path=result,
        )
    )
    assert page._action.isEnabled()
    assert page._action.text() == "打开结果"
