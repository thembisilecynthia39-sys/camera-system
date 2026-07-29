from queue import Queue
from types import SimpleNamespace

import pytest

from multiwebcam.pipeline import session as session_module
from multiwebcam.pipeline.producer import QueueBundle
from multiwebcam.pipeline.session import CaptureSession
from multiwebcam.profiles.settings import RecordingSettings
from multiwebcam.recording import recorder as recorder_module
from multiwebcam.recording.recorder import FrameRecorder
from multiwebcam.recording.recorder import RecordingDrainTimeout


class _FakeSource:
    def __init__(self, device_path: str) -> None:
        self.device_path = device_path
        self._config = SimpleNamespace(fps=30, resolution=(640, 480))


def _running_session() -> CaptureSession:
    source = _FakeSource("/dev/video0")
    session = CaptureSession([source], enable_monitoring=False)
    session._queue_bundles[source.device_path] = QueueBundle(
        display=Queue(),
        recording=Queue(),
        alignment=Queue(),
    )
    session._running = True
    return session


def test_encoder_start_failure_rolls_back_recording_state(monkeypatch, tmp_path):
    class FailingRecorder:
        def __init__(self, **_kwargs) -> None:
            pass

        def start(self) -> None:
            raise OSError("disk unavailable")

    monkeypatch.setattr(session_module, "FrameRecorder", FailingRecorder)
    session = _running_session()

    with pytest.raises(OSError, match="disk unavailable"):
        session.start_recording(tmp_path)

    assert not session.is_recording
    assert not session.has_pending_recording
    assert session._recording_device_paths == []


def test_session_stop_releases_producers_after_recording_drain_timeout():
    class TimedOutRecorder:
        def __init__(self) -> None:
            self.drain_timeouts = []

        def stop(self, drain_timeout=10.0):
            self.drain_timeouts.append(drain_timeout)
            raise RecordingDrainTimeout("encoder still running")

    class Producer:
        def __init__(self) -> None:
            self.stop_requested = False
            self.wait_timeouts = []

        def request_stop(self) -> None:
            self.stop_requested = True

        def wait_stopped(self, timeout) -> bool:
            self.wait_timeouts.append(timeout)
            return True

    session = _running_session()
    recorder = TimedOutRecorder()
    producer = Producer()
    session._frame_recorder = recorder
    session._recording_device_paths = ["/dev/video0"]
    session._is_recording.set()
    session._producers = {"/dev/video0": producer}

    assert session.stop(timeout=0.1) is False

    assert producer.stop_requested
    assert producer.wait_timeouts
    assert recorder.drain_timeouts
    assert recorder.drain_timeouts[0] <= 0.1
    assert session.has_pending_recording


def test_partial_encoder_start_failure_stops_already_started_threads(
    monkeypatch, tmp_path
):
    instances = []

    class Encoder:
        def __init__(self, *, cam_id, **_kwargs) -> None:
            self.cam_id = cam_id
            self.stop_requested = False
            self.joined = False
            instances.append(self)

        def start(self) -> None:
            if self.cam_id == 1:
                raise RuntimeError("thread unavailable")

        def request_stop(self) -> None:
            self.stop_requested = True

        def join(self, timeout=None) -> bool:
            self.joined = True
            return True

    monkeypatch.setattr(recorder_module, "CameraEncoder", Encoder)
    recorder = FrameRecorder(
        recording_queues={
            "/dev/video0": Queue(),
            "/dev/video1": Queue(),
        },
        output_dir=tmp_path,
        cam_ids={"/dev/video0": 0, "/dev/video1": 1},
        settings=RecordingSettings(backend="pyav"),
    )

    with pytest.raises(RuntimeError, match="thread unavailable"):
        recorder.start()

    assert instances[0].stop_requested
    assert instances[0].joined
    assert not recorder.is_running
