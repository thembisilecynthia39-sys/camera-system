from __future__ import annotations

from types import SimpleNamespace

from multiwebcam.pipeline.session import CaptureSession


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
