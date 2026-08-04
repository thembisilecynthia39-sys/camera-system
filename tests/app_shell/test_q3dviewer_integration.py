"""Minimal loader and empty-state tests for q3dviewer integration."""

from __future__ import annotations

import struct
from math import pi
from pathlib import Path

import pytest
import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from camera_system_app.infrastructure.adapters.q3dviewer_adapter import (
    Q3DViewerAdapter,
    ViewerLoadError,
    load_gaussian_ply,
    prepare_q3dviewer,
)
from camera_system_app.ui.pages import ResultViewerPage
from camera_system_app.workers import viewer_load_worker as viewer_worker_module
from camera_system_app.workers.viewer_load_worker import ViewerLoadWorker


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _write_minimal_gaussian_ply(path: Path, vertex_count: int = 1) -> None:
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
        f"element vertex {vertex_count}",
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
    path.write_bytes(
        "\n".join(header).encode("ascii")
        + struct.pack("<14f", *values) * vertex_count
    )


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


def test_binary_gaussian_conversion_checks_cancellation_between_chunks(
    monkeypatch, tmp_path
):
    path = tmp_path / "large.ply"
    _write_minimal_gaussian_ply(path, vertex_count=3)
    prepare_q3dviewer(PROJECT_ROOT)
    import q3dviewer.utils.cloud_io as cloud_io

    cancelled = False
    original_exp = cloud_io.np.exp

    def cancel_after_first_scale_conversion(values):
        nonlocal cancelled
        result = original_exp(values)
        cancelled = True
        return result

    monkeypatch.setattr(
        cloud_io.np,
        "exp",
        cancel_after_first_scale_conversion,
    )

    with pytest.raises(InterruptedError, match="cancel"):
        cloud_io.load_gs_ply(
            str(path),
            cancel_check=lambda: cancelled,
            chunk_rows=1,
        )


def test_application_loader_forwards_cancellation_to_q3dviewer(
    monkeypatch, tmp_path
):
    path = tmp_path / "3DGS.ply"
    _write_minimal_gaussian_ply(path)
    prepare_q3dviewer(PROJECT_ROOT)
    import q3dviewer.utils.cloud_io as cloud_io

    def cancelled_loader(_path, _transform=None, *, cancel_check=None, **_kwargs):
        assert cancel_check is not None
        assert cancel_check()
        raise InterruptedError("Gaussian PLY loading cancelled")

    monkeypatch.setattr(cloud_io, "load_gs_ply", cancelled_loader)

    with pytest.raises(InterruptedError, match="cancel"):
        load_gaussian_ply(
            path,
            PROJECT_ROOT,
            cancel_check=lambda: True,
        )


def test_viewer_worker_suppresses_interrupted_load_signals(
    qapp, monkeypatch, tmp_path
):
    path = tmp_path / "3DGS.ply"
    _write_minimal_gaussian_ply(path)
    worker = ViewerLoadWorker(str(path), PROJECT_ROOT)
    loaded = []
    failed = []

    def interrupted_loader(_path, _project_root, *, cancel_check=None):
        assert cancel_check is not None
        worker.requestInterruption()
        assert cancel_check()
        raise InterruptedError("Gaussian PLY loading cancelled")

    monkeypatch.setattr(
        viewer_worker_module,
        "load_gaussian_ply",
        interrupted_loader,
    )
    worker.loaded.connect(lambda *args: loaded.append(args))
    worker.failed.connect(failed.append)

    worker.start()
    assert worker.wait(3000)
    qapp.processEvents()

    assert loaded == []
    assert failed == []


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


def test_result_page_restores_existing_viewer_after_reload_failure(qapp, tmp_path):
    page = ResultViewerPage(str(tmp_path / "results"), str(tmp_path / "viewer"))
    page.resize(900, 640)
    page.show()
    viewer = QLabel("old viewer")
    page.set_viewer_widget(viewer, "old.ply", 1)
    qapp.processEvents()

    page.show_loading("new.ply")
    page.show_load_error("invalid Gaussian PLY")
    qapp.processEvents()

    assert viewer.isVisible()
    assert page._toolbar.isEnabled()
    assert page._inspector.isVisible()
    assert page._reset.isEnabled()
    page.hide()


def test_result_page_keeps_sphere_capability_state_during_reload(qapp, tmp_path):
    page = ResultViewerPage(str(tmp_path / "results"), str(tmp_path / "viewer"))
    page.show()
    page.set_sphere_modes_available(False, "sphere shader unavailable")
    page.set_viewer_widget(QLabel("old viewer"), "old.ply", 1)

    page.show_loading("new.ply")

    assert page._sphere_available is False
    sphere_index = page._toolbar.display_mode_combo.findData("sphere_solid")
    assert page._toolbar.display_mode_combo.model().item(sphere_index).isEnabled() is False
    page.hide()


