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
from multiwebcam.quality.guidance import CaptureGuidanceTracker, CaptureValidation
from multiwebcam.quality.metrics import CaptureSetQuality
from multiwebcam.snapshot import SnapshotCameraInfo, SnapshotResult, save_snapshot_set
from multiwebcam.sources import (
    FrameSource,
    FrameSourceConfig,
    FrameSourceOptions,
    discover_frame_sources,
    usb_root_bus,
)
from multiwebcam.sources.controls import set_control
from multiwebcam.ui.active_pool import SourcePoolEntry, rebalance_active_source_ids

logger = logging.getLogger(__name__)
_DEFAULT_MAX_ACTIVE_SOURCES = 4
_HOTPLUG_DEBOUNCE_MS = 1000
_HIGH_RESOLUTION = (1280, 720)
_LOW_RESOLUTION = (640, 480)
_MAX_HIGH_RESOLUTION_SOURCES_PER_USB_ROOT = 2


def _initial_low_resolution_source_ids(
    matched: list[tuple[FrameSourceOptions, SourceProfile]],
    active_ids: set[int],
) -> set[int]:
    """Choose stable low-resolution anchors before opening USB cameras.

    When more than two configured 720p sources share one USB root, lowering
    the last enumerated source is not reliable: endpoint scheduling on the
    validated Jetson topology requires the first USB2 source to be the 480p
    anchor.  Select the lowest source IDs up front so the assignment is
    deterministic and independent of discovery iteration side effects.
    """
    high_sources_by_root: dict[str, list[int]] = {}
    for options, profile in matched:
        if (
            profile.source_id in active_ids
            and profile.resolution == _HIGH_RESOLUTION
        ):
            root_bus = usb_root_bus(options.bus_info)
            high_sources_by_root.setdefault(root_bus, []).append(profile.source_id)

    low_resolution_ids: set[int] = set()
    for source_ids in high_sources_by_root.values():
        overflow = len(source_ids) - _MAX_HIGH_RESOLUTION_SOURCES_PER_USB_ROOT
        if overflow > 0:
            low_resolution_ids.update(sorted(source_ids)[:overflow])
    return low_resolution_ids


def _sanitize_recording_name(raw: str) -> str:
    """Sanitize user input to a safe filesystem name."""
    name = raw.strip()
    name = re.sub(r"[^\w\-]", "_", name)
    name = name.lstrip("-")
    return name or "untitled"


def _next_capture_name(captures_dir: Path, object_name: str) -> str:
    """Allocate object1, object2, ... without overwriting an earlier capture."""
    suffix = 1
    while (captures_dir / f"{object_name}{suffix}").exists():
        suffix += 1
    return f"{object_name}{suffix}"


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
            result = self._coordinator._switch_ignore_state_blocking(
                self._source_id,
                self._ignore,
                cancel_check=self.isInterruptionRequested,
            )
        except InterruptedError:
            return
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
            result = discover_frame_sources(
                cancel_check=self.isInterruptionRequested,
            )
            if not self.isInterruptionRequested():
                self.discovery_completed.emit(result, None)
        except InterruptedError:
            return
        except Exception as exc:
            logger.exception("Camera discovery failed")
            self.discovery_completed.emit(None, str(exc))


@dataclass(frozen=True)
class CameraLoadResult:
    """Result delivered to the UI after background camera work completes."""

    error: str | None
    started_session: bool


class _CameraLoadWorker(QThread):
    """Open, refresh, and warm up cameras without blocking the Qt thread."""

    load_completed = Signal(object)  # CameraLoadResult

    def __init__(
        self,
        coordinator: "CaptureCoordinator",
        discovered: list[FrameSourceOptions],
        allow_unconfigured: bool,
        preserve_existing: bool,
        start_session: bool,
    ) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._discovered = discovered
        self._allow_unconfigured = allow_unconfigured
        self._preserve_existing = preserve_existing
        self._start_session = start_session

    def run(self) -> None:
        error: str | None = None
        try:
            if self._start_session:
                self._coordinator._start_session_blocking()
            else:
                self._coordinator._refresh_discovered_sources(
                    self._discovered,
                    allow_unconfigured=self._allow_unconfigured,
                    preserve_existing=self._preserve_existing,
                    update_view=False,
                )
                self._coordinator._recover_capture_session_blocking()
        except Exception as exc:
            logger.exception("Camera load worker failed")
            error = str(exc).strip() or type(exc).__name__
        self.load_completed.emit(CameraLoadResult(error, self._start_session))


class _TaskPackageWorker(QThread):
    """Build the visible eight-image staging task off the Qt UI thread."""

    package_completed = Signal(object, object)  # TaskPackageResult | None, str | None

    def __init__(self, capture_dir: Path) -> None:
        super().__init__()
        self._capture_dir = capture_dir

    def run(self) -> None:
        try:
            from tx_rx.jetson_client import build_configured_task_package

            result = build_configured_task_package(
                self._capture_dir,
                cancel_check=self.isInterruptionRequested,
            )
            if self.isInterruptionRequested():
                return
            self.package_completed.emit(result, None)
        except Exception as exc:
            if self.isInterruptionRequested():
                return
            logger.exception("Task package generation failed for %s", self._capture_dir)
            self.package_completed.emit(None, str(exc).strip() or type(exc).__name__)


@dataclass(frozen=True)
class _SnapshotRequest:
    output_root: Path
    capture_name: str
    object_name: str
    packets: dict
    camera_info: dict[str, SnapshotCameraInfo]
    quality: CaptureSetQuality
    angle_deg: int
    tracker: CaptureGuidanceTracker


@dataclass(frozen=True)
class _SnapshotOutcome:
    request: _SnapshotRequest
    validation: CaptureValidation | None
    result: SnapshotResult | None
    error: str | None = None


class _SnapshotWorker(QThread):
    """Validate one angle and compress its JPEG files off the Qt thread."""

    snapshot_completed = Signal(object)

    def __init__(self, request: _SnapshotRequest) -> None:
        super().__init__()
        self._request = request

    def run(self) -> None:
        request = self._request
        try:
            validation = request.tracker.validate_capture(
                request.angle_deg,
                request.packets,
                request.quality,
            )
            if not validation.accepted:
                self.snapshot_completed.emit(
                    _SnapshotOutcome(request, validation, None)
                )
                return
            result = save_snapshot_set(
                request.output_root,
                request.capture_name,
                request.object_name,
                request.packets,
                request.camera_info,
                request.quality,
                ok_to_capture=True,
                angle_deg=request.angle_deg,
                readiness_percent=validation.guidance.readiness_percent,
                progress_percent=validation.guidance.progress_percent,
                readiness_label=validation.guidance.readiness_label,
            )
        except Exception as exc:
            logger.exception("Failed to capture still images")
            self.snapshot_completed.emit(
                _SnapshotOutcome(request, None, None, str(exc))
            )
            return
        self.snapshot_completed.emit(
            _SnapshotOutcome(request, validation, result)
        )


