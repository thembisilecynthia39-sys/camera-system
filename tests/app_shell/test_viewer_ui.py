"""Offscreen behavior tests for the 3DGS studio toolbar and Inspector."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton

from camera_system_app.domain.viewer import DisplayMode, DisplaySettings
from camera_system_app.ui.pages import ResultViewerPage
from camera_system_app.ui.widgets.viewer_inspector import ViewerInspector
from camera_system_app.ui.widgets.viewer_toolbar import ViewerToolbar


def test_viewer_toolbar_exposes_core_roaming_and_presentation_actions(qapp):
    toolbar = ViewerToolbar()
    names = {button.text() for button in toolbar.findChildren(QToolButton)}

    assert {"打开", "重置", "适配", "播放", "停止", "演示", "导出"} <= names
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
