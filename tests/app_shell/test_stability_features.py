"""Regression tests for persistence, recovery, logging, errors, and shutdown."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from camera_system_app.application.diagnostics import DiagnosticService
from camera_system_app.bootstrap import build_context
from camera_system_app.domain import (
    ErrorCode,
    ReconstructionJob,
    ReconstructionState,
    TaskPersistenceError,
    normalize_error,
)
from camera_system_app.infrastructure.logging import LogService, configure_logging
from camera_system_app.infrastructure.reconstruction_repository import (
    ReconstructionJobRepository,
)
from camera_system_app.ui.lifecycle import LifecycleCoordinator
from camera_system_app.ui.main_window import MainWindow
from camera_system_app.ui.pages import HistoryPage, TransferReconstructionPage
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QToolButton


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_task_repository_uses_managed_directory_and_two_atomic_json_files(tmp_path):
    repository = ReconstructionJobRepository(tmp_path / "tasks")
    capture = tmp_path / "captures" / "object"
    capture.mkdir(parents=True)
    job = ReconstructionJob("job-1", "object", capture)

    repository.save(job)
    task_dir = repository.task_dir(job.job_id)

    assert json.loads((task_dir / "task.json").read_text())["capture_dir"] == str(
        capture.resolve()
    )
    assert json.loads((task_dir / "status.json").read_text())["state"] == "ready"
    assert not list(task_dir.glob("*.tmp"))
    assert repository.get(job.job_id) == job


def test_task_registration_prevents_duplicate_capture_jobs(tmp_path):
    repository = ReconstructionJobRepository(tmp_path / "tasks")
    capture = tmp_path / "capture"
    capture.mkdir()
    first = repository.register(ReconstructionJob("first", "capture", capture))
    second = repository.register(ReconstructionJob("second", "capture", capture))

    assert second.job_id == first.job_id
    assert len(repository.all()) == 1


def test_task_identity_cannot_be_overwritten(tmp_path):
    repository = ReconstructionJobRepository(tmp_path / "tasks")
    first_capture = tmp_path / "first"
    second_capture = tmp_path / "second"
    first_capture.mkdir()
    second_capture.mkdir()
    repository.save(ReconstructionJob("same-job", "first", first_capture))

    with pytest.raises(TaskPersistenceError):
        repository.save(ReconstructionJob("same-job", "second", second_capture))


def test_legacy_flat_job_is_restored_into_managed_task_directory(tmp_path):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    capture = tmp_path / "capture"
    capture.mkdir()
    job = ReconstructionJob("legacy-job", "capture", capture)
    (legacy / "legacy-job.json").write_text(
        json.dumps(job.to_dict()), encoding="utf-8"
    )
    repository = ReconstructionJobRepository(tmp_path / "tasks", legacy)

    restored = repository.all()

    assert restored[0].job_id == job.job_id
    assert (repository.task_dir(job.job_id) / "status.json").is_file()


def test_error_normalization_has_stable_user_categories():
    unavailable = normalize_error(ConnectionError("connection refused"))
    timeout = normalize_error(TimeoutError("request timed out"))
    remote = normalize_error(RuntimeError("HTTP 400 bad request"))

    assert unavailable.code is ErrorCode.SERVICE_UNAVAILABLE
    assert timeout.code is ErrorCode.TIMEOUT
    assert remote.code is ErrorCode.REMOTE_FAILURE


def test_managed_subsystem_logs_are_written_and_tailed(tmp_path):
    log_file = tmp_path / "logs" / "app.log"
    log_file.parent.mkdir()
    logs = configure_logging(log_file, "INFO")

    logging.getLogger("tx_rx.transfer").info("transfer-event")
    logging.getLogger("multiwebcam.camera").warning("camera-event")

    text = logs.tail()
    assert "transfer-event" in text
    assert "camera-event" in text


def test_log_tail_keeps_only_requested_lines(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.write_text(
        "".join("line-{}\n".format(index) for index in range(1000)),
        encoding="utf-8",
    )

    text = LogService(log_file).tail(max_lines=3)

    assert text == "line-997\nline-998\nline-999\n"


def test_diagnostics_include_version_runtime_and_qt(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    context = build_context(project_root=str(PROJECT_ROOT))

    names = {check.name for check in DiagnosticService(context.paths, context.settings).run().checks}

    assert {"应用运行时", "Python", "Qt 绑定", "统一日志"} <= names


def test_history_exposes_retry_and_result_actions(tmp_path, qapp):
    page = HistoryPage()
    capture = tmp_path / "capture"
    capture.mkdir()
    failed = ReconstructionJob(
        "failed-job",
        "capture",
        capture,
        state=ReconstructionState.FAILED,
    )
    page.set_jobs([failed])

    actions = page.table.cellWidget(0, 5)
    assert actions is not None
    assert "重试" in {button.text() for button in actions.findChildren(QPushButton)}
    assert len(actions.findChildren(QPushButton)) == 1
    assert len(actions.findChildren(QToolButton)) == 1
    assert page.table.columnWidth(5) >= 180
    assert page.table.rowHeight(0) >= 58


def test_capture_workspace_uses_connected_dark_surface(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    context = build_context(project_root=str(PROJECT_ROOT))
    window = MainWindow(context.paths, context.settings)

    margins = window.capture_page.layout().contentsMargins()

    assert window.capture_page.objectName() == "capturePageSurface"
    assert window.capture_page.testAttribute(Qt.WA_StyledBackground)
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        0,
        0,
        0,
        0,
    )
    assert window.statusBar().property("mode") == "operational"
    window.navigation.setCurrentRow(2)
    assert window.result_page.objectName() == "resultPageSurface"
    assert window.result_page.testAttribute(Qt.WA_StyledBackground)
    assert window.statusBar().property("mode") == "operational"
    window.navigation.setCurrentRow(3)
    assert window.statusBar().property("mode") == "standard"


def test_interrupted_job_is_retryable_in_transfer_page(tmp_path, qapp):
    page = TransferReconstructionPage("http://127.0.0.1:1", str(tmp_path))
    capture = tmp_path / "capture"
    capture.mkdir()
    job = ReconstructionJob(
        "job",
        "capture",
        capture,
        state=ReconstructionState.INTERRUPTED,
    )

    page.set_job(job)

    assert page._action.isEnabled()
    assert page._action.text() == "重试传输与重建"


class _ShutdownComponent:
    def __init__(self, result=True):
        self.result = result
        self.calls = 0

    def shutdown(self):
        self.calls += 1
        return self.result


def test_lifecycle_shutdown_is_idempotent(qapp):
    from PySide6.QtWidgets import QMainWindow

    window = QMainWindow()
    window.close_requested = _SignalStub()
    component = _ShutdownComponent()
    lifecycle = LifecycleCoordinator(window, [component])

    assert lifecycle.shutdown()
    assert lifecycle.shutdown()
    assert component.calls == 1


class _SignalStub:
    def connect(self, callback):
        self.callback = callback

    def disconnect(self, callback):
        pass
