"""Minimal loader and empty-state tests for q3dviewer integration."""

from __future__ import annotations

import struct
from math import pi
from pathlib import Path

import pytest
import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from camera_system_app.infrastructure.adapters.q3dviewer_adapter import (
    Q3DViewerAdapter,
    ViewerLoadError,
    load_gaussian_ply,
    prepare_q3dviewer,
)
from camera_system_app.ui.pages import ResultViewerPage


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _write_minimal_gaussian_ply(path: Path) -> None:
    properties = (
        "x",
        "y",
        "z",
        "f_dc_0",
        "f_dc_1",
        "f_dc_2",
        "opacity",
        "scale_0",
        "scale_1",
        "scale_2",
        "rot_0",
        "rot_1",
        "rot_2",
        "rot_3",
    )
    header = [
        "ply",
        "format binary_little_endian 1.0",
        "element vertex 1",
        *("property float {}".format(name) for name in properties),
        "end_header",
        "",
    ]
    values = (
        0.0,
        0.0,
        0.0,
        0.2,
        -0.1,
        0.3,
        2.0,
        -2.0,
        -2.0,
        -2.0,
        1.0,
        0.0,
        0.0,
        0.0,
    )
    path.write_bytes("\n".join(header).encode("ascii") + struct.pack("<14f", *values))


def test_minimal_gaussian_ply_loads_in_main_environment(tmp_path):
    path = tmp_path / "3DGS.ply"
    _write_minimal_gaussian_ply(path)

    gaussians = load_gaussian_ply(path, PROJECT_ROOT)

    assert gaussians.shape == (1,)
    assert gaussians.dtype.names == ("pw", "rot", "scale", "alpha", "sh")
    assert gaussians["sh"].shape == (1, 3)


def test_missing_ply_has_explicit_error(tmp_path):
    with pytest.raises(ViewerLoadError, match="不存在"):
        load_gaussian_ply(tmp_path / "missing.ply", PROJECT_ROOT)


def test_truncated_binary_ply_is_rejected(tmp_path):
    path = tmp_path / "truncated.ply"
    properties = (
        "x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
        "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3",
    )
    header = [
        "ply", "format binary_little_endian 1.0", "element vertex 2",
        *("property float {}".format(name) for name in properties),
        "end_header", "",
    ]
    path.write_bytes(
        "\n".join(header).encode("ascii") + struct.pack("<14f", *([0.0] * 14))
    )

    with pytest.raises(ViewerLoadError, match="Truncated PLY"):
        load_gaussian_ply(path, PROJECT_ROOT)


def test_result_page_without_file_remains_usable(qapp, tmp_path):
    page = ResultViewerPage(str(tmp_path / "results"), str(tmp_path / "viewer"))
    selections = []
    page.select_local_result_requested.connect(lambda: selections.append(True))

    assert not page._action.isEnabled()
    assert page._select.isEnabled()
    assert not page._reset.isEnabled()
    assert page._viewer_widget is None
    assert "当前没有" in page._banner._text.text()

    page.set_result_available(str(tmp_path / "missing.ply"))

    assert not page._action.isEnabled()
    assert "不存在" in page._banner._text.text()

    page._select.click()
    assert selections == [True]


def test_camera_pitch_is_not_clipped_and_supports_full_orbit(qapp):
    prepare_q3dviewer(PROJECT_ROOT)
    from q3dviewer.base_glwidget import BaseGLWidget

    widget = BaseGLWidget()
    widget.set_euler([0.0, 0.0, 0.0])
    widget.rotate(-pi / 2, 0.0, 0.0)

    assert widget.euler[0] == pytest.approx(-pi / 2)
    widget.deleteLater()


def test_plain_left_click_does_not_start_gpu_interaction(qapp):
    prepare_q3dviewer(PROJECT_ROOT)
    from q3dviewer.base_glwidget import BaseGLWidget

    widget = BaseGLWidget()
    started = []
    widget.interaction_started.connect(lambda: started.append(True))

    QTest.mousePress(
        widget,
        Qt.MouseButton.LeftButton,
        pos=QPoint(20, 20),
    )
    QTest.mouseRelease(
        widget,
        Qt.MouseButton.LeftButton,
        pos=QPoint(20, 20),
    )
    qapp.processEvents()

    assert started == []
    assert widget.dist == pytest.approx(40.0)
    widget.deleteLater()


def test_gaussian_interaction_preview_suspends_sort_until_release():
    prepare_q3dviewer(PROJECT_ROOT)
    from q3dviewer.custom_items.gaussian_item import GaussianItem

    item = GaussianItem(sort_enabled=True, sort_backend="opengl")
    item.set_interactive_preview(True, max_gaussians=1000)
    assert item.interactive_preview
    assert item.sort_suspended
    assert item.interactive_max_gaussians == 1000

    previous_direction = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    item.prev_Rz = previous_direction.copy()
    item.set_interactive_preview(False)
    assert not item.interactive_preview
    assert not item.sort_suspended
    assert np.array_equal(item.prev_Rz, previous_direction)


def test_embedded_viewer_does_not_continuously_render_while_idle(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)

    assert not adapter._timer.isActive()

    adapter._begin_interaction()
    assert adapter._timer.isActive()
    assert adapter.item.interactive_preview

    adapter._end_interaction()
    assert not adapter._timer.isActive()
    assert not adapter.item.interactive_preview

    adapter._begin_interaction()
    adapter.set_active(False)
    assert not adapter._timer.isActive()
    assert not adapter.item.interactive_preview

    adapter.set_active(True)
    adapter.release()
