from pathlib import Path
from types import SimpleNamespace

from multiwebcam.ui import coordinator as coordinator_module
from multiwebcam.ui.coordinator import CaptureCoordinator


class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)


class _Worker:
    def __init__(self, capture_dir):
        self.capture_dir = capture_dir
        self.package_completed = _Signal()
        self.finished = _Signal()
        self.started = False
        self.deleted = False

    def start(self):
        self.started = True

    def deleteLater(self):
        self.deleted = True


class _View:
    def __init__(self):
        self.link_statuses = []
        self.capture_results = []
        self.busy_states = []

    def set_data_link_status(self, **status):
        self.link_statuses.append(status)

    def set_photo_capture_result(self, message, ok):
        self.capture_results.append((message, ok))

    def set_staging_upload_busy(self, busy):
        self.busy_states.append(busy)


def test_completed_capture_starts_background_staging(monkeypatch, tmp_path):
    monkeypatch.setattr(coordinator_module, "_TaskPackageWorker", _Worker)
    coordinator = CaptureCoordinator(tmp_path)
    view = _View()
    capture_dir = tmp_path / "captures" / "capture_001"

    coordinator._start_task_packaging(view, capture_dir)

    assert coordinator._task_package_worker is not None
    assert coordinator._task_package_worker.started
    assert coordinator._packaging_capture_dir == capture_dir.resolve()
    assert view.link_statuses[-1] == {"transmit": "正在整理 8 张照片..."}


def test_background_staging_scan_is_infrequent_and_never_uploads(tmp_path):
    coordinator = CaptureCoordinator(tmp_path)

    assert coordinator._staging_scan_timer.interval() == 30000
    assert coordinator._staged_upload_worker is None
    assert coordinator._capture_transfer_worker is None


def test_grid_creation_does_not_scan_staging_during_camera_startup(tmp_path, monkeypatch):
    coordinator = CaptureCoordinator(tmp_path)
    scans = []
    monkeypatch.setattr(coordinator, "_start_staging_scan", lambda: scans.append(True))

    coordinator.create_grid_view()

    assert scans == []


def test_staging_completion_updates_existing_data_link_area(tmp_path):
    coordinator = CaptureCoordinator(tmp_path)
    view = _View()
    coordinator._grid_view = view
    coordinator._packaging_capture_dir = (tmp_path / "captures" / "capture_001").resolve()
    result = SimpleNamespace(staging_dir=Path("/fixed/staging/capture_001"))

    coordinator._on_task_package_completed(result, None)

    assert view.link_statuses[-1] == {
        "transmit": "任务已整理，可以检查/上传",
        "receive": "等待上传",
    }
    assert view.capture_results[-1][1] is True
    assert "任务已整理，可以检查/上传" in view.capture_results[-1][0]


def test_staging_scan_exposes_ready_manual_task(tmp_path):
    coordinator = CaptureCoordinator(tmp_path)
    view = _View()
    coordinator._grid_view = view
    task_dir = tmp_path / "staging" / "manual_001"
    task = SimpleNamespace(
        task_id="manual_001",
        task_dir=task_dir,
        state=SimpleNamespace(value="ready"),
        message="可以上传",
    )

    coordinator._on_staging_scan_completed([task], None)

    assert coordinator._ready_staging_dirs == [task_dir.resolve()]
    assert view.link_statuses[-1] == {"transmit": "发现 1 个待上传任务"}


def test_successful_upload_updates_persistent_status(tmp_path):
    coordinator = CaptureCoordinator(tmp_path)
    view = _View()
    coordinator._grid_view = view
    staging_dir = tmp_path / "staging" / "manual_001"
    result = SimpleNamespace(staging_dir=staging_dir)

    coordinator._on_staged_upload_completed([result], [])

    assert staging_dir.resolve() in coordinator._uploaded_staging_dirs
    assert view.busy_states[-1] is False
    assert view.link_statuses[-1] == {
        "transmit": "已上传 1 个任务",
        "receive": "上位机已启动重建",
    }
