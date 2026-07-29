from __future__ import annotations
"""Threaded frame producer wrapping FrameSource."""


import logging
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from typing import TYPE_CHECKING

from multiwebcam.pipeline.frame_metadata import FrameMetadata

if TYPE_CHECKING:
    from multiwebcam.sources.device import FrameSource
    from multiwebcam.sources.frame_packet import FramePacket

logger = logging.getLogger(__name__)


@dataclass
class QueueBundle:
    """Bundle of output queues for a single camera."""

    display: Queue[FramePacket]  # maxsize=1, drop-oldest
    recording: Queue[FramePacket]  # bounded, non-blocking while recording
    alignment: Queue[FrameMetadata]  # metadata only, for monitoring


class FrameProducer:
    """
    Threaded wrapper around FrameSource that pushes frames to multiple queues.

    The producer runs in its own thread, pulling frames from the FrameSource
    and pushing them to queues with different behaviors:
    - Display queue: maxsize=1, drop-oldest for latest frame access
    - Alignment queue: blocking puts for monitoring
    - Recording queue: conditional (only when is_recording flag is set)

    Usage:
        source = FrameSource("/dev/video0")
        is_recording = Event()
        queues = QueueBundle(
            display=Queue(maxsize=1),
            recording=Queue(maxsize=150),
            alignment=Queue(maxsize=150),
        )
        producer = FrameProducer(source, queues, is_recording)

        producer.start()
        # ... consume from queues ...
        producer.stop()
    """

    def __init__(
        self,
        source: FrameSource,
        queues: QueueBundle,
        is_recording: Event,
        recording_overflow: Event | None = None,
        recording_gate: Lock | None = None,
    ) -> None:
        """
        Initialize a FrameProducer.

        Args:
            source: FrameSource to capture from
            queues: QueueBundle bundle for this camera
            is_recording: Shared Event flag - only push to recording queue when set
        """
        self.source = source
        self.queues = queues
        self.is_recording = is_recording
        self.recording_overflow = recording_overflow or Event()
        self.recording_gate = recording_gate or Lock()
        self._thread: Thread | None = None
        self._shutdown_event = Event()
        self._source_ready = Event()
        self._resume_event = Event()
        self._resume_event.set()  # Start in running state
        self._paused_ack = Event()
        self._running = False  # Tracks thread lifecycle
        self._frames_captured = 0
        self._recording_frames_dropped = 0

    @property
    def is_running(self) -> bool:
        """True if the producer thread is running."""
        return self._running

    @property
    def is_ready(self) -> bool:
        """True after the source pipeline has successfully started."""
        return self._running and self._source_ready.is_set()

    @property
    def device_path(self) -> str:
        """Device path of the underlying source."""
        return self.source.device_path

    @property
    def frames_captured(self) -> int:
        """Total frames captured by this producer."""
        return self._frames_captured

    @property
    def recording_frames_dropped(self) -> int:
        """Frames rejected because the lossless recording queue was full."""
        return self._recording_frames_dropped

    def pause(self) -> None:
        """Pause frame production. Producer thread blocks until resume()."""
        self._resume_event.clear()

    def resume(self) -> None:
        """Resume frame production after pause."""
        self._resume_event.set()
        self._paused_ack.clear()

    @property
    def is_paused(self) -> bool:
        """True after the producer thread has acknowledged the pause."""
        return not self._resume_event.is_set() and self._paused_ack.is_set()

    def start(self) -> None:
        """Start the producer thread."""
        if self._running:
            logger.warning(f"Producer for {self.device_path} already running")
            return

        self._shutdown_event.clear()
        self._source_ready.clear()
        self._thread = Thread(target=self._run, daemon=True)
        self._running = True
        self._thread.start()
        logger.info(f"Started producer for {self.device_path}")

    def stop(self, timeout: float = 5.0) -> bool:
        """
        Stop the producer thread.

        Signals the producer thread to exit, then waits for it to release
        its own source. Releasing OpenCV VideoCapture from another thread can
        segfault when a USB camera disappears or its /dev/video node changes.

        Args:
            timeout: Maximum time to wait for thread to join (seconds)
        """
        self.request_stop()
        return self.wait_stopped(timeout)

    def request_stop(self) -> None:
        """Signal capture shutdown without waiting for the reader thread."""
        if not self._running:
            return
        logger.info(f"Stopping producer for {self.device_path}")
        self._shutdown_event.set()
        self._resume_event.set()  # Unblock if paused

    def wait_stopped(self, timeout: float = 5.0) -> bool:
        """Wait for a previously requested stop and source release."""
        if not self._running:
            return True
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    f"Producer thread for {self.device_path} "
                    f"did not terminate within {timeout}s"
                )
                return False

        self._running = False
        logger.info(f"Stopped producer for {self.device_path}")
        return True

    def _run(self) -> None:
        """Producer thread main loop."""
        max_restarts = 3
        restarts = 0

        try:
            try:
                self.source.start()
                self._source_ready.set()
            except Exception as e:
                logger.error(f"Failed to start source {self.device_path}: {e}")
                return

            while not self._shutdown_event.is_set():
                try:
                    for packet in self.source:
                        # Acknowledge that no more packets will be published
                        # before blocking. GPU handoff waits on this event.
                        if not self._resume_event.is_set():
                            self._paused_ack.set()
                        self._resume_event.wait()
                        self._paused_ack.clear()

                        # Check shutdown after resume to avoid processing one more frame
                        if self._shutdown_event.is_set():
                            return

                        # Make frame array read-only to enforce immutability
                        packet.frame.flags.writeable = False

                        self._frames_captured += 1

                        # Display queue: drop-oldest (always get latest)
                        try:
                            self.queues.display.get_nowait()
                        except Empty:
                            pass
                        self.queues.display.put_nowait(packet)

                        # Alignment queue only needs timing metadata, not full frame payloads.
                        metadata = FrameMetadata(
                            device_path=packet.device_path,
                            frame_index=packet.frame_index,
                            frame_time=packet.frame_time,
                        )
                        try:
                            self.queues.alignment.put_nowait(metadata)
                        except Full:
                            try:
                                self.queues.alignment.get_nowait()
                            except Empty:
                                pass
                            self.queues.alignment.put_nowait(metadata)

                        # Never apply encoder backpressure to the camera reader.
                        # A full queue aborts recording instead of stalling USB
                        # capture and growing latency across every consumer.
                        with self.recording_gate:
                            if self.is_recording.is_set():
                                try:
                                    self.queues.recording.put_nowait(packet)
                                except Full:
                                    self._recording_frames_dropped += 1
                                    self.recording_overflow.set()
                                    self.is_recording.clear()
                                    logger.error(
                                        "Recording queue overflow for %s; "
                                        "recording aborted without blocking capture",
                                        self.device_path,
                                    )

                    # Iterator exhausted normally
                    break

                except Exception as e:
                    if self._shutdown_event.is_set():
                        break

                    restarts += 1
                    if restarts > max_restarts:
                        logger.error(
                            f"Producer {self.device_path} exceeded {max_restarts} "
                            f"restarts, giving up: {e}"
                        )
                        break

                    # Transient decode errors happen when V4L2 controls change
                    # mid-stream (e.g. switching exposure mode). Restart the
                    # source and resume capturing.
                    logger.warning(
                        f"Decode error on {self.device_path} ({restarts}/{max_restarts}), "
                        f"restarting source: {e}"
                    )
                    try:
                        self.source.stop()
                        self.source.start()
                    except Exception as restart_err:
                        logger.error(
                            f"Failed to restart source {self.device_path}: {restart_err}"
                        )
                        break
        finally:
            self._paused_ack.clear()
            self._source_ready.clear()
            try:
                self.source.stop()
            except Exception:
                logger.exception("Error while closing source %s", self.device_path)

            self._running = False
            logger.debug(f"Producer thread exiting for {self.device_path}")
