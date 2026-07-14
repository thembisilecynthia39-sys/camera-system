"""V4L2 device capture using OpenCV."""

from __future__ import annotations


import logging
import os
import re
import cv2
from collections import deque
from time import perf_counter, sleep
from typing import Iterator, Literal

from multiwebcam.sources.config import FrameSourceConfig, FrameSourceStatus
from multiwebcam.sources.frame_packet import FramePacket
from multiwebcam.sources.gstreamer import build_jetson_capture_pipeline

logger = logging.getLogger(__name__)

_OPENCV_FOURCC = {
    "mjpeg": "MJPG",
    "mjpe": "MJPG",
    "yuyv": "YUYV",
    "yuyv422": "YUYV",
}


class FrameSourceError(Exception):
    pass


def _opencv_has_gstreamer() -> bool:
    info = cv2.getBuildInformation()
    return "GStreamer:                   YES" in info


def _opencv_has_cuda() -> bool:
    info = cv2.getBuildInformation()
    return "NVIDIA CUDA:                   YES" in info or "CUDA" in info


def _opencv_runtime_summary() -> str:
    return (
        f"cv2={getattr(cv2, '__version__', 'unknown')} "
        f"path={getattr(cv2, '__file__', 'unknown')} "
        f"gstreamer={_opencv_has_gstreamer()} "
        f"cuda={_opencv_has_cuda()} "
        f"PYTHONPATH={os.environ.get('PYTHONPATH', '')!r}"
    )


class FrameSource:
    _FPS_WINDOW_SIZE: int = 10

    def __init__(self, device_path: str, config: FrameSourceConfig | None = None):
        self.device_path = device_path
        self.device_id = self._extract_device_id(device_path)
        self._config = config or FrameSourceConfig()
        self._cap: cv2.VideoCapture | None = None
        self._is_running = False
        self._frame_index = 0
        self._warmup_discarded = 0
        self._timestamps: deque[float] = deque(maxlen=self._FPS_WINDOW_SIZE)
        self._timestamp_source: Literal["pts", "wall_clock"] = "wall_clock"
        self._first_pts: float | None = None

    @staticmethod
    def _extract_device_id(device_path: str) -> int:
        match = re.search(r"video(\d+)$", device_path)
        if match:
            return int(match.group(1))
        raise ValueError(f"Cannot extract device ID from path: {device_path}")

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> FrameSourceStatus:
        if self._is_running:
            return self._build_status()

        logger.info(f"Opening {self.device_path} with OpenCV")
        try:
            self._open_device()
            self._consume_warmup_frames()
            self._is_running = True
            return self._build_status()
        except Exception:
            self._cleanup()
            raise

    def stop(self) -> None:
        self._cleanup()
        self._is_running = False

    def _open_device(self) -> None:
        """Open device with the configured capture backend."""
        if self._config.capture_backend == "gstreamer":
            if not _opencv_has_gstreamer():
                raise FrameSourceError(
                    "Configured capture_backend='gstreamer' but imported OpenCV lacks GStreamer support. "
                    f"{_opencv_runtime_summary()}"
                )
            pipeline = self._config.gstreamer_pipeline or build_jetson_capture_pipeline(
                self.device_path,
                self._config,
            )
            logger.info("Opening %s with GStreamer pipeline: %s", self.device_path, pipeline)
            self._cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            # Use the discovered device path instead of a transient numeric
            # index.  Hotplugging can renumber /dev/videoN while bus_info
            # remains the stable camera identity used by the project.
            self._cap = cv2.VideoCapture(self.device_path, cv2.CAP_V4L2)
        if not self._cap.isOpened():
            raise FrameSourceError(f"Cannot open {self.device_path}")

        if self._config.capture_backend == "opencv_v4l2":
            fourcc = _OPENCV_FOURCC.get(self._config.pixel_format.lower())
            if fourcc is not None:
                self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
            else:
                logger.warning(
                    "OpenCV backend does not know pixel format %s; leaving FOURCC unchanged",
                    self._config.pixel_format,
                )

            width, height = self._config.resolution
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self._cap.set(cv2.CAP_PROP_FPS, self._config.fps)

    def _consume_warmup_frames(self) -> None:
        if self._cap is None:
            raise FrameSourceError("Device not open")

        deadline = perf_counter() + self._config.startup_timeout_seconds
        self._warmup_discarded = 0

        while self._warmup_discarded < self._config.warmup_frames:
            ret, _frame = self._cap.read()
            if ret:
                self._warmup_discarded += 1
                continue

            if perf_counter() >= deadline:
                raise FrameSourceError(
                    f"{self.device_path} opened but delivered no frames within "
                    f"{self._config.startup_timeout_seconds:.1f}s; V4L2 STREAMON may have been "
                    "rejected because of USB bandwidth exhaustion, an unsupported mode, "
                    "or another process using the device"
                )
            sleep(0.01)

    def _cleanup(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._frame_index = 0
        self._timestamps.clear()

    def _calculate_fps(self) -> float:
        if len(self._timestamps) < 2:
            return float(self._config.fps)
        elapsed = self._timestamps[-1] - self._timestamps[0]
        if elapsed <= 0:
            return float(self._config.fps)
        return (len(self._timestamps) - 1) / elapsed

    def _build_status(self) -> FrameSourceStatus:
        return FrameSourceStatus(
            device_path=self.device_path,
            resolution=self._config.resolution,
            actual_fps=self._calculate_fps(),
            first_pts_seconds=self._first_pts,
            timestamp_source=self._timestamp_source,
            warmup_frames_discarded=self._warmup_discarded,
        )

    def __iter__(self) -> Iterator[FramePacket]:
        if not self._is_running:
            self.start()

        if self._cap is None or not self._cap.isOpened():
            raise FrameSourceError("Device not open")

        no_frame_deadline = perf_counter() + self._config.read_timeout_seconds
        while self._is_running:
            ret, frame = self._cap.read()

            if not ret:
                if perf_counter() >= no_frame_deadline:
                    raise FrameSourceError(
                        f"{self.device_path} delivered no frames for {self._config.read_timeout_seconds:.1f}s"
                    )
                sleep(0.01)
                continue

            no_frame_deadline = perf_counter() + self._config.read_timeout_seconds
            frame_time = perf_counter()
            self._timestamps.append(frame_time)

            # Frame is already BGR from OpenCV
            packet = FramePacket(
                device_path=self.device_path,
                device_id=self.device_id,
                frame_index=self._frame_index,
                frame_time=frame_time,
                timestamp_source="wall_clock",
                frame=frame,
                fps=self._calculate_fps(),
            )

            self._frame_index += 1
            yield packet

    def __enter__(self) -> "FrameSource":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