class _StagingScanWorker(QThread):
    """Discover and validate staged tasks without blocking the UI."""

    scan_completed = Signal(object, object)  # list[StagingTask] | None, str | None

    def run(self) -> None:
        try:
            from tx_rx.jetson_client import scan_staging_tasks

            self.scan_completed.emit(scan_staging_tasks(), None)
        except Exception as exc:
            logger.exception("Staging scan failed")
            self.scan_completed.emit(None, str(exc).strip() or type(exc).__name__)


class _StagedUploadWorker(QThread):
    """Upload validated staging directories sequentially."""

    upload_status = Signal(str)
    upload_completed = Signal(object, object)  # list[TaskUploadResult], list[str]

    def __init__(self, task_dirs: list[Path]) -> None:
        super().__init__()
        self._task_dirs = task_dirs

    def run(self) -> None:
        results = []
        errors = []
        total = len(self._task_dirs)
        try:
            from tx_rx.jetson_client import upload_staged_task
        except Exception as exc:
            self.upload_completed.emit([], [str(exc).strip() or type(exc).__name__])
            return
        for index, task_dir in enumerate(self._task_dirs, start=1):
            if self.isInterruptionRequested():
                break
            self.upload_status.emit(f"正在上传 {index}/{total}: {task_dir.name}")
            try:
                results.append(
                    upload_staged_task(
                        task_dir,
                        cancel_check=self.isInterruptionRequested,
                    )
                )
            except Exception as exc:
                logger.exception("Staged task upload failed for %s", task_dir)
                errors.append(f"{task_dir.name}: {str(exc).strip() or type(exc).__name__}")
                if self.isInterruptionRequested():
                    break
        self.upload_completed.emit(results, errors)


class _CaptureTransferWorker(QThread):
    """Lazily run upload, status polling, PLY download, validation, and ACK."""

    progress_changed = Signal(int, str)
    log_message = Signal(str)
    upload_confirmed = Signal(object)
    transfer_completed = Signal(object, object)

    def __init__(self, capture_dir: Path) -> None:
        super().__init__()
        self._capture_dir = capture_dir

    def run(self) -> None:
        try:
            from tx_rx.config import load_config
            from tx_rx.jetson_client import (
                TaskUploadError,
                build_configured_task_package,
                upload_staged_task,
            )
            from tx_rx.jetson_client.transfer import (
                acknowledge_result,
                download_ply,
                get_ply_metadata,
                poll_status,
            )

            def check_interruption() -> None:
                if self.isInterruptionRequested():
                    raise TaskUploadError("transfer cancelled")

            check_interruption()
            config = load_config()
            self.log_message.emit(f"开始校验本地任务：{self._capture_dir.name}")
            self.progress_changed.emit(10, "正在校验照片文件夹...")
            package = build_configured_task_package(self._capture_dir)
            check_interruption()
            self.log_message.emit(f"照片校验通过：capture_id={package.capture_id}")
            self.log_message.emit(f"任务整理目录：{package.staging_dir}")
            self.progress_changed.emit(35, "8张照片已整理，正在上传至 WSL...")
            self.log_message.emit("正在请求 WSL /upload，请等待服务端确认...")
            result = upload_staged_task(
                package.staging_dir,
                cancel_check=self.isInterruptionRequested,
            )
            response = result.upload_response
            self.log_message.emit("WSL /upload 已返回并通过协议校验")
            self.log_message.emit(
                f"接收依据：message_type={response.message_type}, status={response.status}, "
                f"capture_id={response.capture_id}, duplicate={response.duplicate}"
            )
            self.log_message.emit(
                f"重建请求：message_type={result.reconstruct_response.message_type}, "
                f"status={result.reconstruct_response.status}"
            )
            self.upload_confirmed.emit(result)

            self.progress_changed.emit(40, "照片已接收，后台低频等待重建完成...")
            self.log_message.emit(
                f"开始低频轮询训练状态：每 {config.status_poll_interval_seconds:g} 秒一次"
            )
            last_status = None

            def status_progress(message: str) -> None:
                nonlocal last_status
                parts = dict(
                    item.split("=", 1) for item in message.split() if "=" in item
                )
                stage = parts.get("stage", "处理中")
                try:
                    server_progress = max(0, min(100, int(parts.get("progress", "0"))))
                except ValueError:
                    server_progress = 0
                self.progress_changed.emit(40 + int(server_progress * 0.35), f"上位机训练：{stage} {server_progress}%")
                current = (stage, server_progress)
                if current != last_status:
                    self.log_message.emit(f"训练状态：stage={stage}, progress={server_progress}%")
                    last_status = current

            status = poll_status(
                result.task_id,
                package.capture_id,
                config,
                cancel_check=self.isInterruptionRequested,
                progress_callback=status_progress,
            )
            self.log_message.emit(f"训练完成：status={status.status.value}")
            self.progress_changed.emit(78, "训练完成，正在获取模型元数据...")
            check_interruption()
            metadata = get_ply_metadata(
                result.task_id,
                package.capture_id,
                config,
                cancel_check=self.isInterruptionRequested,
            )
            self.log_message.emit(
                f"模型元数据通过校验：{metadata.filename}, {metadata.file_size} bytes, "
                f"{metadata.chunk_count} 块"
            )

            def download_progress(message: str) -> None:
                try:
                    payload = message[len("download="):] if message.startswith("download=") else message
                    downloaded, total = payload.split("/", 1)
                    downloaded_bytes = int(downloaded)
                    total_bytes = int(total)
                    ratio = downloaded_bytes / max(1, total_bytes)
                except (ValueError, AttributeError):
                    downloaded_bytes = 0
                    total_bytes = metadata.file_size
                    ratio = 0.0
                self.progress_changed.emit(
                    80 + int(ratio * 18),
                    f"正在下载 3DGS 模型：{downloaded_bytes}/{total_bytes} bytes",
                )

            self.log_message.emit("仅在训练完成后启动模型下载")
            final_path = download_ply(
                metadata,
                config,
                cancel_check=self.isInterruptionRequested,
                progress_callback=download_progress,
            )
            self.progress_changed.emit(99, "模型下载完成，正在执行完整校验和 ACK...")
            check_interruption()
            ack = acknowledge_result(
                metadata,
                final_path,
                config,
                cancel_check=self.isInterruptionRequested,
            )
            self.log_message.emit(f"模型已校验并保存：{final_path}")
            self.log_message.emit(f"接收确认：message_type={ack.message_type}")
            self.progress_changed.emit(100, "完整闭环完成：模型已安全保存到 Jetson")
            self.transfer_completed.emit(
                {
                    "upload_result": result,
                    "final_path": final_path,
                    "metadata": metadata,
                    "ack": ack,
                },
                None,
            )
        except Exception as exc:
            logger.exception("Selected capture transfer failed: %s", self._capture_dir)
            self.log_message.emit(f"上传失败：{str(exc).strip() or type(exc).__name__}")
            self.transfer_completed.emit(None, str(exc).strip() or type(exc).__name__)


