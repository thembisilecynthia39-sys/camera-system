"""Numerical helpers shared by Gaussian splat and sphere render passes."""

from __future__ import annotations

import math

import numpy as np


def circumscribed_sphere_radius(scales, sigma_multiplier=3.0):
    """Return the radius of the sphere containing a Gaussian ellipsoid.

    The loader supplies effective one-sigma axis lengths.  The sphere therefore
    uses the largest axis and a configurable sigma multiplier without changing
    the source scale array.
    """

    try:
        multiplier = float(sigma_multiplier)
    except (TypeError, ValueError):
        raise ValueError("sigma_multiplier must be a number")
    if not math.isfinite(multiplier) or multiplier <= 0.0:
        raise ValueError("sigma_multiplier must be finite and positive")
    try:
        values = np.asarray(scales, dtype=np.float32)
    except (TypeError, ValueError):
        raise ValueError("scales must be numeric")
    if values.ndim == 0 or values.shape[-1] != 3:
        raise ValueError("scales must have a final dimension of three")
    if not np.isfinite(values).all():
        raise ValueError("scales must be finite")
    if np.any(values < 0.0):
        raise ValueError("scales cannot be negative")
    radii = np.max(values, axis=-1) * np.float32(multiplier)
    return float(radii) if values.ndim == 1 else radii.astype(np.float32, copy=False)


def deterministic_preview_indices(count, max_gaussians):
    """Select evenly spaced source rows while retaining both endpoints."""

    try:
        count = int(count)
        max_gaussians = int(max_gaussians)
    except (TypeError, ValueError):
        raise ValueError("preview counts must be integers")
    if count < 0:
        raise ValueError("count cannot be negative")
    if count == 0:
        return np.empty(0, dtype=np.uint32)
    limit = max(1, max_gaussians)
    preview_count = min(count, limit)
    if preview_count == count:
        return np.arange(count, dtype=np.uint32)
    return np.linspace(0, count - 1, preview_count, dtype=np.uint32)


__all__ = ["circumscribed_sphere_radius", "deterministic_preview_indices"]
