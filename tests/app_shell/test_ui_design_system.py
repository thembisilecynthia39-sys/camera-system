"""Behaviour checks for the workstation UI design system."""

from pathlib import Path
import re

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QPalette, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from camera_system_app.bootstrap import build_context
from camera_system_app.domain import (
    DiagnosticCheck,
    DiagnosticReport,
    DiagnosticStatus,
    ReconstructionJob,
    ReconstructionState,
)
from camera_system_app.ui.design_tokens import SEMANTIC_DARK, SEMANTIC_LIGHT
from camera_system_app.ui.main_window import MainWindow
from camera_system_app.ui.pages import (
    HistoryPage,
    ResultViewerPage,
    SettingsPage,
    TransferReconstructionPage,
)
from camera_system_app.ui.pages.diagnostics_log import DiagnosticsLogPage
from camera_system_app.ui.theme import application_stylesheet
from camera_system_app.ui.widgets import (
    EmptyState,
    MetricCard,
    PageHeader,
    StatusBanner,
    WorkflowStage,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _relative_luminance(hex_color):
    channels = [
        int(hex_color[index : index + 2], 16) / 255.0
        for index in (1, 3, 5)
    ]
    linear = [
        value / 12.92
        if value <= 0.04045
        else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first, second):
    light, dark = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (light + 0.05) / (dark + 0.05)


def _wheel_up_event():
    return QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.NoScrollPhase,
        False,
    )


def test_semantic_text_pairs_meet_wcag_contrast():
    pairs = (
        (SEMANTIC_LIGHT["text"], SEMANTIC_LIGHT["background"]),
        (SEMANTIC_LIGHT["text_muted"], SEMANTIC_LIGHT["surface"]),
        (SEMANTIC_DARK["text"], SEMANTIC_DARK["background"]),
        (SEMANTIC_DARK["text_muted"], SEMANTIC_DARK["background"]),
    )

    for foreground, background in pairs:
        assert _contrast(foreground, background) >= 4.5


def test_stylesheet_resolves_tokens_and_styles_model_views():
    stylesheet = application_stylesheet()

    assert re.search(r"\{[a-z][a-z0-9_]*\}", stylesheet) is None
    assert "QTableView" in stylesheet
    assert SEMANTIC_LIGHT["interactive"] in stylesheet
    assert SEMANTIC_DARK["background"] in stylesheet


def test_status_banner_exposes_semantic_symbol_and_accessible_text(qapp):
    banner = StatusBanner("网络不可用", "danger")

    assert banner.property("status") == "danger"
    assert banner.symbol_text() == "✕"
    assert "网络不可用" in banner.accessibleName()

    banner.set_status("连接正常", "success")

    assert banner.symbol_text() == "✓"
    assert "连接正常" in banner.accessibleName()


def test_status_banner_child_text_uses_light_semantic_color(qapp):
    previous_stylesheet = qapp.styleSheet()
    try:
        qapp.setStyleSheet(application_stylesheet())
        banner = StatusBanner("网络较慢", "warning")
        banner.show()
        qapp.processEvents()

        actual = banner._text.palette().color(QPalette.WindowText).name().upper()

        assert actual == SEMANTIC_LIGHT["warning"].upper()
    finally:
        banner.close()
        qapp.setStyleSheet(previous_stylesheet)


def test_status_banner_child_text_uses_dark_semantic_color(qapp):
    previous_stylesheet = qapp.styleSheet()
    try:
        qapp.setStyleSheet(application_stylesheet())
        surface = QWidget()
        surface.setObjectName("resultPageSurface")
        layout = QVBoxLayout(surface)
        banner = StatusBanner("网络较慢", "warning")
        layout.addWidget(banner)
        surface.show()
        qapp.processEvents()

        actual = banner._text.palette().color(QPalette.WindowText).name().upper()

        assert actual == SEMANTIC_DARK["warning"].upper()
    finally:
        surface.close()
        qapp.setStyleSheet(previous_stylesheet)


def test_empty_state_action_is_optional_and_emits(qapp):
    state = EmptyState(
        "○",
        "等待摄像头画面",
        "请检查 USB 连接。",
        "打开诊断",
    )
    emitted = []
    state.action_requested.connect(lambda: emitted.append(True))

    state.action_button.click()

    assert emitted == [True]
    assert state.title_text() == "等待摄像头画面"
    assert not state.action_button.isHidden()

    passive = EmptyState("◇", "暂无任务", "完成采集后会显示。")
    assert passive.action_button.isHidden()


def test_metric_card_and_workflow_stage_update_observable_state(qapp):
    metric = MetricCard("通过", "0", "success")
    metric.set_value(7)

    stage = WorkflowStage("01", "上传")
    stage.set_progress(42, "正在上传")
    stage.set_state("active")

    assert metric.value_text() == "7"
    assert metric.property("status") == "success"
    assert stage.progress.value() == 42
    assert stage.property("state") == "active"
    assert "正在上传" in stage.accessibleName()


