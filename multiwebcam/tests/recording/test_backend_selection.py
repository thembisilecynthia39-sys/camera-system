from queue import Queue

from multiwebcam.profiles.settings import RecordingSettings
from multiwebcam.recording import recorder as recorder_module
from multiwebcam.recording.recorder import FrameRecorder


def test_missing_jetson_encoder_falls_back_to_pyav(monkeypatch, tmp_path):
    monkeypatch.setattr(
        recorder_module,
        "gstreamer_element_available",
        lambda _element: False,
    )

    recorder = FrameRecorder(
        recording_queues={"/dev/video0": Queue()},
        output_dir=tmp_path,
        cam_ids={"/dev/video0": 0},
        settings=RecordingSettings(
            backend="gstreamer",
            jetson_encoder="missing-hardware-encoder",
        ),
    )

    assert recorder.settings.backend == "pyav"
