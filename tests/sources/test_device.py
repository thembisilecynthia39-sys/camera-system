import pytest

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
