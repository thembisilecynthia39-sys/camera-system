from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QCoreApplication

from tx_rx.jetson_client import TaskPackageError, TaskUploadError
import tx_rx.config
import tx_rx.jetson_client

from multiwebcam.ui.coordinator import (
    _CameraSwitchWorker,
    _CaptureTransferWorker,
    _DiscoveryWorker,
    _StagedUploadWorker,
    _TaskPackageWorker,
)
from multiwebcam.ui import coordinator as coordinator_module


def test_task_package_worker_suppresses_interrupted_packaging(monkeypatch, tmp_path):
    worker = _TaskPackageWorker(tmp_path / "capture_001")
    completed = []

    def cancel_during_packaging(_capture_dir, *, cancel_check):
        worker.requestInterruption()
        assert cancel_check()
        raise TaskPackageError("task packaging cancelled")

    monkeypatch.setattr(
        tx_rx.jetson_client,
        "build_configured_task_package",
        cancel_during_packaging,
    )
    worker.package_completed.connect(
        lambda result, error: completed.append((result, error))
    )

    worker.start()
    assert worker.wait(3000)
    QCoreApplication.processEvents()

    assert completed == []


def test_discovery_worker_suppresses_interrupted_scan(monkeypatch):
    worker = _DiscoveryWorker()
    completed = []

    def cancel_during_discovery(*, cancel_check):
        worker.requestInterruption()
        assert cancel_check()
        raise InterruptedError("camera discovery cancelled")

    monkeypatch.setattr(
        coordinator_module,
        "discover_frame_sources",
        cancel_during_discovery,
    )
    worker.discovery_completed.connect(
        lambda result, error: completed.append((result, error))
    )

    worker.start()
    assert worker.wait(3000)
    QCoreApplication.processEvents()

    assert completed == []


def test_camera_switch_worker_forwards_interruption():
    completed = []

    class Coordinator:
        def _switch_ignore_state_blocking(
            self,
            _source_id,
            _ignore,
            *,
            cancel_check,
        ):
            worker.requestInterruption()
            assert cancel_check()
            raise InterruptedError("camera switch cancelled")

    worker = _CameraSwitchWorker(Coordinator(), 1, True)
    worker.switch_completed.connect(completed.append)

    worker.start()
    assert worker.wait(3000)
    QCoreApplication.processEvents()

    assert completed == []


def test_capture_transfer_forwards_thread_interruption_to_upload(monkeypatch, tmp_path):
    capture_dir = tmp_path / "capture_001"
    staging_dir = tmp_path / "staging" / "capture_001"
    worker = _CaptureTransferWorker(capture_dir)
    completed = []

    monkeypatch.setattr(
        tx_rx.config,
        "load_config",
        lambda: SimpleNamespace(status_poll_interval_seconds=1),
    )
    monkeypatch.setattr(
        tx_rx.jetson_client,
        "build_configured_task_package",
        lambda _capture_dir: SimpleNamespace(
            capture_id="capture_001",
            staging_dir=staging_dir,
        ),
    )

    def cancel_during_upload(_staging_dir, *, cancel_check):
        worker.requestInterruption()
        assert cancel_check()
        raise TaskUploadError("upload cancelled")

    monkeypatch.setattr(
        tx_rx.jetson_client,
        "upload_staged_task",
        cancel_during_upload,
    )
    worker.transfer_completed.connect(
        lambda result, error: completed.append((result, error))
    )

    worker.start()
    assert worker.wait(3000)
    QCoreApplication.processEvents()

    assert completed == [(None, "upload cancelled")]


def test_staged_upload_stops_batch_after_interruption(monkeypatch, tmp_path):
    task_dirs = [
        tmp_path / "staging" / "capture_001",
        tmp_path / "staging" / "capture_002",
    ]
    worker = _StagedUploadWorker(task_dirs)
    attempted: list[Path] = []
    completed = []

    def cancel_first_upload(task_dir, *, cancel_check):
        attempted.append(task_dir)
        worker.requestInterruption()
        assert cancel_check()
        raise TaskUploadError("upload cancelled")

    monkeypatch.setattr(
        tx_rx.jetson_client,
        "upload_staged_task",
        cancel_first_upload,
    )
    worker.upload_completed.connect(
        lambda results, errors: completed.append((results, errors))
    )

    worker.start()
    assert worker.wait(3000)
    QCoreApplication.processEvents()

    assert attempted == [task_dirs[0]]
    assert completed == [([], ["capture_001: upload cancelled"])]
