"""Behaviour checks for the workstation UI design system."""

import re

from camera_system_app.ui.design_tokens import SEMANTIC_DARK, SEMANTIC_LIGHT
from camera_system_app.ui.theme import application_stylesheet
from camera_system_app.ui.widgets import (
    EmptyState,
    MetricCard,
    PageHeader,
    StatusBanner,
    WorkflowStage,
)


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
