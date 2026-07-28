"""Thread-safe, disk-backed receiver task state."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from gaussianobject_rx.protocol.models import TaskStatus
from gaussianobject_rx.server.files import atomic_write_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskRecord:
    task_id: str
    capture_id: str
    checksum: str
    task_dir: str
    package_dir: str
    input_dir: str
    status: str
    progress: int
    message: str
    created_at: str
    updated_at: str
    expected_output_ply: str = ""
    result_path: str = ""
    result_size: int = 0
    result_sha256: str = ""
    error: str = ""
    log_summary: str = ""
    result_acknowledged_at: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class TaskRegistry:
    def __init__(self, task_root: Path) -> None:
        self.task_root = Path(task_root)
        self.task_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._records: Dict[str, TaskRecord] = {}
        self._checksum_index: Dict[str, str] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        for path in self.task_root.glob("*/state.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                record = TaskRecord(**payload)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            if record.status in {
                TaskStatus.UPLOADING.value,
                TaskStatus.RUNNING_COLMAP.value,
                TaskStatus.RUNNING_3DGS.value,
            }:
                record.status = TaskStatus.READY.value
                record.progress = 5
                record.message = "receiver restarted; task queued for automatic recovery"
                record.error = ""
                record.updated_at = utc_now()
                atomic_write_json(path, record.to_dict())
            self._records[record.task_id] = record
            self._checksum_index[record.checksum] = record.task_id

    def find_by_checksum(self, checksum: str) -> Optional[TaskRecord]:
        with self._lock:
            task_id = self._checksum_index.get(checksum)
            return self._copy(self._records[task_id]) if task_id else None

    def get(self, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            record = self._records.get(task_id)
            return self._copy(record) if record else None

    def all(self) -> List[TaskRecord]:
        with self._lock:
            return [self._copy(record) for record in self._records.values()]

    def add(self, record: TaskRecord) -> TaskRecord:
        with self._lock:
            existing = self._checksum_index.get(record.checksum)
            if existing:
                return self._copy(self._records[existing])
            self._records[record.task_id] = record
            self._checksum_index[record.checksum] = record.task_id
            self._save(record)
            return self._copy(record)

    def update(self, task_id: str, **changes: object) -> TaskRecord:
        with self._lock:
            record = self._records[task_id]
            for name, value in changes.items():
                if not hasattr(record, name):
                    raise AttributeError(name)
                setattr(record, name, value)
            record.updated_at = utc_now()
            self._save(record)
            return self._copy(record)

    def _save(self, record: TaskRecord) -> None:
        atomic_write_json(Path(record.task_dir) / "state.json", record.to_dict())

    @staticmethod
    def _copy(record: TaskRecord) -> TaskRecord:
        return TaskRecord(**record.to_dict())
