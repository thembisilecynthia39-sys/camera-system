"""Test that UI infrastructure imports correctly."""

import numpy as np
import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel

from multiwebcam.profiles import SourceProfile
from multiwebcam.profiles.repository import ProfileRepository
from multiwebcam.quality.metrics import ObjectRegion
from multiwebcam.recognition import InferenceStatus
from multiwebcam.sources.config import FrameSourceConfig
from multiwebcam.sources.discovery import FrameSourceOptions, VideoMode
from multiwebcam.ui import CaptureCoordinator, FocusView, GridView, SourceInfo, SourceTile, frame_to_pixmap


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication for tests that need Qt widgets."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_frame_to_pixmap(qapp):
    """frame_to_pixmap converts BGR numpy array to QPixmap."""
    # Create a small test image (BGR)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[25:75, 25:75] = [255, 0, 0]  # Blue square in BGR

    pixmap = frame_to_pixmap(frame)

    assert isinstance(pixmap, QPixmap)
    assert pixmap.width() == 100
    assert pixmap.height() == 100


def test_frame_to_pixmap_accepts_object_region(qapp):
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    region = ObjectRegion(20, 20, 40, 40, 0.16, 0.9, 0.8, 0.8)

    pixmap = frame_to_pixmap(frame, object_region=region)

    assert isinstance(pixmap, QPixmap)
    assert pixmap.width() == 100


def test_grid_view_shows_inference_status(qapp):
    view = GridView()

    view.update_inference_status(
        InferenceStatus(
            backend="ultralytics_tensorrt_subprocess",
            active_count=3,
            detected_count=1,
            latency_ms=24.6,
            warming=False,
        )
    )

    labels = view.findChildren(QLabel)
    assert any("AI: YOLO TensorRT | 25ms | 1/3" in label.text() for label in labels)


def test_grid_view_shows_inference_warmup(qapp):
    view = GridView()

    view.update_inference_status(
        InferenceStatus(
            backend="subprocess",
            active_count=3,
            detected_count=0,
            latency_ms=None,
            warming=True,
        )
    )

    labels = view.findChildren(QLabel)
    assert any("AI: 子进程 预热中 | 0/3" in label.text() for label in labels)


def test_grid_view_shows_inference_inactive(qapp):
    view = GridView()

    view.update_inference_status(
        InferenceStatus(
            backend="heuristic",
            active_count=0,
            detected_count=0,
            latency_ms=None,
            warming=False,
        )
    )

    labels = view.findChildren(QLabel)
    assert any("AI: 启发式 | 未启用" in label.text() for label in labels)


def test_source_info_dataclass():
    """SourceInfo can be constructed with profile and options."""
    profile = SourceProfile.with_defaults(source_id=0, bus_info="usb-0000:00:14.0-1")

    info = SourceInfo(
        source_id=0,
        device_path="/dev/video0",
        profile=profile,
        options=None,
        error=None,
    )

    assert info.source_id == 0
    assert info.device_path == "/dev/video0"
    assert info.profile == profile
    assert info.error is None


def test_source_info_with_error():
    """SourceInfo can track error state for disconnected sources."""
    profile = SourceProfile.with_defaults(source_id=0, bus_info="usb-0000:00:14.0-1")

    info = SourceInfo(
        source_id=0,
        device_path="",
        profile=profile,
        options=None,
        error="Source not connected",
    )

    assert info.error == "Source not connected"
    assert info.device_path == ""


def test_capture_coordinator_construction(tmp_path):
    """CaptureCoordinator can be constructed with a project path."""
    coordinator = CaptureCoordinator(tmp_path)

    assert coordinator.session is None  # Not initialized yet
    assert coordinator.sources == {}


def test_capture_coordinator_initialize(tmp_path):
    """initialize() discovers sources and creates session if any found."""
    coordinator = CaptureCoordinator(tmp_path)
    coordinator.initialize()

    # Session exists if sources were discovered (may have real cameras)
    # If no cameras connected, session is None and sources is empty
    if coordinator.sources:
        assert coordinator.session is not None
    else:
        assert coordinator.session is None


