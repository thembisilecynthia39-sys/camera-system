"""Tests for the application-to-q3dviewer adapter contract."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from camera_system_app.domain.viewer import (
    AppearanceSettings,
    CameraPose,
    DisplayMode,
    DisplaySettings,
)
from camera_system_app.infrastructure.adapters.q3dviewer_adapter import Q3DViewerAdapter


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_adapter_applies_display_settings_without_replacing_gaussian_data(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)
    raw = np.zeros((2, 14), dtype=np.float32)
    adapter.item.set_data(gs_data=raw, validated=True)
    source_buffer = adapter.item.gpu_data.gs_data

    adapter.set_display_settings(
        DisplaySettings(mode=DisplayMode.SPHERE_WIREFRAME)
    )

    assert adapter.item.render_controller.mode == "sphere_wireframe"
    assert adapter.item.gpu_data.gs_data is source_buffer
    adapter.release()


def test_adapter_round_trips_domain_camera_pose_through_native_orbit_state(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)
    pose = CameraPose(position=(0.0, 0.0, 5.0), target=(0.0, 0.0, 0.0))

    adapter.set_camera_pose(pose)
    restored = adapter.get_camera_pose()

    assert restored.position == pytest.approx(pose.position)
    assert restored.target == pytest.approx(pose.target)
    assert restored.rotation_xyzw == pytest.approx(pose.rotation_xyzw)
    adapter.release()


def test_adapter_keeps_appearance_state_at_the_boundary_until_postprocess_exists(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)
    settings = AppearanceSettings(exposure=1.0)

    adapter.set_appearance_settings(settings)

    assert adapter.appearance_settings == settings
    adapter.release()


def test_adapter_capture_frame_validates_sized_output_before_context_work(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)

    with pytest.raises(ValueError):
        adapter.capture_frame(width=0, height=720)
    adapter.release()