def test_page_header_exposes_workflow_eyebrow(qapp):
    header = PageHeader("传输与重建", "后台执行", "工作流 02")

    assert header.eyebrow_text() == "工作流 02"


def test_numbered_navigation_preserves_page_indexes(
    tmp_path, monkeypatch, qapp
):
    for name in ("CONFIG", "DATA", "STATE", "CACHE"):
        monkeypatch.setenv("XDG_{}_HOME".format(name), str(tmp_path / name.lower()))
    context = build_context(project_root=str(PROJECT_ROOT))
    window = MainWindow(context.paths, context.settings)

    assert window.navigation.count() == 6
    assert window.navigation.item(0).text().startswith("01")
    assert window.navigation.item(5).text().startswith("06")

    window.navigation.setCurrentRow(2)

    assert window.stack.currentWidget() is window.result_page


def test_brand_title_fits_sidebar_at_minimum_window_size(
    tmp_path, monkeypatch, qapp
):
    for name in ("CONFIG", "DATA", "STATE", "CACHE"):
        monkeypatch.setenv("XDG_{}_HOME".format(name), str(tmp_path / name.lower()))
    previous_stylesheet = qapp.styleSheet()
    try:
        qapp.setStyleSheet(application_stylesheet())
        context = build_context(project_root=str(PROJECT_ROOT))
        window = MainWindow(context.paths, context.settings)
        window.resize(window.minimumSize())
        window.show()
        qapp.processEvents()
        brand = window.findChild(QLabel, "brandTitle")

        assert brand.width() >= brand.sizeHint().width()
    finally:
        window.close()
        qapp.setStyleSheet(previous_stylesheet)


def test_capture_empty_state_opens_diagnostics(
    tmp_path, monkeypatch, qapp
):
    for name in ("CONFIG", "DATA", "STATE", "CACHE"):
        monkeypatch.setenv("XDG_{}_HOME".format(name), str(tmp_path / name.lower()))
    context = build_context(project_root=str(PROJECT_ROOT))
    window = MainWindow(context.paths, context.settings)

    assert (
        SEMANTIC_DARK["interactive"].lower()
        in window.capture_page._empty_state.text().lower()
    )
    window.capture_page._empty_state.linkActivated.emit("diagnostics")

    assert window.navigation.currentRow() == 5


def test_result_viewer_has_actionable_empty_state(qapp, tmp_path):
    page = ResultViewerPage(str(tmp_path / "results"), str(tmp_path / "viewer"))

    assert page._empty_state.isVisibleTo(page)
    assert "Gaussian" in page._empty_state.title_text()
    assert page._empty_state.action_button.text() == "选择本地 PLY"


def test_transfer_progress_updates_numbered_workflow_stages(qapp, tmp_path):
    page = TransferReconstructionPage("http://host:8000", str(tmp_path))

    page.set_upload_progress(50, 100)
    page.set_reconstruction_progress(33.5, "训练")
    page.set_download_progress(25, 100)

    assert page._upload_stage.progress.value() == 50
    assert page._reconstruction_stage.progress.value() == 33
    assert "训练" in page._reconstruction_stage.accessibleName()
    assert page._download_stage.progress.value() == 25


def test_transfer_workflow_scrolls_at_minimum_window_size(qapp, tmp_path):
    page = TransferReconstructionPage("http://host:8000", str(tmp_path))

    assert page._scroll is not None
    assert page._scroll.widgetResizable()
    assert page._scroll.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded


def test_history_switches_between_empty_state_and_table(qapp, tmp_path):
    page = HistoryPage()

    assert page._empty_state.isVisibleTo(page)
    assert not page.table.isVisibleTo(page)

    capture = tmp_path / "capture"
    capture.mkdir()
    page.set_jobs([ReconstructionJob("job", "capture", capture)])

    assert page.table.isVisibleTo(page)
    assert not page._empty_state.isVisibleTo(page)


def test_history_native_status_cells_and_actions_show_complete_text(
    qapp, tmp_path
):
    previous_stylesheet = qapp.styleSheet()
    try:
        qapp.setStyleSheet(application_stylesheet())
        capture = tmp_path / "capture"
        capture.mkdir()
        page = HistoryPage()
        page.set_jobs(
            [
                ReconstructionJob(
                    "failed-job",
                    "capture",
                    capture,
                    state=ReconstructionState.FAILED,
                ),
                ReconstructionJob("ready-job", "capture", capture),
            ]
        )
        page.resize(1200, 500)
        page.show()
        qapp.processEvents()

        expected_statuses = ("✕ 失败", "○ 待上传")
        for row, expected_status in enumerate(expected_statuses):
            status_item = page.table.item(row, 2)
            actions = page.table.cellWidget(row, 5)
            primary = actions.findChild(QPushButton, "tablePrimaryAction")

            assert page.table.cellWidget(row, 2) is None
            assert status_item.text() == expected_status
            assert primary.height() >= primary.sizeHint().height()
    finally:
        page.close()
        qapp.setStyleSheet(previous_stylesheet)