def test_capture_coordinator_downgrades_third_720p_source_to_640x480(tmp_path):
    coordinator = CaptureCoordinator(tmp_path)

    class _Session:
        active_device_paths = ["/dev/video0", "/dev/video2"]

    coordinator._session = _Session()
    profile_0 = SourceProfile.with_defaults(0, "usb-0").with_resolution((1280, 720))
    profile_1 = SourceProfile.with_defaults(1, "usb-1").with_resolution((1280, 720))
    profile_2 = SourceProfile.with_defaults(2, "usb-2").with_resolution((1280, 720))

    coordinator._sources = {
        0: SourceInfo(0, "/dev/video0", profile_0, options=None),
        1: SourceInfo(1, "/dev/video2", profile_1, options=None),
        2: SourceInfo(2, "/dev/video4", profile_2, options=None),
    }
    coordinator._runtime_configs = {
        0: FrameSourceConfig(resolution=(1280, 720)),
        1: FrameSourceConfig(resolution=(1280, 720)),
    }

    config = coordinator._activation_config(coordinator._sources[2])

    assert config.resolution == (640, 480)


def test_capture_coordinator_keeps_native_640x480_source_resolution(tmp_path):
    coordinator = CaptureCoordinator(tmp_path)

    class _Session:
        active_device_paths = ["/dev/video0", "/dev/video2"]

    coordinator._session = _Session()
    profile_0 = SourceProfile.with_defaults(0, "usb-0").with_resolution((1280, 720))
    profile_1 = SourceProfile.with_defaults(1, "usb-1").with_resolution((1280, 720))
    profile_2 = SourceProfile.with_defaults(2, "usb-2").with_resolution((640, 480))

    coordinator._sources = {
        0: SourceInfo(0, "/dev/video0", profile_0, options=None),
        1: SourceInfo(1, "/dev/video2", profile_1, options=None),
        2: SourceInfo(2, "/dev/video4", profile_2, options=None),
    }
    coordinator._runtime_configs = {
        0: FrameSourceConfig(resolution=(1280, 720)),
        1: FrameSourceConfig(resolution=(1280, 720)),
    }

    config = coordinator._activation_config(coordinator._sources[2])

    assert config.resolution == (640, 480)


def test_capture_coordinator_default_active_pool_allows_four_sources(tmp_path):
    coordinator = CaptureCoordinator(tmp_path)

    assert coordinator._max_active_sources == 4


def test_capture_coordinator_does_not_add_unconfigured_devices_when_profiles_exist(tmp_path, monkeypatch):
    """Configured projects should restore known cameras instead of creating extra windows."""
    import multiwebcam.ui.coordinator as coordinator_module

    profile = SourceProfile.with_defaults(source_id=1, bus_info="usb-known").with_resolution((640, 480))
    ProfileRepository(tmp_path).save(profile)

    discovered = [
        FrameSourceOptions(
            path="/dev/video0",
            model="Known Camera",
            driver="uvcvideo",
            bus_info="usb-known",
            modes=(VideoMode("MJPG", 640, 480, 30.0),),
        ),
        FrameSourceOptions(
            path="/dev/video2",
            model="Unexpected Camera",
            driver="uvcvideo",
            bus_info="usb-unconfigured",
            modes=(VideoMode("MJPG", 640, 480, 30.0),),
        ),
    ]

    class _FakeSession:
        def __init__(self, frame_sources, recording_settings=None):
            self.frame_sources = frame_sources
            self.active_device_paths = [source.device_path for source in frame_sources]

    monkeypatch.setattr(coordinator_module, "discover_frame_sources", lambda: discovered)
    monkeypatch.setattr(coordinator_module, "CaptureSession", _FakeSession)

    coordinator = CaptureCoordinator(tmp_path)
    coordinator.initialize()

    assert set(coordinator.sources) == {1}
    assert coordinator.session is not None
    assert [source.device_path for source in coordinator.session.frame_sources] == ["/dev/video0"]
    assert [p.source_id for p in ProfileRepository(tmp_path).load_all()] == [1]


