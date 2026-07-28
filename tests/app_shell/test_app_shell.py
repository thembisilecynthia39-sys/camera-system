"""Import, path, configuration, and diagnostic tests for the unified shell."""

from __future__ import annotations

import json
import os
from pathlib import Path

from camera_system_app.application.controller import ApplicationController
from camera_system_app.application.diagnostics import report_as_dict
from camera_system_app.bootstrap import build_context
from camera_system_app.infrastructure.paths import AppPaths
from camera_system_app.main import main


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _environment(tmp_path: Path):
    return {
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
    }


def test_paths_do_not_depend_on_current_directory(tmp_path, monkeypatch):
    environment = _environment(tmp_path)
    first = AppPaths.discover(environment=environment)
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    second = AppPaths.discover(environment=environment)

    assert first.project_root == PROJECT_ROOT
    assert second.project_root == PROJECT_ROOT
    assert first.config_file == second.config_file


def test_relative_config_path_is_resolved_from_project_root(tmp_path):
    paths = AppPaths.discover(
        project_root=str(PROJECT_ROOT),
        config_file="local/settings.json",
        environment=_environment(tmp_path),
    )

    assert paths.config_file == PROJECT_ROOT / "local" / "settings.json"


def test_diagnostics_do_not_require_camera_or_wsl(tmp_path, monkeypatch):
    environment = _environment(tmp_path)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    context = build_context(project_root=str(PROJECT_ROOT))
    controller = ApplicationController(
        context.paths,
        context.settings_manager,
        context.settings,
        context.logs,
    )

    payload = report_as_dict(controller.diagnose())

    assert payload["usable"] is True
    assert any(check["name"] == "摄像头" for check in payload["checks"])
    assert any(check["name"] == "WSL 重建服务" for check in payload["checks"])


def test_diagnose_cli_returns_json_without_importing_ui(tmp_path, monkeypatch, capsys):
    environment = _environment(tmp_path)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    exit_code = main(
        [
            "--diagnose",
            "--json",
            "--project-root",
            str(PROJECT_ROOT),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["usable"] is True


def test_settings_are_saved_atomically_with_absolute_paths(tmp_path, monkeypatch):
    environment = _environment(tmp_path)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    context = build_context(project_root=str(PROJECT_ROOT))

    saved = context.settings_manager.save(
        {
            **context.settings.as_dict(),
            "capture_root": "captures/new",
            "wsl_service_url": "http://192.0.2.10:8000",
        }
    )

    assert Path(saved.capture_root).is_absolute()
    assert Path(saved.capture_root) == PROJECT_ROOT / "captures" / "new"
    assert context.paths.config_file.exists()
    assert not list(context.paths.config_dir.glob("*.tmp"))

