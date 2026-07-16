from pathlib import Path

from multiwebcam.profiles.settings import RecordingSettings
from multiwebcam.recording.gstreamer import build_jetson_writer_pipeline
from multiwebcam.sources.config import FrameSourceConfig
from multiwebcam.sources.gstreamer import build_jetson_capture_pipeline


def test_build_jetson_capture_pipeline_for_mjpeg():
    config = FrameSourceConfig(
        resolution=(1280, 720),
        fps=30,
        pixel_format="mjpeg",
        capture_backend="gstreamer",
    )

    pipeline = build_jetson_capture_pipeline("/dev/video0", config)

    assert "v4l2src device=/dev/video0" in pipeline
    assert "image/jpeg,width=1280,height=720,framerate=30/1" in pipeline
    assert "nvv4l2decoder mjpeg=1" in pipeline
    assert pipeline.endswith("appsink drop=true max-buffers=1 sync=false")


def test_build_jetson_capture_pipeline_for_vga_camera():
    config = FrameSourceConfig(
        resolution=(640, 480),
        fps=30,
        pixel_format="mjpeg",
        capture_backend="gstreamer",
    )

    pipeline = build_jetson_capture_pipeline("/dev/video2", config)

    assert "v4l2src device=/dev/video2" in pipeline
    assert "image/jpeg,width=640,height=480,framerate=30/1" in pipeline
    assert pipeline.endswith("appsink drop=true max-buffers=1 sync=false")


def test_build_jetson_writer_pipeline_uses_hw_encoder():
    settings = RecordingSettings(backend="gstreamer", fps=30)

    pipeline = build_jetson_writer_pipeline(Path("/tmp/out.mp4"), (640, 480), 30, settings)

    assert "appsrc !" in pipeline
    assert "nvv4l2h264enc" in pipeline
    assert "filesink location='/tmp/out.mp4'" in pipeline
