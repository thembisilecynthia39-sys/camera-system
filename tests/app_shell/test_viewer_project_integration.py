"""Integration tests for sidecar restoration and presentation mode."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFrame

from camera_system_app.bootstrap import build_context
from camera_system_app.domain.viewer import CameraPose, DisplayMode, DisplaySettings, ViewerProject
from camera_system_app.infrastructure.viewer_project_store import ViewerProjectStore
from camera_system_app.ui.main_window import MainWindow
from camera_system_app.ui.viewer_bindings import ViewerBindings


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _binding(tmp_path, qapp, monkeypatch):
    for name in ("CONFIG", "DATA", "STATE", "CACHE"):
        monkeypatch.setenv("XDG_{}_HOME".format(name), str(tmp_path / name.lower()))
    context = build_context(project_root=str(PROJECT_ROOT))
    window = MainWindow(context.paths, context.settings)
    window.show()
    qapp.processEvents()
    binding = ViewerBindings(window, PROJECT_ROOT, window)
    return binding, window


def test_bindings_restore_matching_sidecar_state(tmp_path, qapp, monkeypatch):
    binding, window = _binding(tmp_path, qapp, monkeypatch)
    source = tmp_path / "room.ply"
    source.write_bytes(b"ply-source")
    store = ViewerProjectStore()
    project = ViewerProject(
        source_path=str(source.resolve()),
        source_size=source.stat().st_size,
        source_sha256=store.sha256_file(source),
        camera=CameraPose(position=(1.0, 2.0, 3.0)),
        display=DisplaySettings(mode=DisplayMode.OVERLAY),
    )
    store.save(project)

    restored = binding._load_project_state(source, project)

    assert restored == project
    window.deleteLater()


def test_bindings_reset_stale_sidecar_instead_of_silently_applying_it(
    tmp_path, qapp, monkeypatch
):
    binding, window = _binding(tmp_path, qapp, monkeypatch)
    source = tmp_path / "room.ply"
    source.write_bytes(b"original")
    store = ViewerProjectStore()
    stale = ViewerProject(
        source_path=str(source.resolve()),
        source_size=source.stat().st_size,
        source_sha256=store.sha256_file(source),
        display=DisplaySettings(mode=DisplayMode.SPHERE_SOLID),
    )
    store.save(stale)
    source.write_bytes(b"changed")
    fallback = ViewerProject(source_path=str(source.resolve()))

    restored = binding._load_project_state(source, fallback, allow_stale=False)

    assert restored == fallback
    window.deleteLater()


def test_presentation_mode_hides_chrome_and_is_reversible(qapp, tmp_path, monkeypatch):
    binding, window = _binding(tmp_path, qapp, monkeypatch)
    sidebar = window.findChild(QFrame, "sidebar")
    assert sidebar is not None
    assert sidebar.isVisible()

    binding.set_presentation_mode(True)
    assert binding.is_presentation_mode
    assert not sidebar.isVisible()
    assert not window.statusBar().isVisible()

    binding.set_presentation_mode(False)
    assert not binding.is_presentation_mode
    assert sidebar.isVisible()
    assert window.statusBar().isVisible()
    window.deleteLater()
