"""Behavioral tests for the pure 3DGS viewer state models."""

from __future__ import annotations

import pytest

from camera_system_app.domain.viewer import (
    AppearanceSettings,
    CameraBookmark,
    CameraMode,
    CameraPose,
    CameraShot,
    CameraTimeline,
    DisplayMode,
    DisplaySettings,
    OutputKind,
    QualityPreset,
    RenderSettings,
    SphereStyle,
    ViewerProject,
    ViewerValidationError,
    validate_render_settings,
)


def test_display_settings_default_to_a_readable_sphere_overlay_contract():
    settings = DisplaySettings()

    assert settings.mode is DisplayMode.STANDARD
    assert settings.sphere_style is SphereStyle.WIREFRAME
    assert settings.sphere_sigma_multiplier == pytest.approx(3.0)
    assert settings.sphere_opacity == pytest.approx(0.5)
    assert settings.sphere_all_instances is False


def test_display_settings_can_request_all_spheres_during_interaction():
    settings = DisplaySettings(sphere_all_instances=True)

    assert DisplaySettings.from_dict(settings.to_dict()) == settings


def test_display_settings_round_trip_preserves_scene_inspection_overlays():
    settings = DisplaySettings(
        show_grid=True,
        show_axis=True,
        show_bounds=True,
        show_center=True,
        show_camera_info=True,
    )

    assert DisplaySettings.from_dict(settings.to_dict()) == settings


def test_camera_timeline_rejects_duplicate_shot_ids():
    pose = CameraPose()
    shot = CameraShot("duplicate", "镜头", pose, pose)

    with pytest.raises(ViewerValidationError, match="shot_id"):
        CameraTimeline(shots=(shot, shot))


def test_appearance_rejects_unknown_tone_mapping():
    with pytest.raises(ViewerValidationError, match="tone mapping"):
        AppearanceSettings(tone_mapping="filmic-unknown")


def test_appearance_round_trip_preserves_spherical_harmonic_degree():
    settings = AppearanceSettings(sh_degree=2)

    assert AppearanceSettings.from_dict(settings.to_dict()) == settings


def test_appearance_rejects_spherical_harmonic_degree_outside_supported_range():
    with pytest.raises(ViewerValidationError, match="SH degree"):
        AppearanceSettings(sh_degree=4)


def test_enum_values_are_stable_for_project_serialization():
    settings = DisplaySettings(
        mode=DisplayMode.OVERLAY,
        quality=QualityPreset.FINAL,
        sphere_style=SphereStyle.SOLID,
    )

    encoded = settings.to_dict()

    assert encoded["mode"] == "overlay"
    assert encoded["quality"] == "final"
    assert encoded["sphere_style"] == "solid"


def test_camera_pose_normalizes_quaternion_and_round_trips_values():
    pose = CameraPose(
        position=(1, 2, 3),
        target=(4, 5, 6),
        rotation_xyzw=(0, 0, 0, 2),
        fov_degrees=62,
    )

    assert pose.position == (1.0, 2.0, 3.0)
    assert pose.rotation_xyzw == pytest.approx((0.0, 0.0, 0.0, 1.0))
    assert CameraPose.from_dict(pose.to_dict()) == pose


def test_viewer_project_round_trips_nested_state_without_loss():
    pose = CameraPose(
        position=(1.0, 2.0, 4.0),
        target=(0.0, 0.0, 1.0),
        rotation_xyzw=(0.1, 0.2, 0.3, 0.9),
        fov_degrees=52.0,
    )
    project = ViewerProject(
        source_path="/tmp/scene.ply",
        source_size=1234,
        source_sha256="a" * 64,
        camera=pose,
        timeline=CameraTimeline(
            fps=24.0,
            shots=(
                CameraShot(
                    shot_id="intro",
                    name="Intro",
                    start=pose,
                    end=CameraPose(target=(0.0, 0.0, 0.0)),
                    duration_seconds=2.5,
                    hold_start_seconds=0.25,
                ),
            ),
        ),
        display=DisplaySettings(mode=DisplayMode.SPHERE_SOLID),
        appearance=AppearanceSettings(exposure=0.75, saturation=1.1),
        render=RenderSettings(
            width=1280,
            height=720,
            fps=24.0,
            output_kind=OutputKind.PNG_SEQUENCE,
            transparent_background=True,
        ),
    )

    restored = ViewerProject.from_dict(project.to_dict())

    assert restored == project


def test_viewer_project_round_trip_preserves_camera_bookmarks_and_mode():
    pose = CameraPose(
        position=(1.0, 2.0, 4.0),
        target=(0.0, 0.0, 1.0),
        fov_degrees=58.0,
    )
    project = ViewerProject(
        camera=pose,
        camera_mode=CameraMode.FLY,
        fly_speed=2.5,
        bookmarks=(CameraBookmark("entrance", "入口", pose),),
    )

    restored = ViewerProject.from_dict(project.to_dict())

    assert restored == project
    assert restored.camera_mode is CameraMode.FLY
    assert restored.fly_speed == pytest.approx(2.5)
    assert restored.bookmarks[0].name == "入口"


@pytest.mark.parametrize(
    "changes",
    [
        {"width": 0},
        {"height": -1},
        {"fps": 0},
        {"fps": 1001},
    ],
)
def test_render_settings_reject_invalid_dimensions_or_fps(changes):
    settings = RenderSettings(**changes)

    with pytest.raises(ViewerValidationError):
        validate_render_settings(settings)


def test_transparent_mp4_is_rejected_before_rendering():
    settings = RenderSettings(
        output_kind=OutputKind.MP4,
        transparent_background=True,
    )

    with pytest.raises(ViewerValidationError, match="PNG"):
        validate_render_settings(settings)
