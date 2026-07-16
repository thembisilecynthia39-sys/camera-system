"""Lifecycle tests for the embedded 3DGS workspace."""

import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

import multiwebcam.ui.views.gaussian_model_view as gaussian_view


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_high_quality_preview_is_disabled_by_default(qapp):
    view = gaussian_view.GaussianModelView()

    assert view._high_quality_checkbox.text() == "高质量预览"
    assert not view._high_quality_checkbox.isChecked()
    assert "24 万个 Gaussian" in view._high_quality_checkbox.toolTip()
    assert gaussian_view.HIGH_QUALITY_MAX_GAUSSIANS == 240_000

    view.shutdown()


def test_quality_toggle_reloads_current_model(qapp, monkeypatch, tmp_path):
    view = gaussian_view.GaussianModelView()
    model_path = tmp_path / "scene.ply"
    view._current_model_path = model_path
    reloaded = []
    monkeypatch.setattr(view, "load_model", reloaded.append)

    view._high_quality_checkbox.setChecked(True)

    assert reloaded == [model_path]
    view.shutdown()


def test_high_quality_interaction_defers_sort_until_release(qapp):
    class FakeGaussianItem:
        sort_enabled = True
        sort_suspended = False
        sort_requests = 0

        def request_sort(self):
            self.sort_requests += 1

    view = gaussian_view.GaussianModelView()
    view._high_quality_checkbox.setChecked(True)
    view._gl_widget = SimpleNamespace(auto_orbit=False)
    view._gaussian_item = FakeGaussianItem()

    view._begin_interaction()

    assert view._gaussian_item.sort_suspended
    assert view._render_timer.interval() == gaussian_view.HIGH_QUALITY_FRAME_INTERVAL_MS

    view._end_interaction()

    assert not view._gaussian_item.sort_suspended
    assert view._gaussian_item.sort_requests == 1
    assert view._render_timer.interval() == 50
    view.shutdown()


def test_inactive_view_stops_warmup_timer(qapp):
    view = gaussian_view.GaussianModelView()
    view._warmup_frames = 5
    view._render_timer.start()

    view.set_active(False)

    assert not view._render_timer.isActive()
    view.shutdown()


def test_shutdown_interrupts_and_joins_model_loader(qapp, monkeypatch):
    def cancellable_loader(path, max_gaussians, full_sh=False, cancelled=None):
        while not cancelled():
            time.sleep(0.005)
        raise InterruptedError("cancelled")

    monkeypatch.setattr(gaussian_view, "_load_binary_ply_preview", cancellable_loader)
    view = gaussian_view.GaussianModelView()
    monkeypatch.setattr(view, "_ensure_renderer", lambda: None)
    view.load_model(Path("model.ply"))

    assert view._load_worker.isRunning()
    view.shutdown()

    assert view._load_worker is None


def _write_binary_gaussian_ply(path: Path, count: int = 4) -> None:
    fields = [
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("rot_0", "<f4"), ("rot_1", "<f4"),
        ("rot_2", "<f4"), ("rot_3", "<f4"),
        ("scale_0", "<f4"), ("scale_1", "<f4"), ("scale_2", "<f4"),
        ("opacity", "<f4"),
        ("f_dc_0", "<f4"), ("f_dc_1", "<f4"), ("f_dc_2", "<f4"),
    ]
    fields.extend((f"f_rest_{index}", "<f4") for index in range(45))
    data = np.zeros(count, dtype=np.dtype(fields))
    data["x"] = np.arange(count, dtype=np.float32)
    data["rot_0"] = 1.0
    for channel in range(3):
        data[f"f_dc_{channel}"] = channel + 1
    for index in range(45):
        data[f"f_rest_{index}"] = index

    header = ["ply", "format binary_little_endian 1.0", f"element vertex {count}"]
    header.extend(f"property float {name}" for name, _dtype in fields)
    header.extend(("end_header", ""))
    with path.open("wb") as stream:
        stream.write("\n".join(header).encode("ascii"))
        data.tofile(stream)


def test_lightweight_loader_decimates_and_keeps_dc_only(tmp_path):
    path = tmp_path / "scene.ply"
    _write_binary_gaussian_ply(path)

    gs_data, _center, _distance = gaussian_view._load_binary_ply_preview(
        path, max_gaussians=2, full_sh=False
    )

    assert gs_data.shape == (2, 14)
    assert gs_data[:, 0].tolist() == [0.0, 3.0]


def test_high_quality_loader_keeps_all_gaussians_and_degree_three_sh(tmp_path):
    path = tmp_path / "scene.ply"
    _write_binary_gaussian_ply(path)

    gs_data, _center, _distance = gaussian_view._load_binary_ply_preview(
        path, max_gaussians=0, full_sh=True
    )

    assert gs_data.shape == (4, 59)
    assert gs_data[0, 11:14].tolist() == [1.0, 2.0, 3.0]
    assert gs_data[0, 14:17].tolist() == [0.0, 15.0, 30.0]
