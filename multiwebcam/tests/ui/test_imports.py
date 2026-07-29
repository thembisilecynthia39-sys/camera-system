"""Test that UI infrastructure imports correctly."""

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QPixmap, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from multiwebcam.profiles import SourceProfile
from multiwebcam.profiles.repository import ProfileRepository
from multiwebcam.quality.guidance import CaptureGuidance
from multiwebcam.quality.metrics import ObjectRegion
from multiwebcam.recognition import InferenceStatus
from multiwebcam.sources.config import FrameSourceConfig
from multiwebcam.sources.discovery import FrameSourceOptions, VideoMode
from multiwebcam.sources.controls import V4L2Control
from multiwebcam.ui import CaptureCoordinator, FocusView, GridView, SourceInfo, SourceTile, frame_to_pixmap
from multiwebcam.ui.coordinator import CameraLoadResult
from multiwebcam.ui.components import GuardedSlider, GuardedSpinBox
from multiwebcam.ui.views.control_panel import ControlPanel


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


def test_grid_view_escape_exits_fullscreen_and_syncs_button(qapp):
    view = GridView()
    view.show()
    qapp.processEvents()
    view._toggle_fullscreen()
    qapp.processEvents()
    assert view.isFullScreen()

    QTest.keyClick(view, Qt.Key_Escape)
    qapp.processEvents()

    assert not view.isFullScreen()
    assert view._fullscreen_btn.text() == "全屏"
    view.close()


def test_grid_view_fullscreen_exit_restores_maximized_state(qapp):
    view = GridView()
    view.showMaximized()
    qapp.processEvents()
    assert view.isMaximized()
    view._toggle_fullscreen()
    qapp.processEvents()

    QTest.keyClick(view, Qt.Key_Escape)
    qapp.processEvents()

    assert not view.isFullScreen()
    assert view.isMaximized()
    view.close()


def test_grid_view_exposes_keyboard_accessible_staging_upload_action(qapp):
    view = GridView()
    requests = []
    view.upload_staged_tasks_requested.connect(lambda: requests.append(True))
    button = next(button for button in view.findChildren(QPushButton) if button.text() == "检查并上传")

    button.click()

    assert requests == [True]
    assert button.isEnabled()


def test_grid_view_presents_eight_angle_progress_as_distinct_steps(qapp):
    view = GridView(capture_only=True)
    guidance = CaptureGuidance(
        current_angle_deg=90,
        readiness_percent=78.0,
        readiness_label="acceptable",
        progress_percent=25.0,
        next_angle_deg=90,
        completed_angles=(0, 45),
        suggested_retake_angle=None,
        warning=None,
        ready_to_capture=True,
        loop_complete=False,
    )

    view.update_guidance(guidance)

    assert view._guide_progress.value() == 25
    assert view._guide_progress.format() == "2 / 8"
    assert len(view._guide_angle_steps) == 8
    assert view._guide_angle_steps[0].property("state") == "done"
    assert view._guide_angle_steps[90].property("state") == "current"
    assert view._guide_angle_steps[135].property("state") == "pending"


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