class CaptureCoordinator(QObject):
    """Composition root for capture subsystem.

    Owns the CaptureSession and the long-lived CapturePresenter.
    All signal/slot wiring happens here.
    """

    capture_available = Signal()
    runtime_state_changed = Signal(str, object)
    capture_progress_changed = Signal(object)
    capture_completed = Signal(object)
    model_resources_released = Signal(bool)

    def __init__(
        self,
        project_path: Path,
        parent: QObject | None = None,
        capture_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self._project_path = project_path
        self._capture_only = capture_only
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
        self._camera_load_worker: _CameraLoadWorker | None = None
        self._task_package_worker: _TaskPackageWorker | None = None
        self._snapshot_worker: _SnapshotWorker | None = None
        self._staging_scan_worker: _StagingScanWorker | None = None
        self._staged_upload_worker: _StagedUploadWorker | None = None
        self._capture_transfer_worker: _CaptureTransferWorker | None = None
        self._packaging_capture_dir: Path | None = None
        self._packaged_capture_dirs: set[Path] = set()
        self._ready_staging_dirs: list[Path] = []
        self._uploaded_staging_dirs: set[Path] = set()
        self._upload_after_scan = False
        self._runtime_configs: dict[int, FrameSourceConfig] = {}
        self._profile_locked = False
        self._guidance_tracker = CaptureGuidanceTracker()
        self._active_snapshot_name: str | None = None
        self._active_snapshot_object_name: str | None = None
        self._last_guidance = None
        self._manual_camera_load_requested = False
        self._hotplug_pending = False
        self._hotplug_timer = QTimer(self)
        self._hotplug_timer.setSingleShot(True)
        self._hotplug_timer.setInterval(_HOTPLUG_DEBOUNCE_MS)
        self._hotplug_timer.timeout.connect(self._poll_hotplug)
        self._hotplug_watcher = QFileSystemWatcher(self)
        self._hotplug_watcher.directoryChanged.connect(lambda _path: self._schedule_hotplug_poll())
        self._watch_hotplug_paths()
        self._staging_scan_timer = QTimer(self)
        self._staging_scan_timer.setInterval(30000)
        self._staging_scan_timer.timeout.connect(self._start_staging_scan)
        if not self._capture_only:
            self._staging_scan_timer.start()

    def initialize(
        self,
        allow_unconfigured: bool = False,
        discovered: list[FrameSourceOptions] | None = None,
    ) -> None:
        """Discover sources, match to profiles, create session and presenter.

        Normal startup keeps a configured project closed to unknown devices.
        A user-requested camera load is allowed to register a newly discovered
        device after it has been inspected by the V4L2 discovery worker.
        """
        profiles = self._repo.load_all()
        self._settings = self._repo.load_settings()
        self._profile_locked = bool(profiles)
        profiles_by_bus = {p.bus_info: p for p in profiles}

        if discovered is None:
            discovered = discover_frame_sources()
        if self._profile_locked:
            profiles_by_bus = self._rebind_profiles_if_topology_changed(profiles, discovered)
        matched: list[tuple[FrameSourceOptions, SourceProfile]] = []

        next_source_id = max((p.source_id for p in profiles), default=-1) + 1

        for options in discovered:
            if options.bus_info in profiles_by_bus:
                profile = profiles_by_bus[options.bus_info]
            elif not self._profile_locked or allow_unconfigured:
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
        low_resolution_source_ids = _initial_low_resolution_source_ids(
            matched,
            active_ids,
        )

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

            # USB bandwidth is shared by the root controller.  Apply the
            # deterministic anchor selected above instead of lowering the
            # last enumerated camera, which is unstable on the Jetson USB2
            # topology documented for this project.
            if profile.source_id in low_resolution_source_ids:
                config = self._config_with_resolution(config, _LOW_RESOLUTION)

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
            self._presenter.model_resources_released.connect(
                self.model_resources_released.emit
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
        if self._session is None:
            return

        try:
            self._start_session_blocking()
            self._refresh_presenter_lookup()
        except Exception as exc:
            # A capture failure must not prevent the Qt event loop from
            # starting. The grid remains available so the user can inspect
            # the failed tile and retry after reconnecting the device.
            logger.exception("Capture session failed to start")
            self._mark_capture_start_failure(exc)

        self._sync_capture_start_state()

    def start_async(self) -> None:
        """Discover and start cameras without blocking the Qt thread.

        ``MainWindow`` calls this after the initial grid has been created so
        V4L2 discovery and warm-up cannot delay the first paint. The
        synchronous ``start`` method remains available for command-line probes
        and tests that intentionally own their worker context.
        """
        if self._camera_load_worker is not None or self._discovery_worker is not None:
            return
        self.runtime_state_changed.emit(
            "discovering",
            {"message": "正在后台扫描摄像头…", "camera_count": 0},
        )
        if self._grid_view is not None:
            if hasattr(self._grid_view, "set_camera_load_busy"):
                self._grid_view.set_camera_load_busy(True)
            self._grid_view.set_video_paused(True, "正在后台扫描摄像头...")
        if self._session is None:
            self._poll_hotplug()
            return
        self._start_camera_load_worker(
            [],
            allow_unconfigured=False,
            preserve_existing=False,
            start_session=True,
        )

    def _start_session_blocking(self) -> None:
        """Start cameras and apply hardware settings in the caller's worker."""
        if self._session is None:
            return
        self._apply_saved_controls()
        self._session.start()
        self._record_session_startup_errors()
        self._pause_ignored_producers()

    def _recover_capture_session_blocking(self) -> None:
        """Retry an unhealthy session without interrupting a healthy one."""
        if self._session is None or self._session.producers_healthy:
            return
        self._session.stop()
        self._start_session_blocking()

    def _mark_capture_start_failure(self, error: Exception) -> None:
        detail = str(error).strip() or type(error).__name__
        for info in self._sources.values():
            if info.device_path:
                info.error = detail

    def _sync_capture_start_state(self) -> None:
        if self._session is None:
            self.runtime_state_changed.emit(
                "unavailable",
                {
                    "message": "未发现可用摄像头，请检查 USB 连接或 /dev/video*。",
                    "camera_count": 0,
                },
            )
            if self._grid_view is not None:
                self._grid_view.set_capture_available(
                    False,
                    "未发现可用摄像头，请检查 /dev/video*、v4l2-ctl 或 USB 连接",
                )
            return
        if self._grid_view is None:
            return

        active_count = len(self.get_source_id_lookup())
        failed_count = sum(1 for info in self._sources.values() if info.device_path and info.error)
        self._grid_view.set_capture_available(active_count > 0)
        self._sync_grid_runtime_state()

        if failed_count:
            if active_count:
                self._grid_view.set_photo_capture_result(
                    f"已启动 {active_count} 路摄像头，{failed_count} 路启动失败；可点击“加载摄像头”重试",
                    ok=False,
                )
            else:
                self._grid_view.set_photo_capture_result(
                    "摄像头暂未启动，请检查连接后点击“加载摄像头”重试",
                    ok=False,
                )
        elif active_count:
            self._grid_view.set_photo_capture_result("视频传输已启动", ok=True)
        if active_count:
            self.runtime_state_changed.emit(
                "ready",
                {
                    "message": "已启动 {} 路摄像头。".format(active_count),
                    "camera_count": active_count,
                },
            )
        else:
            self.runtime_state_changed.emit(
                "unavailable",
                {
                    "message": "摄像头已发现，但没有可用视频流。",
                    "camera_count": 0,
                    "failed_count": failed_count,
                },
            )

    def stop(self, timeout_ms: int = 5000) -> bool:
        """Stop presenter and session."""
        import time

        self._hotplug_timer.stop()
        self._staging_scan_timer.stop()
        deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
        all_stopped = True

        def stop_worker(attribute: str) -> None:
            nonlocal all_stopped
            worker = getattr(self, attribute)
            if worker is None:
                return
            worker.requestInterruption()
            remaining = max(0, int((deadline - time.monotonic()) * 1000))
            if worker.wait(remaining):
                setattr(self, attribute, None)
            else:
                logger.error("%s did not stop before shutdown deadline", attribute)
                all_stopped = False

        stop_worker("_discovery_worker")
        stop_worker("_switch_worker")
        stop_worker("_camera_load_worker")
        stop_worker("_task_package_worker")
        stop_worker("_snapshot_worker")
        if self._task_package_worker is None:
            self._packaging_capture_dir = None
        stop_worker("_staging_scan_worker")
        stop_worker("_staged_upload_worker")
        stop_worker("_capture_transfer_worker")
        if not all_stopped:
            self._hotplug_timer.start()
            if not self._capture_only:
                self._staging_scan_timer.start()
            return False
        if self._presenter:
            remaining = max(0, int((deadline - time.monotonic()) * 1000))
            if self._presenter.shutdown(remaining) is False:
                logger.error("Capture presenter did not stop before shutdown deadline")
                self._hotplug_timer.start()
                if not self._capture_only:
                    self._staging_scan_timer.start()
                return False
        if self._session:
            remaining = max(0.0, deadline - time.monotonic())
            if self._session.stop(remaining) is False:
                self._hotplug_timer.start()
                if not self._capture_only:
                    self._staging_scan_timer.start()
                return False
        self._disconnect_view()
        self.runtime_state_changed.emit(
            "stopped",
            {"message": "摄像头线程已停止并释放。", "camera_count": 0},
        )
        return True

    def _watch_hotplug_paths(self) -> None:
        paths = []
        for path in (Path("/dev"), Path("/sys/class/video4linux")):
            if path.exists():
                paths.append(str(path))
        if paths:
            self._hotplug_watcher.addPaths(paths)

    def _schedule_hotplug_poll(self) -> None:
        if self._session is not None and self._session.is_recording:
            self._hotplug_pending = True
            self.runtime_state_changed.emit(
                "error",
                {
                    "message": "录制期间检测到摄像头连接变化；录制结束后将自动复查。",
                    "camera_count": len(self.get_source_id_lookup()),
                },
            )
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

        view = GridView(parent, capture_only=self._capture_only)
        self._grid_view = view
        view.set_app_settings(self._settings)
        view.settings_save_requested.connect(lambda settings: self._save_app_settings(view, settings))
        if not self._capture_only:
            view.upload_staged_tasks_requested.connect(lambda: self._upload_staged_tasks(view))
            view.transfer_folder_requested.connect(lambda: self._select_transfer_folder(view))
            view.transfer_upload_requested.connect(lambda path: self._upload_selected_capture(view, path))
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
            if not self._capture_only:
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
        self._connect(
            p.recording_failed,
            lambda message: self.runtime_state_changed.emit(
                "error",
                {
                    "message": message,
                    "camera_count": len(self.get_source_id_lookup()),
                },
            ),
        )

        def rec_true() -> None:
            view.set_recording(True)
            self.runtime_state_changed.emit(
                "recording",
                {
                    "message": "正在录制多路视频。",
                    "camera_count": len(self.get_source_id_lookup()),
                },
            )

        def _on_recording_stopped():
            view.set_recording(False)
            view.set_default_recording_name(next_recording_name(recordings_dir))
            self.runtime_state_changed.emit(
                "ready",
                {
                    "message": "录制已停止，摄像头保持预览。",
                    "camera_count": len(self.get_source_id_lookup()),
                },
            )
            if self._hotplug_pending:
                self._hotplug_pending = False
                self._hotplug_timer.start()

        self._connect(p.recording_started, rec_true)
        self._connect(
            p.recording_stopping,
            lambda: self.runtime_state_changed.emit(
                "stopping",
                {
                    "message": "正在安全结束录制并清空编码队列…",
                    "camera_count": len(self.get_source_id_lookup()),
                },
            ),
        )
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
        if not self._capture_only:
            view.model_file_requested.connect(lambda: self._select_3dgs_model(view))

        p.enter_grid_mode()
        self._pause_ignored_producers()
        self._refresh_guidance(view)
        if (
            self._session.producers_healthy
            or self._session.startup_errors
            or any(info.device_path and info.error for info in self._sources.values())
        ):
            self._sync_capture_start_state()
        return view

    def _save_app_settings(self, view, settings: AppSettings) -> None:
        """Persist workstation settings and apply recording settings safely."""
        self._repo.save_settings(settings)
        self._settings = settings
        if self._session is not None:
            self._session.recording_settings = settings.recording
        view.show_settings_saved()

    def _on_grid_workspace_changed(self, index: int) -> None:
        """Transfer compute resources between live capture and model viewing."""
        self.set_model_mode(index == 5)

    def set_model_mode(self, active: bool) -> bool:
        """Pause or resume capture work for an externally hosted 3DGS viewer."""
        if self._presenter is None:
            if active:
                self.model_resources_released.emit(True)
            return True
        if active:
            if self._presenter.mode == "model":
                return True
            try:
                self._presenter.enter_model_mode()
                if self._grid_view is not None:
                    self._grid_view.set_video_paused(True, "摄像头已暂停，资源用于 3DGS")
            except RuntimeError:
                logger.warning("Cannot pause cameras for 3DGS while recording")
                return False
            return True
        if self._presenter.mode in {"model", "quiescing"}:
            self._presenter.enter_grid_mode()
            self._pause_ignored_producers()
            if self._grid_view is not None:
                self._grid_view.set_video_paused(False, "视频传输已恢复")
        return True

    def _select_transfer_folder(self, view) -> None:
        from PySide6.QtWidgets import QFileDialog

        captures_dir = self._project_path / "captures"
        captures_dir.mkdir(parents=True, exist_ok=True)
        selected = QFileDialog.getExistingDirectory(view, "选择照片拍摄文件夹", str(captures_dir))
        if selected:
            view.set_transfer_folder(Path(selected))

    def _upload_selected_capture(self, view, path: str) -> None:
        if self._capture_transfer_worker is not None:
            view.set_transfer_progress(0, "已有照片任务正在上传，请稍候")
            return
        capture_dir = Path(path)
        if not capture_dir.is_dir():
            view.set_transfer_progress(0, "所选照片文件夹不存在，请重新选择")
            return
        view.set_transfer_busy(True)
        view.set_transfer_progress(5, "准备校验照片任务...")
        worker = _CaptureTransferWorker(capture_dir)
        self._capture_transfer_worker = worker
        worker.progress_changed.connect(view.set_transfer_progress)
        worker.log_message.connect(view.append_transfer_log)
        worker.upload_confirmed.connect(lambda result: self._on_capture_upload_confirmed(view, result))
        worker.transfer_completed.connect(
            lambda result, error: self._on_capture_transfer_completed(view, result, error)
        )
        worker.finished.connect(self._release_capture_transfer_worker)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_capture_upload_confirmed(self, view, result) -> None:
        from tx_rx.config import load_config

        config = load_config()
        object_name = result.upload_response.capture_id
        remote_path = f"{config.remote_task_root}/{result.task_id}/input/images"
        view.set_transfer_result(object_name, remote_path, result.task_id)
        view.append_transfer_log(f"用户任务名称：{object_name}")
        view.append_transfer_log(f"WSL 照片目录：{remote_path}")
        view.append_transfer_log(
            "接收成功判定：HTTP成功 + upload_received + "
            f"status={result.upload_response.status} + 身份一致"
        )
        if result.upload_response.duplicate and result.upload_response.status == "finished":
            result_message = f"“{object_name}”已在上位机中，准备下载已有模型"
            view.append_transfer_log("重复任务判定：duplicate=true，服务端状态=finished")
        elif result.upload_response.duplicate:
            result_message = (
                f"“{object_name}”已在上位机中，当前状态={result.upload_response.status}"
            )
            view.append_transfer_log(
                f"重复任务判定：duplicate=true，服务端状态={result.upload_response.status}"
            )
        else:
            result_message = f"“{object_name}”照片上传成功，上位机已接收并启动重建"
        view.set_transfer_progress(
            38,
            result_message,
        )

    def _on_capture_transfer_completed(self, view, outcome, error: str | None) -> None:
        view.set_transfer_busy(False)
        if error is not None or outcome is None:
            view.set_transfer_progress(0, f"传输或接收失败：{error or '未知错误'}")
            return
        final_path = outcome["final_path"]
        view.set_transfer_download_result(final_path)
        view.set_transfer_progress(100, f"模型接收完成：{final_path}")
        view.set_data_link_status(transmit="照片已上传", receive="3DGS 模型已接收并校验")

    def _release_capture_transfer_worker(self) -> None:
        self._capture_transfer_worker = None

    def _load_cameras(self, view) -> None:
        """Scan V4L2 devices before resuming or adding cameras.

        Loading is intentionally a discovery action even when the current
        session is healthy. This lets a camera that appeared late join the
        active pool without tearing down the cameras already streaming.
        """
        if self._session is not None and self._session.is_recording:
            view.set_video_paused(False, "录制期间不能扫描摄像头")
            return
        if (
            self._discovery_worker is not None
            or self._camera_load_worker is not None
            or self._switch_worker is not None
        ):
            view.set_video_paused(True, "摄像头扫描或连接仍在进行中...")
            return

        self._manual_camera_load_requested = True
        if hasattr(view, "set_camera_load_busy"):
            view.set_camera_load_busy(True)
        if hasattr(view, "set_ignore_controls_enabled"):
            view.set_ignore_controls_enabled(False)
        view.set_video_paused(True, "正在用 v4l2-ctl 扫描 USB 摄像头...")
        self._poll_hotplug()

    def _toggle_video_transmission(self, view) -> None:
        if self._discovery_worker is not None or self._camera_load_worker is not None:
            view.set_video_paused(True, "摄像头扫描或连接仍在进行中...")
            return
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

        selected, _ = QFileDialog.getOpenFileName(
            view,
            "打开 3DGS 模型",
            str(self._project_path / "result"),
            "Gaussian Splat PLY (*.ply);;所有文件 (*)",
        )
        if not selected:
            return
        view.load_model(selected)

    def _on_photo_requested(self, view) -> None:
        if self._presenter is None or self._snapshot_worker is not None:
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

        quality = self._presenter.latest_quality()
        if quality is None:
            view.set_photo_capture_result("图像质量检查尚未完成，请稍候再拍", ok=False)
            return
        if set(quality.frame_qualities) != set(packets):
            view.set_photo_capture_result("摄像头画面刚发生变化，请稍候再拍", ok=False)
            return
        selected_angle = view.selected_angle_deg()
        raw_object_name = view.capture_object_name().strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", raw_object_name):
            view.set_photo_capture_result("请先输入物体名称", ok=False)
            return
        if self._active_snapshot_name is None:
            self._active_snapshot_object_name = raw_object_name
            self._active_snapshot_name = _next_capture_name(
                self._project_path / "captures", self._active_snapshot_object_name
            )

        request = _SnapshotRequest(
            output_root=self._project_path / "captures",
            capture_name=self._active_snapshot_name,
            object_name=self._active_snapshot_object_name,
            packets=packets,
            camera_info=camera_info,
            quality=quality,
            angle_deg=selected_angle,
            tracker=self._guidance_tracker,
        )
        view.set_photo_busy(True)
        view.set_photo_capture_result("正在后台检查并保存当前角度…", ok=True)
        self._snapshot_worker = _SnapshotWorker(request)
        self._snapshot_worker.snapshot_completed.connect(
            self._on_snapshot_completed
        )
        self._snapshot_worker.finished.connect(
            self._snapshot_worker.deleteLater
        )
        self._snapshot_worker.start()

    def _on_snapshot_completed(self, outcome: object) -> None:
        worker = self._snapshot_worker
        if worker is not None:
            worker.wait()
            self._snapshot_worker = None
        if not isinstance(outcome, _SnapshotOutcome):
            return

        view = self._grid_view
        if view is not None:
            view.set_photo_busy(False)
        if outcome.error:
            if view is not None:
                view.set_photo_capture_result(
                    f"拍摄失败: {outcome.error}",
                    ok=False,
                )
            return
        if outcome.validation is None:
            return
        validation = outcome.validation
        self._last_guidance = validation.guidance
        if view is not None:
            view.update_guidance(validation.guidance)
        if not validation.accepted or outcome.result is None:
            if view is not None:
                view.set_photo_capture_result(
                    f"拍摄已阻止: {_zh_capture_message(validation.message)}",
                    ok=False,
                )
            return

        request = outcome.request
        result = outcome.result
        guidance = self._guidance_tracker.register_capture(
            request.angle_deg,
            result.frame_id,
            request.packets,
            request.quality,
        )
        self._last_guidance = guidance
        self.capture_progress_changed.emit(guidance)
        if view is not None:
            view.update_guidance(guidance)
            if guidance.next_angle_deg is not None:
                view.set_selected_angle_deg(guidance.next_angle_deg)
        rel_dir = result.output_dir.relative_to(self._project_path)
        status = _zh_readiness_label(guidance.readiness_label)
        if view is not None:
            view.set_photo_capture_result(
                (
                    f"已拍摄 {request.angle_deg}° 第 {result.frame_id:06d} 组 "
                    f"({status} {guidance.readiness_percent:.0f}%, 进度 {guidance.progress_percent:.0f}%) "
                    f"-> {rel_dir}/images"
                ),
                ok=result.ok_to_capture,
            )
        if guidance.loop_complete:
            self._emit_capture_completion_if_ready(guidance, result.output_dir)
            if not self._capture_only and view is not None:
                self._start_task_packaging(view, result.output_dir)
            self._active_snapshot_name = None
            self._active_snapshot_object_name = None
            self._guidance_tracker = CaptureGuidanceTracker()

    def _emit_capture_completion_if_ready(self, guidance, capture_dir: Path) -> bool:
        """Publish one application event only after all fixed angles are present."""
        if not guidance.loop_complete:
            return False
        capture_dir = Path(capture_dir).resolve()
        self.capture_completed.emit(
            {
                "capture_dir": str(capture_dir),
                "object_name": self._active_snapshot_object_name or capture_dir.name,
                "completed_angles": tuple(guidance.completed_angles),
            }
        )
        return True

    def _start_task_packaging(self, view, capture_dir: Path) -> None:
        """Create the configured visible staging task once per completed capture."""
        capture_dir = capture_dir.resolve()
        if capture_dir in self._packaged_capture_dirs:
            return
        if self._task_package_worker is not None:
            view.set_data_link_status(transmit="任务整理正在进行")
            return

        view.set_data_link_status(transmit="正在整理 8 张照片...")
        self._packaging_capture_dir = capture_dir
        self._task_package_worker = _TaskPackageWorker(capture_dir)
        self._task_package_worker.package_completed.connect(self._on_task_package_completed)
        self._task_package_worker.finished.connect(self._release_task_package_worker)
        self._task_package_worker.finished.connect(self._task_package_worker.deleteLater)
        self._task_package_worker.start()

    def _on_task_package_completed(self, result, error: str | None) -> None:
        view = self._grid_view
        if error is not None or result is None:
            message = f"任务整理失败: {error or '未知错误'}"
            logger.error(message)
            if view is not None:
                view.set_data_link_status(transmit=message)
                view.set_photo_capture_result(message, ok=False)
            return

        if self._packaging_capture_dir is not None:
            self._packaged_capture_dirs.add(self._packaging_capture_dir)
        message = "任务已整理，可以检查/上传"
        logger.info("%s: %s", message, result.staging_dir)
        if view is not None:
            view.set_data_link_status(transmit=message, receive="等待上传")
            view.set_photo_capture_result(f"{message}: {result.staging_dir}", ok=True)

    def _release_task_package_worker(self) -> None:
        self._task_package_worker = None
        self._packaging_capture_dir = None
        self._start_staging_scan()

    def _start_staging_scan(self) -> None:
        if self._staging_scan_worker is not None:
            return
        self._staging_scan_worker = _StagingScanWorker()
        self._staging_scan_worker.scan_completed.connect(self._on_staging_scan_completed)
        self._staging_scan_worker.finished.connect(self._release_staging_scan_worker)
        self._staging_scan_worker.finished.connect(self._staging_scan_worker.deleteLater)
        self._staging_scan_worker.start()

    def _on_staging_scan_completed(self, tasks, error: str | None) -> None:
        view = self._grid_view
        if error is not None or tasks is None:
            if view is not None:
                view.set_data_link_status(transmit=f"任务目录检查失败: {error or '未知错误'}")
            self._ready_staging_dirs = []
            return

        ready = [
            task.task_dir.resolve()
            for task in tasks
            if task.state.value == "ready" and task.task_dir.resolve() not in self._uploaded_staging_dirs
        ]
        self._ready_staging_dirs = ready
        invalid = [task for task in tasks if task.state.value == "invalid"]
        incomplete = [task for task in tasks if task.state.value == "incomplete"]
        uploaded = [task for task in tasks if task.state.value == "uploaded"]
        if view is not None and self._staged_upload_worker is None:
            if invalid:
                view.set_data_link_status(transmit=f"任务目录异常: {invalid[0].task_id}")
            elif ready:
                view.set_data_link_status(transmit=f"发现 {len(ready)} 个待上传任务")
            elif incomplete:
                view.set_data_link_status(transmit=incomplete[0].message)
            elif uploaded:
                view.set_data_link_status(transmit=f"已上传 {len(uploaded)} 个任务")
        if self._upload_after_scan:
            self._upload_after_scan = False
            self._start_staged_upload(view)

    def _release_staging_scan_worker(self) -> None:
        self._staging_scan_worker = None

    def _upload_staged_tasks(self, view) -> None:
        if self._staged_upload_worker is not None:
            view.set_data_link_status(transmit="上传正在进行")
            return
        view.set_staging_upload_busy(True)
        view.set_data_link_status(transmit="正在检查任务目录...")
        self._upload_after_scan = True
        self._start_staging_scan()

    def _start_staged_upload(self, view) -> None:
        if view is None:
            return
        if not self._ready_staging_dirs:
            view.set_staging_upload_busy(False)
            view.set_data_link_status(transmit="没有可上传的完整任务")
            return
        self._staged_upload_worker = _StagedUploadWorker(list(self._ready_staging_dirs))
        self._staged_upload_worker.upload_status.connect(
            lambda message: view.set_data_link_status(transmit=message)
        )
        self._staged_upload_worker.upload_completed.connect(self._on_staged_upload_completed)
        self._staged_upload_worker.finished.connect(self._release_staged_upload_worker)
        self._staged_upload_worker.finished.connect(self._staged_upload_worker.deleteLater)
        self._staged_upload_worker.start()

    def _on_staged_upload_completed(self, results, errors) -> None:
        for result in results:
            self._uploaded_staging_dirs.add(result.staging_dir.resolve())
        view = self._grid_view
        if view is None:
            return
        view.set_staging_upload_busy(False)
        if errors:
            view.set_data_link_status(transmit=f"上传失败: {errors[0]}", receive="等待重试")
            view.set_photo_capture_result(f"上传失败: {errors[0]}", ok=False)
        else:
            view.set_data_link_status(
                transmit=f"已上传 {len(results)} 个任务",
                receive="上位机已启动重建",
            )
            view.set_photo_capture_result(f"已上传 {len(results)} 个任务并启动重建", ok=True)

    def _release_staged_upload_worker(self) -> None:
        self._staged_upload_worker = None

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
        live_quality = quality or self._presenter.latest_quality()
        if live_quality is None:
            return
        guidance = self._guidance_tracker.evaluate(
            packets,
            live_quality,
            view.selected_angle_deg(),
            check_matchability=False,
        )
        self._last_guidance = guidance
        view.update_guidance(guidance)
        self.capture_progress_changed.emit(guidance)

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
        if (
            self._discovery_worker is not None
            or self._camera_load_worker is not None
            or self._switch_worker is not None
        ):
            return
        if self._session is not None and self._session.is_recording:
            self._hotplug_pending = True
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

        manual_load = self._manual_camera_load_requested
        if error_or_none:
            logger.warning("Skipping hotplug refresh: %s", error_or_none)
            if manual_load:
                self._start_camera_load_worker(
                    [],
                    allow_unconfigured=True,
                    preserve_existing=True,
                    start_session=False,
                )
            elif self._session is None:
                self._on_camera_load_completed(CameraLoadResult(str(error_or_none), True))
            return

        discovered = options_or_none
        if not isinstance(discovered, list):
            if manual_load:
                self._start_camera_load_worker(
                    [],
                    allow_unconfigured=True,
                    preserve_existing=True,
                    start_session=False,
                )
            elif self._session is None:
                self._on_camera_load_completed(
                    CameraLoadResult("摄像头扫描返回了无效结果", True)
                )
            return
        if self._session is None:
            try:
                # Profile matching and presenter creation are lightweight UI
                # setup. The actual V4L2 open/warm-up happens in the worker.
                self.initialize(allow_unconfigured=manual_load, discovered=discovered)
            except Exception as exc:
                logger.exception("Failed to initialize cameras after discovery")
                self._on_camera_load_completed(
                    CameraLoadResult(str(exc).strip() or type(exc).__name__, True)
                )
                return
            self._start_camera_load_worker(
                [],
                allow_unconfigured=manual_load,
                preserve_existing=manual_load,
                start_session=True,
            )
            return

        self._start_camera_load_worker(
            discovered,
            allow_unconfigured=manual_load,
            preserve_existing=manual_load,
            start_session=False,
        )

    def _start_camera_load_worker(
        self,
        discovered: list[FrameSourceOptions],
        *,
        allow_unconfigured: bool,
        preserve_existing: bool,
        start_session: bool,
    ) -> None:
        if self._camera_load_worker is not None:
            return
        self._camera_load_worker = _CameraLoadWorker(
            self,
            discovered,
            allow_unconfigured=allow_unconfigured,
            preserve_existing=preserve_existing,
            start_session=start_session,
        )
        self._camera_load_worker.load_completed.connect(
            self._on_camera_load_completed,
            Qt.ConnectionType.QueuedConnection,
        )
        self._camera_load_worker.finished.connect(self._camera_load_worker.deleteLater)
        self._camera_load_worker.start()

    def _on_camera_load_completed(self, result: object) -> None:
        if self._camera_load_worker is not None:
            self._camera_load_worker.wait()
            self._camera_load_worker = None

        if isinstance(result, CameraLoadResult):
            load_error = result.error
            started_session = result.started_session
        else:
            load_error = str(result) if result else None
            started_session = False

        manual_load = self._manual_camera_load_requested
        self._manual_camera_load_requested = False
        if self._grid_view is not None and hasattr(self._grid_view, "set_camera_load_busy"):
            self._grid_view.set_camera_load_busy(False)

        if load_error:
            logger.warning("Camera load completed with error: %s", load_error)
            if not manual_load:
                self._mark_capture_start_failure(RuntimeError(load_error))

        self._sync_grid_source_tiles()
        self._refresh_presenter_lookup()
        if self._session is not None and self._presenter is not None:
            try:
                self._presenter.enter_grid_mode()
                self._pause_ignored_producers()
            except RuntimeError:
                logger.warning("Cannot restore grid mode after camera load")
        self._sync_capture_start_state()

        if started_session and self._session is not None:
            self.capture_available.emit()

        if not manual_load or self._grid_view is None:
            return

        if self._session is None:
            self._grid_view.set_video_paused(True, "未发现可用 USB 摄像头，等待下次扫描")
            return

        if self._session.producers_healthy:
            if load_error:
                message = "连接失败，继续使用已有摄像头"
            elif any(info.device_path and info.error for info in self._sources.values()):
                message = "新摄像头未能打开，继续使用已有摄像头"
            else:
                message = "扫描完成，视频传输已启动"
            self._grid_view.set_video_paused(False, message)
        else:
            self._grid_view.set_video_paused(True, "扫描完成，但没有可用摄像头")

    def _record_session_startup_errors(self) -> None:
        if self._session is None:
            return
        for device_path, error in self._session.startup_errors.items():
            for info in self._sources.values():
                if info.device_path == device_path:
                    info.error = error
                    break

    def _sync_grid_source_tiles(self) -> None:
        """Create/update source tiles on the Qt thread after worker changes."""
        if self._grid_view is None:
            return
        for info in self._sources.values():
            if not self._grid_view.has_source(info.source_id):
                self._grid_view.add_source(
                    info.source_id,
                    info.profile.label,
                    ignore=info.profile.ignore,
                )
            self._grid_view.set_source_ignored(info.source_id, info.profile.ignore)
            config = self._runtime_configs.get(info.source_id, self._source_config(info))
            w, h = config.resolution
            self._grid_view.set_tile_resolution(info.source_id, f"{w}x{h}")

    def _refresh_discovered_sources(
        self,
        discovered: list[FrameSourceOptions],
        allow_unconfigured: bool = False,
        preserve_existing: bool = False,
        update_view: bool = True,
    ) -> None:
        if self._session is None:
            return

        options_by_bus = {options.bus_info: options for options in discovered}
        sources_by_bus = {info.profile.bus_info: info for info in self._sources.values()}

        next_source_id = max(self._sources, default=-1) + 1
        for options in discovered:
            if options.bus_info in sources_by_bus:
                continue
            if self._profile_locked and not allow_unconfigured:
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

        active_paths = set(self._session.active_device_paths)
        for info in self._sources.values():
            options = options_by_bus.get(info.profile.bus_info)
            if options is None:
                if preserve_existing:
                    # A manual scan can be transiently incomplete while USB
                    # nodes settle. Never remove a working source just because
                    # this one scan did not report it.
                    continue
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
                except Exception as exc:
                    logger.exception("Failed to activate source %s during hotplug refresh", info.source_id)
                    info.error = str(exc).strip() or type(exc).__name__
                    should_ignore = True

            if info.device_path and not info.error and info.profile.ignore != should_ignore:
                ignore_updates[info.source_id] = should_ignore

        for source_id, ignore in ignore_updates.items():
            info = self._sources[source_id]
            updated_profile = info.profile.with_ignore(ignore)
            self._repo.save(updated_profile)
            info.profile = updated_profile

        if update_view:
            self._sync_grid_source_tiles()
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
                if not info.device_path:
                    message = "未连接"
                else:
                    detail = (info.error or "启动失败").splitlines()[0].strip()
                    message = f"启动失败: {detail[:100]}"
                self._grid_view.set_source_error(source_id, message)
            else:
                self._grid_view.clear_source_error(source_id)
            is_active_low_anchor = (
                info.device_path in active_paths
                and config.resolution == _LOW_RESOLUTION
            )
            can_toggle_ignore = bool(info.device_path and not info.error) and not is_active_low_anchor
            self._grid_view.set_source_ignore_enabled(source_id, can_toggle_ignore)

    def _switch_ignore_state_blocking(
        self,
        source_id: int,
        ignore: bool,
        cancel_check=None,
    ) -> CameraSwitchResult:
        def check_cancelled() -> None:
            if cancel_check is not None and cancel_check():
                raise InterruptedError("camera switch cancelled")

        check_cancelled()
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
                check_cancelled()
                self._session.remove_source(info.device_path)
                self._runtime_configs.pop(source_id, None)
                check_cancelled()
            ignore_updates[source_id] = True
            activated = self._activate_next_standby_blocking(
                ignore_updates,
                excluded_source_id=source_id,
                cancel_check=cancel_check,
            )
            if activated:
                return CameraSwitchResult(source_id, ignore, ignore_updates)

            try:
                self._activate_source_blocking(
                    source_id,
                    cancel_check=cancel_check,
                )
                ignore_updates[source_id] = False
                return CameraSwitchResult(
                    source_id,
                    ignore,
                    ignore_updates,
                    "No standby source could replace the requested camera",
                )
            except InterruptedError:
                raise
            except Exception as exc:
                return CameraSwitchResult(source_id, ignore, ignore_updates, str(exc))

        if len(self._session.active_device_paths) >= self._max_active_sources:
            return CameraSwitchResult(
                source_id,
                ignore,
                {source_id: True},
                "Active camera pool is full",
            )

        check_cancelled()
        self._activate_source_blocking(
            source_id,
            cancel_check=cancel_check,
        )
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
        cancel_check=None,
    ) -> bool:
        if self._session is None:
            return False
        excluded_source_ids = {excluded_source_id} if excluded_source_id is not None else set()
        while len(self._session.active_device_paths) < self._max_active_sources:
            if cancel_check is not None and cancel_check():
                raise InterruptedError("camera switch cancelled")
            standby_id = self._choose_standby_source_id(ignore_updates, excluded_source_ids)
            if standby_id is None:
                return False
            try:
                self._activate_source_blocking(
                    standby_id,
                    cancel_check=cancel_check,
                )
                ignore_updates[standby_id] = False
                return True
            except InterruptedError:
                raise
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

    def _activate_source_blocking(
        self,
        source_id: int,
        cancel_check=None,
    ) -> None:
        if cancel_check is not None and cancel_check():
            raise InterruptedError("camera switch cancelled")
        info = self._sources.get(source_id)
        if info is None or self._session is None or not info.device_path or info.error:
            return
        if info.device_path in self._session.active_device_paths:
            return

        config = self._activation_config(info)
        source = FrameSource(info.device_path, config)
        if cancel_check is None:
            self._session.add_source(source)
        else:
            self._session.add_source(
                source,
                cancel_check=cancel_check,
            )
        self._runtime_configs[source_id] = config
        for name, cv in info.profile.controls.items():
            if cancel_check is not None and cancel_check():
                raise InterruptedError("camera switch cancelled")
            set_control(info.device_path, name, cv.value)

    def _activation_config(self, info: SourceInfo) -> FrameSourceConfig:
        config = self._source_config(info)
        if config.resolution != _HIGH_RESOLUTION:
            return config

        target_root = usb_root_bus(info.profile.bus_info)
        active_paths = set(self._session.active_device_paths) if self._session else set()
        active_high = sum(
            1
            for source_id, runtime_config in self._runtime_configs.items()
            if runtime_config.resolution == _HIGH_RESOLUTION
            and self._sources.get(source_id) is not None
            and self._sources[source_id].device_path in active_paths
            and usb_root_bus(self._sources[source_id].profile.bus_info) == target_root
        )
        if active_high >= _MAX_HIGH_RESOLUTION_SOURCES_PER_USB_ROOT:
            return self._config_with_resolution(config, _LOW_RESOLUTION)
        return config

    @staticmethod
    def _config_with_resolution(
        config: FrameSourceConfig,
        resolution: tuple[int, int],
    ) -> FrameSourceConfig:
        """Copy a capture config while changing only its resolution."""
        return FrameSourceConfig(
            resolution=resolution,
            fps=config.fps,
            pixel_format=config.pixel_format,
            capture_backend=config.capture_backend,
            gstreamer_pipeline=config.gstreamer_pipeline,
            warmup_frames=config.warmup_frames,
            startup_timeout_seconds=config.startup_timeout_seconds,
            read_timeout_seconds=config.read_timeout_seconds,
            v4l2_options=config.v4l2_options,
        )

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
