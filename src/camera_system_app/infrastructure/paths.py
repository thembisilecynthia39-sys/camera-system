"""Stable application paths that never depend on the current directory."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional


APP_SLUG = "camera-system"


def _expanded_path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _xdg_path(
    environment: Mapping[str, str],
    variable: str,
    fallback: Path,
) -> Path:
    value = environment.get(variable)
    return Path(value).expanduser().resolve() if value else fallback


@dataclass(frozen=True)
class AppPaths:
    """All paths used by the shell and its future service adapters."""

    package_root: Path
    project_root: Path
    config_dir: Path
    config_file: Path
    data_dir: Path
    state_dir: Path
    cache_dir: Path
    log_dir: Path
    log_file: Path

    @classmethod
    def discover(
        cls,
        project_root: Optional[str] = None,
        config_file: Optional[str] = None,
        environment: Optional[Mapping[str, str]] = None,
    ) -> "AppPaths":
        env = dict(os.environ if environment is None else environment)
        package_root = Path(__file__).resolve().parents[1]
        source_candidate = package_root.parents[1]
        source_workspace = (
            source_candidate
            if (source_candidate / "multiwebcam").is_dir()
            and (source_candidate / "Tx_Rx").is_dir()
            else None
        )

        home = Path(env.get("HOME", str(Path.home()))).expanduser().resolve()
        config_home = _xdg_path(env, "XDG_CONFIG_HOME", home / ".config")
        data_home = _xdg_path(env, "XDG_DATA_HOME", home / ".local" / "share")
        state_home = _xdg_path(env, "XDG_STATE_HOME", home / ".local" / "state")
        cache_home = _xdg_path(env, "XDG_CACHE_HOME", home / ".cache")

        config_dir = config_home / APP_SLUG
        data_dir = data_home / APP_SLUG
        state_dir = state_home / APP_SLUG
        cache_dir = cache_home / APP_SLUG

        requested_root = project_root or env.get("CAMERA_SYSTEM_PROJECT_ROOT")
        if requested_root:
            base = source_workspace or data_dir
            resolved_project = _expanded_path(requested_root, base)
        elif source_workspace is not None:
            resolved_project = source_workspace
        else:
            resolved_project = data_dir / "workspace"

        requested_config = config_file or env.get("CAMERA_SYSTEM_CONFIG")
        resolved_config = (
            _expanded_path(requested_config, resolved_project)
            if requested_config
            else config_dir / "settings.json"
        )
        resolved_config_dir = resolved_config.parent
        log_dir = state_dir / "logs"
        return cls(
            package_root=package_root,
            project_root=resolved_project,
            config_dir=resolved_config_dir,
            config_file=resolved_config,
            data_dir=data_dir,
            state_dir=state_dir,
            cache_dir=cache_dir,
            log_dir=log_dir,
            log_file=log_dir / "camera-system.log",
        )

    def prepare_runtime_directories(self) -> None:
        """Create only application-owned runtime directories."""

        for path in (self.config_dir, self.data_dir, self.state_dir, self.cache_dir, self.log_dir):
            path.mkdir(parents=True, exist_ok=True)

