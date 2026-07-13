from __future__ import annotations
"""Multi-camera capture session orchestration."""


import logging
import time
from pathlib import Path
from queue import Empty, Queue
from threading import Event, RLock

from multiwebcam.pipeline.alignment import AlignmentMonitor, AlignmentStats
from multiwebcam.pipeline.producer import FrameProducer, QueueBundle
from multiwebcam.pipeline.report import CameraStats
from multiwebcam.profiles.settings import RecordingSettings
from multiwebcam.recording.recorder import FrameRecorder, RecordingResult
from multiwebcam.sources.config import FrameSourceConfig, FrameSourceStatus
from multiwebcam.sources.device import FrameSource
from multiwebcam.sources.frame_packet import FramePacket

logger = logging.getLogger(__name__)


class CaptureSessionError(Exception):
    """Raised when capture session operations fail."""

    pass


class CaptureSession:
    """
    Orchestrates multi-camera capture with per-camera frame access.

    Creates producer threads for each camera and provides access to latest
    frames and per-camera statistics.

    Long-lived model - create once, call start()/stop() explicitly.
    No context manager pattern (to avoid confusion in MVP architecture).

    Usage:
        sources = [
            FrameSource("/dev/video0"),
            FrameSource("/dev/video2"),
        ]

        session = CaptureSession(sources)
        session.start()

        # Get latest frames for display
        frames = session.get_latest_frames()
        for device_path, packet in frames.items():
            if packet is not None:
                cv2.imshow(device_path, packet.frame)

        # Check camera stats
        stats = session.get_camera_stats()
        if stats:
            for device_path, stat in stats.items():
                print(f"{device_path}: {stat.measured_fps:.1f} fps")

        session.stop()
    """

    def __init__(
        self,
        sources: list[FrameSource],
        enable_monitoring: bool = True,
        monitor_interval_seconds: float = 2.0,
        recording_buffer_seconds: float = 6.0,
        alignment_window_seconds: float = 3.0,
        recording_settings: RecordingSettings | None = None,
    ) -> None:
        """
        Initialize a CaptureSession.

        Args:
            sources: List of FrameSource instances to capture from
            enable_monitoring: If True, track per-camera statistics
            monitor_interval_seconds: How often to update monitoring stats
            recording_buffer_seconds: Buffer size for recording queue (seconds)
            alignment_window_seconds: Window for alignment statistics (seconds)
        """
        if not sources:
            raise CaptureSessionError("At least one FrameSource required")

        self.sources = sources
        self.enable_monitoring = enable_monitoring
        self.monitor_interval_seconds = monitor_interval_seconds
        self.recording_buffer_seconds = recording_buffer_seconds
        self.alignment_window_seconds = alignment_window_seconds
        self.recording_settings = recording_settings or RecordingSettings()

        # Per-camera queue bundles (display, recording, alignment)
        self._queue_bundles: dict[str, QueueBundle] = {}
        self._producers: dict[str, FrameProducer] = {}  # device_path -> producer
        self._state_lock = RLock()

        # Alignment monitor (if monitoring enabled)
        self._alignment_monitor: AlignmentMonitor | None = None

        # Monitoring state (per-camera) - fallback if AlignmentMonitor not used
        self._monitoring_window_start = 0.0
        self._monitoring_last_frame_count: dict[str, int] = {}
        self._latest_stats: dict[str, CameraStats] | None = None

        self._running = False
        self._is_recording = Event()  # Shared flag for producers
        self._frame_recorder: FrameRecorder | None = None  # Created on start_recording()
        self._recording_device_paths: list[str] = []

    @staticmethod
    def _source_fps(source: FrameSource) -> int:
        return max(1, int(getattr(source, "_config").fps))

    def _recording_queue_capacity(self, source: FrameSource) -> int:
        return max(1, int(self.recording_buffer_seconds * self._source_fps(source)))

    def _alignment_queue_capacity(self, source: FrameSource) -> int:
        fps = self._source_fps(source)
        # Alignment monitoring only needs enough recent metadata to cover short scheduling hiccups.
        return max(8, min(64, fps))

    def start(self) -> None:
        """Start all producers."""
        if self._running:
            logger.warning("CaptureSession already running")
            return

        logger.info(f"Starting capture session with {len(self.sources)} cameras")

        # Start all cameras in parallel and validate PTS compatibility
        # Cameras stay open - producers take over the already-running sources
        self._start_all_sources_parallel()

        # Initialize monitoring state
        if self.enable_monitoring:
            self._monitoring_window_start = time.perf_counter()
            for source in self.sources:
                self._monitoring_last_frame_count[source.device_path] = 0

        # Create per-camera queue bundles and producers
        for source in self.sources:
            path = source.device_path

            # Create three-queue bundle
            self._queue_bundles[path] = QueueBundle(
                display=Queue(maxsize=1),
                recording=Queue(maxsize=self._recording_queue_capacity(source)),
                alignment=Queue(maxsize=self._alignment_queue_capacity(source)),
            )

            queues = self._queue_bundles[path]
            producer = FrameProducer(
                source,
                queues=queues,
                is_recording=self._is_recording,
            )
            self._producers[path] = producer

        # Start all producers
        for producer in self._producers.values():
            producer.start()

        # Start alignment monitor if monitoring enabled
        self._start_alignment_monitor()

        self._running = True
        logger.info("Capture session started")

    def stop(self) -> None:
        """Stop all producers."""
        if not self._running:
            return

        logger.info("Stopping capture session")

        # Stop recording if active
        if self._is_recording.is_set():
            self.stop_recording()

        # Stop alignment monitor
        self._stop_alignment_monitor()

        # Stop all producers
        for producer in self._producers.values():
            producer.stop()

        self._running = False
        logger.info("Capture session stopped")

    def pause_producer(self, device_path: str) -> None:
        """Pause a specific producer by device path."""
        with self._state_lock:
            producer = self._producers.get(device_path)
        if producer is None:
            raise ValueError(f"No producer found for device path: {device_path}")
        if self._is_recording.is_set():
            logger.warning(f"Pausing {device_path} while recording - frames will be missing")
        producer.pause()

    def resume_producer(self, device_path: str) -> None:
        """Resume a specific producer by device path."""
        with self._state_lock:
            producer = self._producers.get(device_path)
        if producer is None:
            raise ValueError(f"No producer found for device path: {device_path}")
        producer.resume()

    def pause_all_except(self, device_path: str) -> None:
        """Pause all producers except the specified one."""
        with self._state_lock:
            producers = list(self._producers.items())
        if device_path not in {path for path, _producer in producers}:
            raise ValueError(f"No producer found for device path: {device_path}")
        if self._is_recording.is_set():
            paused_cameras = [path for path, _producer in producers if path != device_path]
            logger.warning(f"Pausing {len(paused_cameras)} camera(s) while recording - frames will be missing")
        for other_path, producer in producers:
            if other_path != device_path:
                producer.pause()

    def resume_all(self) -> None:
        """Resume all producers."""
        with self._state_lock:
            producers = list(self._producers.values())
        for producer in producers:
            producer.resume()

    @property
    def producers_healthy(self) -> bool:
        """True when every configured producer thread is alive."""
        with self._state_lock:
            producers = list(self._producers.values())
        return bool(producers) and all(producer.is_running for producer in producers)

    @property
    def all_producers_paused(self) -> bool:
        with self._state_lock:
            producers = list(self._producers.values())
        return bool(producers) and all(producer.is_paused for producer in producers)

    def add_source(self, source: FrameSource) -> FrameSourceStatus:
        """Add and start a source while the session is running."""
        if self._is_recording.is_set():
            raise CaptureSessionError("Cannot add source while recording")

        with self._state_lock:
            already_active = source.device_path in self._producers
        if already_active:
            raise CaptureSessionError(f"Source already active: {source.device_path}")

        status = source.start()

        queues = QueueBundle(
            display=Queue(maxsize=1),
            recording=Queue(maxsize=self._recording_queue_capacity(source)),
            alignment=Queue(maxsize=self._alignment_queue_capacity(source)),
        )
        producer = FrameProducer(
            source,
            queues=queues,
            is_recording=self._is_recording,
        )

        with self._state_lock:
            if source.device_path in self._producers:
                source.stop()
                raise CaptureSessionError(f"Source already active: {source.device_path}")
            self.sources.append(source)
            self._queue_bundles[source.device_path] = queues
            self._producers[source.device_path] = producer
            self._monitoring_last_frame_count[source.device_path] = 0

        if self._running:
            producer.start()
            self._restart_alignment_monitor()

        return status

    def remove_source(self, device_path: str) -> None:
        """Stop and remove a source while the session is running."""
        if self._is_recording.is_set():
            raise CaptureSessionError("Cannot remove source while recording")

        self._stop_alignment_monitor()

        with self._state_lock:
            producer = self._producers.pop(device_path, None)
            if producer is None:
                raise CaptureSessionError(f"No producer found for device path: {device_path}")
            self._queue_bundles.pop(device_path, None)
            self._monitoring_last_frame_count.pop(device_path, None)
            if self._latest_stats is not None:
                self._latest_stats.pop(device_path, None)
            self.sources = [source for source in self.sources if source.device_path != device_path]

        producer.stop()

        self._start_alignment_monitor()

    def replace_source(self, device_path: str, new_config: FrameSourceConfig) -> FrameSourceStatus:
        """
        Replace a running camera source with a new configuration.

        Stops the old producer, creates a new FrameSource with new_config,
        and starts a new producer using the same queues. This allows changing
        camera settings (e.g., resolution, fps) without tearing down the entire session.

        Args:
            device_path: The device path to replace (e.g., '/dev/video0')
            new_config: New configuration for the frame source

        Returns:
            FrameSourceStatus from starting the new source

        Raises:
            CaptureSessionError: If session not running, recording active,
                               or device_path not found
        """
        # Guards
        if not self._running:
            raise CaptureSessionError("Session not started")

        if self._is_recording.is_set():
            raise CaptureSessionError("Cannot change source config while recording")

        if device_path not in self._producers:
            raise CaptureSessionError(f"No producer found for device path: {device_path}")

        logger.info(f"Replacing source {device_path} with new config: {new_config}")

        # Stop old producer
        old_producer = self._producers[device_path]
        old_producer.stop()

        # Drain stale display frame
        queues = self._queue_bundles[device_path]
        try:
            queues.display.get_nowait()
        except Empty:
            pass

        # Create and start new source
        new_source = FrameSource(device_path, new_config)
        status = new_source.start()

        # Create new producer with existing queues
        new_producer = FrameProducer(
            new_source,
            queues=queues,
            is_recording=self._is_recording,
        )

        # Replace producer
        self._producers[device_path] = new_producer

        # Update sources list - replace old source with new one
        for i, source in enumerate(self.sources):
            if source.device_path == device_path:
                self.sources[i] = new_source
                break

        # Start new producer
        new_producer.start()

        logger.info(f"Source {device_path} replaced successfully")

        return status

    def get_latest_frames(self) -> dict[str, FramePacket | None]:
        """
        Get the most recent frame from each camera for display.

        Returns a dict mapping device_path to FramePacket (or None if no
        frame has been received yet from that camera).

        This method is thread-safe and non-blocking. Frames are consumed
        from the display queue - the producer's drop-oldest strategy ensures
        the queue always has the latest frame.
        """
        with self._state_lock:
            queue_items = list(self._queue_bundles.items())

        frames: dict[str, FramePacket | None] = {}
        for device_path, queues in queue_items:
            try:
                # Consume the frame - producer's drop-oldest ensures it's latest
                packet = queues.display.get_nowait()
                frames[device_path] = packet
            except Empty:
                frames[device_path] = None
        return frames

    def get_camera_stats(self) -> dict[str, CameraStats] | None:
        """
        Get per-camera performance statistics.

        Returns None if monitoring is disabled. Otherwise returns a dict
        mapping device_path to CameraStats.

        If AlignmentMonitor is active, uses timestamp-based stats (accurate).
        Otherwise falls back to frame counter-based stats (wall-clock estimate).
        """
        if not self.enable_monitoring:
            return None

        # Use AlignmentMonitor if available (more accurate)
        if self._alignment_monitor is not None:
            return self._alignment_monitor.get_camera_stats()

        # Fallback: use wall-clock based monitoring
        now = time.perf_counter()
        elapsed = now - self._monitoring_window_start

        if elapsed >= self.monitor_interval_seconds:
            self._update_monitoring_stats()
            self._monitoring_window_start = now

        return self._latest_stats

    def get_alignment_stats(self) -> AlignmentStats | None:
        """
        Get multi-camera alignment quality statistics.

        Returns None if monitoring is disabled or no alignment data available yet.
        """
        if not self.enable_monitoring or self._alignment_monitor is None:
            return None

        return self._alignment_monitor.get_alignment_stats()

    def get_queue_sizes(self, device_paths: list[str]) -> dict[str, int]:
        """Queue sizes for given device paths. Works regardless of recording state."""
        with self._state_lock:
            queues = {path: self._queue_bundles[path] for path in device_paths if path in self._queue_bundles}
        return {path: bundle.recording.qsize() for path, bundle in queues.items()}

    def start_recording(self, output_dir: Path, cam_ids: dict[str, int] | None = None) -> None:
        """
        Begin recording all cameras to output_dir.

        Args:
            output_dir: Directory for MP4 files and timestamps.csv
            cam_ids: Optional mapping of device_path -> cam_id for filenames.
                    If None, auto-assigns based on device_id from path
                    (e.g., /dev/video0 -> 0, /dev/video2 -> 1)

        Raises:
            CaptureSessionError: If already recording
        """
        if self._is_recording.is_set():
            raise CaptureSessionError("Already recording")

        if not self._running:
            raise CaptureSessionError("Session not started - call start() first")

        # Build default cam_ids if not provided
        if cam_ids is None:
            cam_ids = {}
            for i, device_path in enumerate(sorted(self._queue_bundles.keys())):
                # Extract device_id from device_path (e.g., /dev/video0 -> 0)
                try:
                    device_id = int(device_path.split("video")[-1])
                    cam_ids[device_path] = device_id
                except ValueError:
                    # Fallback to enumeration if device_path doesn't match expected format
                    cam_ids[device_path] = i

        # Only record cameras specified in cam_ids
        recording_queues = {
            device_path: queues.recording
            for device_path, queues in self._queue_bundles.items()
            if device_path in cam_ids
        }

        # Drain excluded recording queues to prevent stale frames
        for device_path, queues in self._queue_bundles.items():
            if device_path not in cam_ids:
                while not queues.recording.empty():
                    try:
                        queues.recording.get_nowait()
                    except Empty:
                        break

        self._recording_device_paths = list(recording_queues.keys())

        # Create recorder
        self._frame_recorder = FrameRecorder(
            recording_queues=recording_queues,
            output_dir=output_dir,
            cam_ids=cam_ids,
            settings=self.recording_settings,
        )

        # Start recording (order matters: flag first, then recorder)
        self._is_recording.set()
        self._frame_recorder.start()

        logger.info(f"Recording started to {output_dir}")

    def stop_recording(self) -> RecordingResult | None:
        """
        Stop recording and finalize files.

        Returns RecordingResult with frame counts and any errors,
        or None if not recording.

        The recording process:
        1. Clear is_recording flag (producers stop pushing)
        2. Send sentinel (None) to each recording queue
        3. Recorder drains queues and finalizes MP4 + timestamps.csv
        """
        if not self._is_recording.is_set():
            logger.warning("Not recording, nothing to stop")
            return None

        if self._frame_recorder is None:
            logger.error("Recording flag set but no recorder exists")
            self._is_recording.clear()
            return None

        logger.info("Stopping recording...")

        # Clear flag first (producers stop pushing)
        self._is_recording.clear()

        # Send sentinels only to queues that were recording
        for device_path in self._recording_device_paths:
            self._queue_bundles[device_path].recording.put(None)
        self._recording_device_paths = []

        # Stop recorder (drains queues, finalizes files)
        result = self._frame_recorder.stop()
        self._frame_recorder = None

        logger.info(
            f"Recording stopped: {result.duration_seconds:.1f}s, {sum(result.frames_per_camera.values())} frames"
        )

        return result

    @property
    def is_recording(self) -> bool:
        """True if currently recording."""
        return self._is_recording.is_set()

    @property
    def active_device_paths(self) -> list[str]:
        """List of device paths for active cameras."""
        with self._state_lock:
            return [source.device_path for source in self.sources]

    def _start_alignment_monitor(self) -> None:
        if not self.enable_monitoring or not self._queue_bundles or self._alignment_monitor is not None:
            return
        alignment_queues = {device_path: queues.alignment for device_path, queues in self._queue_bundles.items()}
        self._alignment_monitor = AlignmentMonitor(
            alignment_queues,
            expected_cameras=len(self.sources),
            window_seconds=self.alignment_window_seconds,
        )
        self._alignment_monitor.start()

    def _stop_alignment_monitor(self) -> None:
        if self._alignment_monitor is not None:
            self._alignment_monitor.stop()
            self._alignment_monitor = None

    def _restart_alignment_monitor(self) -> None:
        if not self._running:
            return
        self._stop_alignment_monitor()
        self._start_alignment_monitor()

    def _update_monitoring_stats(self) -> None:
        """
        Update monitoring statistics from producer frame counters (fallback).

        This is less accurate than AlignmentMonitor (uses wall-clock intervals
        instead of actual frame timestamps). Only used if AlignmentMonitor
        is not active.
        """
        camera_stats: dict[str, CameraStats] = {}

        for device_path, producer in self._producers.items():
            # Calculate frames received this window
            current_count = producer.frames_captured
            last_count = self._monitoring_last_frame_count.get(device_path, 0)
            frames_in_window = current_count - last_count
            self._monitoring_last_frame_count[device_path] = current_count

            # Calculate measured fps from monitoring interval
            if frames_in_window > 0:
                measured_fps = frames_in_window / self.monitor_interval_seconds
            else:
                measured_fps = 0.0

            # Alignment queue depth
            queue_depth = self._queue_bundles[device_path].alignment.qsize()

            camera_stats[device_path] = CameraStats(
                device_path=device_path,
                frames_in_window=frames_in_window,
                measured_fps=measured_fps,
                jitter_ms=0.0,  # Not available in fallback mode
                queue_depth=queue_depth,
            )

        self._latest_stats = camera_stats

    def _start_all_sources_parallel(self) -> None:
        """
        Start all cameras in parallel and validate PTS compatibility.

        Opens all cameras simultaneously using threads, then checks that
        their PTS timestamps are from the same epoch. Cameras stay open
        after validation - they're handed to producers.

        Raises:
            CaptureSessionError: If cameras have incompatible timestamp epochs.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def start_source(source: FrameSource) -> tuple[str, float | None, Exception | None]:
            """Start a single source and return its PTS info."""
            try:
                status = source.start()
                return (source.device_path, status.first_pts_seconds, None)
            except Exception as e:
                return (source.device_path, None, e)

        # Start all cameras in parallel
        pts_values: list[tuple[str, float | None]] = []
        errors: list[tuple[str, Exception]] = []

        with ThreadPoolExecutor(max_workers=len(self.sources)) as executor:
            futures = {executor.submit(start_source, s): s for s in self.sources}
            for future in as_completed(futures):
                device_path, pts, error = future.result()
                if error is not None:
                    errors.append((device_path, error))
                else:
                    pts_values.append((device_path, pts))

        # If any camera failed to start, stop the ones that did and raise
        if errors:
            for source in self.sources:
                if source.is_running:
                    source.stop()
            error_msgs = [f"{device_path}: {e}" for device_path, e in errors]
            raise CaptureSessionError("Failed to start cameras:\n" + "\n".join(error_msgs))

        # Validate PTS compatibility
        pts_cameras = [(device_path, pts) for device_path, pts in pts_values if pts is not None]

        if not pts_cameras:
            logger.warning(
                "All cameras using wall-clock timestamps (PTS unavailable). Temporal alignment may be less accurate."
            )
            return

        if len(pts_cameras) < len(self.sources):
            logger.warning(
                f"{len(self.sources) - len(pts_cameras)} camera(s) using wall-clock "
                f"while others use PTS. Mixing timestamp sources may reduce alignment accuracy."
            )

        # Check PTS epoch consistency
        pts_times = [pts for _, pts in pts_cameras]
        spread = max(pts_times) - min(pts_times)

        if spread >= 60:
            # Stop all cameras before raising
            for source in self.sources:
                source.stop()
            raise CaptureSessionError(
                f"PTS timestamps have incompatible epochs (spread: {spread:.1f}s). "
                "Cameras may be using different timestamp bases."
            )

        logger.info(
            f"PTS validation passed: {len(pts_cameras)} camera(s) using compatible timestamps (spread: {spread:.3f}s)"
        )
