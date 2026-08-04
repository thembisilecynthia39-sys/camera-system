from __future__ import annotations

from types import SimpleNamespace

import pytest

from multiwebcam.pipeline.session import CaptureSession
from multiwebcam.sources.config import FrameSourceConfig
from multiwebcam.sources.device import FrameSource


class _FakeSource:
    def __init__(self, device_path: str, error: Exception | None = None) -> None:
        self.device_path = device_path
        self._error = error
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self):
        if self._error is not None:
            raise self._error
        self._running = True
        return SimpleNamespace(first_pts_seconds=None)

    def stop(self) -> None:
        self._running = False


def test_capture_session_keeps_healthy_sources_when_peer_fails():
    healthy = _FakeSource("/dev/video0")
    failed = _FakeSource("/dev/video2", RuntimeError("device busy"))
    session = CaptureSession([healthy, failed])

    session._start_all_sources_parallel()

    assert [source.device_path for source in session.sources] == ["/dev/video0"]
    assert session.startup_errors == {"/dev/video2": "device busy"}
    assert healthy.is_running


def test_capture_session_can_start_without_any_camera_for_ui_retry():
    failed = _FakeSource("/dev/video4", RuntimeError("no frames"))
    session = CaptureSession([failed], enable_monitoring=False)

    session.start()

    try:
        assert session.startup_errors == {"/dev/video4": "no frames"}
        assert session.active_device_paths == []
        assert not session.producers_healthy
    finally:
        session.stop()


def test_capture_session_signals_all_producers_before_waiting():
    events = []

    class _FakeProducer:
        def __init__(self, name: str) -> None:
            self.name = name

        def request_stop(self) -> None:
            events.append(("request", self.name))

        def wait_stopped(self, timeout: float) -> bool:
            assert events[:2] == [("request", "a"), ("request", "b")]
            events.append(("wait", self.name))
            return True

    session = CaptureSession([_FakeSource("/dev/video0")], enable_monitoring=False)
    session._running = True
    session._producers = {
        "a": _FakeProducer("a"),
        "b": _FakeProducer("b"),
    }
    session._stop_alignment_monitor = lambda timeout: True

    assert session.stop()
    assert events == [
        ("request", "a"),
        ("request", "b"),
        ("wait", "a"),
        ("wait", "b"),
    ]


def test_frame_source_warmup_observes_cancellation_and_releases_device(
    monkeypatch,
):
    class Capture:
        def __init__(self) -> None:
            self.released = False

        def read(self):
            return False, None

        def release(self):
            self.released = True

    capture = Capture()
    source = FrameSource(
        "/dev/video0",
        FrameSourceConfig(warmup_frames=1),
    )
    monkeypatch.setattr(
        source,
        "_open_device",
        lambda: setattr(source, "_cap", capture),
    )
    checks = iter((False, False, True))

    with pytest.raises(InterruptedError, match="cancel"):
        source.start(cancel_check=lambda: next(checks, True))

    assert capture.released
    assert not source.is_running
