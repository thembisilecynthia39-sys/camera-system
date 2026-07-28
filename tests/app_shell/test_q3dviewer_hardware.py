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
    adapter.release()
    assert not adapter.item.is_initialized()
    adapter.widget.close()
