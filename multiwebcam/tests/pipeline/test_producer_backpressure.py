from __future__ import annotations

import time
from queue import Queue
from threading import Event, Lock

import numpy as np

from multiwebcam.pipeline.producer import FrameProducer, QueueBundle
from multiwebcam.sources.frame_packet import FramePacket


def _packet(index: int) -> FramePacket:
    return FramePacket(
        device_path="/dev/video0",
        device_id=0,
        frame_index=index,
        frame_time=float(index),
        timestamp_source="wall_clock",
        frame=np.zeros((4, 4, 3), dtype=np.uint8),
        fps=30.0,
    )


class _OneFrameSource:
    device_path = "/dev/video0"

    def __init__(self) -> None:
        self.stopped = Event()

    def start(self) -> None:
        pass

    def stop(self) -> None:
        self.stopped.set()

    def __iter__(self):
        yield _packet(1)


def test_full_recording_queue_aborts_without_blocking_producer() -> None:
    source = _OneFrameSource()
    recording = Queue(maxsize=1)
    recording.put_nowait(_packet(0))
    recording_active = Event()
    recording_active.set()
    overflow = Event()
    producer = FrameProducer(
        source,
        QueueBundle(
            display=Queue(maxsize=1),
            recording=recording,
            alignment=Queue(maxsize=1),
        ),
        recording_active,
        recording_overflow=overflow,
        recording_gate=Lock(),
    )

    started = time.monotonic()
    producer.start()
    assert source.stopped.wait(1.0)

    assert time.monotonic() - started < 1.0
    assert overflow.is_set()
    assert not recording_active.is_set()
    assert producer.recording_frames_dropped == 1
