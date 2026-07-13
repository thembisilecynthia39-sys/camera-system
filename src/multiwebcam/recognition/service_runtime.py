from __future__ import annotations
"""Runtime helpers shared by subprocess inference tools."""

import os
from pathlib import Path

SYSTEM_LIBFFI_SO7 = Path("/usr/lib/aarch64-linux-gnu/libffi.so.7")
MPL_CONFIG_DIR = "/tmp/multiwebcam-mpl"

PYTHON_ENV_OVERRIDES = (
    "PYTHONPATH",
    "PYTHONHOME",
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "CONDA_DEFAULT_ENV",
    "CONDA_PROMPT_MODIFIER",
)


def build_service_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build a clean but Jetson-friendly inference service environment.

    The service must ignore the main app's Python path and virtualenv markers,
    but it must still see the user's site-packages. On this Jetson, NVIDIA's
    PyTorch wheel is installed under ``~/.local`` while the service interpreter
    is ``/usr/bin/python3`` through ``.venv-jetson``.
    """

    env = dict(os.environ if base_env is None else base_env)
    for key in PYTHON_ENV_OVERRIDES:
        env.pop(key, None)
    env.pop("PYTHONNOUSERSITE", None)
    env["MPLCONFIGDIR"] = MPL_CONFIG_DIR
    _prepend_ld_preload(env, SYSTEM_LIBFFI_SO7)
    return env


def _prepend_ld_preload(env: dict[str, str], library_path: Path) -> None:
    if not library_path.exists():
        return
    preload = env.get("LD_PRELOAD", "").strip()
    preload_parts = [part for part in preload.split(":") if part]
    if str(library_path) not in preload_parts:
        preload_parts.insert(0, str(library_path))
    env["LD_PRELOAD"] = ":".join(preload_parts)
