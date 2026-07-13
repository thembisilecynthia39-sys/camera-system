"""Capture subsystem coordinator (composition root)."""


from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QThread, QTimer, Qt, Signal

from multiwebcam.recording.naming import next_recording_name
from multiwebcam.ui.recording_intent import GridRecordingIntent

from multiwebcam.pipeline.session import CaptureSession
from multiwebcam.profiles import AppSettings, ControlValue, ProfileRepository, SourceProfile
from multiwebcam.quality.guidance import CaptureGuidanceTracker
from multiwebcam.quality.metrics import evaluate_capture_set
from multiwebcam.snapshot import SnapshotCameraInfo, save_snapshot_set
from multiwebcam.sources import FrameSource, FrameSourceConfig, FrameSourceOptions, discover_frame_sources
from multiwebcam.sources.controls import set_control
from multiwebcam.ui.active_pool import SourcePoolEntry, rebalance_active_source_ids

logger = logging.getLogger(__name__)
_DEFAULT_MAX_ACTIVE_SOURCES = 4
_HOTPLUG_DEBOUNCE_MS = 1000
_HIGH_RESOLUTION = (1280, 720)
_LOW_RESOLUTION = (640, 480)
_MAX_ACTIVE_HIGH_RESOLUTION_SOURCES = 2


def _sanitize_recording_name(raw: str) -> str:
    """Sanitize user input to a safe filesystem name."""
    name = raw.strip()
    name = re.sub(r"[^\w\-]", "_", name)
    name = name.lstrip("-")
    return name or "untitled"


def _zh_capture_message(message: str) -> str:
    if message.startswith("target not detected"):
        return "未检测到目标，请把物体放到画面中央后再拍摄"
    if "improve sharpness or exposure" in message:
        return "画面质量不足，请改善清晰度或曝光"
    if "already covered" in message:
        return "该角度已拍过，如需重拍请提高画面质量"
    if message.startswith("duplicate"):
        return "角度重复，请旋转到下一角度"
    if message.startswith("low overlap"):
        return "与相邻角度重叠不足，请减小旋转幅度或增加纹理"
    return (
        message.replace("READY", "可拍摄")
        .replace("BORDERLINE", "勉强可拍")
        .replace("WAIT", "请等待")
    )


def _zh_readiness_label(label: str) -> str:
    return {
        "READY": "可拍摄",
        "BORDERLINE": "勉强可拍",
        "WAIT": "请等待",
    }.get(label, label)


@dataclass
class SourceInfo:
    """Runtime info for a discovered source."""

    source_id: int
    device_path: str
    profile: SourceProfile
    options: FrameSourceOptions | None
    error: str | None = None


@dataclass
class CameraSwitchResult:
    """Result of an async active/standby camera switch."""

    requested_source_id: int
    requested_ignore: bool
    ignore_updates: dict[int, bool]
    error: str | None = None


class _CameraSwitchWorker(QThread):
    """Run slow V4L2 open/close work off the Qt UI thread."""

    switch_completed = Signal(object)  # CameraSwitchResult

    def __init__(self, coordinator: "CaptureCoordinator", source_id: int, ignore: bool) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._source_id = source_id
        self._ignore = ignore

    def run(self) -> None:
        try:
            result = self._coordinator._switch_ignore_state_blocking(self._source_id, self._ignore)
        except Exception as exc:
            logger.exception("Camera switch failed")
            result = CameraSwitchResult(
                requested_source_id=self._source_id,
                requested_ignore=self._ignore,
                ignore_updates={},
                error=str(exc),
            )
        self.switch_completed.emit(result)


class _DiscoveryWorker(QThread):
    """Run V4L2 discovery off the Qt UI thread."""

    discovery_completed = Signal(object, object)  # list[FrameSourceOptions] | None, str | None

    def run(self) -> None:
        try:
            self.discovery_completed.emit(discover_frame_sources(), None)
        except Exception as exc:
            logger.exception("Camera discovery failed")
            self.discovery_completed.emit(None, str(exc))