def test_viewer_worker_includes_source_identity_metadata(qapp, tmp_path):
    path = tmp_path / "3DGS.ply"
    _write_minimal_gaussian_ply(path)
    worker = ViewerLoadWorker(str(path), PROJECT_ROOT)
    loaded = []
    worker.loaded.connect(lambda payload, loaded_path: loaded.append((payload, loaded_path)))

    worker.start()
    assert worker.wait(3000)
    qapp.processEvents()

    assert len(loaded) == 1
    payload, loaded_path = loaded[0]
    data, bounds, source_size, source_sha256 = payload
    assert data.shape == (1,)
    assert bounds[0].shape == (3,)
    assert loaded_path == str(path)
    assert source_size == path.stat().st_size
    assert len(source_sha256) == 64


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


def test_left_click_jitter_below_drag_threshold_changes_no_camera_state(qapp):
    prepare_q3dviewer(PROJECT_ROOT)
    from q3dviewer.base_glwidget import BaseGLWidget

    class _MoveEvent:
        def localPos(self):
            return QPointF(22, 21)

        def buttons(self):
            return Qt.MouseButton.LeftButton

        def modifiers(self):
            return Qt.KeyboardModifier.NoModifier

    widget = BaseGLWidget()
    started = []
    widget.interaction_started.connect(lambda: started.append(True))
    center = widget.center.copy()

    QTest.mousePress(
        widget,
        Qt.MouseButton.LeftButton,
        pos=QPoint(20, 20),
    )
    widget.mouseMoveEvent(_MoveEvent())
    QTest.mouseRelease(
        widget,
        Qt.MouseButton.LeftButton,
        pos=QPoint(22, 21),
    )
    qapp.processEvents()

    assert started == []
    assert np.array_equal(widget.center, center)
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


def test_large_gaussian_models_use_cpu_depth_sort_fallback(monkeypatch):
    prepare_q3dviewer(PROJECT_ROOT)
    import q3dviewer.custom_items.gaussian_item as gaussian_module

    item = gaussian_module.GaussianItem(
        sort_enabled=True,
        sort_backend="opengl",
        max_bitonic_gaussians=2,
    )
    item.gs_data = np.zeros((3, 14), dtype=np.float32)
    item.gs_data[:, 2] = np.array([2.0, 0.0, 1.0], dtype=np.float32)
    item.view_matrix = np.eye(4, dtype=np.float32)
    item.prev_Rz = np.array([np.inf, np.inf, np.inf], dtype=np.float32)
    item.num_sort = 4
    item.ssbo_gi = 17
    uploaded = []

    monkeypatch.setattr(gaussian_module, "glBindBuffer", lambda *args: None)
    monkeypatch.setattr(
        gaussian_module,
        "glBufferData",
        lambda _target, _size, values, _usage: uploaded.append(np.asarray(values).copy()),
    )
    monkeypatch.setattr(gaussian_module, "glBindBufferBase", lambda *args: None)

    item.try_sort()

    assert np.array_equal(uploaded[-1], np.array([1, 2, 0, 3], dtype=np.uint32))
    assert item.sort_skipped_large_model is False
    assert item.sort_fallback_used is True


def test_depth_picker_clips_neighborhood_at_widget_edges(monkeypatch):
    prepare_q3dviewer(PROJECT_ROOT)
    import q3dviewer.base_glwidget as base_glwidget

    depth = np.zeros((5, 5), dtype=np.float32)
    offset = np.array(
        [(dx, dy) for dy in range(-3, 4) for dx in range(-3, 4)],
        dtype=np.int64,
    )

    samples = base_glwidget.BaseGLWidget._sample_depth_neighborhood(
        depth, 4, 4, offset
    )

    assert samples.size == 16


def test_interaction_preview_keeps_full_sh_storage_stride(monkeypatch):
    prepare_q3dviewer(PROJECT_ROOT)
    import q3dviewer.custom_items.gaussian_item as gaussian_module

    item = gaussian_module.GaussianItem(
        sort_enabled=False,
        sort_backend="opengl",
    )
    item.gs_data = np.zeros((2, 59), dtype=np.float32)
    item.sh_dim = 48
    item.view_matrix = np.eye(4, dtype=np.float32)
    item.interactive_preview = True
    item.interactive_max_gaussians = 2
    item._preview_count = 2
    item.prep_program = 7
    item.ssbo_preview_gi = 11
    uniforms = {}

    monkeypatch.setattr(gaussian_module, "glUseProgram", lambda _program: None)
    monkeypatch.setattr(
        gaussian_module,
        "set_uniform",
        lambda _program, value, name: uniforms.__setitem__(name, value),
    )
    monkeypatch.setattr(
        gaussian_module,
        "glBindBufferBase",
        lambda _target, _binding, _buffer: None,
    )
    monkeypatch.setattr(
        gaussian_module,
        "raw_glDispatchCompute",
        lambda _x, _y, _z: None,
    )
    monkeypatch.setattr(
        gaussian_module,
        "raw_glMemoryBarrier",
        lambda _barrier: None,
    )

    assert item.preprocessGS() == 2
    assert uniforms["data_sh_dim"] == 48
    assert uniforms["render_sh_dim"] == 3


def test_embedded_viewer_does_not_continuously_render_while_idle(qapp):
    adapter = Q3DViewerAdapter(PROJECT_ROOT)

    assert not adapter._timer.isActive()
    assert not adapter.widget.enable_depth_picking

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
