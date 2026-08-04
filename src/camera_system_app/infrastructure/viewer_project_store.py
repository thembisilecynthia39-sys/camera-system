"""Atomic persistence for 3DGS viewer sidecar projects."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Optional, Union

from camera_system_app.domain.viewer import ViewerProject, ViewerValidationError


PathLike = Union[str, Path]


class ViewerProjectStoreError(RuntimeError):
    """Base error for sidecar operations safe to present in the UI."""

    def __init__(self, message: str) -> None:
        self.user_message = message
        super().__init__(message)


class ViewerProjectNotFoundError(ViewerProjectStoreError):
    """The requested sidecar does not exist."""


class ViewerProjectFormatError(ViewerProjectStoreError):
    """The sidecar is not valid JSON or does not contain viewer state."""


class ViewerProjectSourceMismatchError(ViewerProjectStoreError):
    """The sidecar identity does not match the currently opened source."""


class ViewerProjectStore:
    """Read and write .splatview.json files without touching the source PLY."""

    @staticmethod
    def default_path(source_path: PathLike) -> Path:
        """Return the sidecar path beside a source file."""

        return Path(source_path).with_suffix(".splatview.json")

    @staticmethod
    def sha256_file(
        path: PathLike,
        chunk_size: int = 1024 * 1024,
        cancel_check=None,
    ) -> str:
        """Hash a source file in bounded memory."""

        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            while True:
                if cancel_check is not None and cancel_check():
                    raise InterruptedError("viewer source hashing cancelled")
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def save(self, project: ViewerProject, sidecar_path: Optional[PathLike] = None) -> Path:
        """Atomically publish a JSON sidecar and return its final path."""

        if not isinstance(project, ViewerProject):
            raise ViewerProjectFormatError("viewer project must be a ViewerProject value")
        target = Path(sidecar_path) if sidecar_path is not None else self.default_path(project.source_path)
        target = target.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            project.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        temporary_path = None  # type: Optional[Path]
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(target.parent),
                prefix=".{}.".format(target.name),
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temporary_path), str(target))
            temporary_path = None
        except OSError as exc:
            raise ViewerProjectStoreError(
                "无法保存查看器项目：{}".format(exc)
            )
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except OSError:
                    pass
        return target

    def load(
        self,
        sidecar_path: PathLike,
        *,
        source_path: Optional[PathLike] = None,
        allow_source_mismatch: bool = False,
        source_identity=None,
    ) -> ViewerProject:
        """Load a project and optionally verify it against the current source."""

        sidecar = Path(sidecar_path)
        if not sidecar.is_file():
            raise ViewerProjectNotFoundError(
                "找不到查看器项目文件：{}".format(sidecar)
            )
        try:
            raw = json.loads(sidecar.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("root must be an object")
            project = ViewerProject.from_dict(raw)
        except (OSError, ValueError, TypeError, KeyError, ViewerValidationError) as exc:
            if isinstance(exc, ViewerValidationError):
                detail = str(exc)
            else:
                detail = "{}".format(exc)
            raise ViewerProjectFormatError(
                "查看器项目文件格式无效：{}".format(detail)
            )

        if source_path is None:
            return project
        source = Path(source_path)
        if not source.is_file():
            raise ViewerProjectSourceMismatchError(
                "源文件不存在，无法验证查看器项目：{}".format(source)
            )
        if source_identity is None:
            actual_size = source.stat().st_size
            actual_sha256 = self.sha256_file(source)
        else:
            try:
                actual_size = int(source_identity[0])
                actual_sha256 = str(source_identity[1]).lower()
            except (IndexError, TypeError, ValueError):
                raise ViewerProjectSourceMismatchError(
                    "源文件身份信息无效，无法验证查看器项目：{}".format(source)
                )
            if actual_size < 0 or len(actual_sha256) != 64:
                raise ViewerProjectSourceMismatchError(
                    "源文件身份信息无效，无法验证查看器项目：{}".format(source)
                )
        matches = (
            project.source_size == actual_size
            and project.source_sha256.lower() == actual_sha256
        )
        if not matches and not allow_source_mismatch:
            raise ViewerProjectSourceMismatchError(
                "源文件已 changed，查看器项目未应用：{}".format(source)
            )
        return replace(
            project,
            source_path=str(source.resolve()),
            source_size=actual_size,
            source_sha256=actual_sha256,
        )


__all__ = [
    "ViewerProjectFormatError",
    "ViewerProjectNotFoundError",
    "ViewerProjectSourceMismatchError",
    "ViewerProjectStore",
    "ViewerProjectStoreError",
]
