import json
from pathlib import Path

import pytest

from tx_rx.jetson_client import (
    InvalidImageCountError,
    StagingTaskState,
    load_staged_task_package,
    prepare_manual_task,
    scan_staging_tasks,
)
from tx_rx.protocol.models import TASK_ANGLES


def _manual_task(root: Path, task_id: str = "manual_001", count: int = 8) -> Path:
    task_dir = root / task_id
    images_dir = task_dir / "images"
    images_dir.mkdir(parents=True)
    for index in range(count):
        (images_dir / f"{index}.jpg").write_bytes(f"manual-image-{index}".encode())
    return task_dir


def _config(path: Path, staging_root: Path) -> Path:
    path.write_text(
        f'schema_version: "1.0"\nstaging_root: {staging_root}\n'
        'server_url: http://127.0.0.1:8000\nupload_timeout_seconds: 30\n',
        encoding="utf-8",
    )
    return path


def test_prepare_manual_task_completes_eight_images_in_place(tmp_path):
    task_dir = _manual_task(tmp_path)
    before = {path.name: path.read_bytes() for path in (task_dir / "images").iterdir()}

    result = prepare_manual_task(task_dir)

    assert result.staging_dir == task_dir
    assert result.manifest_path.is_file()
    assert result.metadata_json_path.is_file()
    assert result.manifest.angles == TASK_ANGLES
    assert {path.name: path.read_bytes() for path in (task_dir / "images").iterdir()} == before
    metadata = json.loads(result.metadata_json_path.read_text(encoding="utf-8"))
    assert metadata["source"] == "manual"
    assert load_staged_task_package(task_dir).checksum == result.checksum


def test_prepare_manual_task_requires_exact_names(tmp_path):
    task_dir = _manual_task(tmp_path, count=7)
    with pytest.raises(InvalidImageCountError, match="exactly 0.jpg through 7.jpg"):
        prepare_manual_task(task_dir)


def test_scanner_prepares_manual_task_and_reports_partial_task(tmp_path):
    staging_root = tmp_path / "staging"
    complete = _manual_task(staging_root, "manual_complete")
    _manual_task(staging_root, "manual_partial", count=3)
    config = _config(tmp_path / "config.yaml", staging_root)

    tasks = scan_staging_tasks(config)

    by_id = {task.task_id: task for task in tasks}
    assert by_id["manual_complete"].state is StagingTaskState.READY
    assert by_id["manual_complete"].package is not None
    assert (complete / "task.json").is_file()
    assert by_id["manual_partial"].state is StagingTaskState.INCOMPLETE
    assert by_id["manual_partial"].message == "等待照片: 3/8"


def test_scanner_preserves_uploaded_state_across_scans(tmp_path):
    staging_root = tmp_path / "staging"
    task_dir = _manual_task(staging_root)
    prepare_manual_task(task_dir)
    package = load_staged_task_package(task_dir)
    (task_dir / "upload.json").write_text(
        json.dumps({"task_id": "server-1", "checksum": package.checksum}),
        encoding="utf-8",
    )
    config = _config(tmp_path / "config.yaml", staging_root)

    tasks = scan_staging_tasks(config)

    assert tasks[0].state is StagingTaskState.UPLOADED