def test_capture_coordinator_does_not_persist_ignore_when_no_devices_found(tmp_path, monkeypatch):
    import multiwebcam.ui.coordinator as coordinator_module

    active_profile = SourceProfile.with_defaults(source_id=2, bus_info="usb-active").with_ignore(False)
    ProfileRepository(tmp_path).save(active_profile)
    monkeypatch.setattr(coordinator_module, "discover_frame_sources", lambda: [])

    coordinator = CaptureCoordinator(tmp_path)
    coordinator.initialize()
    view = coordinator.create_grid_view()

    loaded = ProfileRepository(tmp_path).get_by_source_id(2)
    assert loaded is not None
    assert loaded.ignore is False
    assert coordinator.session is None
    assert view.has_source(2)


def test_capture_coordinator_rebinds_profiles_when_topology_changed(tmp_path, monkeypatch):
    import multiwebcam.ui.coordinator as coordinator_module

    repo = ProfileRepository(tmp_path)
    repo.save(SourceProfile.with_defaults(source_id=1, bus_info="usb-old-standby").with_ignore(True))
    repo.save(SourceProfile.with_defaults(source_id=2, bus_info="usb-old-a").with_ignore(False))
    repo.save(SourceProfile.with_defaults(source_id=4, bus_info="usb-old-b").with_ignore(False))
    repo.save(SourceProfile.with_defaults(source_id=5, bus_info="usb-old-c").with_ignore(False))

    discovered = [
        FrameSourceOptions(
            path="/dev/video0",
            model="Camera A",
            driver="uvcvideo",
            bus_info="usb-new-a",
            modes=(VideoMode("MJPG", 640, 480, 30.0),),
        ),
        FrameSourceOptions(
            path="/dev/video2",
            model="Camera B",
            driver="uvcvideo",
            bus_info="usb-new-b",
            modes=(VideoMode("MJPG", 640, 480, 30.0),),
        ),
        FrameSourceOptions(
            path="/dev/video4",
            model="Camera C",
            driver="uvcvideo",
            bus_info="usb-new-c",
            modes=(VideoMode("MJPG", 640, 480, 30.0),),
        ),
    ]

    class _FakeSession:
        def __init__(self, frame_sources, recording_settings=None):
            self.frame_sources = frame_sources
            self.active_device_paths = [source.device_path for source in frame_sources]

    monkeypatch.setattr(coordinator_module, "discover_frame_sources", lambda: discovered)
    monkeypatch.setattr(coordinator_module, "CaptureSession", _FakeSession)

    coordinator = CaptureCoordinator(tmp_path)
    coordinator.initialize()

    profiles = {profile.source_id: profile for profile in repo.load_all()}
    assert profiles[2].bus_info == "usb-new-a"
    assert profiles[4].bus_info == "usb-new-b"
    assert profiles[5].bus_info == "usb-new-c"
    assert profiles[1].ignore is True
    assert coordinator.session is not None
    assert [source.device_path for source in coordinator.session.frame_sources] == [
        "/dev/video0",
        "/dev/video2",
        "/dev/video4",
    ]


def test_source_tile_construction(qapp):
    """SourceTile can be constructed with source_id and label."""
    tile = SourceTile(source_id=0, label="Test Camera")

    assert tile.source_id == 0
    # Tile has expected child widgets
    assert tile._frame_label is not None
    assert tile._name_label.text() == "Test Camera"
    assert tile._focus_btn is not None


def test_source_tile_hides_default_technical_label(qapp):
    tile = SourceTile(source_id=5, label="source_5", display_index=1)

    assert tile._camera_chip.text() == "相机 1"
    assert tile._name_label.text() == ""
    assert tile._name_label.isHidden()


def test_grid_view_construction(qapp):
    """GridView can be constructed and add sources."""
    view = GridView()

    # Initially empty
    assert len(view._tiles) == 0

    # Can add sources
    view.add_source(0, "Camera 0")
    view.add_source(1, "Camera 1")

    assert len(view._tiles) == 2
    assert 0 in view._tiles
    assert 1 in view._tiles


