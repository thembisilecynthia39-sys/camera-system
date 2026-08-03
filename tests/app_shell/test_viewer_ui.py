"""Offscreen behavior tests for the 3DGS studio toolbar and Inspector."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QToolButton, QWidget

from camera_system_app.domain.viewer import (
    CameraBookmark,
    CameraMode,
    CameraPose,
    CameraShot,
    CameraTimeline,
    DisplayMode,
    DisplaySettings,
)
from camera_system_app.ui.pages import ResultViewerPage
from camera_system_app.ui.widgets.viewer_inspector import ViewerInspector
from camera_system_app.ui.widgets.viewer_toolbar import ViewerToolbar
from camera_system_app.ui.widgets.viewer_timeline import ViewerTimelineWidget


def test_viewer_toolbar_exposes_core_roaming_and_presentation_actions(qapp):
    toolbar = ViewerToolbar()
    names = {button.text() for button in toolbar.findChildren(QToolButton)}

    assert {"打开", "重置", "适配", "保存", "另存", "播放", "停止", "演示", "导出"} <= names
    assert toolbar.display_mode_combo.findData(DisplayMode.STANDARD.value) >= 0
    assert toolbar.display_mode_combo.findData(DisplayMode.SPHERE_WIREFRAME.value) >= 0
    assert toolbar.display_mode_combo.findData(DisplayMode.OVERLAY.value) >= 0
    assert toolbar.quality_combo.count() >= 3


def test_viewer_toolbar_emits_mode_and_playback_signals(qapp):
    toolbar = ViewerToolbar()
    modes = []
    playback = []
    toolbar.display_mode_changed.connect(modes.append)
    toolbar.play_requested.connect(lambda: playback.append("play"))

    toolbar.display_mode_combo.setCurrentIndex(
        toolbar.display_mode_combo.findData(DisplayMode.SPHERE_SOLID.value)
    )
    toolbar.play_button.click()

    assert modes == [DisplayMode.SPHERE_SOLID.value]
    assert playback == ["play"]


def test_viewer_toolbar_syncing_playback_state_does_not_emit_commands(qapp):
    toolbar = ViewerToolbar()
    commands = []
    toolbar.play_requested.connect(lambda: commands.append("play"))
    toolbar.pause_requested.connect(lambda: commands.append("pause"))

    toolbar.set_playing(True)
    toolbar.set_playing(False)

    assert commands == []


def test_sphere_controls_disable_when_renderer_reports_shader_unavailable(qapp):
    toolbar = ViewerToolbar()
    inspector = ViewerInspector()

    toolbar.set_sphere_modes_available(False, "shader unavailable")
    inspector.set_sphere_modes_available(False, "shader unavailable")

    for combo in (toolbar.display_mode_combo, inspector.display_mode_combo):
        for value in (DisplayMode.SPHERE_WIREFRAME.value, DisplayMode.SPHERE_SOLID.value, DisplayMode.OVERLAY.value):
            index = combo.findData(value)
            assert combo.model().item(index).isEnabled() is False
        assert combo.currentData() == DisplayMode.STANDARD.value
    assert inspector.sphere_sigma_multiplier.isEnabled() is False
    assert inspector.sphere_opacity.isEnabled() is False
    assert inspector.sphere_line_width.isEnabled() is False


def test_viewer_inspector_groups_viewer_controls_into_collapsible_sections(qapp):
    inspector = ViewerInspector()
    section_names = {section.title() for section in inspector.sections}

    assert {"视图", "相机", "外观", "渲染"} <= section_names
    assert inspector.sections[0].is_expanded
    assert all(section.is_expanded for section in inspector.sections[1:]) is False
    assert inspector.sphere_sigma_multiplier.value() == 3.0
    assert inspector.sphere_opacity.value() == 0.5


def test_viewer_inspector_emits_display_settings_with_sphere_defaults(qapp):
    inspector = ViewerInspector()
    emitted = []
    inspector.display_settings_changed.connect(emitted.append)

    inspector.display_mode_combo.setCurrentIndex(
        inspector.display_mode_combo.findData(DisplayMode.SPHERE_WIREFRAME.value)
    )
    inspector.sphere_sigma_multiplier.setValue(4.0)

    assert emitted
    assert isinstance(emitted[-1], DisplaySettings)
    assert emitted[-1].mode is DisplayMode.SPHERE_WIREFRAME
    assert emitted[-1].sphere_sigma_multiplier == 4.0


def test_viewer_inspector_can_request_all_spheres_during_interaction(qapp):
    inspector = ViewerInspector()
    emitted = []
    inspector.display_settings_changed.connect(emitted.append)

    inspector.sphere_all_instances.setChecked(True)

    assert emitted
    assert emitted[-1].sphere_all_instances is True


def test_viewer_inspector_exposes_tone_mapping_choices(qapp):
    inspector = ViewerInspector()
    emitted = []
    inspector.appearance_settings_changed.connect(emitted.append)

    inspector.tone_mapping_combo.setCurrentIndex(
        inspector.tone_mapping_combo.findData("reinhard")
    )

    assert emitted
    assert emitted[-1].tone_mapping == "reinhard"


def test_viewer_inspector_emits_editable_background_color(qapp):
    inspector = ViewerInspector()
    emitted = []
    inspector.display_settings_changed.connect(emitted.append)

    inspector.background_color_edit.setText("#336699")
    inspector.background_color_edit.editingFinished.emit()

    assert emitted
    assert emitted[-1].background_color == (0.2, 0.4, 0.6)


def test_viewer_inspector_disables_transparency_for_mp4_output(qapp):
    inspector = ViewerInspector()

    inspector.output_kind.setCurrentIndex(
        inspector.output_kind.findData("mp4")
    )
    assert inspector.transparent_background.isEnabled() is False
    inspector.output_kind.setCurrentIndex(
        inspector.output_kind.findData("png")
    )
    assert inspector.transparent_background.isEnabled() is True


def test_viewer_inspector_exposes_fly_navigation_and_camera_bookmarks(qapp):
    inspector = ViewerInspector()
    modes = []
    speeds = []
    added = []
    loaded = []
    deleted = []
    inspector.camera_mode_changed.connect(modes.append)
    inspector.fly_speed_changed.connect(speeds.append)
    inspector.bookmark_add_requested.connect(added.append)
    inspector.bookmark_load_requested.connect(loaded.append)
    inspector.bookmark_delete_requested.connect(deleted.append)

    inspector.camera_mode_combo.setCurrentIndex(
        inspector.camera_mode_combo.findData(CameraMode.FLY.value)
    )
    inspector.fly_speed.setValue(2.5)
    inspector.bookmark_name_edit.setText("入口")
    inspector.bookmark_add_button.click()

    pose = CameraPose(position=(1.0, 2.0, 4.0))
    inspector.set_bookmarks((CameraBookmark("entrance", "入口", pose),))
    inspector.bookmark_combo.setCurrentIndex(0)
    inspector.bookmark_load_button.click()
    inspector.bookmark_delete_button.click()

    assert modes == [CameraMode.FLY.value]
    assert speeds[-1] == 2.5
    assert added == ["入口"]
    assert loaded == ["entrance"]
    assert deleted == ["entrance"]


def test_viewer_inspector_exposes_editable_camera_position_and_target(qapp):
    inspector = ViewerInspector()
    emitted = []
    inspector.camera_pose_changed.connect(emitted.append)
    pose = CameraPose(
        position=(1.0, 2.0, 3.0),
        target=(0.5, 0.25, -1.0),
        fov_degrees=57.0,
    )

    inspector.set_camera_pose(pose)
    inspector.position_x.setValue(4.0)

    assert inspector.position_y.value() == 2.0
    assert inspector.target_z.value() == -1.0
    assert emitted[-1].position == (4.0, 2.0, 3.0)
    assert emitted[-1].target == (0.5, 0.25, -1.0)
    assert emitted[-1].fov_degrees == 57.0


def test_result_page_contains_studio_shell_and_fits_minimum_window(qapp, tmp_path):
    page = ResultViewerPage(str(tmp_path / "results"), str(tmp_path / "viewer"))
    page.resize(776, 656)
    page.show()
    qapp.processEvents()

    assert page._toolbar.isEnabled() is False
    assert page._inspector.isVisible() is False
    assert page._studio_splitter.minimumSize().width() >= 0
    assert page._toolbar.minimumSizeHint().height() >= 40
    page.hide()


def test_result_page_toolbar_does_not_force_a_wider_than_minimum_window(qapp, tmp_path):
    page = ResultViewerPage(str(tmp_path / "results"), str(tmp_path / "viewer"))
    page.resize(720, 600)
    page.show()
    qapp.processEvents()

    assert page.minimumSizeHint().width() <= 720
    page.hide()


def test_loaded_result_hides_duplicate_source_card_to_keep_viewport_tall(qapp, tmp_path):
    page = ResultViewerPage(str(tmp_path / "results"), str(tmp_path / "viewer"))
    page.resize(720, 600)
    page.show()
    page.set_viewer_widget(QLabel(), "scene.ply", 1)
    qapp.processEvents()

    assert page._source_card.isVisible() is False
    assert page.minimumSizeHint().height() <= 680
    page.hide()


def test_narrow_viewer_switches_between_timeline_and_inspector_without_squeezing_gl(
    qapp, tmp_path
):
    page = ResultViewerPage(str(tmp_path / "results"), str(tmp_path / "viewer"))
    page.resize(720, 600)
    page.show()
    viewport = QWidget()
    viewport.setMinimumSize(480, 320)
    page.set_viewer_widget(viewport, "scene.ply", 1)
    qapp.processEvents()

    assert page._timeline.isVisible()
    assert not page._inspector.isVisible()
    assert page.minimumSizeHint().width() <= 720

    page._toolbar.inspector_button.click()
    assert page._inspector.isVisible()
    assert not page._timeline.isVisible()
    page._toolbar.timeline_button.click()
    assert page._timeline.isVisible()
    assert not page._inspector.isVisible()
    page.hide()


def test_sphere_fallback_banner_survives_viewer_widget_activation(qapp, tmp_path):
    page = ResultViewerPage(str(tmp_path / "results"), str(tmp_path / "viewer"))
    page.set_sphere_modes_available(False, "shader unavailable")
    page.set_viewer_widget(QLabel(), "scene.ply", 1)

    assert "外接球显示不可用" in page._banner._text.text()
    page.hide()


def test_result_page_exposes_model_backed_camera_director_timeline(qapp, tmp_path):
    page = ResultViewerPage(str(tmp_path / "results"), str(tmp_path / "viewer"))
    assert isinstance(page._timeline, ViewerTimelineWidget)
    timeline = CameraTimeline(
        shots=(
            CameraShot(
                "shot-1",
                "走廊",
                CameraPose(position=(0.0, 0.0, 5.0)),
                CameraPose(position=(1.0, 0.0, 5.0)),
            ),
        ),
        fps=24.0,
    )
    page.set_timeline(timeline)
    assert page._timeline.timeline == timeline
    assert page._timeline.frame_slider.maximum() == 72
    page.set_current_frame(12)
    assert page._timeline.frame_slider.value() == 12
    page.hide()


def test_result_page_marks_unsaved_viewer_project_changes_on_save_action(qapp, tmp_path):
    page = ResultViewerPage(str(tmp_path / "results"), str(tmp_path / "viewer"))
    assert page._toolbar.save_button.isEnabled() is False
    page.set_viewer_widget(QLabel(), "scene.ply", 1)

    page.set_project_dirty(True)

    assert page._toolbar.save_button.isEnabled()
    assert page._toolbar.save_button.text() == "保存*"
    page.set_project_dirty(False)
    assert page._toolbar.save_button.text() == "保存"
    page.hide()
