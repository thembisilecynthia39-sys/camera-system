from __future__ import annotations

from queue import Queue

from multiwebcam.pipeline.alignment import AlignmentMonitor
from multiwebcam.pipeline.frame_metadata import FrameMetadata
from multiwebcam.pipeline.session import CaptureSession
from multiwebcam.sources.config import FrameSourceConfig
from multiwebcam.sources.device import FrameSource


def test_alignment_monitor_drains_metadata_without_frame_payload():
    queue: Queue[FrameMetadata] = Queue()
    queue.put(FrameMetadata(device_path="/dev/video0", frame_index=1, frame_time=1.0))
    queue.put(FrameMetadata(device_path="/dev/video0", frame_index=2, frame_time=1.1))

    monitor = AlignmentMonitor(
        {"/dev/video0": queue},
        expected_cameras=1,
        window_seconds=3.0,
    )

    drained = monitor._drain_queues()

    assert [item.frame_index for item in drained] == [1, 2]
    assert queue.empty()


def test_capture_session_uses_small_alignment_queue_and_fps_scaled_recording_queue():
    source = FrameSource("/dev/video0", FrameSourceConfig(fps=30))
    session = CaptureSession([source], recording_buffer_seconds=6.0)

    assert session._recording_queue_capacity(source) == 180
    assert session._alignment_queue_capacity(source) == 30
