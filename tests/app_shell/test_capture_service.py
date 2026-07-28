"""Tests for the multiwebcam runtime adapter and fake camera backend."""

from __future__ import annotations

import time
import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from camera_system.domain import TASK_ANGLES
from camera_system_app.domain import CaptureRuntimeStatus
from camera_system_app.infrastructure.adapters import MultiWebcamCaptureAdapter
from camera_system_app.testing import FakeCameraBackend
from multiwebcam.pipeline.session import CaptureSession
from multiwebcam.quality.metrics import ObjectRegion, evaluate_capture_set
from multiwebcam.sources.frame_packet import FramePacket
from multiwebcam.ui.coordinator import CaptureCoordinator
from multiwebcam.ui.views import GridView


class _FakeGridView(QWidget):
    focus_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.shutdown_count = 0

    def shutdown(self) -> None:
        self.shutdown_count += 1


class _FakeCoordinator(QObject):
    runtime_state_changed = Signal(str, object)
    capture_progress_changed = Signal(object)
    capture_completed = Signal(object)
    capture_available = Signal()
    model_resources_released = Signal(bool)

    def __init__(self, project_root: Path, capture_only: bool = False) -> None:
        super().__init__()
        self.project_root = project_root
        self.capture_only = capture_only
        self.start_count = 0
        self.stop_count = 0
        self.grid_create_count = 0
        self.grid = None
        self.model_mode_calls = []

    def create_grid_view(self):
        self.grid_create_count += 1
        self.grid = _FakeGridView()
        return self.grid

    def create_focus_view(self, source_id: int):
        raise RuntimeError("not used")

    def start_async(self) -> None:
        self.start_count += 1
        self.runtime_state_changed.emit(
            "ready",
            {"message": "fake camera ready", "camera_count": 1},
        )

    def stop(self) -> None:
        self.stop_count += 1
        self.runtime_state_changed.emit(
            "stopped",
            {"message": "fake camera stopped", "camera_count": 0},
        )

    def get_source_id_lookup(self):
        return {"/dev/fake-video0": 0}

    def set_model_mode(self, active: bool) -> bool:
        self.model_mode_calls.append(bool(active))
        return True


