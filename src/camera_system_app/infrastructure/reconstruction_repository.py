"""Managed task directories with atomic task/status persistence."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from camera_system_app.domain import ApplicationError, ReconstructionJob, TaskPersistenceError


_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")
_TASK_FIELDS = {
    "job_id",
    "capture_id",
    "capture_dir",
    "created_at",
}
_STATUS_FIELDS = set(ReconstructionJob.__dataclass_fields__) - _TASK_FIELDS


class ReconstructionJobRepository:
    """Store each task under ``<root>/<job_id>/task.json|status.json``."""

    def __init__(self, root: Path, legacy_root: Optional[Path] = None) -> None:
        self.root = Path(root).resolve()
        self.legacy_root = Path(legacy_root).resolve() if legacy_root else None
        self._lock = threading.RLock()
        self._logger = logging.getLogger("camera_system_app.tasks")
        self.invalid_task_directories: List[Path] = []

    def task_dir(self, job_id: str) -> Path:
        if not _SAFE_JOB_ID.fullmatch(str(job_id)):
            raise TaskPersistenceError("任务 ID 不安全，无法访问任务目录。", str(job_id))
        return self.root / job_id

    def save(self, job: ReconstructionJob) -> ReconstructionJob:
        """Atomically persist immutable task identity and mutable status."""

        with self._lock:
            try:
                directory = self.task_dir(job.job_id)
                directory.mkdir(parents=True, exist_ok=True)
                payload = job.to_dict()
                task_payload = {
                    "schema_version": 1,
                    **{key: payload[key] for key in _TASK_FIELDS},
                }
                status_payload = {
                    "schema_version": 1,
                    "job_id": job.job_id,
                    **{key: payload[key] for key in _STATUS_FIELDS},
                }
                task_path = directory / "task.json"
                if task_path.exists():
                    existing = self._read_json(task_path)
                    for key in _TASK_FIELDS:
                        if existing.get(key) != task_payload.get(key):
                            raise TaskPersistenceError(
                                "任务身份与已有本地记录冲突，拒绝覆盖。",
                                "{}: {}".format(directory, key),
                            )
                else:
                    self._atomic_json(task_path, task_payload)
                self._atomic_json(directory / "status.json", status_payload)
            except TaskPersistenceError:
                raise
            except (OSError, TypeError, ValueError) as exc:
                raise TaskPersistenceError(
                    "无法保存本地任务状态，请检查磁盘空间和目录权限。",
                    "{}: {}".format(directory, exc),
                ) from exc
        return job

    def get(self, job_id: str) -> ReconstructionJob:
        with self._lock:
            return self._load_directory(self.task_dir(job_id))

    def all(self) -> List[ReconstructionJob]:
        with self._lock:
            self._migrate_legacy()
            if not self.root.is_dir():
                return []
            jobs: List[ReconstructionJob] = []
            self.invalid_task_directories = []
            for directory in self.root.iterdir():
                if not directory.is_dir():
                    continue
                try:
                    jobs.append(self._load_directory(directory))
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    self.invalid_task_directories.append(directory)
                    self._logger.error(
                        "Ignoring invalid task directory %s: %s", directory, exc
                    )
            return sorted(jobs, key=lambda item: item.created_at, reverse=True)

    def find_capture(self, capture_dir: Path) -> Optional[ReconstructionJob]:
        target = Path(capture_dir).resolve()
        return next((job for job in self.all() if job.capture_dir == target), None)

    def register(self, job: ReconstructionJob) -> ReconstructionJob:
        """Create once or return the existing task for the same capture."""

        with self._lock:
            existing = self.find_capture(job.capture_dir)
            if existing is not None:
                return existing
            directory = self.task_dir(job.job_id)
            if directory.exists():
                if not (directory / "status.json").exists() and (
                    directory / "task.json"
                ).exists():
                    self.save(job)
                loaded = self._load_directory(directory)
                if loaded.capture_dir != job.capture_dir:
                    raise TaskPersistenceError(
                        "本地任务 ID 冲突，未创建重复任务。",
                        job.job_id,
                    )
                return loaded
            return self.save(job)

    def _load_directory(self, directory: Path) -> ReconstructionJob:
        task = self._read_json(directory / "task.json")
        status = self._read_json(directory / "status.json")
        if task.get("job_id") != directory.name or status.get("job_id") != directory.name:
            raise ValueError("task identity does not match directory name")
        payload: Dict[str, Any] = {
            key: value for key, value in task.items() if key in _TASK_FIELDS
        }
        payload.update(
            {
                key: value
                for key, value in status.items()
                if key in _STATUS_FIELDS
            }
        )
        return ReconstructionJob.from_dict(payload)

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        if not isinstance(payload, dict):
            raise ValueError("{} must contain an object".format(path))
        return payload

    @staticmethod
    def _atomic_json(path: Path, payload: Dict[str, Any]) -> None:
        descriptor, temporary = tempfile.mkstemp(
            prefix=".{}-".format(path.stem),
            suffix=".json.tmp",
            dir=str(path.parent),
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, str(path))
            directory_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def _migrate_legacy(self) -> None:
        if self.legacy_root is None or not self.legacy_root.is_dir():
            return
        for path in self.legacy_root.glob("*.json"):
            try:
                with path.open("r", encoding="utf-8") as stream:
                    job = ReconstructionJob.from_dict(json.load(stream))
                if not self.task_dir(job.job_id).exists():
                    self.save(job)
            except (ApplicationError, OSError, ValueError, TypeError, KeyError) as exc:
                self._logger.error("Cannot migrate legacy task %s: %s", path, exc)