def test_3dgs_model_dialog_opens_result_directory(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    coordinator = CaptureCoordinator(tmp_path)
    dialog_calls = []

    class _View:
        def load_model(self, path):
            raise AssertionError(f"unexpected model load: {path}")

    def fake_get_open_file_name(parent, title, directory, file_filter):
        dialog_calls.append((parent, title, directory, file_filter))
        return "", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", fake_get_open_file_name)
    view = _View()

    coordinator._select_3dgs_model(view)

    assert dialog_calls[0][2] == str(tmp_path / "result")


def test_capture_coordinator_does_not_raise_when_session_start_fails(tmp_path):
    coordinator = CaptureCoordinator(tmp_path)

    class _FailingSession:
        startup_errors = {}

        def start(self):
            raise RuntimeError("camera busy")

    coordinator._session = _FailingSession()

    coordinator.start()


def test_capture_coordinator_load_cameras_always_scans(tmp_path, monkeypatch):
    """Loading cameras must rescan even when the existing session is healthy."""
    coordinator = CaptureCoordinator(tmp_path)

    class _Session:
        is_recording = False

    class _View:
        def __init__(self):
            self.messages = []

        def set_video_paused(self, paused, message):
            self.messages.append((paused, message))

    scans = []
    monkeypatch.setattr(coordinator, "_poll_hotplug", lambda: scans.append(True))
    coordinator._session = _Session()
    view = _View()

    coordinator._load_cameras(view)

    assert scans == [True]
    assert coordinator._manual_camera_load_requested is True
    assert view.messages == [(True, "正在用 v4l2-ctl 扫描 USB 摄像头...")]


def test_capture_coordinator_discovery_defers_camera_open_to_worker(tmp_path, monkeypatch):
    """Discovery completion must schedule camera I/O instead of doing it on Qt's thread."""
    coordinator = CaptureCoordinator(tmp_path)
    coordinator._session = object()
    coordinator._manual_camera_load_requested = True
    calls = []

    monkeypatch.setattr(
        coordinator,
        "_start_camera_load_worker",
        lambda discovered, **kwargs: calls.append((discovered, kwargs)),
    )

    coordinator._on_discovery_completed([], None)

    assert calls == [
        (
            [],
            {
                "allow_unconfigured": True,
                "preserve_existing": True,
                "start_session": False,
            },
        )
    ]
    assert coordinator._manual_camera_load_requested is True


def test_capture_coordinator_initial_start_defers_camera_open_to_worker(tmp_path, monkeypatch):
    coordinator = CaptureCoordinator(tmp_path)
    coordinator._session = object()
    calls = []

    monkeypatch.setattr(
        coordinator,
        "_start_camera_load_worker",
        lambda discovered, **kwargs: calls.append((discovered, kwargs)),
    )

    coordinator.start_async()

    assert calls == [
        (
            [],
            {
                "allow_unconfigured": False,
                "preserve_existing": False,
                "start_session": True,
            },
        )
    ]


def test_capture_coordinator_initial_start_defers_discovery_to_worker(tmp_path, monkeypatch):
    """A cold start must not run V4L2 discovery on the Qt/main thread."""
    coordinator = CaptureCoordinator(tmp_path)
    calls = []

    monkeypatch.setattr(coordinator, "_poll_hotplug", lambda: calls.append(True))

    coordinator.start_async()

    assert calls == [True]
    assert coordinator.session is None


def test_initial_discovery_failure_clears_camera_load_state(tmp_path, monkeypatch):
    coordinator = CaptureCoordinator(tmp_path)
    results = []
    monkeypatch.setattr(coordinator, "_on_camera_load_completed", results.append)

    coordinator._on_discovery_completed(None, "v4l2 scan failed")

    assert results == [CameraLoadResult("v4l2 scan failed", True)]


def test_capture_coordinator_manual_empty_scan_keeps_existing_source(tmp_path):
    """An incomplete manual scan must not remove a camera already streaming."""
    coordinator = CaptureCoordinator(tmp_path)

    class _Session:
        active_device_paths = ["/dev/video0"]

    profile = SourceProfile.with_defaults(source_id=0, bus_info="usb-known")
    info = SourceInfo(0, "/dev/video0", profile, options=None)
    coordinator._session = _Session()
    coordinator._sources = {0: info}

    coordinator._refresh_discovered_sources([], preserve_existing=True)

    assert info.device_path == "/dev/video0"
    assert info.error is None


def test_capture_coordinator_manual_new_camera_failure_keeps_existing_sources(tmp_path):
    """A failed new camera open must leave the existing active source intact."""
    coordinator = CaptureCoordinator(tmp_path)
    coordinator._profile_locked = True

    class _Session:
        active_device_paths = ["/dev/video0"]

        def add_source(self, source):
            raise RuntimeError(f"cannot open {source.device_path}")

    known_profile = SourceProfile.with_defaults(source_id=0, bus_info="usb-known")
    coordinator._session = _Session()
    coordinator._sources = {
        0: SourceInfo(0, "/dev/video0", known_profile, options=None),
    }

    new_options = FrameSourceOptions(
        path="/dev/video2",
        model="New Camera",
        driver="uvcvideo",
        bus_info="usb-new",
        modes=(VideoMode("MJPG", 640, 480, 30.0),),
    )

    coordinator._refresh_discovered_sources(
        [new_options],
        allow_unconfigured=True,
        preserve_existing=True,
    )

    assert coordinator._session.active_device_paths == ["/dev/video0"]
    assert coordinator.sources[0].error is None
    assert coordinator.sources[1].device_path == "/dev/video2"
    assert "cannot open /dev/video2" in coordinator.sources[1].error


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


def test_capture_coordinator_uses_first_usb2_source_as_initial_480p_anchor(
    tmp_path, monkeypatch
):
    import multiwebcam.ui.coordinator as coordinator_module

    repo = ProfileRepository(tmp_path)
    profiles = (
        SourceProfile.with_defaults(0, "usb-root-1.3"),
        SourceProfile.with_defaults(1, "usb-root-2.1.2"),
        SourceProfile.with_defaults(2, "usb-root-2.4.3"),
        SourceProfile.with_defaults(3, "usb-root-2.4.4"),
    )
    for profile in profiles:
        repo.save(profile.with_resolution((1280, 720)))

    discovered = [
        FrameSourceOptions(
            path=f"/dev/video{source_id * 2}",
            model=f"Camera {source_id}",
            driver="uvcvideo",
            bus_info=profile.bus_info,
            modes=(VideoMode("MJPG", 1280, 720, 30.0),),
        )
        for source_id, profile in enumerate(profiles)
    ]

    class _FakeSession:
        def __init__(self, frame_sources, recording_settings=None):
            self.frame_sources = frame_sources
            self.active_device_paths = [
                source.device_path for source in frame_sources
            ]

    monkeypatch.setattr(coordinator_module, "CaptureSession", _FakeSession)

    coordinator = CaptureCoordinator(tmp_path)
    coordinator.initialize(discovered=discovered)

    assert {
        source_id: config.resolution
        for source_id, config in coordinator._runtime_configs.items()
    } == {
        0: (1280, 720),
        1: (640, 480),
        2: (1280, 720),
        3: (1280, 720),
    }


def test_capture_coordinator_downgrades_third_720p_source_on_same_usb_root(tmp_path):
    coordinator = CaptureCoordinator(tmp_path)

    class _Session:
        active_device_paths = ["/dev/video0", "/dev/video2"]

    coordinator._session = _Session()
    profile_0 = SourceProfile.with_defaults(0, "usb-root-2.1").with_resolution((1280, 720))
    profile_1 = SourceProfile.with_defaults(1, "usb-root-2.2").with_resolution((1280, 720))
    profile_2 = SourceProfile.with_defaults(2, "usb-root-2.3").with_resolution((1280, 720))

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


def test_capture_coordinator_keeps_usb3_high_resolution_out_of_usb2_budget(tmp_path):
    coordinator = CaptureCoordinator(tmp_path)

    class _Session:
        active_device_paths = ["/dev/video0", "/dev/video2"]

    coordinator._session = _Session()
    usb3 = SourceProfile.with_defaults(0, "usb-root-1.3").with_resolution((1280, 720))
    usb2_a = SourceProfile.with_defaults(1, "usb-root-2.1").with_resolution((1280, 720))
    usb2_b = SourceProfile.with_defaults(2, "usb-root-2.2").with_resolution((1280, 720))

    coordinator._sources = {
        0: SourceInfo(0, "/dev/video0", usb3, options=None),
        1: SourceInfo(1, "/dev/video2", usb2_a, options=None),
        2: SourceInfo(2, "/dev/video4", usb2_b, options=None),
    }
    coordinator._runtime_configs = {
        0: FrameSourceConfig(resolution=(1280, 720)),
        1: FrameSourceConfig(resolution=(1280, 720)),
    }

    config = coordinator._activation_config(coordinator._sources[2])

    assert config.resolution == (1280, 720)


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


def test_grid_view_has_five_balanced_status_cards(qapp):
    view = GridView()

    cards = view.findChildren(type(view._side_panel), "dashboardCard")
    titles = [card.findChild(QLabel, "cardTitle").text() for card in cards]

    assert titles == ["系统状态", "AI 检测", "数据链路", "质量监测", "告警信息"]
    assert all(card.maximumHeight() <= 210 for card in cards)


def test_grid_view_data_link_tracks_reconstructed_3dgs_file(qapp):
    view = GridView()

    assert view._data_transmit_value.text() == "等待上位机"
    assert view._data_receive_value.text() == "等待 3DGS 文件"

    view.set_data_link_status(transmit="正在发送采集数据")
    view._model_view.model_loaded.emit("scene.ply")

    assert view._data_transmit_value.text() == "正在发送采集数据"
    assert view._data_receive_value.text() == "已接收: scene.ply"


def test_grid_view_refreshes_camera_count_when_source_recovers(qapp):
    view = GridView()
    for source_id in range(4):
        view.add_source(source_id, f"Camera {source_id}")

    view.set_source_error(3, "Disconnected")
    assert view._system_status.cameras._label.text() == "3 路摄像头"

    view.clear_source_error(3)
    assert view._system_status.cameras._label.text() == "4 路摄像头"


def test_grid_view_alert_reports_disconnected_camera_count(qapp):
    view = GridView()
    for source_id in range(4):
        view.add_source(source_id, f"Camera {source_id}")

    view.set_source_error(1, "Disconnected")
    view.set_source_error(3, "Disconnected")

    message = view._alert_rows[0][2].text()
    assert message == "检测到 2 路断连，请检查或重新加载"

    view.clear_source_error(1)
    view.clear_source_error(3)
    assert view._alert_rows[0][2].text() == "暂无告警"


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


def test_camera_numeric_control_ignores_wheel_even_with_focus(qapp):
    spinbox = GuardedSpinBox()
    spinbox.setRange(0, 10)
    spinbox.setValue(5)
    spinbox.show()
    spinbox.setFocus()
    qapp.processEvents()
    event = QWheelEvent(
        QPointF(1, 1),
        QPointF(1, 1),
        QPoint(),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )

    qapp.sendEvent(spinbox, event)

    assert spinbox.value() == 5
    assert not event.isAccepted()


def test_camera_slider_commits_only_after_drag_release(qapp):
    panel = ControlPanel([V4L2Control("brightness", "int", 0, 100, 1, 50, 50)])
    slider = panel.findChild(GuardedSlider)
    changes = []
    panel.control_changed.connect(lambda name, value: changes.append((name, value)))

    slider.setSliderDown(True)
    slider.setValue(61)
    assert changes == []

    slider.setSliderDown(False)
    assert changes == [("brightness", 61)]


def test_camera_numeric_entry_commits_only_when_editing_finishes(qapp):
    panel = ControlPanel([V4L2Control("white_balance_temperature", "int", 2000, 7500, 10, 4600, 4600)])
    editor = panel.findChild(GuardedSpinBox, "cameraValueEditor")
    changes = []
    panel.control_changed.connect(lambda name, value: changes.append((name, value)))

    editor.setValue(5000)
    assert changes == []

    editor.editingFinished.emit()
    assert changes == [("white_balance_temperature", 5000)]
    assert editor.width() == 72


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
