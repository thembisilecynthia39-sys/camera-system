import pytest
import cv2

from multiwebcam.sources.config import FrameSourceConfig
from multiwebcam.sources.device import FrameSource, FrameSourceError


def test_gstreamer_backend_reports_missing_opencv_gstreamer_support(monkeypatch):
    config = FrameSourceConfig(capture_backend="gstreamer")
    source = FrameSource("/dev/video0", config)

    monkeypatch.setattr("multiwebcam.sources.device._opencv_has_gstreamer", lambda: False)
    monkeypatch.setattr("multiwebcam.sources.device._opencv_has_cuda", lambda: False)
    monkeypatch.setattr("multiwebcam.sources.device.cv2.__version__", "4.13.0")
    monkeypatch.setattr("multiwebcam.sources.device.cv2.__file__", "/tmp/fake-cv2")

    with pytest.raises(FrameSourceError, match="lacks GStreamer support"):
        source._open_device()


def test_opencv_v4l2_uses_discovered_device_path(monkeypatch):
    calls = []

    class _Capture:
        def isOpened(self):
            return True

        def set(self, *_args):
            return True

    def _video_capture(target, backend):
        calls.append((target, backend))
        return _Capture()

    monkeypatch.setattr("multiwebcam.sources.device.cv2.VideoCapture", _video_capture)
    source = FrameSource(
        "/dev/video6",
        FrameSourceConfig(resolution=(640, 480), pixel_format="mjpeg"),
    )

    source._open_device()

    assert calls == [("/dev/video6", cv2.CAP_V4L2)]
