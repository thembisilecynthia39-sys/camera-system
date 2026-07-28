from __future__ import annotations

import numpy as np

from multiwebcam.quality.guidance import CaptureGuidanceTracker
from multiwebcam.quality.metrics import ObjectRegion, evaluate_capture_set
from multiwebcam.sources.frame_packet import FramePacket


def make_packet(path: str, seed: int, frame_time: float, low_texture: bool = False) -> FramePacket:
    if low_texture:
        frame = np.full((180, 240, 3), 20, dtype=np.uint8)
    else:
        rng = np.random.default_rng(seed)
        frame = rng.integers(40, 215, size=(180, 240, 3), dtype=np.uint8)
    return FramePacket(
        device_path=path,
        device_id=seed,
        frame_index=seed,
        frame_time=frame_time,
        timestamp_source="wall_clock",
        frame=frame,
        fps=30.0,
    )


def make_packets(seed_offset: int = 0, low_texture: bool = False) -> dict[str, FramePacket]:
    return {
        "/dev/video0": make_packet("/dev/video0", seed_offset + 1, 1.0, low_texture=low_texture),
        "/dev/video2": make_packet("/dev/video2", seed_offset + 2, 1.02, low_texture=low_texture),
    }


def test_tracker_starts_with_first_missing_angle():
    tracker = CaptureGuidanceTracker()
    packets = make_packets()
    quality = evaluate_capture_set(packets)

    guidance = tracker.evaluate(packets, quality, 0)

    assert guidance.next_angle_deg == 0
    assert guidance.progress_percent == 0.0
    assert guidance.completed_angles == ()


def test_tracker_progress_increases_after_registering_captures():
    tracker = CaptureGuidanceTracker()

    packets_0 = make_packets(10)
    quality_0 = evaluate_capture_set(packets_0)
    after_first = tracker.register_capture(0, 1, packets_0, quality_0)

    packets_45 = make_packets(20)
    quality_45 = evaluate_capture_set(packets_45)
    after_second = tracker.register_capture(45, 2, packets_45, quality_45)

    assert after_first.progress_percent > 0.0
    assert after_second.progress_percent > after_first.progress_percent
    assert after_second.next_angle_deg == 90
    assert after_second.completed_angles == (0, 45)


def test_validation_blocks_low_quality_capture():
    tracker = CaptureGuidanceTracker()
    packets = make_packets(low_texture=True)
    quality = evaluate_capture_set(packets)

    validation = tracker.validate_capture(0, packets, quality)

    assert not validation.accepted
    assert validation.guidance.readiness_label == "WAIT"


def test_validation_blocks_duplicate_when_existing_angle_is_better():
    tracker = CaptureGuidanceTracker()
    packets = make_packets(30)
    quality = evaluate_capture_set(packets)
    tracker.register_capture(0, 1, packets, quality)

    validation = tracker.validate_capture(0, packets, quality)

    assert not validation.accepted
    assert "already covered" in validation.message


def test_validation_blocks_capture_when_detector_does_not_find_target():
    tracker = CaptureGuidanceTracker()
    packets = make_packets(40)
    quality = evaluate_capture_set(packets, object_regions={path: None for path in packets})

    validation = tracker.validate_capture(0, packets, quality)

    assert not validation.accepted
    assert "target not detected" in validation.message
    assert not validation.guidance.ready_to_capture


def test_live_guidance_can_skip_expensive_descriptor_matching(monkeypatch):
    tracker = CaptureGuidanceTracker()
    packets = make_packets(45)
    quality = evaluate_capture_set(packets)
    tracker.register_capture(0, 1, packets, quality)

    def unexpected_match(*_args):
        raise AssertionError("live guidance must not run ORB matching")

    monkeypatch.setattr(
        "multiwebcam.quality.guidance._descriptor_overlap",
        unexpected_match,
    )

    guidance = tracker.evaluate(
        make_packets(55),
        quality,
        45,
        check_matchability=False,
    )

    assert guidance.next_angle_deg == 45


def test_tracker_marks_loop_complete_after_all_required_angles():
    tracker = CaptureGuidanceTracker()
    region = ObjectRegion(
        x=40,
        y=30,
        width=150,
        height=110,
        area_ratio=0.38,
        centeredness=0.9,
        fill_ratio=0.8,
        confidence=0.85,
    )

    guidance = None
    for index, angle in enumerate(tracker.required_angles):
        packets = make_packets(50 + index * 10)
        quality = evaluate_capture_set(packets, object_regions={path: region for path in packets})
        guidance = tracker.register_capture(angle, index + 1, packets, quality)

    assert guidance is not None
    assert guidance.loop_complete
    assert guidance.next_angle_deg is None
    assert guidance.completed_angles == tracker.required_angles
