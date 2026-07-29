"""JSON/YAML-backed settings with stable, absolute path defaults."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from camera_system_app.infrastructure.paths import AppPaths


@dataclass(frozen=True)
class AppSettings:
    """Settings shared by all application pages and service adapters."""

    schema_version: int
    language: str
    log_level: str
    wsl_service_url: str
    capture_root: str
    transfer_staging_root: str
    result_root: str
    viewer_root: str
    upload_timeout_seconds: int
    request_timeout_seconds: int
    status_poll_interval_seconds: float
    reconstruction_timeout_seconds: int
    download_timeout_seconds: int
    max_ply_size_bytes: int
    start_maximized: bool

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SettingsManager:
    """Load and atomically save the unified settings file."""

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.last_error: Optional[str] = None

    def defaults(self) -> AppSettings:
        project = self.paths.project_root
        return AppSettings(
            schema_version=1,
            language="zh_CN",
            log_level="INFO",
            wsl_service_url="",
            capture_root=str((project / "captures").resolve()),
            transfer_staging_root=str((self.paths.data_dir / "staging").resolve()),
            result_root=str((project / "result").resolve()),
            viewer_root=str((project / "3DGSviewer" / "q3dviewer").resolve()),
            upload_timeout_seconds=300,
            request_timeout_seconds=30,
            status_poll_interval_seconds=2.0,
            reconstruction_timeout_seconds=21600,
            download_timeout_seconds=600,
            max_ply_size_bytes=2147483648,
            start_maximized=True,
        )

    def load(self) -> AppSettings:
        self.last_error = None
        defaults = self.defaults()
        if not self.paths.config_file.exists():
            return defaults
        try:
            payload = self._read_payload()
            if not isinstance(payload, dict):
                raise ValueError("配置根节点必须是对象/映射")
            return self._from_mapping(payload, defaults)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.last_error = str(exc)
            return defaults

    def save(self, values: Mapping[str, Any]) -> AppSettings:
        settings = self._from_mapping(values, self.defaults())
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="settings-",
            suffix=self.paths.config_file.suffix + ".tmp",
            dir=str(self.paths.config_dir),
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                self._write_payload(handle, settings.as_dict())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, str(self.paths.config_file))
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
        return settings

    def _read_payload(self) -> Any:
        with self.paths.config_file.open("r", encoding="utf-8") as handle:
            if self.paths.config_file.suffix.lower() in {".yaml", ".yml"}:
                try:
                    import yaml
                except ImportError as exc:
                    raise ValueError("读取 YAML 配置需要 PyYAML") from exc
                return yaml.safe_load(handle)
            return json.load(handle)

    def _write_payload(self, handle: Any, payload: Mapping[str, Any]) -> None:
        if self.paths.config_file.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError as exc:
                raise ValueError("保存 YAML 配置需要 PyYAML") from exc
            yaml.safe_dump(
                dict(payload),
                handle,
                allow_unicode=True,
                sort_keys=False,
            )
            return
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    def _from_mapping(
        self,
        values: Mapping[str, Any],
        defaults: AppSettings,
    ) -> AppSettings:
        base = defaults.as_dict()
        allowed = set(base)
        base.update({key: value for key, value in values.items() if key in allowed})

        project = self.paths.project_root

        def absolute_path(key: str) -> str:
            value = str(base[key]).strip()
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = project / path
            return str(path.resolve())

        level = str(base["log_level"]).upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            level = defaults.log_level

        def integer(key: str, minimum: int, maximum: int) -> int:
            try:
                return min(max(int(base[key]), minimum), maximum)
            except (TypeError, ValueError):
                return int(getattr(defaults, key))

        def decimal(key: str, minimum: float, maximum: float) -> float:
            try:
                return min(max(float(base[key]), minimum), maximum)
            except (TypeError, ValueError):
                return float(getattr(defaults, key))

        return AppSettings(
            schema_version=1,
            language=str(base["language"]) or defaults.language,
            log_level=level,
            wsl_service_url=str(base["wsl_service_url"]).strip(),
            capture_root=absolute_path("capture_root"),
            transfer_staging_root=absolute_path("transfer_staging_root"),
            result_root=absolute_path("result_root"),
            viewer_root=absolute_path("viewer_root"),
            upload_timeout_seconds=integer("upload_timeout_seconds", 1, 86400),
            request_timeout_seconds=integer("request_timeout_seconds", 1, 86400),
            status_poll_interval_seconds=decimal(
                "status_poll_interval_seconds", 0.1, 3600.0
            ),
            reconstruction_timeout_seconds=integer(
                "reconstruction_timeout_seconds", 1, 604800
            ),
            download_timeout_seconds=integer("download_timeout_seconds", 1, 86400),
            max_ply_size_bytes=integer("max_ply_size_bytes", 1, 1099511627776),
            start_maximized=bool(base["start_maximized"]),
        )
