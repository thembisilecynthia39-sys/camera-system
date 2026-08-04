"""CPU-only lifecycle tests for the viewer frame encoders."""

from __future__ import annotations

import numpy as np
import pytest

from camera_system_app.domain.viewer import OutputKind
from camera_system_app.infrastructure.viewer_encoder import (
    BoundedFrameSink,
    EncoderBackpressureError,
    EncoderConfig,
    EncoderConfigurationError,
    EncoderError,
    EncoderState,
    FrameEncoder,
    UnsupportedEncoderError,
)


def _frame(value=20):
    return np.full((2, 3, 4), value, dtype=np.uint8)


def test_bounded_sink_reports_backpressure_without_dropping_frames():
    sink = BoundedFrameSink(maxsize=1)
    sink.put("first", block=False)
    with pytest.raises(EncoderBackpressureError):
        sink.put("second", block=False)
    assert sink.get(timeout=0.1) == "first"
    sink.close()


def test_encoder_config_and_unknown_backend_fail_with_actionable_errors(tmp_path):
    with pytest.raises(EncoderConfigurationError):
        EncoderConfig(tmp_path / "frame.png", width=0, height=2)
    with pytest.raises(UnsupportedEncoderError):
        FrameEncoder(
            EncoderConfig(
                tmp_path / "frame.png",
                width=3,
                height=2,
                output_kind=OutputKind.PNG,
                backend="not-a-backend",
            )
        ).start()


def test_png_encoder_publishes_one_atomic_frame(tmp_path):
    output = tmp_path / "still.png"
    encoder = FrameEncoder(
        EncoderConfig(
            output,
            width=3,
            height=2,
            output_kind=OutputKind.PNG,
            backend="png",
        )
    )
    encoder.start()
    encoder.submit(_frame(), block=False)
    assert encoder.finish() == output

    from PIL import Image

    with Image.open(output) as image:
        assert image.size == (3, 2)
        assert image.mode == "RGB"
    assert encoder.state is EncoderState.FINISHED
    assert encoder.frames_written == 1


def test_png_sequence_keeps_frame_count_and_cleans_abort(tmp_path):
    output = tmp_path / "frames"
    encoder = FrameEncoder(
        EncoderConfig(
            output,
            width=3,
            height=2,
            output_kind=OutputKind.PNG_SEQUENCE,
            backend="png",
        )
    )
    encoder.start()
    encoder.submit(_frame(10))
    encoder.submit(_frame(30))
    encoder.finish()
    assert sorted(path.name for path in output.glob("*.png")) == [
        "frame_000000.png",
        "frame_000001.png",
    ]

    aborted_output = tmp_path / "aborted.png"
    aborted = FrameEncoder(
        EncoderConfig(
            aborted_output,
            width=3,
            height=2,
            output_kind=OutputKind.PNG,
            backend="png",
        )
    )
    aborted.start()
    aborted.submit(_frame())
    aborted.abort()
    assert aborted.state is EncoderState.ABORTED
    assert not aborted_output.exists()


def test_pyav_mp4_encoder_publishes_a_playable_real_video(tmp_path):
    av = pytest.importorskip("av")
    output = tmp_path / "tour.mp4"
    encoder = FrameEncoder(
        EncoderConfig(
            output,
            width=16,
            height=16,
            fps=2.0,
            output_kind=OutputKind.MP4,
            backend="pyav",
        )
    )
    encoder.start()
    encoder.submit(np.full((16, 16, 3), 10, dtype=np.uint8))
    encoder.submit(np.full((16, 16, 3), 80, dtype=np.uint8))
    assert encoder.finish() == output

    with av.open(str(output), mode="r") as container:
        stream = container.streams.video[0]
        decoded = list(container.decode(stream))

    assert output.stat().st_size > 0
    assert stream.width == 16
    assert stream.height == 16
    assert len(decoded) == 2
    assert float(stream.average_rate) == pytest.approx(2.0)
    assert encoder.state is EncoderState.FINISHED


def test_encoder_rejects_wrong_frame_size_and_does_not_publish(tmp_path):
    output = tmp_path / "bad.png"
    encoder = FrameEncoder(
        EncoderConfig(
            output,
            width=3,
            height=2,
            output_kind=OutputKind.PNG,
            backend="png",
        )
    )
    encoder.start()
    encoder.submit(np.zeros((4, 4, 3), dtype=np.uint8))
    with pytest.raises(EncoderError):
        encoder.finish()
    assert encoder.state is EncoderState.FAILED
    assert not output.exists()
