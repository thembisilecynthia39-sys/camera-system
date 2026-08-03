"""Small deterministic presentation-look pass for final readback frames."""

from __future__ import annotations

import numpy as np

from camera_system_app.domain.viewer import AppearanceSettings


class AppearanceProcessingError(ValueError):
    """The readback buffer or appearance settings are not processable."""


def apply_appearance(frame, settings: AppearanceSettings) -> np.ndarray:
    """Apply a bounded look without mutating the renderer readback buffer."""

    if not isinstance(settings, AppearanceSettings):
        raise AppearanceProcessingError("appearance settings must be an AppearanceSettings value")
    source = np.asarray(frame)
    if source.ndim != 3 or source.shape[2] not in (3, 4):
        raise AppearanceProcessingError("appearance input must be an RGB or RGBA image")
    if source.dtype != np.uint8:
        source = np.clip(source, 0.0, 255.0).astype(np.uint8)
    rgb = source[:, :, :3].astype(np.float32) / 255.0
    alpha = source[:, :, 3:4].copy() if source.shape[2] == 4 else None

    rgb *= float(2.0 ** max(-20.0, min(20.0, settings.exposure)))
    tone_mapping = settings.tone_mapping.lower().strip()
    if tone_mapping == "aces":
        rgb = (rgb * (2.51 * rgb + 0.03)) / (rgb * (2.43 * rgb + 0.59) + 0.14)
    elif tone_mapping == "reinhard":
        rgb = rgb / (1.0 + rgb)
    elif tone_mapping != "none":
        raise AppearanceProcessingError("unsupported tone mapping: {}".format(settings.tone_mapping))

    rgb = (rgb - 0.5) * float(settings.contrast) + 0.5
    luminance = (
        rgb[:, :, 0:1] * 0.2126
        + rgb[:, :, 1:2] * 0.7152
        + rgb[:, :, 2:3] * 0.0722
    )
    rgb = luminance + (rgb - luminance) * float(settings.saturation)

    if settings.vignette > 0.0:
        height, width = rgb.shape[:2]
        y = np.linspace(-1.0, 1.0, height, dtype=np.float32)[:, None]
        x = np.linspace(-1.0, 1.0, width, dtype=np.float32)[None, :]
        radius = np.sqrt(x * x + y * y) / np.sqrt(2.0)
        factor = 1.0 - float(settings.vignette) * np.clip(radius, 0.0, 1.0) ** 2
        rgb *= factor[:, :, None]

    if settings.sharpening > 0.0 and min(rgb.shape[:2]) >= 3:
        padded = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")
        blur = (
            padded[:-2, 1:-1]
            + padded[2:, 1:-1]
            + padded[1:-1, :-2]
            + padded[1:-1, 2:]
            + padded[:-2, :-2]
            + padded[:-2, 2:]
            + padded[2:, :-2]
            + padded[2:, 2:]
        ) / 8.0
        rgb += (rgb - blur) * float(settings.sharpening)

    rgb = np.clip(np.rint(rgb * 255.0), 0.0, 255.0).astype(np.uint8)
    if alpha is None:
        return rgb
    return np.concatenate((rgb, alpha), axis=2)


__all__ = ["AppearanceProcessingError", "apply_appearance"]
