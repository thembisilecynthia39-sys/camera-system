"""Tests for the application-to-q3dviewer adapter contract."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from camera_system_app.domain.viewer import (
    AppearanceSettings,
    CameraMode,
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


def test_adapter_applies_roaming_mode_and_fly_speed_to_embedded_widget(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)

    adapter.set_camera_mode(CameraMode.FLY)
    adapter.set_fly_speed(2.5)

    assert adapter.widget.camera_mode == "fly"
    assert adapter.widget.fly_speed == pytest.approx(2.5)
    assert adapter.get_camera_state()["camera_mode"] == "fly"
    adapter.release()


def test_adapter_exposes_standard_axis_view_presets(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)

    adapter.set_view_preset("top")

    assert adapter.widget.euler == pytest.approx((-np.pi / 2.0, 0.0, 0.0))
    adapter.release()


def test_adapter_publishes_sphere_shader_availability(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)
    events = []
    adapter.sphere_availability_changed.connect(
        lambda available, error: events.append((available, error))
    )

    callback = adapter.item.render_controller._sphere_availability_callback
    callback(False, "shader unavailable")

    assert events == [(False, "shader unavailable")]
    adapter.release()


def test_adapter_applies_appearance_state_to_interactive_and_final_boundaries(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)
    settings = AppearanceSettings(exposure=1.0)

    adapter.set_appearance_settings(settings)

    assert adapter.appearance_settings == settings
    assert adapter.item.render_controller.appearance_settings == settings
    adapter.release()


def test_adapter_capture_frame_validates_sized_output_before_context_work(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)

    with pytest.raises(ValueError):
        adapter.capture_frame(width=0, height=720)
    adapter.release()
