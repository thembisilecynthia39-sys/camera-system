from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from multiwebcam.sources.controls import V4L2Control
from multiwebcam.ui.views.control_panel import ControlPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _texts(widget, widget_type):
    return [child.text() for child in widget.findChildren(widget_type)]


def test_control_panel_empty_state_is_localized(qapp):
    panel = ControlPanel([])

    labels = _texts(panel, QLabel)

    assert "摄像头控制" in labels
    assert "当前摄像头没有可调参数" in labels


def test_control_panel_uses_localized_common_control_labels(qapp):
    panel = ControlPanel(
        [
            V4L2Control(
                name="exposure_absolute",
                type="int",
                min=3,
                max=2047,
                step=1,
                default=250,
                current=166,
            ),
            V4L2Control(
                name="focus_auto",
                type="bool",
                min=0,
                max=1,
                step=1,
                default=1,
                current=1,
            ),
        ]
    )

    labels = _texts(panel, QLabel)
    buttons = _texts(panel, QPushButton)

    assert "曝光时间" in labels
    assert "自动对焦" in labels
    assert "恢复默认值" in buttons


def test_control_panel_keeps_unknown_control_names_readable(qapp):
    panel = ControlPanel(
        [
            V4L2Control(
                name="vendor_special_mode",
                type="bool",
                min=0,
                max=1,
                step=1,
                default=0,
                current=0,
            )
        ]
    )

    labels = _texts(panel, QLabel)

    assert "Vendor Special Mode" in labels
