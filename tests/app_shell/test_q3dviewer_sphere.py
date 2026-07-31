"""CPU-side contracts for shared Gaussian data and circumscribed spheres."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from camera_system_app.infrastructure.adapters.q3dviewer_adapter import prepare_q3dviewer


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_circumscribed_sphere_radius_uses_three_sigma_maximum_axis():
    from q3dviewer.utils.gaussian_sphere import circumscribed_sphere_radius

    scales = np.array([[1.0, 2.0, 0.5], [0.25, 0.5, 0.75]], dtype=np.float32)

    radius = circumscribed_sphere_radius(scales)

    assert radius == pytest.approx(np.array([6.0, 2.25], dtype=np.float32))


def test_circumscribed_sphere_radius_does_not_mutate_source_scales():
    from q3dviewer.utils.gaussian_sphere import circumscribed_sphere_radius

    scales = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    original = scales.copy()

    assert circumscribed_sphere_radius(scales, sigma_multiplier=2.0) == pytest.approx(6.0)
    assert np.array_equal(scales, original)


def test_circumscribed_sphere_radius_rejects_invalid_scales_or_multiplier():
    from q3dviewer.utils.gaussian_sphere import circumscribed_sphere_radius

    with pytest.raises(ValueError):
        circumscribed_sphere_radius(np.ones((2, 2), dtype=np.float32))
    with pytest.raises(ValueError):
        circumscribed_sphere_radius(np.array([1.0, -2.0, 3.0]), sigma_multiplier=3.0)
    with pytest.raises(ValueError):
        circumscribed_sphere_radius(np.ones(3), sigma_multiplier=0.0)


def test_preview_indices_are_deterministic_and_include_first_and_last_rows():
    from q3dviewer.utils.gaussian_sphere import deterministic_preview_indices

    indices = deterministic_preview_indices(10, 4)

    assert indices.dtype == np.uint32
    assert np.array_equal(indices, np.array([0, 3, 6, 9], dtype=np.uint32))
    assert np.array_equal(deterministic_preview_indices(3, 20), np.array([0, 1, 2], dtype=np.uint32))


def test_gaussian_gpu_data_keeps_one_contiguous_source_buffer_and_preview_view():
    prepare_q3dviewer(PROJECT_ROOT)
    from q3dviewer.custom_items.gaussian_gpu_data import GaussianGpuData

    raw = np.arange(5 * 14, dtype=np.float32).reshape(5, 14)
    owner = GaussianGpuData()

    owner.set_data(raw, validated=True)
    preview = owner.build_preview_indices(max_gaussians=3)

    assert owner.count == 5
    assert owner.row_width == 14
    assert owner.sh_dim == 3
    assert owner.gs_data.flags["C_CONTIGUOUS"]
    assert np.shares_memory(owner.gs_data, raw)
    assert np.array_equal(preview, np.array([0, 2, 4], dtype=np.uint32))


def test_gaussian_item_uses_the_shared_gpu_data_owner_for_existing_set_data_api():
    prepare_q3dviewer(PROJECT_ROOT)
    from q3dviewer.custom_items.gaussian_item import GaussianItem

    item = GaussianItem(sort_enabled=False, sort_backend="opengl")
    raw = np.zeros((2, 14), dtype=np.float32)

    item.set_data(gs_data=raw, validated=True)

    assert item.gpu_data.count == 2
    assert item.gs_data is item.gpu_data.gs_data
