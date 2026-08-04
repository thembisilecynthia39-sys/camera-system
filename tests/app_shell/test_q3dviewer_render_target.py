"""Tests for camera snapshots and sized q3dviewer output targets."""

from __future__ import annotations

import pytest

from camera_system_app.infrastructure.adapters.q3dviewer_adapter import prepare_q3dviewer


def test_render_target_validates_positive_bounded_dimensions():
    from q3dviewer.render_target import RenderTarget, RenderTargetError

    assert RenderTarget.validate_size(1920, 1080, max_dimension=4096) == (1920, 1080)
    with pytest.raises(RenderTargetError):
        RenderTarget.validate_size(0, 1080)
    with pytest.raises(RenderTargetError):
        RenderTarget.validate_size(9000, 1080, max_dimension=8192)


def test_base_widget_camera_state_round_trips_without_transform_accumulation(qapp):
    prepare_q3dviewer(__import__("pathlib").Path(__file__).resolve().parents[2])
    from q3dviewer.base_glwidget import BaseGLWidget

    widget = BaseGLWidget()
    original = widget.get_camera_state()
    changed = {
        "center": [1.0, 2.0, 3.0],
        "euler": [0.4, -0.3, 1.2],
        "distance": 7.5,
        "fov_degrees": 52.0,
    }

    widget.set_camera_state(changed)
    first = widget.get_camera_state()
    widget.set_camera_state(first)
    second = widget.get_camera_state()

    assert first == second
    assert first["center"] == pytest.approx(changed["center"])
    assert first["euler"] == pytest.approx(changed["euler"])
    assert first["distance"] == pytest.approx(7.5)
    assert first["fov_degrees"] == pytest.approx(52.0)
    widget.set_camera_state(original)
    widget.deleteLater()


def test_base_widget_persists_camera_mode_and_fly_speed(qapp):
    prepare_q3dviewer(__import__("pathlib").Path(__file__).resolve().parents[2])
    from q3dviewer.base_glwidget import BaseGLWidget

    widget = BaseGLWidget()
    state = widget.get_camera_state()

    assert state["camera_mode"] == "orbit"
    assert state["fly_speed"] == pytest.approx(1.0)

    widget.set_camera_state({**state, "camera_mode": "fly", "fly_speed": 2.5})
    changed = widget.get_camera_state()

    assert changed["camera_mode"] == "fly"
    assert changed["fly_speed"] == pytest.approx(2.5)
    widget.deleteLater()


def test_base_widget_fly_rotation_keeps_camera_position(qapp, monkeypatch):
    prepare_q3dviewer(__import__("pathlib").Path(__file__).resolve().parents[2])
    from q3dviewer.base_glwidget import BaseGLWidget

    widget = BaseGLWidget()
    widget.set_camera_mode("fly")
    calls = []
    monkeypatch.setattr(widget, "rotate_keep_cam_pos", lambda *args: calls.append("fly"))
    monkeypatch.setattr(widget, "rotate", lambda *args: calls.append("orbit"))
    from q3dviewer.Qt import QtCore

    widget.active_keys = {QtCore.Qt.Key_Left}
    widget.update_movement()

    assert calls == ["fly"]
    widget.deleteLater()


def test_base_widget_rejects_incomplete_camera_state(qapp):
    prepare_q3dviewer(__import__("pathlib").Path(__file__).resolve().parents[2])
    from q3dviewer.base_glwidget import BaseGLWidget

    widget = BaseGLWidget()

    with pytest.raises(ValueError):
        widget.set_camera_state({"center": [0, 0, 0]})
    with pytest.raises(ValueError):
        widget.set_camera_state(
            {"center": [0, 0, 0], "euler": [0, 0, 0], "distance": 0}
        )
    widget.deleteLater()


def test_render_to_array_rejects_invalid_output_size_before_needing_a_context(qapp):
    prepare_q3dviewer(__import__("pathlib").Path(__file__).resolve().parents[2])
    from q3dviewer.base_glwidget import BaseGLWidget
    from q3dviewer.render_target import RenderTargetError

    widget = BaseGLWidget()

    with pytest.raises(RenderTargetError):
        widget.render_to_array(0, 720)
    widget.deleteLater()
