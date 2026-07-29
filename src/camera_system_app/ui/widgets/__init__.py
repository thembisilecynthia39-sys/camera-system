"""Shared shell widgets."""

from camera_system_app.ui.widgets.empty_state import EmptyState
from camera_system_app.ui.widgets.focus_wheel_spinbox import (
    FocusWheelDoubleSpinBox,
    FocusWheelSpinBox,
)
from camera_system_app.ui.widgets.metric_card import MetricCard
from camera_system_app.ui.widgets.page_header import PageHeader
from camera_system_app.ui.widgets.status_banner import StatusBanner
from camera_system_app.ui.widgets.workflow_stage import WorkflowStage

__all__ = [
    "EmptyState",
    "FocusWheelDoubleSpinBox",
    "FocusWheelSpinBox",
    "MetricCard",
    "PageHeader",
    "StatusBanner",
    "WorkflowStage",
]
