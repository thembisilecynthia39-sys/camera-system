"""Subprocess smoke test for a complete offscreen Qt event loop."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_qt_shell_starts_without_hardware_or_wsl(tmp_path):
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(tmp_path / "home"),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "QT_QPA_PLATFORM": "offscreen",
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
        }
    )
    preload = Path("/lib/aarch64-linux-gnu/libGLdispatch.so.0")
    if preload.exists():
        environment["LD_PRELOAD"] = str(preload)

    completed = subprocess.run(
        [
            "/usr/bin/python3",
            "-m",
            "camera_system_app",
            "--project-root",
            str(PROJECT_ROOT),
            "--windowed",
            "--smoke-test-ms",
            "100",
        ],
        cwd=str(tmp_path),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=15,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr

