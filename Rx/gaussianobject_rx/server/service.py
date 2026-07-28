"""Receiver business operations independent of HTTP transport."""

from __future__ import annotations

import re
import shutil
import logging
from pathlib import Path

from gaussianobject_rx.protocol.models import TaskStatus
from gaussianobject_rx.server.archive_validator import validate_and_extract_archive
from gaussianobject_rx.server.baseline_adapter import prepare_baseline_input
from gaussianobject_rx.server.config import ReceiverConfig
from gaussianobject_rx.server.reconstruction import ReconstructionManager
from gaussianobject_rx.server.task_registry import TaskRecord, TaskRegistry, utc_now


logger = logging.getLogger(__name__)


class ReceiverService:
    def __init__(self, config: ReceiverConfig) -> None:
        self.config = config
        self.registry = TaskRegistry(config.task_root)
        self.reconstruction = ReconstructionManager(config, self.registry)
        self._recover_ready_tasks()

    def ingest_archive(self, archive_path: Path, checksum: str) -> tuple[TaskRecord, bool]:
        existing = self.registry.find_by_checksum(checksum)
        if existing is not None:
            return self._submit_if_ready(existing), True

        task_id = f"task-{checksum}"
        temporary_task_dir = self.config.task_root / f".{task_id}.part"
        if temporary_task_dir.exists():
            raise ValueError(f"unfinished task directory already exists: {temporary_task_dir}")
        temporary_task_dir.mkdir(parents=True)
        task_dir = temporary_task_dir
        try:
            validated = validate_and_extract_archive(
                archive_path,
                temporary_task_dir / "package",
                checksum,
                self.config.max_extracted_size_bytes,
            )
            task_dir = _allocate_task_dir(self.config.task_root, validated.manifest.capture_id)
            temporary_task_dir.rename(task_dir)
            package_dir = task_dir / "package"
            input_images = prepare_baseline_input(
                package_dir,
                task_dir,
                validated.image_dimensions,
            )
            now = utc_now()
            record = TaskRecord(
                task_id=task_id,
                capture_id=validated.manifest.capture_id,
                checksum=checksum,
                task_dir=str(task_dir),
                package_dir=str(package_dir),
                input_dir=str(input_images),
                status=TaskStatus.READY.value,
                progress=0,
                message="upload validated and baseline input prepared",
                created_at=now,
                updated_at=now,
            )
            return self._submit_if_ready(self.registry.add(record)), False
        except Exception:
            shutil.rmtree(task_dir, ignore_errors=True)
            if task_dir != temporary_task_dir:
                shutil.rmtree(temporary_task_dir, ignore_errors=True)
            raise

    def stop(self) -> None:
        self.reconstruction.stop()

    def _submit_if_ready(self, record: TaskRecord) -> TaskRecord:
        if record.status == TaskStatus.READY.value:
            return self.reconstruction.submit(record.task_id)
        return record

    def _recover_ready_tasks(self) -> None:
        for record in self.registry.all():
            if record.status != TaskStatus.READY.value:
                continue
            try:
                self.reconstruction.submit(record.task_id)
            except Exception as exc:
                logger.warning("could not automatically recover task %s: %s", record.task_id, exc)


def _allocate_task_dir(task_root: Path, capture_id: str) -> Path:
    """Return a readable, non-conflicting directory for a validated capture."""

    name = re.sub(r"[^A-Za-z0-9._-]+", "_", capture_id).strip("._-") or "capture"
    candidate = task_root / name
    suffix = 2
    while candidate.exists():
        candidate = task_root / f"{name}-{suffix}"
        suffix += 1
    return candidate
