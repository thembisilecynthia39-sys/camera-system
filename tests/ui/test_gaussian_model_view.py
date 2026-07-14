"""Lifecycle tests for the embedded 3DGS workspace."""

import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

import multiwebcam.ui.views.gaussian_model_view as gaussian_view


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_quality_sorting_is_enabled_by_default(qapp):
    view = gaussian_view.GaussianModelView()

    assert view._sort_checkbox.isChecked()

    view.shutdown()


def test_inactive_view_stops_warmup_timer(qapp):
    view = gaussian_view.GaussianModelView()
    view._warmup_frames = 5
    view._render_timer.start()

    view.set_active(False)

    assert not view._render_timer.isActive()
    view.shutdown()


def test_shutdown_interrupts_and_joins_model_loader(qapp, monkeypatch):
    def cancellable_loader(path, max_gaussians, cancelled=None):
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
