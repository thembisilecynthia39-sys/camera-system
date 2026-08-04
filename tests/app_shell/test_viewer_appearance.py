"""Bounded deterministic presentation-look processing."""

from __future__ import annotations

import numpy as np

from camera_system_app.application.viewer_appearance import apply_appearance
from camera_system_app.domain.viewer import AppearanceSettings


def test_appearance_preserves_shape_alpha_and_input_buffer():
    frame = np.zeros((3, 4, 4), dtype=np.uint8)
    frame[:, :, :3] = 80
    frame[:, :, 3] = 123
    original = frame.copy()

    result = apply_appearance(frame, AppearanceSettings(exposure=1.0))

    assert result.shape == frame.shape
    assert result.dtype == np.uint8
    assert np.array_equal(result[:, :, 3], frame[:, :, 3])
    assert np.array_equal(frame, original)
    assert result[:, :, :3].mean() > frame[:, :, :3].mean()


def test_appearance_applies_vignette_and_sharpening_without_overflow():
    frame = np.full((7, 7, 3), 180, dtype=np.uint8)
    frame[3, 3] = (255, 255, 255)
    result = apply_appearance(
        frame,
        AppearanceSettings(
            tone_mapping="none",
            vignette=1.0,
            sharpening=1.0,
            contrast=1.2,
            saturation=1.3,
        ),
    )

    assert result.dtype == np.uint8
    assert result.min() >= 0
    assert result.max() <= 255
    assert result[0, 0].mean() < result[3, 3].mean()
