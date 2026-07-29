"""Release entry-point and packaging regression tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

from camera_system_app.bootstrap import build_context


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run(*args: str, env=None, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(PROJECT_ROOT / args[0]), *args[1:]],
        cwd="/",
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def test_yaml_settings_load_and_save_atomically(tmp_path, monkeypatch):
    config = tmp_path / "settings.yaml"
    config.write_text(
        "schema_version: 1\n"
        "wsl_service_url: http://192.0.2.10:8000\n"
        "capture_root: captures/test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))

    context = build_context(str(PROJECT_ROOT), str(config))
    assert context.settings.wsl_service_url == "http://192.0.2.10:8000"
    assert Path(context.settings.capture_root) == PROJECT_ROOT / "captures" / "test"

    saved = context.settings_manager.save(
        {**context.settings.as_dict(), "log_level": "DEBUG"}
    )
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert saved.log_level == "DEBUG"
    assert payload["log_level"] == "DEBUG"
    assert not list(tmp_path.glob("*.tmp"))


def test_launcher_supports_version_and_is_cwd_independent(tmp_path):
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
        }
    )
    result = _run("scripts/jetson/run.sh", "--version", env=env)
    assert result.returncode == 0, result.stderr
    assert "Camera System 0.1.0" in result.stdout


def test_installer_renders_working_desktop_entry_without_bashrc_change(tmp_path):
    home = tmp_path / "home"
    desktop = home / "Desktop"
    bashrc = home / ".bashrc"
    home.mkdir()
    bashrc.write_text("# keep-me\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_DESKTOP_DIR": str(desktop),
        }
    )

    result = _run(
        "scripts/jetson/install.sh",
        "--skip-system-packages",
        "--skip-python-deps",
        env=env,
    )

    assert result.returncode == 0, result.stderr
    entry = (desktop / "camera-system.desktop").read_text(encoding="utf-8")
    assert str(PROJECT_ROOT / "scripts" / "jetson" / "run.sh") in entry
    assert "@APP_ROOT@" not in entry
    assert os.access(desktop / "camera-system.desktop", os.X_OK)
    assert bashrc.read_text(encoding="utf-8") == "# keep-me\n"
    assert (tmp_path / "config" / "camera-system" / "settings.yaml").is_file()


def test_release_script_creates_relocatable_app_directory(tmp_path):
    result = _run(
        "scripts/jetson/release.sh",
        "--output",
        str(tmp_path),
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    package = tmp_path / "camera-system-0.1.0-jetson-arm64"

    assert (package / "scripts/jetson/run.sh").is_file()
    assert (package / "packaging/linux/camera-system.desktop").is_file()
    assert (package / "resources/icons/camera-system.svg").is_file()
    assert (package / "requirements/jetson.txt").is_file()
    assert Path(str(package) + ".tar.gz").is_file()
    assert Path(str(package) + ".tar.gz.sha256").is_file()
    assert not (package / ".git").exists()
    assert not (package / "captures").exists()
    assert not list(package.rglob("__pycache__"))