def test_history_action_column_is_visible_at_minimum_width(qapp, tmp_path):
    previous_stylesheet = qapp.styleSheet()
    try:
        qapp.setStyleSheet(application_stylesheet())
        capture = tmp_path / "capture"
        capture.mkdir()
        page = HistoryPage()
        page.set_jobs(
            [
                ReconstructionJob(
                    "failed-task-20260729",
                    "capture",
                    capture,
                    state=ReconstructionState.FAILED,
                )
            ]
        )
        page.resize(776, 500)
        page.show()
        qapp.processEvents()

        action_right = (
            page.table.columnViewportPosition(5)
            + page.table.columnWidth(5)
        )

        assert action_right <= page.table.viewport().width()
        assert page.table.horizontalScrollBar().maximum() == 0
    finally:
        page.close()
        qapp.setStyleSheet(previous_stylesheet)


def test_settings_groups_scroll_without_changing_values(
    tmp_path, monkeypatch, qapp
):
    for name in ("CONFIG", "DATA", "STATE", "CACHE"):
        monkeypatch.setenv("XDG_{}_HOME".format(name), str(tmp_path / name.lower()))
    context = build_context(project_root=str(PROJECT_ROOT))
    page = SettingsPage(context.settings, str(context.paths.config_file))

    assert page._scroll.widgetResizable()
    assert (
        page.values()["wsl_service_url"]
        == context.settings.wsl_service_url
    )
    assert page._save_button.isVisibleTo(page)


def test_timeout_spin_boxes_ignore_wheel_without_focus(
    tmp_path, monkeypatch, qapp
):
    for name in ("CONFIG", "DATA", "STATE", "CACHE"):
        monkeypatch.setenv("XDG_{}_HOME".format(name), str(tmp_path / name.lower()))
    context = build_context(project_root=str(PROJECT_ROOT))
    page = SettingsPage(context.settings, str(context.paths.config_file))
    page.resize(900, 680)
    page.show()
    page._save_button.setFocus()
    qapp.processEvents()
    controls = (
        (page._upload_timeout, 10),
        (page._request_timeout, 11),
        (page._poll_interval, 1.5),
        (page._reconstruction_timeout, 12),
        (page._download_timeout, 13),
    )

    for control, initial in controls:
        control.setValue(initial)
        qapp.sendEvent(control, _wheel_up_event())
        assert control.value() == initial

    page.close()


def test_timeout_spin_box_accepts_wheel_after_mouse_selection(
    tmp_path, monkeypatch, qapp
):
    for name in ("CONFIG", "DATA", "STATE", "CACHE"):
        monkeypatch.setenv("XDG_{}_HOME".format(name), str(tmp_path / name.lower()))
    context = build_context(project_root=str(PROJECT_ROOT))
    page = SettingsPage(context.settings, str(context.paths.config_file))
    page.resize(900, 680)
    page.show()
    control = page._upload_timeout
    control.setValue(10)
    QTest.mouseClick(
        control,
        Qt.LeftButton,
        pos=QPoint(10, control.height() // 2),
    )
    qapp.processEvents()

    qapp.sendEvent(control, _wheel_up_event())

    assert control.hasFocus()
    assert control.value() == 11
    page.close()


def test_timeout_spin_box_ignores_wheel_after_keyboard_focus(
    tmp_path, monkeypatch, qapp
):
    for name in ("CONFIG", "DATA", "STATE", "CACHE"):
        monkeypatch.setenv("XDG_{}_HOME".format(name), str(tmp_path / name.lower()))
    context = build_context(project_root=str(PROJECT_ROOT))
    page = SettingsPage(context.settings, str(context.paths.config_file))
    page.resize(900, 680)
    page.show()
    control = page._upload_timeout
    control.setValue(10)
    control.setFocus(Qt.TabFocusReason)
    qapp.processEvents()

    qapp.sendEvent(control, _wheel_up_event())

    assert control.hasFocus()
    assert control.value() == 10
    page.close()


def test_diagnostic_metrics_follow_report(qapp):
    page = DiagnosticsLogPage("/tmp/camera-system.log")
    report = DiagnosticReport.from_checks(
        [
            DiagnosticCheck(
                "摄像头",
                DiagnosticStatus.PASS,
                "已连接",
            ),
            DiagnosticCheck(
                "WSL",
                DiagnosticStatus.WARNING,
                "未检查",
            ),
            DiagnosticCheck(
                "OpenGL",
                DiagnosticStatus.FAILURE,
                "不可用",
            ),
        ]
    )

    page.set_report(report)

    assert page._passed_metric.value_text() == "1"
    assert page._warning_metric.value_text() == "1"
    assert page._failure_metric.value_text() == "1"
    assert page._splitter.count() == 2