def test_grid_view_uses_two_by_two_layout_for_four_sources(qapp):
    """Four sources should lay out as a 2x2 grid instead of 3+1."""
    view = GridView()
    for source_id in range(4):
        view.add_source(source_id, f"Camera {source_id}")

    assert view._grid_layout.itemAtPosition(0, 0).widget() is view._tiles[0]
    assert view._grid_layout.itemAtPosition(0, 1).widget() is view._tiles[1]
    assert view._grid_layout.itemAtPosition(1, 0).widget() is view._tiles[2]
    assert view._grid_layout.itemAtPosition(1, 1).widget() is view._tiles[3]


def test_grid_view_numbers_non_contiguous_sources_by_visible_order(qapp):
    view = GridView()
    for source_id in (2, 4, 5, 8):
        view.add_source(source_id, f"source_{source_id}")

    assert [tile._camera_chip.text() for tile in view._tiles.values()] == [
        "相机 1",
        "相机 2",
        "相机 3",
        "相机 4",
    ]


def test_grid_view_action_buttons_emit_expected_signals(qapp):
    view = GridView()
    events = []

    view.record_requested.connect(lambda intent: events.append(("record", intent.is_extrinsic, intent.recording_name)))
    view.photo_requested.connect(lambda: events.append(("photo",)))
    view.stop_requested.connect(lambda: events.append(("stop",)))
    view.open_folder_requested.connect(lambda: events.append(("open",)))
    view.mirror_toggled.connect(lambda checked: events.append(("mirror", checked)))
    view.poll_interval_changed.connect(lambda ms: events.append(("poll", ms)))
    view.angle_changed.connect(lambda angle: events.append(("angle", angle)))

    view.set_default_recording_name("trial_001")
    view._record_btn.click()
    view._photo_btn.click()
    view._open_folder_btn.click()
    view._mirror_cb.setChecked(True)
    view._fps_combo.setCurrentText("30 fps")
    view._angle_combo.setCurrentText("90°")
    view.set_recording(True)
    view._stop_btn.click()

    assert ("record", False, "trial_001") in events
    assert ("photo",) in events
    assert ("stop",) in events
    assert ("open",) in events
    assert ("mirror", True) in events
    assert ("poll", 33) in events
    assert ("angle", 90) in events


def test_grid_view_extrinsic_record_button_emits_extrinsic_intent(qapp):
    view = GridView()
    events = []
    view.record_requested.connect(lambda intent: events.append(intent))

    view._extrinsic_cb.setChecked(True)
    view._record_btn.click()

    assert events
    assert events[0].is_extrinsic is True


def test_focus_view_construction(qapp):
    """FocusView can be constructed with source_id and label."""
    view = FocusView(source_id=0, label="Test Camera")

    assert view.source_id == 0
    assert "Test Camera" in view._info_label.text()
    assert view._frame_label is not None
    assert view._back_btn is not None


def test_focus_view_action_buttons_emit_expected_signals(qapp):
    view = FocusView(source_id=0, label="Test Camera")
    events = []

    view.apply_requested.connect(lambda: events.append("apply"))
    view.record_requested.connect(lambda: events.append("record"))
    view.stop_requested.connect(lambda: events.append("stop"))
    view.back_requested.connect(lambda: events.append("back"))

    view._apply_btn.click()
    view._record_btn.click()
    view._stop_btn.click()
    view._back_btn.click()

    assert events == ["apply", "record", "back"]
    assert view._config_status_label.text() == "正在应用配置..."

    view.set_recording(True)
    view._stop_btn.click()
    assert events[-1] == "stop"


def test_focus_view_reports_config_apply_result(qapp):
    view = FocusView(source_id=0, label="Test Camera")

    view.set_config_applied(FrameSourceConfig(resolution=(640, 480), fps=30))
    assert "已应用: 640x480 @ 30fps" == view._config_status_label.text()

    view.set_config_error("Cannot open /dev/video0")
    assert "应用失败: Cannot open /dev/video0" == view._config_status_label.text()


def test_focus_view_shows_empty_control_panel(qapp):
    view = FocusView(source_id=0, label="Test Camera")

    view.set_controls([])

    labels = [label.text() for label in view.findChildren(QLabel)]
    assert "摄像头控制" in labels
    assert "当前摄像头没有可调参数" in labels
