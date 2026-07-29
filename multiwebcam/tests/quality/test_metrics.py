import numpy as np

from multiwebcam.quality.metrics import ObjectRegion, QualityLevel, evaluate_frame


def test_evaluate_frame_detects_empty_frame_as_bad():
    quality = evaluate_frame(np.zeros((0, 0, 3), dtype=np.uint8))

    assert quality.level == QualityLevel.BAD
    assert quality.score_percent == 0.0
    assert "empty frame" in quality.reasons


def test_evaluate_frame_detects_low_texture_dark_frame_as_bad():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)

    quality = evaluate_frame(frame)

    assert quality.level == QualityLevel.BAD
    assert "too dark" in quality.reasons
    assert "low texture" in quality.reasons


def test_evaluate_frame_accepts_textured_well_exposed_frame():
    rng = np.random.default_rng(42)
    frame = rng.integers(40, 215, size=(240, 320, 3), dtype=np.uint8)

    quality = evaluate_frame(frame)

    assert quality.level != QualityLevel.BAD
    assert quality.feature_count >= 200
    assert quality.score_percent > 60.0


def test_evaluate_frame_detects_center_subject_region():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[70:170, 100:220] = 255

    quality = evaluate_frame(frame)

    assert quality.object_region is not None
    assert quality.object_region.centeredness > 0.7
    assert quality.object_score > 0.4


def test_evaluate_frame_penalizes_off_center_subject():
    centered = np.zeros((240, 320, 3), dtype=np.uint8)
    centered[70:170, 100:220] = 255
    off_center = np.zeros((240, 320, 3), dtype=np.uint8)
    off_center[20:120, 10:130] = 255

    centered_quality = evaluate_frame(centered)
    off_center_quality = evaluate_frame(off_center)

    assert centered_quality.object_region is not None
    assert off_center_quality.object_region is not None
    assert off_center_quality.object_region.centeredness < centered_quality.object_region.centeredness
    assert off_center_quality.object_score < centered_quality.object_score


def test_evaluate_frame_uses_supplied_object_region():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    override = ObjectRegion(100, 80, 120, 100, 0.15, 0.95, 1.0, 0.9)

    quality = evaluate_frame(frame, object_region=override)

    assert quality.object_region == override
    assert quality.object_score > 0.0


def test_downsampled_quality_detection_returns_source_frame_coordinates():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[210:510, 440:840] = 255

    quality = evaluate_frame(frame)

    assert quality.object_region is not None
    assert quality.object_region.x > 400
    assert quality.object_region.width > 350