def _wait_for_frame(session: CaptureSession, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        packet = session.get_latest_frames().get("/dev/fake-video0")
        if packet is not None:
            return packet
        time.sleep(0.01)
    return None


def _packets(seed: int):
    rng = np.random.default_rng(seed)
    frame = rng.integers(40, 215, size=(180, 240, 3), dtype=np.uint8)
    return {
        "/dev/fake-video0": FramePacket(
            device_path="/dev/fake-video0",
            device_id=0,
            frame_index=seed,
            frame_time=float(seed),
            timestamp_source="wall_clock",
            frame=frame,
            fps=30.0,
        )
    }


def test_fake_camera_backend_runs_through_existing_capture_session():
    camera = FakeCameraBackend()
    session = CaptureSession([camera], enable_monitoring=False)

    session.start()
    packet = _wait_for_frame(session)
    session.stop()

    assert packet is not None
    assert packet.frame.shape == (240, 320, 3)
    assert camera.released.wait(1.0)
    assert not session.producers_healthy


def test_capture_session_releases_and_restarts_sources_for_gpu_handoff():
    camera = FakeCameraBackend()
    session = CaptureSession([camera], enable_monitoring=False)

    session.start()
    assert _wait_for_frame(session) is not None
    assert session.suspend_all(timeout=1.0)
    assert session.all_producers_quiesced
    assert camera.released.is_set()

    session.resume_all()
    assert _wait_for_frame(session) is not None
    assert camera.start_count >= 2
    assert session.stop()


def test_capture_adapter_start_and_stop_are_idempotent(qapp, tmp_path):
    adapter = MultiWebcamCaptureAdapter(
        tmp_path,
        coordinator_factory=_FakeCoordinator,
    )
    states = []
    adapter.state_changed.connect(states.append)

    adapter.initialize_view()
    adapter.start()
    adapter.start()
    adapter.stop()
    adapter.stop()

    assert adapter.coordinator.capture_only is True
    assert adapter.coordinator.start_count == 1
    assert adapter.coordinator.stop_count == 1
    assert states[-1].status is CaptureRuntimeStatus.STOPPED


def test_capture_adapter_forwards_completed_event(qapp, tmp_path):
    adapter = MultiWebcamCaptureAdapter(
        tmp_path,
        coordinator_factory=_FakeCoordinator,
    )
    completed = []
    adapter.capture_completed.connect(completed.append)

    capture_dir = tmp_path / "captures" / "object1"
    adapter.coordinator.capture_completed.emit(
        {
            "capture_dir": str(capture_dir),
            "object_name": "object",
            "completed_angles": TASK_ANGLES,
        }
    )

    assert len(completed) == 1
    assert completed[0].capture_dir == capture_dir.resolve()
    assert completed[0].completed_angles == TASK_ANGLES


def test_capture_adapter_rebinds_grid_after_async_capture_is_available(qapp, tmp_path):
    adapter = MultiWebcamCaptureAdapter(
        tmp_path,
        coordinator_factory=_FakeCoordinator,
    )
    views = []
    adapter.view_changed.connect(views.append)

    adapter.initialize_view()
    initial_view = adapter.current_view
    adapter.coordinator.capture_available.emit()

    assert adapter.coordinator.grid_create_count == 2
    assert adapter.current_view is not initial_view
    assert views == [initial_view, adapter.current_view]
    adapter.stop()


def test_capture_adapter_transfers_compute_to_result_review(qapp, tmp_path):
    adapter = MultiWebcamCaptureAdapter(
        tmp_path,
        coordinator_factory=_FakeCoordinator,
    )

    assert adapter.set_result_review_active(True)
    assert adapter.coordinator.model_mode_calls == [True]
    assert not adapter.result_review_gpu_ready

    adapter.coordinator.model_resources_released.emit(True)
    assert adapter.result_review_gpu_ready

    adapter.coordinator.capture_available.emit()
    assert adapter.coordinator.model_mode_calls[-1] is True

    assert adapter.set_result_review_active(False)
    assert adapter.coordinator.model_mode_calls[-1] is False
    assert not adapter.result_review_gpu_ready
    adapter.stop()


def test_real_adapter_reuses_capture_only_grid_view(qapp, tmp_path):
    txrx_was_loaded = "tx_rx" in sys.modules
    gaussian_was_loaded = "multiwebcam.ui.views.gaussian_model_view" in sys.modules
    adapter = MultiWebcamCaptureAdapter(tmp_path)

    adapter.initialize_view()

    assert isinstance(adapter.current_view, GridView)
    assert adapter.current_view._capture_only is True
    assert adapter.current_view._nav_buttons[4].isHidden()
    assert adapter.current_view._nav_buttons[5].isHidden()
    assert type(adapter.current_view._model_view) is QWidget
    assert not adapter.coordinator._staging_scan_timer.isActive()
    assert not adapter.current_view._bottom_status._ping_timer.isActive()
    assert ("tx_rx" in sys.modules) is txrx_was_loaded
    assert (
        "multiwebcam.ui.views.gaussian_model_view" in sys.modules
    ) is gaussian_was_loaded
    adapter.stop()


def test_coordinator_emits_completion_only_after_eight_angles(qapp, tmp_path):
    coordinator = CaptureCoordinator(tmp_path, capture_only=True)
    completed = []
    coordinator.capture_completed.connect(completed.append)
    coordinator._active_snapshot_object_name = "object"
    region = ObjectRegion(
        x=40,
        y=30,
        width=150,
        height=110,
        area_ratio=0.38,
        centeredness=0.9,
        fill_ratio=0.8,
        confidence=0.85,
    )

    for index, angle in enumerate(TASK_ANGLES):
        packets = _packets(100 + index)
        quality = evaluate_capture_set(
            packets,
            object_regions={path: region for path in packets},
        )
        guidance = coordinator._guidance_tracker.register_capture(
            angle,
            index + 1,
            packets,
            quality,
        )
        coordinator._emit_capture_completion_if_ready(
            guidance,
            tmp_path / "captures" / "object1",
        )
        assert len(completed) == (1 if index == 7 else 0)

    assert completed[0]["completed_angles"] == TASK_ANGLES
    assert completed[0]["object_name"] == "object"
    coordinator.stop()
