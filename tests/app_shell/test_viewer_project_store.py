"""Tests for atomic viewer sidecar persistence and source identity checks."""

from __future__ import annotations

import json

import pytest

from camera_system_app.domain.viewer import CameraPose, ViewerProject
from camera_system_app.infrastructure.viewer_project_store import (
    ViewerProjectFormatError,
    ViewerProjectNotFoundError,
    ViewerProjectSourceMismatchError,
    ViewerProjectStore,
)


def _project_for(source, store):
    return ViewerProject(
        source_path=str(source.resolve()),
        source_size=source.stat().st_size,
        source_sha256=store.sha256_file(source),
        camera=CameraPose(position=(1.0, 2.0, 3.0)),
    )


def test_default_path_places_splatview_sidecar_next_to_source(tmp_path):
    source = tmp_path / "room.ply"

    assert ViewerProjectStore.default_path(source) == tmp_path / "room.splatview.json"


def test_save_and_load_round_trip_validates_current_source_identity(tmp_path):
    source = tmp_path / "room.ply"
    source.write_bytes(b"ply-data")
    store = ViewerProjectStore()
    project = _project_for(source, store)

    sidecar = store.save(project)
    restored = store.load(sidecar, source_path=source)

    assert restored == project
    assert json.loads(sidecar.read_text(encoding="utf-8"))["source"]["sha256"] == project.source_sha256
    assert not list(tmp_path.glob("*.tmp"))


def test_load_reports_missing_sidecar_with_a_typed_error(tmp_path):
    with pytest.raises(ViewerProjectNotFoundError):
        ViewerProjectStore().load(tmp_path / "missing.splatview.json")


def test_load_reports_malformed_json_with_a_typed_error(tmp_path):
    sidecar = tmp_path / "room.splatview.json"
    sidecar.write_text("not-json", encoding="utf-8")

    with pytest.raises(ViewerProjectFormatError):
        ViewerProjectStore().load(sidecar)


def test_load_rejects_a_changed_source_before_applying_stale_camera_state(tmp_path):
    source = tmp_path / "room.ply"
    source.write_bytes(b"original")
    store = ViewerProjectStore()
    store.save(_project_for(source, store))
    source.write_bytes(b"changed-source")

    with pytest.raises(ViewerProjectSourceMismatchError, match="changed"):
        store.load(store.default_path(source), source_path=source)


def test_load_can_explicitly_accept_a_changed_source_and_refresh_identity(tmp_path):
    source = tmp_path / "room.ply"
    source.write_bytes(b"original")
    store = ViewerProjectStore()
    store.save(_project_for(source, store))
    source.write_bytes(b"changed-source")

    restored = store.load(
        store.default_path(source),
        source_path=source,
        allow_source_mismatch=True,
    )

    assert restored.source_size == source.stat().st_size
    assert restored.source_sha256 == store.sha256_file(source)
