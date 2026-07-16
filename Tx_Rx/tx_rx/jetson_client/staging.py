"""Discover and prepare reconstruction tasks in the configured staging queue."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from tx_rx.config import load_config
from tx_rx.jetson_client.task_manifest import (
    CaptureDataError,
    TaskPackageError,
    TaskPackageResult,
    load_staged_task_package,
    prepare_manual_task,
)


class StagingTaskState(str, Enum):
    READY = "ready"
    UPLOADED = "uploaded"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"


@dataclass(frozen=True)
class StagingTask:
    task_id: str
    task_dir: Path
    state: StagingTaskState
    message: str
    package: Optional[TaskPackageResult] = None


def scan_staging_tasks(config_path: Optional[Path] = None) -> List[StagingTask]:
    """Scan configured directories and complete any valid manual eight-image task."""

    root = load_config(config_path).staging_root
    root.mkdir(parents=True, exist_ok=True)
    tasks: List[StagingTask] = []
    task_dirs = sorted((path for path in root.iterdir() if path.is_dir()), key=lambda path: path.name)
    for task_dir in task_dirs:
        try:
            if (task_dir / "task.json").is_file():
                package = load_staged_task_package(task_dir)
            else:
                images_dir = task_dir / "images"
                jpg_count = len(list(images_dir.glob("*.jpg"))) if images_dir.is_dir() else 0
                if jpg_count < 8:
                    tasks.append(
                        StagingTask(
                            task_dir.name,
                            task_dir,
                            StagingTaskState.INCOMPLETE,
                            f"等待照片: {jpg_count}/8",
                        )
                    )
                    continue
                package = prepare_manual_task(task_dir)
            if _has_valid_upload_receipt(task_dir, package):
                tasks.append(StagingTask(task_dir.name, task_dir, StagingTaskState.UPLOADED, "已上传", package))
            else:
                tasks.append(StagingTask(task_dir.name, task_dir, StagingTaskState.READY, "可以上传", package))
        except TaskPackageError as exc:
            tasks.append(StagingTask(task_dir.name, task_dir, StagingTaskState.INVALID, str(exc)))
    return tasks


def _has_valid_upload_receipt(task_dir: Path, package: TaskPackageResult) -> bool:
    receipt_path = task_dir / "upload.json"
    if not receipt_path.is_file():
        return False
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict):
            raise ValueError("receipt must be an object")
        if not str(receipt.get("task_id", "")).strip():
            raise ValueError("task_id is missing")
        if receipt.get("checksum") != package.checksum:
            raise ValueError("checksum does not match task")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise CaptureDataError(f"staging task {task_dir.name}: invalid upload.json: {exc}") from exc
    return True
