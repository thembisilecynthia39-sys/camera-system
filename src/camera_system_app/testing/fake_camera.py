"""Synthetic camera implementing the FrameSource surface used by CaptureSession."""

from __future__ import annotations

import re
import time
from threading import Event
from typing import Iterator, Optional

import numpy as np

from multiwebcam.sources.config import FrameSourceConfig, FrameSourceStatus
from multiwebcam.sources.frame_packet import FramePacket


class FakeCameraBackend:
    """Generate deterministic BGR frames without opening a device."""

    def __init__(
        self,
        device_path: str = "/dev/fake-video0",
        config: Optional[FrameSourceConfig] = None,
        seed: int = 7,
    ) -> None:
        self.device_path = device_path
        match = re.search(r"(\d+)$", device_path)
        self.device_id = int(match.group(1)) if match else 0
        self._config = config or FrameSourceConfig(
            resolution=(320, 240),
            fps=30,
            warmup_frames=0,
        )
        self._seed = seed
        self._running = False
        self._stop_event = Event()
        self.start_count = 0
        self.stop_count = 0
        self.released = Event()

    def start(self) -> FrameSourceStatus:
        self.start_count += 1
        self._running = True
        self._stop_event.clear()
        self.released.clear()
        return FrameSourceStatus(
            device_path=self.device_path,
            resolution=self._config.resolution,
            actual_fps=float(self._config.fps),
            first_pts_seconds=time.monotonic(),
            timestamp_source="wall_clock",
            warmup_frames_discarded=0,
        )

    def stop(self) -> None:
        self.stop_count += 1
        self._running = False
        self._stop_event.set()
        self.released.set()

    def __iter__(self) -> Iterator[FramePacket]:
        rng = np.random.default_rng(self._seed)
        width, height = self._config.resolution
        interval = 1.0 / max(1, self._config.fps)
        frame_index = 0
        while self._running and not self._stop_event.is_set():
            frame = rng.integers(32, 224, size=(height, width, 3), dtype=np.uint8)
            yield FramePacket(
                device_path=self.device_path,
                device_id=self.device_id,
                frame_index=frame_index,
                frame_time=time.monotonic(),
                timestamp_source="wall_clock",
                frame=frame,
                fps=float(self._config.fps),
            )
            frame_index += 1
            self._stop_event.wait(interval)