class CaptureCoordinator(QObject):
    """Composition root for capture subsystem.

    Owns the CaptureSession and the long-lived CapturePresenter.
    All signal/slot wiring happens here.
    """

    capture_available = Signal()

    def __init__(self, project_path: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._project_path = project_path
        self._repo = ProfileRepository(project_path)
        self._settings = AppSettings()
        self._session: CaptureSession | None = None
        self._presenter = None  # CapturePresenter, created in initialize()
        self._sources: dict[int, SourceInfo] = {}
        self._view_connections: list[tuple] = []
        self._grid_view = None
        self._max_active_sources = _DEFAULT_MAX_ACTIVE_SOURCES
        self._switch_worker: _CameraSwitchWorker | None = None
        self._discovery_worker: _DiscoveryWorker | None = None
        self._runtime_configs: dict[int, FrameSourceConfig] = {}
        self._profile_locked = False
        self._guidance_tracker = CaptureGuidanceTracker()
        self._last_guidance = None
        self._manual_camera_load_requested = False
        self._hotplug_timer = QTimer(self)
        self._hotplug_timer.setSingleShot(True)
        self._hotplug_timer.setInterval(_HOTPLUG_DEBOUNCE_MS)
        self._hotplug_timer.timeout.connect(self._poll_hotplug)
        self._hotplug_watcher = QFileSystemWatcher(self)
        self._hotplug_watcher.directoryChanged.connect(lambda _path: self._schedule_hotplug_poll())
        self._watch_hotplug_paths()

    def initialize(self) -> None:
        """Discover sources, match to profiles, create session and presenter."""
        profiles = self._repo.load_all()
        self._settings = self._repo.load_settings()
        self._profile_locked = bool(profiles)
        profiles_by_bus = {p.bus_info: p for p in profiles}

        discovered = discover_frame_sources()
        if self._profile_locked:
            profiles_by_bus = self._rebind_profiles_if_topology_changed(profiles, discovered)
        matched: list[tuple[FrameSourceOptions, SourceProfile]] = []

        next_source_id = max((p.source_id for p in profiles), default=-1) + 1

        for options in discovered:
            if options.bus_info in profiles_by_bus:
                profile = profiles_by_bus[options.bus_info]
            elif not self._profile_locked:
                profile = SourceProfile.with_defaults(
                    source_id=next_source_id,
                    bus_info=options.bus_info,
                )
                next_source_id += 1
                self._repo.save(profile)
            else:
                logger.info(
                    "Ignoring unconfigured capture device %s (%s); project profile is locked",
                    options.path,
                    options.bus_info,
                )
                continue
            matched.append((options, profile))

        active_ids = rebalance_active_source_ids(
            [
                SourcePoolEntry(
                    source_id=profile.source_id,
                    device_path=options.path,
                    ignored=profile.ignore,
                    connected=True,
                )
                for options, profile in matched
            ],
            max_active=self._max_active_sources,
        )

        frame_sources: list[FrameSource] = []

        for options, profile in matched:
            should_ignore = profile.source_id not in active_ids
            if profile.ignore != should_ignore:
                profile = profile.with_ignore(should_ignore)
                self._repo.save(profile)

            config = FrameSourceConfig(
                resolution=profile.resolution,
                fps=profile.capture_fps,
                pixel_format=profile.pixel_format,
                capture_backend=profile.capture_backend,
                gstreamer_pipeline=profile.gstreamer_pipeline,
            )

            if not profile.ignore:
                source = FrameSource(options.path, config)
                frame_sources.append(source)
                self._runtime_configs[profile.source_id] = config

            self._sources[profile.source_id] = SourceInfo(
                source_id=profile.source_id,
                device_path=options.path,
                profile=profile,
                options=options,
            )

        for profile in profiles:
            if profile.source_id not in self._sources:
                self._sources[profile.source_id] = SourceInfo(
                    source_id=profile.source_id,
                    device_path="",
                    profile=profile,
                    options=None,
                    error="Source not connected",
                )

        if frame_sources:
            self._session = CaptureSession(
                frame_sources,
                recording_settings=self._settings.recording,
            )

            from multiwebcam.ui.presenters.capture import CapturePresenter

            self._presenter = CapturePresenter(
                self._session,
                self.get_source_id_lookup(),
                inference_settings=self._settings.inference,
            )

    def _rebind_profiles_if_topology_changed(
        self,
        profiles: list[SourceProfile],
        discovered: list[FrameSourceOptions],
    ) -> dict[str, SourceProfile]:
        profiles_by_bus = {profile.bus_info: profile for profile in profiles}
        if not profiles or not discovered:
            return profiles_by_bus

        discovered_buses = {options.bus_info for options in discovered}
        unmatched_profiles = sorted(
            [profile for profile in profiles if profile.bus_info not in discovered_buses],
            key=lambda profile: (profile.ignore, profile.source_id),
        )
        new_options = [options for options in discovered if options.bus_info not in profiles_by_bus]

        if not unmatched_profiles or not new_options:
            return profiles_by_bus

        logger.warning(
            "Rebinding %s configured profile(s) to newly discovered camera topology",
            min(len(unmatched_profiles), len(new_options)),
        )
        rebound: list[SourceProfile] = []
        for profile, options in zip(unmatched_profiles, new_options):
            updated = profile.with_updates(bus_info=options.bus_info)
            self._repo.save(updated)
            rebound.append(updated)

        rebound_by_id = {profile.source_id: profile for profile in rebound}
        return {
            rebound_by_id.get(profile.source_id, profile).bus_info: rebound_by_id.get(profile.source_id, profile)
            for profile in profiles
        }

    def start(self) -> None:
        """Start the capture session."""
        if self._session:
            self._apply_saved_controls()
            self._session.start()
            self._pause_ignored_producers()

    def stop(self) -> None:
        """Stop presenter and session."""
        self._hotplug_timer.stop()
        self._disconnect_view()
        if self._discovery_worker is not None:
            self._discovery_worker.wait()
            self._discovery_worker = None
        if self._switch_worker is not None:
            self._switch_worker.wait()
            self._switch_worker = None
        if self._presenter:
            self._presenter.shutdown()
        if self._session:
            self._session.stop()

    def _watch_hotplug_paths(self) -> None:
        paths = []
        for path in (Path("/dev"), Path("/sys/class/video4linux")):
            if path.exists():
                paths.append(str(path))
        if paths:
            self._hotplug_watcher.addPaths(paths)

    def _schedule_hotplug_poll(self) -> None:
        if self._session is not None and self._session.is_recording:
            return
        self._hotplug_timer.start()

    @property
    def session(self) -> CaptureSession | None:
        return self._session

    @property
    def sources(self) -> dict[int, SourceInfo]:
        return self._sources

    def get_source_id_lookup(self) -> dict[str, int]:
        active_paths = set(self._session.active_device_paths) if self._session is not None else set()
        return {
            info.device_path: info.source_id
            for info in self._sources.values()
            if info.device_path and not info.error and info.device_path in active_paths
        }

    def get_device_path(self, source_id: int) -> str | None:
        info = self._sources.get(source_id)
        return info.device_path if info and not info.error else None

    def _pause_ignored_producers(self) -> None:
        """Pause producers for cameras marked as ignored in their profile.

        Silently skips devices whose producers haven't been created yet
        (e.g. when called before session.start()).
        """
        if self._session is None:
            return
        for info in self._sources.values():
            if info.profile.ignore and info.device_path and not info.error:
                try:
                    self._session.pause_producer(info.device_path)
                except ValueError:
                    pass

    def _apply_saved_controls(self) -> None:
        for info in self._sources.values():
            if not info.device_path or info.error:
                continue
            for name, cv in info.profile.controls.items():
                set_control(info.device_path, name, cv.value)

    def _disconnect_view(self) -> None:
        """Disconnect all presenter-to-view connections before view teardown."""
        for signal, slot in self._view_connections:
            try:
                signal.disconnect(slot)
            except RuntimeError:
                pass  # Already disconnected
        self._view_connections.clear()

    def _connect(self, signal, slot) -> None:
        """Connect and track a signal-slot pair for later disconnection."""
        signal.connect(slot)
        self._view_connections.append((signal, slot))

    def create_grid_view(self, parent=None):
        """Create and wire a grid view. Returns the view only."""
        self._disconnect_view()

        from multiwebcam.ui.views import GridView

        view = GridView(parent)
        self._grid_view = view
        view.set_storage_available(shutil.disk_usage(self._project_path).free)
        for source_id, info in self._sources.items():
            view.add_source(source_id, info.profile.label, ignore=info.profile.ignore)
            config = self._runtime_configs.get(source_id, self._source_config(info))
            w, h = config.resolution
            view.set_tile_resolution(source_id, f"{w}x{h}")
            if not info.device_path or info.error:
                view.set_source_error(source_id, "Disconnected")
        self._sync_grid_runtime_state()

        recordings_dir = self._project_path / "recordings"
        view.set_default_recording_name(next_recording_name(recordings_dir))

        if self._session is None or self._presenter is None:
            view.set_capture_available(False, "未发现可用摄像头，请检查 /dev/video*、v4l2-ctl 或 USB 连接")
            view.open_folder_requested.connect(self._open_project_folder)
            view.model_file_requested.connect(lambda: self._select_3dgs_model(view))
            view.load_cameras_requested.connect(lambda: self._load_cameras(view))
            view.pause_video_requested.connect(lambda: self._load_cameras(view))
            return view

        p = self._presenter

        # Wire presenter -> view
        self._connect(p.frames_ready, view.display_frames)
        self._connect(p.grid_stats_updated, view.update_stats)
        self._connect(p.quality_updated, view.update_quality)
        self._connect(p.quality_updated, lambda _qualities, quality: self._refresh_guidance(view, quality))
        self._connect(p.alignment_updated, view.update_alignment)
        self._connect(p.inference_status_updated, view.update_inference_status)
        self._connect(p.recording_stopping, view.set_stopping)
        self._connect(p.recording_queue_depth, view.update_queue_depth)
        self._connect(p.recording_duration, view.update_duration)

        def rec_true() -> None:
            view.set_recording(True)

        def _on_recording_stopped():
            view.set_recording(False)
            view.set_default_recording_name(next_recording_name(recordings_dir))

        self._connect(p.recording_started, rec_true)
        self._connect(p.recording_stopped, _on_recording_stopped)

        self._connect(view.ignore_toggled, self._on_ignore_toggled)
        self._connect(view.angle_changed, lambda _angle: self._refresh_guidance(view))

        view.set_mirror(p.mirror)
        self._connect(view.mirror_toggled, p.set_mirror)

        # Wire view -> presenter (view owns these, die with view)
        def _on_record(intent: GridRecordingIntent):
            if intent.is_extrinsic:
                output_dir = self._project_path / "calibration" / "extrinsic"
            else:
                name = _sanitize_recording_name(intent.recording_name)
                output_dir = self._project_path / "recordings" / name

            if output_dir.exists() and any(output_dir.iterdir()):
                relative = str(output_dir.relative_to(self._project_path))
                if not view.confirm_overwrite(relative):
                    return

            cam_ids = {
                info.device_path: info.source_id
                for info in self._sources.values()
                if info.device_path and not info.error and not info.profile.ignore
            }
            if cam_ids:
                p.start_recording(output_dir, cam_ids=cam_ids)

        view.record_requested.connect(_on_record)
        view.photo_requested.connect(lambda: self._on_photo_requested(view))
        view.stop_requested.connect(p.stop_recording)
        view.poll_interval_changed.connect(p.set_grid_poll_interval)
        view.workspace_changed.connect(lambda index: self._on_grid_workspace_changed(index))
        view.load_cameras_requested.connect(lambda: self._load_cameras(view))
        view.pause_video_requested.connect(lambda: self._toggle_video_transmission(view))

        view.open_folder_requested.connect(self._open_project_folder)
        view.model_file_requested.connect(lambda: self._select_3dgs_model(view))

        p.enter_grid_mode()
        self._pause_ignored_producers()
        self._refresh_guidance(view)
        return view

    def _on_grid_workspace_changed(self, index: int) -> None:
        """Transfer compute resources between live capture and model viewing."""
        if self._presenter is None:
            return
        if index == 4:
            try:
                self._presenter.enter_model_mode()
                if self._grid_view is not None:
                    self._grid_view.set_video_paused(True, "摄像头已暂停，资源用于 3DGS")
            except RuntimeError:
                logger.warning("Cannot pause cameras for 3DGS while recording")
            return
        if self._presenter.mode == "model":
            self._presenter.enter_grid_mode()
            self._pause_ignored_producers()
            if self._grid_view is not None:
                self._grid_view.set_video_paused(False, "视频传输已恢复")

    def _load_cameras(self, view) -> None:
        """Resume healthy cameras, scanning USB only when the current session is unhealthy."""
        if self._session is not None and self._session.producers_healthy:
            self._presenter.enter_grid_mode()
            self._pause_ignored_producers()
            view.set_video_paused(False, "摄像头正常，视频传输已启动")
            return
        self._manual_camera_load_requested = True
        view.set_video_paused(True, "正在扫描 USB 摄像头...")
        self._poll_hotplug()

    def _toggle_video_transmission(self, view) -> None:
        if self._session is None or self._presenter is None:
            self._load_cameras(view)
            return
        if self._presenter.mode == "paused":
            self._load_cameras(view)
            return
        try:
            self._presenter.pause_video_transmission()
        except RuntimeError:
            view.set_video_paused(False, "录制期间不能暂停视频传输")
            return
        view.set_video_paused(True, "视频传输已暂停")

    def _open_project_folder(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._project_path)))

    def _select_3dgs_model(self, view) -> None:
        """Select a PLY result for the embedded 3DGS workspace."""
        from PySide6.QtWidgets import QFileDialog

        initial_dir = self._project_path
        project_models = sorted(self._project_path.glob("*.ply"), key=lambda path: path.stat().st_mtime)
        if project_models:
            initial_dir = project_models[-1].parent

        selected, _ = QFileDialog.getOpenFileName(
            view,
            "打开 3DGS 模型",
            str(initial_dir),
            "Gaussian Splat PLY (*.ply);;所有文件 (*)",
        )
        if not selected:
            return
        view.load_model(selected)

    def _on_photo_requested(self, view) -> None:
        if self._presenter is None:
            return
        packets = self._presenter.latest_packets()
        if not packets:
            view.set_photo_capture_result("当前没有可拍摄画面", ok=False)
            return

        camera_info = self._snapshot_camera_info(packets.keys())
        if set(camera_info) != set(packets):
            missing = sorted(set(packets) - set(camera_info))
            view.set_photo_capture_result(f"无法匹配摄像头信息: {', '.join(missing)}", ok=False)
            return

        quality = evaluate_capture_set(
            packets,
            object_regions=self._presenter.latest_object_regions(),
        )
        selected_angle = view.selected_angle_deg()
        validation = self._guidance_tracker.validate_capture(selected_angle, packets, quality)
        self._last_guidance = validation.guidance
        view.update_guidance(validation.guidance)
        if not validation.accepted:
            view.set_photo_capture_result(f"拍摄已阻止: {_zh_capture_message(validation.message)}", ok=False)
            return

        try:
            result = save_snapshot_set(
                self._project_path / "captures",
                packets,
                camera_info,
                quality,
                ok_to_capture=validation.accepted,
                angle_deg=selected_angle,
                readiness_percent=validation.guidance.readiness_percent,
                progress_percent=validation.guidance.progress_percent,
                readiness_label=validation.guidance.readiness_label,
            )
        except Exception as exc:
            logger.exception("Failed to capture still images")
            view.set_photo_capture_result(f"拍摄失败: {exc}", ok=False)
            return

        guidance = self._guidance_tracker.register_capture(selected_angle, result.frame_id, packets, quality)
        self._last_guidance = guidance
        view.update_guidance(guidance)
        if guidance.next_angle_deg is not None:
            view.set_selected_angle_deg(guidance.next_angle_deg)
        rel_dir = result.output_dir.relative_to(self._project_path)
        status = _zh_readiness_label(guidance.readiness_label)
        view.set_photo_capture_result(
            (
                f"已拍摄 {selected_angle}° 第 {result.frame_id:06d} 组 "
                f"({status} {guidance.readiness_percent:.0f}%, 进度 {guidance.progress_percent:.0f}%) "
                f"-> {rel_dir}/images"
            ),
            ok=result.ok_to_capture,
        )

    def _snapshot_camera_info(self, device_paths) -> dict[str, SnapshotCameraInfo]:
        info_by_path = {}
        active_paths = set(self._session.active_device_paths) if self._session is not None else set()
        for info in self._sources.values():
            if not info.device_path or info.device_path not in device_paths or info.device_path not in active_paths:
                continue
            config = self._runtime_configs.get(info.source_id, self._source_config(info))
            info_by_path[info.device_path] = SnapshotCameraInfo(
                source_id=info.source_id,
                label=info.profile.label,
                bus_info=info.profile.bus_info,
                device_path=info.device_path,
                resolution=config.resolution,
                fps=config.fps,
                pixel_format=config.pixel_format,
            )
        return info_by_path

    def _refresh_guidance(self, view, quality=None) -> None:
        if self._presenter is None:
            return
        packets = self._presenter.latest_packets()
        if not packets:
            view.update_guidance(None)
            self._last_guidance = None
            return
        live_quality = quality or self._presenter.latest_quality() or evaluate_capture_set(packets)
        guidance = self._guidance_tracker.evaluate(packets, live_quality, view.selected_angle_deg())
        self._last_guidance = guidance
        view.update_guidance(guidance)

    def create_focus_view(self, source_id: int, parent=None):
        """Create and wire a focus view. Returns the view only."""
        if self._session is None or self._presenter is None:
            raise RuntimeError("Cannot create focus view: no capture session")

        self._disconnect_view()
        self._grid_view = None

        from multiwebcam.ui.views import FocusView

        info = self._sources.get(source_id)
        if not info or info.error:
            raise ValueError(f"Source {source_id} not available")
        if info.device_path not in self._session.active_device_paths:
            raise ValueError(f"Source {source_id} is not active")

        view = FocusView(source_id, info.profile.label, parent)
        config = FrameSourceConfig(
            resolution=info.profile.resolution,
            fps=info.profile.capture_fps,
            pixel_format=info.profile.pixel_format,
            capture_backend=info.profile.capture_backend,
            gstreamer_pipeline=info.profile.gstreamer_pipeline,
        )

        p = self._presenter

        # Wire presenter -> view
        self._connect(p.frame_ready, view.display_frame)
        self._connect(p.focus_stats_updated, view.update_stats)
        self._connect(p.resolutions_available, view.populate_resolutions)
        self._connect(p.framerates_available, view.populate_framerates)
        self._connect(p.initial_config_ready, view.set_current_config)
        self._connect(p.config_applied, view.set_config_applied)
        self._connect(p.config_error, view.set_config_error)
        self._connect(p.controls_ready, view.set_controls)
        self._connect(p.recording_stopping, view.set_stopping)

        def rec_true() -> None:
            view.set_recording(True)

        def rec_false() -> None:
            view.set_recording(False)

        self._connect(p.recording_started, rec_true)
        self._connect(p.recording_stopped, rec_false)

        # Wire control panel each time controls_ready fires
        def _wire_control_panel(controls) -> None:
            if view.control_panel is not None:
                view.control_panel.control_changed.connect(p.on_control_changed)
                view.control_panel.defaults_restore_requested.connect(p.on_restore_defaults)

        self._connect(p.controls_ready, _wire_control_panel)

        # Persist control changes
        def persist_slot(name: str, value: int) -> None:
            self._on_control_persist(source_id, name, value)

        self._connect(p.control_persist_requested, persist_slot)

        def cleared_slot() -> None:
            self._on_controls_cleared(source_id)

        self._connect(p.controls_cleared, cleared_slot)

        # Wire view -> presenter (view owns these)
        view.resolution_selected.connect(p.on_resolution_selected)
        view.apply_requested.connect(lambda: self._on_apply_config(view))
        output_dir = self._project_path / "calibration" / "intrinsic"
        view.record_requested.connect(lambda: p.start_recording(output_dir))
        view.stop_requested.connect(p.stop_recording)

        p.enter_focus_mode(
            info.device_path,
            source_id,
            info.options,
            config,
        )
        self._pause_ignored_producers()
        return view

    def _on_control_persist(self, source_id: int, name: str, value: int) -> None:
        info = self._sources.get(source_id)
        if not info:
            return

        from multiwebcam.sources.controls import query_controls

        controls = query_controls(info.device_path)
        ctrl = next((c for c in controls if c.name == name), None)
        if ctrl is None:
            return

        ctrl_min = ctrl.min if ctrl.min is not None else 0
        ctrl_max = ctrl.max if ctrl.max is not None else 1
        control_value = ControlValue(
            value=value,
            min=ctrl_min,
            max=ctrl_max,
        )
        updated_profile = info.profile.with_control(name, control_value)
        self._repo.save(updated_profile)
        info.profile = updated_profile

    def _on_controls_cleared(self, source_id: int) -> None:
        info = self._sources.get(source_id)
        if not info:
            return
        updated_profile = info.profile.with_controls_cleared()
        self._repo.save(updated_profile)
        info.profile = updated_profile

    def _on_ignore_toggled(self, source_id: int, ignore: bool) -> None:
        info = self._sources.get(source_id)
        if not info or info.error or not info.device_path:
            return
        if self._session is None:
            return
        if self._switch_worker is not None:
            if self._grid_view is not None:
                self._grid_view.set_source_ignored(source_id, info.profile.ignore)
            return
        if self._session.is_recording:
            if self._grid_view is not None:
                self._grid_view.set_source_ignored(source_id, info.profile.ignore)
            return

        if self._grid_view is not None:
            self._grid_view.set_ignore_controls_enabled(False)

        self._switch_worker = _CameraSwitchWorker(self, source_id, ignore)
        self._switch_worker.switch_completed.connect(
            self._on_camera_switch_completed,
            Qt.ConnectionType.QueuedConnection,
        )
        self._switch_worker.finished.connect(self._switch_worker.deleteLater)
        self._switch_worker.start()

    def _on_camera_switch_completed(self, result: CameraSwitchResult) -> None:
        if self._switch_worker is not None:
            self._switch_worker.wait()
            self._switch_worker = None

        if not result.ignore_updates:
            info = self._sources.get(result.requested_source_id)
            if info is not None and self._grid_view is not None:
                self._grid_view.set_source_ignored(result.requested_source_id, info.profile.ignore)

        for source_id, ignore in result.ignore_updates.items():
            info = self._sources.get(source_id)
            if info is None:
                continue
            updated_profile = info.profile.with_ignore(ignore)
            self._repo.save(updated_profile)
            info.profile = updated_profile
            if self._grid_view is not None:
                self._grid_view.set_source_ignored(source_id, ignore)
                config = self._runtime_configs.get(source_id, self._source_config(info))
                w, h = config.resolution
                self._grid_view.set_tile_resolution(source_id, f"{w}x{h}")

        if result.error:
            logger.warning("Camera switch completed with error: %s", result.error)

        self._refresh_presenter_lookup()
        if self._grid_view is not None:
            self._grid_view.set_ignore_controls_enabled(True)
            self._sync_grid_runtime_state()

    def _source_config(self, info: SourceInfo) -> FrameSourceConfig:
        return FrameSourceConfig(
            resolution=info.profile.resolution,
            fps=info.profile.capture_fps,
            pixel_format=info.profile.pixel_format,
            capture_backend=info.profile.capture_backend,
            gstreamer_pipeline=info.profile.gstreamer_pipeline,
        )

    def _refresh_presenter_lookup(self) -> None:
        if self._presenter is not None:
            self._presenter.set_source_id_lookup(self.get_source_id_lookup())

    def _poll_hotplug(self) -> None:
        if self._discovery_worker is not None or self._switch_worker is not None:
            return
        if self._session is not None and self._session.is_recording:
            return

        self._discovery_worker = _DiscoveryWorker()
        self._discovery_worker.discovery_completed.connect(
            self._on_discovery_completed,
            Qt.ConnectionType.QueuedConnection,
        )
        self._discovery_worker.finished.connect(self._discovery_worker.deleteLater)
        self._discovery_worker.start()

    def _on_discovery_completed(self, options_or_none: object, error_or_none: object) -> None:
        if self._discovery_worker is not None:
            self._discovery_worker.wait()
            self._discovery_worker = None

        if error_or_none:
            self._manual_camera_load_requested = False
            logger.warning("Skipping hotplug refresh: %s", error_or_none)
            return

        discovered = options_or_none
        if not isinstance(discovered, list):
            self._manual_camera_load_requested = False
            return
        if self._session is None:
            self._initialize_from_hotplug(discovered)
            if self._manual_camera_load_requested:
                self._manual_camera_load_requested = False
                if self._grid_view is not None:
                    if self._session is None:
                        self._grid_view.set_video_paused(True, "未发现可用 USB 摄像头")
                    else:
                        self._grid_view.set_video_paused(False, "USB 扫描完成，视频传输已启动")
            return
        self._refresh_discovered_sources(discovered)
        if self._manual_camera_load_requested:
            self._manual_camera_load_requested = False
            if self._session is not None and self._presenter is not None:
                if not self._session.producers_healthy:
                    self._session.stop()
                    self._session.start()
                    self._refresh_presenter_lookup()
                self._presenter.enter_grid_mode()
                self._pause_ignored_producers()
                if self._grid_view is not None:
                    self._grid_view.set_video_paused(False, "USB 扫描完成，视频传输已启动")

    def _initialize_from_hotplug(self, discovered: list[FrameSourceOptions]) -> None:
        if not discovered:
            return

        self.initialize()
        if self._session is None:
            return

        self._apply_saved_controls()
        self._session.start()
        self._pause_ignored_producers()
        self._refresh_presenter_lookup()
        self.capture_available.emit()

    def _refresh_discovered_sources(self, discovered: list[FrameSourceOptions]) -> None:
        if self._session is None:
            return

        options_by_bus = {options.bus_info: options for options in discovered}
        sources_by_bus = {info.profile.bus_info: info for info in self._sources.values()}

        next_source_id = max(self._sources, default=-1) + 1
        for options in discovered:
            if options.bus_info in sources_by_bus:
                continue
            if self._profile_locked:
                logger.info(
                    "Ignoring hotplugged unconfigured capture device %s (%s)",
                    options.path,
                    options.bus_info,
                )
                continue

            profile = SourceProfile.with_defaults(
                source_id=next_source_id,
                bus_info=options.bus_info,
            ).with_ignore(True)
            next_source_id += 1
            self._repo.save(profile)

            info = SourceInfo(
                source_id=profile.source_id,
                device_path=options.path,
                profile=profile,
                options=options,
            )
            self._sources[profile.source_id] = info
            sources_by_bus[options.bus_info] = info
            if self._grid_view is not None and not self._grid_view.has_source(info.source_id):
                self._grid_view.add_source(info.source_id, info.profile.label, ignore=True)
                w, h = info.profile.resolution
                self._grid_view.set_tile_resolution(info.source_id, f"{w}x{h}")

        active_paths = set(self._session.active_device_paths)
        for info in self._sources.values():
            options = options_by_bus.get(info.profile.bus_info)
            if options is None:
                if info.device_path in active_paths:
                    try:
                        self._session.remove_source(info.device_path)
                        self._runtime_configs.pop(info.source_id, None)
                    except Exception:
                        logger.exception("Failed to remove disconnected source %s", info.device_path)
                info.device_path = ""
                info.options = None
                info.error = "Source not connected"
                continue

            if info.device_path and info.device_path != options.path and info.device_path in active_paths:
                try:
                    self._session.remove_source(info.device_path)
                    self._runtime_configs.pop(info.source_id, None)
                except Exception:
                    logger.exception("Failed to remove moved source %s", info.device_path)

            info.device_path = options.path
            info.options = options
            info.error = None

        active_ids = rebalance_active_source_ids(self._pool_entries_with_updates({}), self._max_active_sources)
        ignore_updates: dict[int, bool] = {}

        for info in self._sources.values():
            should_ignore = info.source_id not in active_ids
            if not info.device_path or info.error:
                should_ignore = True

            is_active = bool(info.device_path and info.device_path in self._session.active_device_paths)

            if should_ignore and is_active:
                try:
                    self._session.remove_source(info.device_path)
                    self._runtime_configs.pop(info.source_id, None)
                    is_active = False
                except Exception:
                    logger.exception("Failed to deactivate source %s during hotplug refresh", info.source_id)

            if not should_ignore and not is_active:
                try:
                    self._activate_source_blocking(info.source_id)
                except Exception:
                    logger.exception("Failed to activate source %s during hotplug refresh", info.source_id)
                    should_ignore = True

            if info.device_path and not info.error and info.profile.ignore != should_ignore:
                ignore_updates[info.source_id] = should_ignore

        for source_id, ignore in ignore_updates.items():
            info = self._sources[source_id]
            updated_profile = info.profile.with_ignore(ignore)
            self._repo.save(updated_profile)
            info.profile = updated_profile

        if self._grid_view is not None:
            for info in self._sources.values():
                if self._grid_view.has_source(info.source_id):
                    self._grid_view.set_source_ignored(info.source_id, info.profile.ignore)
                    config = self._runtime_configs.get(info.source_id, self._source_config(info))
                    w, h = config.resolution
                    self._grid_view.set_tile_resolution(info.source_id, f"{w}x{h}")
            self._sync_grid_runtime_state()

        self._refresh_presenter_lookup()

    def _sync_grid_runtime_state(self) -> None:
        if self._grid_view is None or self._session is None:
            return
        active_paths = set(self._session.active_device_paths)
        for source_id, info in self._sources.items():
            if not self._grid_view.has_source(source_id):
                continue
            config = self._runtime_configs.get(source_id, self._source_config(info))
            w, h = config.resolution
            self._grid_view.set_tile_resolution(source_id, f"{w}x{h}")
            if not info.device_path or info.error:
                self._grid_view.set_source_error(source_id, "Disconnected")
            is_active_low_anchor = (
                info.device_path in active_paths
                and config.resolution == _LOW_RESOLUTION
            )
            can_toggle_ignore = bool(info.device_path and not info.error) and not is_active_low_anchor
            self._grid_view.set_source_ignore_enabled(source_id, can_toggle_ignore)

    def _switch_ignore_state_blocking(self, source_id: int, ignore: bool) -> CameraSwitchResult:
        if self._session is None:
            return CameraSwitchResult(source_id, ignore, {}, "No active capture session")
        if self._session.is_recording:
            return CameraSwitchResult(source_id, ignore, {source_id: self._sources[source_id].profile.ignore})

        info = self._sources.get(source_id)
        if info is None or info.error or not info.device_path:
            return CameraSwitchResult(source_id, ignore, {}, "Source is not available")

        ignore_updates: dict[int, bool] = {}

        if ignore:
            if info.device_path in self._session.active_device_paths:
                self._session.remove_source(info.device_path)
                self._runtime_configs.pop(source_id, None)
            ignore_updates[source_id] = True
            activated = self._activate_next_standby_blocking(ignore_updates, excluded_source_id=source_id)
            if activated:
                return CameraSwitchResult(source_id, ignore, ignore_updates)

            try:
                self._activate_source_blocking(source_id)
                ignore_updates[source_id] = False
                return CameraSwitchResult(
                    source_id,
                    ignore,
                    ignore_updates,
                    "No standby source could replace the requested camera",
                )
            except Exception as exc:
                return CameraSwitchResult(source_id, ignore, ignore_updates, str(exc))

        if len(self._session.active_device_paths) >= self._max_active_sources:
            return CameraSwitchResult(
                source_id,
                ignore,
                {source_id: True},
                "Active camera pool is full",
            )

        self._activate_source_blocking(source_id)
        ignore_updates[source_id] = False
        return CameraSwitchResult(source_id, ignore, ignore_updates)

    def _pool_entries_with_updates(self, ignore_updates: dict[int, bool]) -> list[SourcePoolEntry]:
        return [
            SourcePoolEntry(
                source_id=info.source_id,
                device_path=info.device_path,
                ignored=ignore_updates.get(info.source_id, info.profile.ignore),
                connected=bool(info.device_path and not info.error),
            )
            for info in self._sources.values()
        ]

    def _active_source_ids_from_session(self) -> set[int]:
        if self._session is None:
            return set()
        active_paths = set(self._session.active_device_paths)
        return {
            info.source_id
            for info in self._sources.values()
            if info.device_path and info.device_path in active_paths
        }

    def _activate_next_standby_blocking(
        self,
        ignore_updates: dict[int, bool],
        excluded_source_id: int | None = None,
    ) -> bool:
        if self._session is None:
            return False
        excluded_source_ids = {excluded_source_id} if excluded_source_id is not None else set()
        while len(self._session.active_device_paths) < self._max_active_sources:
            standby_id = self._choose_standby_source_id(ignore_updates, excluded_source_ids)
            if standby_id is None:
                return False
            try:
                self._activate_source_blocking(standby_id)
                ignore_updates[standby_id] = False
                return True
            except Exception:
                logger.exception("Failed to activate standby source %s", standby_id)
                ignore_updates[standby_id] = True
                excluded_source_ids.add(standby_id)
        return True

    def _choose_standby_source_id(
        self,
        ignore_updates: dict[int, bool],
        excluded_source_ids: set[int],
    ) -> int | None:
        active_source_ids = self._active_source_ids_from_session()
        for entry in sorted(self._pool_entries_with_updates(ignore_updates), key=lambda item: item.source_id):
            if entry.source_id in excluded_source_ids:
                continue
            if entry.source_id in active_source_ids:
                continue
            if not entry.connected or not entry.device_path:
                continue
            if entry.ignored:
                return entry.source_id
        return None

    def _activate_source_blocking(self, source_id: int) -> None:
        info = self._sources.get(source_id)
        if info is None or self._session is None or not info.device_path or info.error:
            return
        if info.device_path in self._session.active_device_paths:
            return

        config = self._activation_config(info)
        source = FrameSource(info.device_path, config)
        self._session.add_source(source)
        self._runtime_configs[source_id] = config
        for name, cv in info.profile.controls.items():
            set_control(info.device_path, name, cv.value)

    def _activation_config(self, info: SourceInfo) -> FrameSourceConfig:
        config = self._source_config(info)
        if config.resolution != _HIGH_RESOLUTION:
            return config

        active_paths = set(self._session.active_device_paths) if self._session else set()
        active_high = sum(
            1
            for source_id, runtime_config in self._runtime_configs.items()
            if runtime_config.resolution == _HIGH_RESOLUTION
            and self._sources.get(source_id) is not None
            and self._sources[source_id].device_path in active_paths
        )
        if active_high >= _MAX_ACTIVE_HIGH_RESOLUTION_SOURCES:
            return FrameSourceConfig(
                resolution=_LOW_RESOLUTION,
                fps=config.fps,
                pixel_format=config.pixel_format,
                capture_backend=config.capture_backend,
                gstreamer_pipeline=config.gstreamer_pipeline,
                warmup_frames=config.warmup_frames,
                startup_timeout_seconds=config.startup_timeout_seconds,
                read_timeout_seconds=config.read_timeout_seconds,
                v4l2_options=config.v4l2_options,
            )
        return config

    def _on_apply_config(self, view) -> None:
        """Handle Apply button -- change source configuration."""
        if self._presenter is None or self._session is None:
            return

        resolution = view.selected_resolution
        framerate = view.selected_framerate

        if resolution == (0, 0) or framerate == 0:
            self._presenter.apply_config_error("Invalid configuration selected")
            return

        new_config = FrameSourceConfig(
            resolution=resolution,
            fps=framerate,
            pixel_format="mjpeg",
            capture_backend=self._source_config(self._sources[view.source_id]).capture_backend,
            gstreamer_pipeline=self._source_config(self._sources[view.source_id]).gstreamer_pipeline,
        )

        device_path = self._presenter.focused_device_path
        if device_path is None:
            self._presenter.apply_config_error("No focused device")
            return

        try:
            self._session.replace_source(device_path, new_config)
        except Exception as e:
            self._presenter.apply_config_error(str(e))
            return

        source_id = self.get_source_id_lookup().get(device_path)
        if source_id is not None:
            info = self._sources.get(source_id)
            if info:
                updated_profile = info.profile.with_updates(
                    resolution=resolution,
                    capture_fps=framerate,
                    pixel_format="mjpeg",
                )
                self._repo.save(updated_profile)
                info.profile = updated_profile

        self._presenter.apply_config_result(new_config)
