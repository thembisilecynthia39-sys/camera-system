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


def test_adapter_snapshot_restores_scene_after_failed_replacement(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)
    old_data = np.zeros((2, 14), dtype=np.float32)
    old_data[:, 0] = (1.0, 2.0)
    adapter.set_gaussians(
        old_data,
        bounds=(np.zeros(3, dtype=np.float32), np.ones(3, dtype=np.float32)),
    )
    adapter.set_display_settings(DisplaySettings(mode=DisplayMode.OVERLAY))
    adapter.set_appearance_settings(AppearanceSettings(exposure=0.5))
    snapshot = adapter.snapshot_scene()

    adapter.set_gaussians(
        np.ones((3, 14), dtype=np.float32),
        bounds=(np.ones(3, dtype=np.float32), np.full(3, 2.0, dtype=np.float32)),
    )
    adapter.restore_scene(snapshot)

    assert np.array_equal(adapter.item.gs_data, old_data)
    assert adapter.item.render_controller.mode == "overlay"
    assert adapter.appearance_settings.exposure == pytest.approx(0.5)
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


def test_adapter_preserves_requested_position_when_pose_rotation_is_inconsistent(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)
    pose = CameraPose(
        position=(1.0, 0.0, 0.0),
        target=(0.0, 0.0, 0.0),
        rotation_xyzw=(0.0, 0.0, 0.0, 1.0),
    )

    adapter.set_camera_pose(pose)
    restored = adapter.get_camera_pose()

    assert restored.position == pytest.approx(pose.position)
    assert restored.target == pytest.approx(pose.target)
    adapter.release()


def test_adapter_orbit_can_complete_full_turn(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)
    orbit = getattr(adapter, "orbit", None)
    assert callable(orbit)

    initial = adapter.get_camera_pose()
    orbit(2.0 * np.pi, 0.0)
    restored = adapter.get_camera_pose()

    assert restored.position == pytest.approx(initial.position, abs=1e-6)
    assert restored.target == pytest.approx(initial.target, abs=1e-6)
    adapter.release()


def test_adapter_end_interaction_restores_full_quality_after_scripted_orbit(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)

    adapter.orbit(delta_yaw=0.1)
    assert adapter.item.interactive_preview is True

    assert adapter.end_interaction() is True
    assert adapter.item.interactive_preview is False
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
