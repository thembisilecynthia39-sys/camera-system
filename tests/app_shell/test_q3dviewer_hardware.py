"""Opt-in Jetson/NVIDIA OpenGL rendering verification."""

from __future__ import annotations

import os
import struct
from pathlib import Path

import numpy as np
import pytest


HARDWARE_GL = os.environ.get("CAMERA_SYSTEM_HARDWARE_GL_TEST") == "1"

if HARDWARE_GL:
    from PySide6.QtGui import QSurfaceFormat

    _format = QSurfaceFormat()
    _format.setRenderableType(QSurfaceFormat.OpenGL)
    _format.setVersion(4, 3)
    _format.setProfile(QSurfaceFormat.CoreProfile)
    _format.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(_format)


@pytest.mark.skipif(not HARDWARE_GL, reason="requires the Jetson X11 OpenGL session")
def test_jetson_core_profile_renders_gaussian_ply(qapp, tmp_path):
    from OpenGL.GL import GL_RENDERER, GL_VERSION, glGetString
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtGui import QGuiApplication

    from camera_system_app.infrastructure.adapters.q3dviewer_adapter import (
        Q3DViewerAdapter,
        load_gaussian_ply,
    )

    project_root = Path(__file__).resolve().parents[2]
    assert QGuiApplication.platformName() == "xcb"
    configured_path = os.environ.get("CAMERA_SYSTEM_HARDWARE_PLY")
    path = Path(configured_path) if configured_path else tmp_path / "3DGS.ply"
    if not configured_path:
        names = (
            "x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
            "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3",
        )
        header = [
            "ply", "format binary_little_endian 1.0", "element vertex 1",
            *("property float {}".format(name) for name in names),
            "end_header", "",
        ]
        values = (0, 0, 0, 0.2, -0.1, 0.3, 2, -2, -2, -2, 1, 0, 0, 0)
        path.write_bytes(
            "\n".join(header).encode("ascii") + struct.pack("<14f", *values)
        )
    data = load_gaussian_ply(path, project_root)
    adapter = Q3DViewerAdapter(project_root)
    errors = []
    adapter.rendering_failed.connect(errors.append)
    adapter.set_gaussians(data)
    default_center = adapter.widget.center.copy()
    default_euler = adapter.widget.euler.copy()
    default_distance = adapter.widget.dist
    adapter.widget.rotate(0.1, 0.0, 0.1)
    adapter.widget.translate(np.array([0.2, 0.1, 0.0]))
    adapter.widget.update_dist(0.5)
    assert not np.allclose(adapter.widget.euler, default_euler)
    assert not np.allclose(adapter.widget.center, default_center)
    assert adapter.widget.dist != default_distance
    adapter.reset_view()
    assert np.allclose(adapter.widget.euler, default_euler)
    assert np.allclose(adapter.widget.center, default_center)
    assert adapter.widget.dist == default_distance
    adapter.widget.resize(640, 480)
    adapter.widget.show()
    QTest.qWait(800)
    qapp.processEvents()
    click_center = adapter.widget.center.copy()
    click_distance = adapter.widget.dist
    interaction_started = []
    adapter.widget.interaction_started.connect(
        lambda: interaction_started.append(True)
    )
    QTest.mouseClick(
        adapter.widget,
        Qt.MouseButton.LeftButton,
        pos=adapter.widget.rect().center(),
    )
    QTest.qWait(250)
    qapp.processEvents()
    assert interaction_started == []
    assert np.array_equal(adapter.widget.center, click_center)
    assert adapter.widget.dist == click_distance

    class _DragEvent:
        def __init__(self, position, button):
            self._position = QPointF(position)
            self._button = button

        def localPos(self):
            return self._position

        def buttons(self):
            return self._button

        def modifiers(self):
            return Qt.KeyboardModifier.NoModifier

    drag_origin = adapter.widget.rect().center()
    left_center = adapter.widget.center.copy()
    left_euler = adapter.widget.euler.copy()
    left_distance = adapter.widget.dist
    QTest.mousePress(
        adapter.widget,
        Qt.MouseButton.LeftButton,
        pos=drag_origin,
    )
    adapter.widget.mouseMoveEvent(
        _DragEvent(drag_origin + QPoint(40, 20), Qt.MouseButton.LeftButton)
    )
    QTest.mouseRelease(
        adapter.widget,
        Qt.MouseButton.LeftButton,
        pos=drag_origin + QPoint(40, 20),
    )
    QTest.qWait(250)
    qapp.processEvents()
    assert not np.array_equal(adapter.widget.center, left_center)
    assert np.array_equal(adapter.widget.euler, left_euler)
    assert adapter.widget.dist == left_distance
    assert not adapter.item.interactive_preview

    right_center = adapter.widget.center.copy()
    right_euler = adapter.widget.euler.copy()
    right_distance = adapter.widget.dist
    QTest.mousePress(
        adapter.widget,
        Qt.MouseButton.RightButton,
        pos=drag_origin,
    )
    adapter.widget.mouseMoveEvent(
        _DragEvent(drag_origin + QPoint(35, 15), Qt.MouseButton.RightButton)
    )
    QTest.mouseRelease(
        adapter.widget,
        Qt.MouseButton.RightButton,
        pos=drag_origin + QPoint(35, 15),
    )
    QTest.qWait(250)
    qapp.processEvents()
    assert np.array_equal(adapter.widget.center, right_center)
    assert not np.array_equal(adapter.widget.euler, right_euler)
    assert adapter.widget.dist == right_distance
    assert not adapter.item.interactive_preview

    class _WheelEvent:
        def angleDelta(self):
            return QPoint(0, 120)

    wheel_center = adapter.widget.center.copy()
    wheel_euler = adapter.widget.euler.copy()
    wheel_distance = adapter.widget.dist
    adapter.widget.wheelEvent(_WheelEvent())
    QTest.qWait(250)
    qapp.processEvents()
    assert np.array_equal(adapter.widget.center, wheel_center)
    assert np.array_equal(adapter.widget.euler, wheel_euler)
    assert adapter.widget.dist < wheel_distance
    assert not adapter.item.interactive_preview

    projection = adapter.widget.projection_matrix.copy()
    adapter.widget.update_dist(0.5)
    QTest.qWait(100)
    qapp.processEvents()
    assert not np.allclose(adapter.widget.projection_matrix, projection)
    adapter.reset_view()

    assert adapter.widget.isValid()
    context_format = adapter.widget.context().format()
    assert context_format.profile() == QSurfaceFormat.CoreProfile
    assert (context_format.majorVersion(), context_format.minorVersion()) >= (4, 3)
    adapter.widget.makeCurrent()
    renderer = (glGetString(GL_RENDERER) or b"").decode()
    version = (glGetString(GL_VERSION) or b"").decode()
    frame = adapter.widget.grabFramebuffer()
    adapter.widget.doneCurrent()

    assert "NVIDIA" in renderer
    assert "Tegra" in renderer or "Orin" in renderer
    assert version.startswith(("4.3", "4.4", "4.5", "4.6"))
    assert not frame.isNull()
    converted = frame.convertToFormat(frame.Format_RGBA8888)
    buffer = converted.constBits()
    byte_count = converted.byteCount()
    if hasattr(buffer, "setsize"):
        buffer.setsize(byte_count)
    pixels = np.frombuffer(buffer, dtype=np.uint8, count=byte_count)
    pixels = pixels.reshape(converted.height(), converted.width(), 4)
    assert np.any(pixels[:, :, :3] != pixels[0, 0, :3])
    assert not errors

    for mode in ("sphere_wireframe", "sphere_solid", "overlay"):
        adapter.item.set_display_mode(mode)
        adapter.widget.update()
        QTest.qWait(250)
        qapp.processEvents()
        sphere_frame = adapter.widget.grabFramebuffer()
        assert not sphere_frame.isNull()
        assert sphere_frame.size() == frame.size()
    assert not errors
    adapter.release()
    assert not adapter.item.is_initialized()
    adapter.widget.close()
