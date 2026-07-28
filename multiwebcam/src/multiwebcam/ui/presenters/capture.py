"""Unified capture presenter for grid and focus modes."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QPixmap

from multiwebcam.pipeline.session import CaptureSession
from multiwebcam.profiles.settings import InferenceSettings
from multiwebcam.quality.metrics import CaptureSetQuality, ObjectRegion
from multiwebcam.recognition import AsyncObjectDetector, InferenceStatus, create_detector
from multiwebcam.sources.config import FrameSourceConfig
from multiwebcam.sources.controls import V4L2Control
from multiwebcam.sources.discovery import FrameSourceOptions
from multiwebcam.sources.frame_packet import FramePacket
from multiwebcam.ui.control_worker import CameraControlWorker
from multiwebcam.ui.preview_workers import (
    PreviewRequest,
    PreviewWorker,
    QualityWorker,
)

logger = logging.getLogger(__name__)

_PIXEL_FORMAT = "mjpeg"
_DETECTION_HOLD_SECONDS = 1.5
_DETECTION_SMOOTHING_ALPHA = 0.65
_GRID_POLL_MS = 66
_FOCUS_POLL_MS = 33
_SLOW_POLL_LOG_INTERVAL_SECONDS = 5.0


class _StopRecordingWorker(QThread):
    """Worker thread for non-blocking recording stop.

    Signal named stop_completed (not finished) to avoid shadowing QThread.finished.
    """

    stop_completed = Signal(object)  # RecordingResult | None

    def __init__(self, session: CaptureSession) -> None:
        super().__init__()
        self._session = session
        self.succeeded = False

    def run(self) -> None:
        try:
            result = self._session.stop_recording()
            self.succeeded = result is not None
        except Exception:
            logger.exception("Error during recording stop")
            result = None
        self.stop_completed.emit(result)


class CapturePresenter(QObject):
    """Long-lived presenter that switches between grid and focus modes.

    Created once alongside the session. Mode switches don't destroy the presenter.
    Recording logic is implemented once and works in both modes.
    """

    # Grid mode display
    frames_ready = Signal(object)  # dict[int, QPixmap]
    grid_stats_updated = Signal(object)  # dict[int, CameraStats]
    alignment_updated = Signal(object)  # AlignmentStats
    quality_updated = Signal(object, object)  # dict[int, FrameQuality], CaptureSetQuality
    inference_status_updated = Signal(object)  # InferenceStatus

    # Focus mode display
    frame_ready = Signal(QPixmap)
    focus_stats_updated = Signal(object)  # CameraStats

    # Focus mode configuration
    resolutions_available = Signal(object)
    framerates_available = Signal(object)
    initial_config_ready = Signal(str, str)
    config_applied = Signal(object)
    config_error = Signal(str)

    # Focus mode V4L2 controls
    controls_ready = Signal(object)  # list[V4L2Control]
    control_persist_requested = Signal(str, int)
    controls_cleared = Signal()

    # Recording (shared across modes)
    recording_started = Signal()
    recording_stopping = Signal()  # stop initiated, drain in progress
    recording_stopped = Signal()  # stop complete
    recording_duration = Signal(float)  # elapsed seconds
    recording_queue_depth = Signal(object)  # dict[int, int]: source_id -> depth

    def __init__(
        self,
        session: CaptureSession,
        source_id_lookup: dict[str, int],
        inference_settings: InferenceSettings | None = None,
        grid_poll_ms: int = _GRID_POLL_MS,
        focus_poll_ms: int = _FOCUS_POLL_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._source_id_lookup = source_id_lookup
        self._grid_poll_ms = grid_poll_ms
        self._focus_poll_ms = focus_poll_ms
        self._inference_settings = inference_settings or InferenceSettings()

        self._mode: str = "idle"
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_poll)

        self._focused_device_path: str | None = None
        self._focused_source_id: int | None = None
        self._source_options: FrameSourceOptions | None = None
        self._current_config: FrameSourceConfig | None = None
        self._current_controls: list[V4L2Control] = []

        self._mirror: bool = False

        self._stop_worker: _StopRecordingWorker | None = None
        self._recording_start_time: float | None = None
        self._recording_device_paths: list[str] = []
        self._latest_packets_by_path: dict[str, FramePacket] = {}
        self._latest_quality: CaptureSetQuality | None = None
        self._latest_frame_qualities_by_path = {}
        self._latest_object_regions_by_path = {}
        self._latest_detection_seen_time_by_path: dict[str, float] = {}
        self._latest_detection_latency_by_path: dict[str, float] = {}
        self._latest_detection_backend_by_path: dict[str, str] = {}
        self._last_inference_submit_by_path: dict[str, float] = {}
        self._last_quality_emit_time = 0.0
        self._last_slow_poll_log_time = 0.0
        self._quality_interval_seconds = 0.5
        self._preview_worker = PreviewWorker(parent=self)
        self._preview_worker.images_ready.connect(
            self._on_preview_images_ready,
            Qt.ConnectionType.QueuedConnection,
        )
        self._quality_worker = QualityWorker(parent=self)
        self._quality_worker.quality_ready.connect(
            self._on_quality_ready,
            Qt.ConnectionType.QueuedConnection,
        )
        self._control_worker = CameraControlWorker(parent=self)
        self._control_worker.controls_ready.connect(
            self._on_controls_ready,
            Qt.ConnectionType.QueuedConnection,
        )
        self._control_worker.control_applied.connect(
            self._on_control_applied,
            Qt.ConnectionType.QueuedConnection,
        )
        self._control_worker.defaults_restored.connect(
            self._on_defaults_restored,
            Qt.ConnectionType.QueuedConnection,
        )
        try:
            self._object_detector = AsyncObjectDetector(create_detector(self._inference_settings))
        except Exception:
            logger.exception(
                "Failed to initialize inference backend %s, falling back to heuristic",
                self._inference_settings.backend,
            )
            fallback = InferenceSettings()
            self._inference_settings = fallback
            self._object_detector = AsyncObjectDetector(create_detector(fallback))

    @property
    def focused_device_path(self) -> str | None:
        return self._focused_device_path

    @property
    def focused_source_id(self) -> int | None:
        return self._focused_source_id

    @property
    def mirror(self) -> bool:
        return self._mirror

    def set_mirror(self, enabled: bool) -> None:
        self._mirror = enabled

    @property
    def mode(self) -> str:
        return self._mode

    def set_source_id_lookup(self, source_id_lookup: dict[str, int]) -> None:
        self._source_id_lookup = source_id_lookup
        active_paths = set(source_id_lookup)
        self._latest_packets_by_path = {
            path: packet for path, packet in self._latest_packets_by_path.items() if path in active_paths
        }

    def latest_packets(self) -> dict[str, FramePacket]:
        return dict(self._latest_packets_by_path)

    def latest_quality(self) -> CaptureSetQuality | None:
        return self._latest_quality

    def latest_object_regions(self) -> dict[str, ObjectRegion | None]:
        return self._object_regions_for_quality(self.latest_packets())

    def enter_grid_mode(self) -> None:
        """Switch to grid mode -- resume all cameras, start grid polling."""
        if self._session.is_recording or self._stop_worker is not None:
            raise RuntimeError("Cannot switch mode while recording or stopping")
        self._session.resume_all()
        self._focused_device_path = None
        self._focused_source_id = None
        self._mode = "grid"
        self._timer.start(self._grid_poll_ms)

    def enter_model_mode(self) -> None:
        """Pause camera production and preview analysis for the 3DGS workspace."""
        if self._session.is_recording or self._stop_worker is not None:
            raise RuntimeError("Cannot enter model mode while recording or stopping")
        self._timer.stop()
        self._preview_worker.clear_pending()
        self._quality_worker.clear_pending()
        for device_path in self._session.active_device_paths:
            self._session.pause_producer(device_path)
        self._focused_device_path = None
        self._focused_source_id = None
        self._mode = "model"

    def pause_video_transmission(self) -> None:
        """Pause all camera producers while remaining in the capture workspace."""
        if self._session.is_recording or self._stop_worker is not None:
            raise RuntimeError("Cannot pause video while recording or stopping")
        self._timer.stop()
        self._preview_worker.clear_pending()
        self._quality_worker.clear_pending()
        for device_path in self._session.active_device_paths:
            self._session.pause_producer(device_path)
        self._mode = "paused"

    def enter_focus_mode(
        self,
        device_path: str,
        source_id: int,
        source_options: FrameSourceOptions | None = None,
        current_config: FrameSourceConfig | None = None,
    ) -> None:
        """Switch to focus mode -- pause others, start focus polling."""
        if self._session.is_recording or self._stop_worker is not None:
            raise RuntimeError("Cannot switch mode while recording or stopping")
        self._session.resume_all()
        self._session.pause_all_except(device_path)
        self._focused_device_path = device_path
        self._focused_source_id = source_id
        self._source_options = source_options
        self._current_config = current_config
        self._mode = "focus"
        self._timer.start(self._focus_poll_ms)

        if source_options is not None and current_config is not None:
            self._emit_initial_capabilities()
        self._emit_controls()

    def set_grid_poll_interval(self, ms: int) -> None:
        """Change the grid mode polling interval."""
        self._grid_poll_ms = ms
        if self._mode == "grid":
            self._timer.setInterval(ms)

    # --- Recording lifecycle ---

    def start_recording(self, output_dir: Path, cam_ids: dict[str, int] | None = None) -> None:
        """Start recording. cam_ids defaults based on current mode."""
        if self._stop_worker is not None:
            return

        if cam_ids is None:
            if self._mode == "focus":
                cam_ids = {self._focused_device_path: self._focused_source_id}
            else:
                cam_ids = dict(self._source_id_lookup.items())

        self._session.start_recording(output_dir, cam_ids=cam_ids)
        self._recording_device_paths = list(cam_ids.keys())
        self._recording_start_time = time.monotonic()
        self.recording_started.emit()

    def stop_recording(self) -> None:
        """Stop recording asynchronously. Emits recording_stopping immediately."""
        if self._stop_worker is not None:
            return
        if not self._session.is_recording:
            return

        self.recording_stopping.emit()
        self._stop_worker = _StopRecordingWorker(self._session)
        self._stop_worker.stop_completed.connect(self._on_stop_complete)
        self._stop_worker.start()

    def _on_stop_complete(self, result: object) -> None:
        """Handle async stop completion on main thread."""
        if self._stop_worker is not None:
            self._stop_worker.wait()
            self._stop_worker = None
        self._recording_device_paths = []
        self._recording_start_time = None
        self.recording_stopped.emit()

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        """Stop everything. Called once during app close."""
        self._timer.stop()
        worker_timeout = max(0.0, timeout_ms / 1000.0)
        if not self._preview_worker.stop(worker_timeout):
            return False
        if not self._quality_worker.stop(worker_timeout):
            return False
        if not self._control_worker.stop(worker_timeout):
            return False
        if self._stop_worker is not None:
            self._stop_worker.requestInterruption()
            if not self._stop_worker.wait(timeout_ms):
                return False
            self._stop_worker = None
        if (
            self._stop_worker is None
            and (self._session.is_recording or self._session.has_pending_recording)
        ):
            self._stop_worker = _StopRecordingWorker(self._session)
            self._stop_worker.start()
        if self._stop_worker is not None:
            if not self._stop_worker.wait(timeout_ms):
                return False
            if not self._stop_worker.succeeded:
                self._stop_worker = None
                return False
            self._stop_worker = None
        if not self._object_detector.stop(timeout=worker_timeout):
            return False
        self._mode = "idle"
        return True

    # --- Poll ---

    def _on_poll(self) -> None:
        if self._mode == "grid":
            self._poll_grid()
        elif self._mode == "focus":
            self._poll_focus()
        self._poll_recording()

    def _poll_grid(self) -> None:
        poll_start = time.perf_counter()
        self._refresh_detection_results()
        frames = self._session.get_latest_frames()
        preview_requests: dict[int, PreviewRequest] = {}
        packets_for_quality: dict[str, FramePacket] = {}
        for device_path, packet in frames.items():
            if packet is not None and device_path in self._source_id_lookup:
                self._latest_packets_by_path[device_path] = packet
                packets_for_quality[device_path] = packet
                self._submit_for_detection(device_path, packet)
                source_id = self._source_id_lookup[device_path]
                object_region = None
                if device_path in self._latest_object_regions_by_path:
                    object_region = self._latest_object_regions_by_path[device_path]
                elif device_path in self._latest_frame_qualities_by_path:
                    object_region = self._latest_frame_qualities_by_path[device_path].object_region
                preview_requests[source_id] = PreviewRequest(
                    frame=packet.frame,
                    mirror=self._mirror,
                    object_region=object_region,
                )
        self._preview_worker.submit(preview_requests)

        if packets_for_quality and time.monotonic() - self._last_quality_emit_time >= self._quality_interval_seconds:
            self._emit_quality_update()
            self._last_quality_emit_time = time.monotonic()

        stats = self._session.get_camera_stats()
        if stats:
            stats_by_id = {self._source_id_lookup[p]: s for p, s in stats.items() if p in self._source_id_lookup}
            if stats_by_id:
                self.grid_stats_updated.emit(stats_by_id)

        alignment = self._session.get_alignment_stats()
        if alignment:
            self.alignment_updated.emit(alignment)

        elapsed_ms = (time.perf_counter() - poll_start) * 1000.0
        if elapsed_ms > self._grid_poll_ms:
            now = time.monotonic()
            if now - self._last_slow_poll_log_time >= _SLOW_POLL_LOG_INTERVAL_SECONDS:
                logger.warning(
                    "Grid preview poll took %.1fms, above %.1fms interval for %d camera(s)",
                    elapsed_ms,
                    float(self._grid_poll_ms),
                    len(frames),
                )
                self._last_slow_poll_log_time = now

    def _poll_focus(self) -> None:
        self._refresh_detection_results()
        frames = self._session.get_latest_frames()
        packet = frames.get(self._focused_device_path)
        if packet is not None:
            if self._focused_device_path is not None:
                self._latest_packets_by_path[self._focused_device_path] = packet
                self._submit_for_detection(self._focused_device_path, packet)
            object_region = self._latest_object_regions_by_path.get(packet.device_path)
            if self._focused_source_id is not None:
                self._preview_worker.submit(
                    {
                        self._focused_source_id: PreviewRequest(
                            frame=packet.frame,
                            mirror=self._mirror,
                            object_region=object_region,
                            max_size=(1280, 720),
                        )
                    }
                )

        stats = self._session.get_camera_stats()
        if stats and self._focused_device_path in stats:
            self.focus_stats_updated.emit(stats[self._focused_device_path])

    def _emit_quality_update(self) -> None:
        packets = {
            path: packet for path, packet in self._latest_packets_by_path.items() if path in self._source_id_lookup
        }
        if not packets:
            return
        self._refresh_detection_results()
        self._quality_worker.submit(
            packets,
            self._object_regions_for_quality(packets),
        )

    def _on_preview_images_ready(self, images: object) -> None:
        if not isinstance(images, dict):
            return
        if self._mode == "focus" and self._focused_source_id in images:
            self.frame_ready.emit(
                QPixmap.fromImage(images[self._focused_source_id])
            )
            return
        if self._mode != "grid":
            return
        pixmaps = {
            int(source_id): QPixmap.fromImage(image)
            for source_id, image in images.items()
        }
        if pixmaps:
            self.frames_ready.emit(pixmaps)

    def _on_quality_ready(self, quality: object) -> None:
        if self._mode != "grid" or not isinstance(quality, CaptureSetQuality):
            return
        self._latest_quality = quality
        self._latest_frame_qualities_by_path = dict(quality.frame_qualities)
        quality_by_id = {
            self._source_id_lookup[path]: frame_quality
            for path, frame_quality in quality.frame_qualities.items()
            if path in self._source_id_lookup
        }
        self.quality_updated.emit(quality_by_id, quality)

    def _submit_for_detection(self, device_path: str, packet: FramePacket) -> None:
        interval_seconds = max(0.0, self._inference_settings.interval_ms / 1000.0)
        now = time.monotonic()
        last_submit = self._last_inference_submit_by_path.get(device_path, 0.0)
        if now - last_submit < interval_seconds:
            return
        self._last_inference_submit_by_path[device_path] = now
        self._object_detector.submit(device_path, packet.frame, packet.frame_index)

    def _refresh_detection_results(self) -> None:
        results = self._object_detector.results()
        now = time.monotonic()
        active_paths = set(self._source_id_lookup)

        for path, result in results.items():
            if path not in active_paths:
                continue
            previous = self._latest_object_regions_by_path.get(path)
            if result.object_region is not None:
                self._latest_object_regions_by_path[path] = _smooth_object_region(previous, result.object_region)
                self._latest_detection_seen_time_by_path[path] = now
            elif now - self._latest_detection_seen_time_by_path.get(path, 0.0) > _DETECTION_HOLD_SECONDS:
                self._latest_object_regions_by_path[path] = None
            self._latest_detection_latency_by_path[path] = result.latency_ms
            self._latest_detection_backend_by_path[path] = result.backend

        for path in list(self._latest_object_regions_by_path):
            if path not in active_paths:
                self._latest_object_regions_by_path.pop(path, None)
                self._latest_detection_seen_time_by_path.pop(path, None)
                self._latest_detection_latency_by_path.pop(path, None)
                self._latest_detection_backend_by_path.pop(path, None)

        self._emit_inference_status(active_paths)

    def _emit_inference_status(self, active_paths: set[str]) -> None:
        active_count = len(active_paths)
        detected_count = sum(
            1 for path in active_paths if self._latest_object_regions_by_path.get(path) is not None
        )
        latencies = [
            self._latest_detection_latency_by_path[path]
            for path in active_paths
            if path in self._latest_detection_latency_by_path
        ]
        backends = {
            self._latest_detection_backend_by_path[path]
            for path in active_paths
            if path in self._latest_detection_backend_by_path
        }
        backend = ", ".join(sorted(backends)) if backends else self._object_detector.backend_name
        status = InferenceStatus(
            backend=backend,
            active_count=active_count,
            detected_count=detected_count,
            latency_ms=sum(latencies) / len(latencies) if latencies else None,
            warming=bool(active_count and not latencies),
        )
        self.inference_status_updated.emit(status)

    def _poll_recording(self) -> None:
        """Emit recording signals. Works during both recording and drain."""
        is_recording = self._session.is_recording
        is_draining = self._stop_worker is not None

        if not is_recording and not is_draining:
            return

        # Duration (only while actively recording, not during drain)
        if is_recording and self._recording_start_time is not None:
            elapsed = time.monotonic() - self._recording_start_time
            self.recording_duration.emit(elapsed)

        # Queue depths (during recording AND drain)
        if self._recording_device_paths:
            depths = self._session.get_queue_sizes(self._recording_device_paths)
            if depths:
                depths_by_id = {self._source_id_lookup[p]: d for p, d in depths.items() if p in self._source_id_lookup}
                self.recording_queue_depth.emit(depths_by_id)

    # --- Focus mode capabilities ---

    def _object_regions_for_quality(self, packets: dict[str, FramePacket]) -> dict[str, ObjectRegion | None]:
        regions: dict[str, ObjectRegion | None] = {}
        for path in packets:
            regions[path] = self._latest_object_regions_by_path.get(path)
        return regions

    def _emit_initial_capabilities(self) -> None:
        if self._source_options is None or self._current_config is None:
            return

        resolutions = self._source_options.resolutions(_PIXEL_FORMAT)
        res_strings = sorted(
            [f"{w}x{h}" for w, h in resolutions],
            key=lambda s: int(s.split("x")[0]),
            reverse=True,
        )
        self.resolutions_available.emit(res_strings)

        w, h = self._current_config.resolution
        fps_list = self._source_options.framerates(_PIXEL_FORMAT, w, h)
        fps_strings = [str(int(f)) for f in fps_list]
        self.framerates_available.emit(fps_strings)

        self.initial_config_ready.emit(
            f"{w}x{h}",
            str(self._current_config.fps),
        )

    def on_resolution_selected(self, resolution_str: str) -> None:
        if self._source_options is None or not resolution_str or "x" not in resolution_str:
            return

        w, h = resolution_str.split("x")
        fps_list = self._source_options.framerates(_PIXEL_FORMAT, int(w), int(h))
        fps_strings = [str(int(f)) for f in fps_list]
        self.framerates_available.emit(fps_strings)

    def apply_config_result(self, new_config: FrameSourceConfig) -> None:
        self._current_config = new_config
        self.config_applied.emit(new_config)

    def apply_config_error(self, error: str) -> None:
        self.config_error.emit(error)

    # --- V4L2 controls ---

    def _emit_controls(self) -> None:
        if self._focused_device_path is None:
            return
        self._control_worker.query(self._focused_device_path)

    def _on_controls_ready(self, device_path: str, controls: object) -> None:
        if device_path != self._focused_device_path or not isinstance(controls, list):
            return
        self._current_controls = controls
        self.controls_ready.emit(controls)

    def on_control_changed(self, name: str, value: int) -> None:
        if self._focused_device_path:
            self._control_worker.set_value(self._focused_device_path, name, value)

    def _on_control_applied(
        self,
        device_path: str,
        name: str,
        value: int,
        succeeded: bool,
    ) -> None:
        if succeeded and device_path == self._focused_device_path:
            self.control_persist_requested.emit(name, value)

    def on_restore_defaults(self) -> None:
        if self._focused_device_path is None:
            return
        self._control_worker.restore_defaults(
            self._focused_device_path,
            self._current_controls,
        )

    def _on_defaults_restored(self, device_path: str) -> None:
        if device_path != self._focused_device_path:
            return
        self.controls_cleared.emit()
        self._emit_controls()


def _smooth_object_region(previous: ObjectRegion | None, current: ObjectRegion) -> ObjectRegion:
    if previous is None:
        return current
    alpha = _DETECTION_SMOOTHING_ALPHA

    def blend_int(old: int, new: int) -> int:
        return int(round(alpha * old + (1.0 - alpha) * new))

    def blend_float(old: float, new: float) -> float:
        return alpha * old + (1.0 - alpha) * new

    return ObjectRegion(
        x=blend_int(previous.x, current.x),
        y=blend_int(previous.y, current.y),
        width=blend_int(previous.width, current.width),
        height=blend_int(previous.height, current.height),
        area_ratio=blend_float(previous.area_ratio, current.area_ratio),
        centeredness=blend_float(previous.centeredness, current.centeredness),
        fill_ratio=blend_float(previous.fill_ratio, current.fill_ratio),
        confidence=max(previous.confidence * alpha, current.confidence),
    )
