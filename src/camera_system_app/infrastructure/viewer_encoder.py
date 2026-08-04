"""Bounded, atomic frame encoders for stills, sequences, and MP4 output."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Lock, Thread

import numpy as np

from camera_system_app.domain.viewer import OutputKind


class EncoderError(RuntimeError):
    """Base class for recoverable encoder failures."""


class EncoderConfigurationError(EncoderError):
    """The encoder configuration cannot produce a safe output."""


class UnsupportedEncoderError(EncoderError):
    """The requested codec backend is unavailable on this machine."""


class EncoderBackpressureError(EncoderError):
    """A non-blocking submit found the bounded frame sink full."""


class EncoderClosedError(EncoderError):
    """A frame was submitted after the encoder lifecycle had ended."""


class EncoderOutputError(EncoderError):
    """The temporary output could not be published atomically."""


class EncoderState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    FINISHED = "finished"
    ABORTED = "aborted"
    FAILED = "failed"


@dataclass(frozen=True)
class EncoderConfig:
    """Frozen output settings shared by the render controller and encoder."""

    output_path: Path
    width: int
    height: int
    fps: float = 30.0
    output_kind: OutputKind = OutputKind.MP4
    backend: str = "auto"
    transparent_background: bool = False
    background_color: tuple[float, float, float] = (0.025, 0.035, 0.055)
    queue_capacity: int = 2
    codec: str = "libx264"

    def __post_init__(self) -> None:
        path = Path(self.output_path).expanduser()
        try:
            width = int(self.width)
            height = int(self.height)
            capacity = int(self.queue_capacity)
            fps = float(self.fps)
        except (TypeError, ValueError):
            raise EncoderConfigurationError("输出尺寸、帧率和队列容量必须是数字")
        if width <= 0 or height <= 0:
            raise EncoderConfigurationError("输出宽度和高度必须为正数")
        if not 1.0 <= fps <= 240.0:
            raise EncoderConfigurationError("输出帧率必须在 1 到 240 FPS 之间")
        if capacity <= 0:
            raise EncoderConfigurationError("编码队列容量必须为正数")
        try:
            kind = self.output_kind if isinstance(self.output_kind, OutputKind) else OutputKind(self.output_kind)
        except (TypeError, ValueError):
            raise EncoderConfigurationError("不支持的输出格式：{}".format(self.output_kind))
        if kind is OutputKind.MP4 and self.transparent_background:
            raise EncoderConfigurationError("MP4 不支持透明背景，请改用 PNG 输出")
        try:
            color = tuple(float(component) for component in self.background_color)
        except (TypeError, ValueError):
            raise EncoderConfigurationError("背景颜色必须包含三个数值")
        if len(color) != 3 or any(component < 0.0 or component > 1.0 for component in color):
            raise EncoderConfigurationError("背景颜色必须是 0 到 1 之间的 RGB 值")
        backend = str(self.backend).lower().strip()
        if not backend:
            raise EncoderConfigurationError("编码后端不能为空")
        if kind in (OutputKind.PNG, OutputKind.PNG_SEQUENCE) and backend == "auto":
            backend = "png"
        object.__setattr__(self, "output_path", path)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "fps", fps)
        object.__setattr__(self, "output_kind", kind)
        object.__setattr__(self, "backend", backend)
        object.__setattr__(self, "background_color", color)
        object.__setattr__(self, "queue_capacity", capacity)


class BoundedFrameSink:
    """A producer-owned bounded queue with explicit close and abort states."""

    def __init__(self, maxsize: int = 2):
        if int(maxsize) <= 0:
            raise ValueError("maxsize must be positive")
        self._queue = Queue(maxsize=int(maxsize))
        self._lock = Lock()
        self._closed = False
        self._aborted = False

    @property
    def maxsize(self) -> int:
        return self._queue.maxsize

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    @property
    def aborted(self) -> bool:
        with self._lock:
            return self._aborted

    @property
    def available_slots(self) -> int:
        return max(0, self._queue.maxsize - self._queue.qsize())

    def put(self, frame, *, block: bool = True, timeout: float | None = None) -> None:
        with self._lock:
            if self._closed:
                raise EncoderClosedError("编码帧队列已经关闭")
        try:
            if not block:
                self._queue.put_nowait(frame)
            elif timeout is None:
                self._queue.put(frame)
            else:
                self._queue.put(frame, timeout=max(0.0, float(timeout)))
        except Full as exc:
            raise EncoderBackpressureError("编码器队列已满，渲染线程需要等待") from exc

    def get(self, timeout: float | None = None):
        deadline = None if timeout is None else time.monotonic() + max(0.0, float(timeout))
        while True:
            try:
                wait = 0.05 if deadline is None else max(0.0, min(0.05, deadline - time.monotonic()))
                return self._queue.get(timeout=wait)
            except Empty:
                with self._lock:
                    if self._closed:
                        return None
                if deadline is not None and time.monotonic() >= deadline:
                    raise

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        # get() observes the closed state after already queued frames drain.

    def abort(self) -> None:
        with self._lock:
            if self._closed:
                self._aborted = True
                return
            self._closed = True
            self._aborted = True
        while True:
            try:
                self._queue.get_nowait()
            except Empty:
                break
        self._queue.put(None)


def _pillow_available() -> bool:
    return importlib.util.find_spec("PIL") is not None


def _pyav_available() -> bool:
    return importlib.util.find_spec("av") is not None


def _gstreamer_available() -> bool:
    inspector = shutil.which("gst-inspect-1.0")
    if inspector is None:
        return False
    try:
        result = subprocess.run(
            [inspector, "nvv4l2h264enc"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def available_encoder_backends() -> tuple[str, ...]:
    """Return available backend names without importing optional codecs."""

    backends = []
    if _pillow_available():
        backends.append("png")
    if _pyav_available():
        backends.append("pyav")
    if _gstreamer_available():
        backends.append("gstreamer")
    return tuple(backends)


def encoder_backend_available(name: str) -> bool:
    return str(name).lower() in available_encoder_backends()


class FrameEncoder:
    """Encode frames on a worker and publish only a complete final output."""

    def __init__(self, config: EncoderConfig):
        if not isinstance(config, EncoderConfig):
            raise EncoderConfigurationError("config must be an EncoderConfig value")
        self.config = config
        self.sink = BoundedFrameSink(config.queue_capacity)
        self._state = EncoderState.CREATED
        self._state_lock = Lock()
        self._thread: Thread | None = None
        self._temp_path: Path | None = None
        self._writer = None
        self._container = None
        self._stream = None
        self._frames_written = 0
        self._error: EncoderError | None = None

    @property
    def state(self) -> EncoderState:
        with self._state_lock:
            return self._state

    @property
    def frames_written(self) -> int:
        return self._frames_written

    @property
    def error(self) -> EncoderError | None:
        return self._error

    @property
    def is_running(self) -> bool:
        return self.state is EncoderState.RUNNING

    def start(self) -> None:
        if self.state is not EncoderState.CREATED:
            raise EncoderClosedError("编码器只能启动一次")
        backend = self._resolved_backend()
        if not encoder_backend_available(backend):
            raise UnsupportedEncoderError(
                "编码后端不可用：{}（当前可用：{}）".format(
                    backend, ", ".join(available_encoder_backends()) or "无"
                )
            )
        self.config.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._temp_path = self._create_temp_path()
        self._set_state(EncoderState.RUNNING)
        self._thread = Thread(target=self._run, name="viewer-frame-encoder", daemon=True)
        self._thread.start()

    def submit(self, frame, *, block: bool = True, timeout: float | None = None) -> None:
        if self.state is not EncoderState.RUNNING:
            raise EncoderClosedError("编码器尚未运行或已经结束")
        self.sink.put(frame, block=block, timeout=timeout)

    def finish(self, timeout: float | None = 30.0) -> Path:
        if self.state is EncoderState.CREATED:
            raise EncoderClosedError("编码器尚未启动")
        if self.state is EncoderState.ABORTED:
            raise EncoderClosedError("编码器已经取消")
        if self.state is EncoderState.FINISHED:
            return self.config.output_path
        if self.state is EncoderState.FAILED:
            raise self._error or EncoderError("编码器失败")
        self.sink.close()
        if not self._join(timeout):
            raise EncoderError("等待编码器完成超时")
        if self.state is EncoderState.FAILED:
            raise self._error or EncoderError("编码器失败")
        if self.state is not EncoderState.FINISHED:
            raise EncoderError("编码器未完成")
        return self.config.output_path

    def abort(self, timeout: float | None = 30.0) -> None:
        if self.state is EncoderState.CREATED:
            self._set_state(EncoderState.ABORTED)
            return
        if self.state in (EncoderState.FINISHED, EncoderState.ABORTED):
            return
        self.sink.abort()
        if not self._join(timeout):
            raise EncoderError("取消编码器超时")
        if self.state is not EncoderState.FAILED:
            self._set_state(EncoderState.ABORTED)
        self._cleanup_temp()

    def _resolved_backend(self) -> str:
        backend = self.config.backend
        if backend != "auto":
            return backend
        if self.config.output_kind in (OutputKind.PNG, OutputKind.PNG_SEQUENCE):
            return "png"
        if encoder_backend_available("gstreamer"):
            return "gstreamer"
        return "pyav"

    def _create_temp_path(self) -> Path:
        output = self.config.output_path
        if self.config.output_kind is OutputKind.PNG_SEQUENCE:
            return Path(tempfile.mkdtemp(prefix=".{}-".format(output.name), dir=str(output.parent)))
        descriptor, name = tempfile.mkstemp(
            prefix=".{}-".format(output.stem),
            suffix=".part",
            dir=str(output.parent),
        )
        os.close(descriptor)
        return Path(name)

    def _run(self) -> None:
        try:
            while True:
                item = self.sink.get()
                if item is None:
                    break
                frame = self._validate_frame(item)
                self._encode_frame(frame)
                self._frames_written += 1
            if self._frames_written <= 0:
                raise EncoderError("没有收到可编码的渲染帧")
            if self.config.output_kind is OutputKind.PNG and self._frames_written != 1:
                raise EncoderError("PNG 单帧输出只允许一个渲染帧")
            self._finalize_backend()
            self._publish()
            self._set_state(EncoderState.FINISHED)
        except Exception as exc:
            if isinstance(exc, EncoderError):
                error = exc
            else:
                error = EncoderError("编码失败：{}".format(exc))
            self._error = error
            self._close_backend()
            self._cleanup_temp()
            self._set_state(EncoderState.ABORTED if self.sink.aborted else EncoderState.FAILED)

    def _validate_frame(self, frame) -> np.ndarray:
        array = np.asarray(frame)
        if array.ndim != 3 or array.shape[0] != self.config.height or array.shape[1] != self.config.width:
            raise EncoderError(
                "渲染帧尺寸不匹配：期望 {}x{}，收到 {}".format(
                    self.config.width,
                    self.config.height,
                    tuple(array.shape),
                )
            )
        if array.shape[2] not in (3, 4):
            raise EncoderError("渲染帧必须是 RGB 或 RGBA")
        if array.dtype != np.uint8:
            if np.issubdtype(array.dtype, np.floating) and float(np.nanmax(array)) <= 1.0:
                array = array * 255.0
            array = np.clip(array, 0.0, 255.0).astype(np.uint8)
        return np.ascontiguousarray(array)

    def _rgb_frame(self, array: np.ndarray) -> np.ndarray:
        if array.shape[2] == 3:
            return array
        rgb = array[:, :, :3].astype(np.float32)
        alpha = array[:, :, 3:4].astype(np.float32) / 255.0
        background = np.asarray(self.config.background_color, dtype=np.float32) * 255.0
        return np.clip(rgb * alpha + background * (1.0 - alpha), 0.0, 255.0).astype(np.uint8)

    def _png_frame(self, array: np.ndarray) -> np.ndarray:
        if self.config.transparent_background:
            if array.shape[2] == 4:
                return array
            alpha = np.full((array.shape[0], array.shape[1], 1), 255, dtype=np.uint8)
            return np.concatenate((array, alpha), axis=2)
        return self._rgb_frame(array)

    def _encode_frame(self, array: np.ndarray) -> None:
        kind = self.config.output_kind
        if kind in (OutputKind.PNG, OutputKind.PNG_SEQUENCE):
            try:
                from PIL import Image
            except ImportError as exc:
                raise UnsupportedEncoderError("PNG 输出需要 Pillow") from exc
            image_array = self._png_frame(array)
            image = Image.fromarray(image_array, mode="RGBA" if image_array.shape[2] == 4 else "RGB")
            if kind is OutputKind.PNG:
                image.save(str(self._temp_path), format="PNG")
            else:
                assert self._temp_path is not None
                image.save(
                    str(self._temp_path / "frame_{:06d}.png".format(self._frames_written)),
                    format="PNG",
                )
            return
        if self._resolved_backend() == "pyav":
            self._encode_pyav(array)
            return
        if self._resolved_backend() == "gstreamer":
            self._encode_gstreamer(array)
            return
        raise UnsupportedEncoderError("不支持的编码后端：{}".format(self._resolved_backend()))

    def _encode_pyav(self, array: np.ndarray) -> None:
        if self._container is None:
            try:
                import av
            except ImportError as exc:
                raise UnsupportedEncoderError("MP4 PyAV 后端不可用") from exc
            self._container = av.open(str(self._temp_path), mode="w", format="mp4")
            self._stream = self._container.add_stream(self.config.codec, rate=self.config.fps)
            self._stream.width = self.config.width
            self._stream.height = self.config.height
            self._stream.pix_fmt = "yuv420p"
        import av

        frame = av.VideoFrame.from_ndarray(self._rgb_frame(array), format="rgb24")
        frame.pts = self._frames_written
        for packet in self._stream.encode(frame):
            self._container.mux(packet)

    def _encode_gstreamer(self, array: np.ndarray) -> None:
        if self._writer is None:
            try:
                import cv2
                from multiwebcam.profiles.settings import RecordingSettings
                from multiwebcam.recording.gstreamer import build_jetson_writer_pipeline
            except ImportError as exc:
                raise UnsupportedEncoderError("Jetson GStreamer 后端不可用") from exc
            settings = RecordingSettings(fps=max(1, int(round(self.config.fps))))
            pipeline = build_jetson_writer_pipeline(
                self._temp_path,
                (self.config.width, self.config.height),
                int(round(self.config.fps)),
                settings,
            )
            self._writer = cv2.VideoWriter(
                pipeline,
                cv2.CAP_GSTREAMER,
                0,
                float(self.config.fps),
                (self.config.width, self.config.height),
            )
            if not self._writer.isOpened():
                raise EncoderError("无法打开 Jetson GStreamer H.264 编码器")
        self._writer.write(self._rgb_frame(array)[:, :, ::-1])

    def _finalize_backend(self) -> None:
        if self._stream is not None and self._container is not None:
            for packet in self._stream.encode():
                self._container.mux(packet)
            self._container.close()
            self._container = None
            self._stream = None
        if self._writer is not None:
            self._writer.release()
            self._writer = None

    def _close_backend(self) -> None:
        try:
            if self._container is not None:
                self._container.close()
        except Exception:
            pass
        try:
            if self._writer is not None:
                self._writer.release()
        except Exception:
            pass
        self._container = None
        self._stream = None
        self._writer = None

    def _publish(self) -> None:
        if self._temp_path is None:
            raise EncoderOutputError("编码临时文件不存在")
        output = self.config.output_path
        if self.config.output_kind is OutputKind.PNG_SEQUENCE and output.exists():
            raise EncoderOutputError("PNG 序列目标目录已存在，请选择新的输出目录")
        try:
            os.replace(str(self._temp_path), str(output))
        except OSError as exc:
            raise EncoderOutputError("无法发布最终输出：{}".format(exc)) from exc
        self._temp_path = None

    def _cleanup_temp(self) -> None:
        if self._temp_path is None:
            return
        try:
            if self._temp_path.is_dir():
                shutil.rmtree(str(self._temp_path))
            else:
                self._temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        self._temp_path = None

    def _join(self, timeout: float | None) -> bool:
        if self._thread is None:
            return True
        self._thread.join(timeout=None if timeout is None else max(0.0, float(timeout)))
        return not self._thread.is_alive()

    def _set_state(self, state: EncoderState) -> None:
        with self._state_lock:
            self._state = state


__all__ = [
    "BoundedFrameSink",
    "EncoderBackpressureError",
    "EncoderClosedError",
    "EncoderConfig",
    "EncoderConfigurationError",
    "EncoderError",
    "EncoderOutputError",
    "EncoderState",
    "FrameEncoder",
    "UnsupportedEncoderError",
    "available_encoder_backends",
    "encoder_backend_available",
]
