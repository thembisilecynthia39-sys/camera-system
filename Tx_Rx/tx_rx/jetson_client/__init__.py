"""Jetson-side task preparation helpers."""

from tx_rx.jetson_client.task_manifest import (
    CaptureDataError,
    InvalidImageCountError,
    MissingCaptureFileError,
    TaskPackageError,
    TaskPackageResult,
    build_configured_task_package,
    build_task_package,
    load_staged_task_package,
    prepare_manual_task,
)
from tx_rx.jetson_client.staging import StagingTask, StagingTaskState, scan_staging_tasks
from tx_rx.jetson_client.uploader import TaskUploadError, TaskUploadResult, upload_staged_task

__all__ = [
    "CaptureDataError",
    "InvalidImageCountError",
    "MissingCaptureFileError",
    "TaskPackageError",
    "TaskPackageResult",
    "build_configured_task_package",
    "build_task_package",
    "load_staged_task_package",
    "prepare_manual_task",
    "StagingTask",
    "StagingTaskState",
    "scan_staging_tasks",
    "TaskUploadError",
    "TaskUploadResult",
    "upload_staged_task",
]
