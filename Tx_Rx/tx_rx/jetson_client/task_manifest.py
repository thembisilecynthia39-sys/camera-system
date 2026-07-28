"""Build a deterministic eight-image reconstruction staging package."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from pydantic import ValidationError

from tx_rx.config import load_config
from tx_rx.protocol.models import TASK_ANGLES, TaskFile, TaskImage, TaskManifest

logger = logging.getLogger(__name__)

_REQUIRED_CAPTURE_FILES = ("metadata.csv", "quality.csv", "cameras.json")
_SCHEMA_VERSION = "1.0"
_JPEG_SUFFIXES = {".jpg", ".jpeg"}
CancelCheck = Callable[[], bool]


class TaskPackageError(Exception):
    """Base error raised while preparing a reconstruction task."""


class CaptureDataError(TaskPackageError):
    """The capture metadata cannot describe one complete task."""


class MissingCaptureFileError(TaskPackageError):
    """A required capture file is absent."""


class InvalidImageCountError(CaptureDataError):
    """A complete set of exactly eight image records cannot be located."""


@dataclass(frozen=True)
class TaskPackageResult:
    capture_id: str
    staging_dir: Path
    images_dir: Path
    manifest_path: Path
    metadata_json_path: Path
    image_count: int
    checksum: str
    manifest: TaskManifest


@dataclass(frozen=True)
class _CaptureImageRecord:
    angle: int
    source_filename: str
    frame_id: str


def prepare_manual_task(
    task_dir: Path,
    cancel_check: Optional[CancelCheck] = None,
) -> TaskPackageResult:
    """Complete a manual task containing only ``images/0.jpg`` through ``7.jpg``."""

    task_dir = Path(task_dir)
    _check_cancel(cancel_check)
    task_id = task_dir.name or str(task_dir)
    if not task_dir.is_dir():
        raise MissingCaptureFileError(f"manual task {task_id}: directory does not exist: {task_dir}")
    if (task_dir / "task.json").exists():
        return load_staged_task_package(task_dir, cancel_check=cancel_check)

    images_dir = task_dir / "images"
    if not images_dir.is_dir():
        raise MissingCaptureFileError(f"manual task {task_id}: images directory does not exist: {images_dir}")
    actual_jpgs = {path.name for path in images_dir.glob("*.jpg") if path.is_file()}
    expected_jpgs = {f"{index}.jpg" for index in range(8)}
    if actual_jpgs != expected_jpgs:
        raise InvalidImageCountError(
            f"manual task {task_id}: images must be exactly 0.jpg through 7.jpg; got {sorted(actual_jpgs)}"
        )

    image_models: List[TaskImage] = []
    for index, angle in enumerate(TASK_ANGLES):
        _check_cancel(cancel_check)
        path = images_dir / f"{index}.jpg"
        if path.stat().st_size <= 0:
            raise CaptureDataError(f"manual task {task_id}: image is empty: {path}")
        image_models.append(
            TaskImage(
                index=index,
                angle=angle,
                filename=path.name,
                source_filename=path.name,
                sha256=_sha256_file(path, cancel_check),
                size_bytes=path.stat().st_size,
            )
        )

    metadata_payload: Dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "capture_id": task_id,
        "image_count": 8,
        "angles": TASK_ANGLES,
        "source": "manual",
        "images": [
            {
                "index": image.index,
                "angle": image.angle,
                "filename": image.filename,
                "source_filename": image.source_filename,
            }
            for image in image_models
        ],
    }
    metadata_path = task_dir / "metadata.json"
    _atomic_write_json(metadata_path, metadata_payload, task_id)
    included_paths = [metadata_path, *(images_dir / f"{index}.jpg" for index in range(8))]
    task_files = _describe_files(
        task_dir,
        included_paths,
        cancel_check=cancel_check,
    )
    checksum = _task_checksum(task_files)
    manifest = TaskManifest(
        schema_version=_SCHEMA_VERSION,
        capture_id=task_id,
        image_count=8,
        angles=list(TASK_ANGLES),
        images=image_models,
        files=task_files,
        created_at=datetime.now(timezone.utc),
        checksum=checksum,
    )
    _atomic_write_json(task_dir / "task.json", manifest.model_dump(mode="json"), task_id)
    logger.info("Prepared manual task %s at %s", task_id, task_dir)
    return _result_from_manifest(task_dir, manifest)


def build_configured_task_package(
    capture_dir: Path,
    config_path: Optional[Path] = None,
    selected_images: Optional[Sequence[str]] = None,
    cancel_check: Optional[CancelCheck] = None,
) -> TaskPackageResult:
    """Build a package in the staging root fixed by ``config.yaml``."""

    config = load_config(config_path)
    return build_task_package(
        capture_dir,
        config.staging_root,
        selected_images,
        cancel_check=cancel_check,
    )


def load_staged_task_package(
    staging_dir: Path,
    cancel_check: Optional[CancelCheck] = None,
) -> TaskPackageResult:
    """Validate and open a completed staging directory for future upload."""

    staging_dir = Path(staging_dir)
    return _load_existing_package(
        staging_dir,
        staging_dir.name or str(staging_dir),
        cancel_check=cancel_check,
    )


def build_task_package(
    capture_dir: Path,
    output_root: Path,
    selected_images: Optional[Sequence[str]] = None,
    cancel_check: Optional[CancelCheck] = None,
) -> TaskPackageResult:
    """Create or return a validated staging package derived from ``capture_dir``.

    The input directory is only read. ``selected_images`` may explicitly name
    eight JPEGs under ``capture_dir/images``; their given order maps to indexes
    0 through 7. Without a selection, an exactly-eight directory is mapped by
    filename order and multi-round directories retain metadata selection.
    """

    capture_dir = Path(capture_dir)
    output_root = Path(output_root)
    _check_cancel(cancel_check)
    capture_id = capture_dir.name or str(capture_dir)
    images_source_dir = _validate_capture_layout(capture_dir, capture_id)

    staging_dir = output_root / capture_id
    if staging_dir.exists():
        return _load_existing_package(
            staging_dir,
            capture_id,
            cancel_check=cancel_check,
        )

    records = _read_task_records(
        capture_dir / "metadata.csv", images_source_dir, capture_id, selected_images
    )
    output_root.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(prefix=f".{capture_id}-", dir=str(output_root)))

    try:
        _check_cancel(cancel_check)
        images_dir = temporary_dir / "images"
        images_dir.mkdir()
        image_models: List[TaskImage] = []

        for index, record in enumerate(records):
            _check_cancel(cancel_check)
            source_path = images_source_dir / record.source_filename
            if not source_path.is_file():
                raise MissingCaptureFileError(
                    f"capture {capture_id}: source image does not exist: {source_path}"
                )
            destination = images_dir / f"{index}.jpg"
            _copy_capture_file(
                source_path,
                destination,
                capture_id,
                cancel_check=cancel_check,
            )
            image_models.append(
                TaskImage(
                    index=index,
                    angle=record.angle,
                    filename=destination.name,
                    source_filename=record.source_filename,
                    sha256=_sha256_file(destination, cancel_check),
                    size_bytes=destination.stat().st_size,
                )
            )

        for filename in _REQUIRED_CAPTURE_FILES:
            _check_cancel(cancel_check)
            source = capture_dir / filename
            if source.is_file():
                _copy_capture_file(
                    source,
                    temporary_dir / filename,
                    capture_id,
                    cancel_check=cancel_check,
                )

        metadata_payload: Dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "capture_id": capture_id,
            "image_count": 8,
            "angles": TASK_ANGLES,
            "images": [
                {
                    "index": image.index,
                    "angle": image.angle,
                    "filename": image.filename,
                    "source_filename": image.source_filename,
                    "frame_id": records[image.index].frame_id,
                }
                for image in image_models
            ],
        }
        metadata_json_path = temporary_dir / "metadata.json"
        _atomic_write_json(metadata_json_path, metadata_payload, capture_id)

        included_paths = [path for path in temporary_dir.rglob("*") if path.is_file()]
        task_files = _describe_files(
            temporary_dir,
            included_paths,
            cancel_check=cancel_check,
        )
        checksum = _task_checksum(task_files)
        manifest = TaskManifest(
            schema_version=_SCHEMA_VERSION,
            capture_id=capture_id,
            image_count=8,
            angles=list(TASK_ANGLES),
            images=image_models,
            files=task_files,
            created_at=datetime.now(timezone.utc),
            checksum=checksum,
        )
        _atomic_write_json(
            temporary_dir / "task.json",
            manifest.model_dump(mode="json"),
            capture_id,
        )

        _check_cancel(cancel_check)
        os.replace(str(temporary_dir), str(staging_dir))
        logger.info("Created task package %s at %s", capture_id, staging_dir)
        return _result_from_manifest(staging_dir, manifest)
    except TaskPackageError:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise
    except (OSError, ValueError, ValidationError, TypeError) as exc:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise TaskPackageError(f"capture {capture_id}: task package generation failed: {exc}") from exc


def _validate_capture_layout(capture_dir: Path, capture_id: str) -> Path:
    if not capture_dir.is_dir():
        raise MissingCaptureFileError(f"capture {capture_id}: capture directory does not exist: {capture_dir}")
    nested_images = capture_dir / "images"
    images_dir = nested_images if nested_images.is_dir() else capture_dir
    if not any(path.is_file() and path.suffix.lower() in _JPEG_SUFFIXES for path in images_dir.iterdir()):
        raise MissingCaptureFileError(f"capture {capture_id}: no JPEG images found in {images_dir}")
    return images_dir


def _read_task_records(
    metadata_path: Path,
    images_dir: Path,
    capture_id: str,
    selected_images: Optional[Sequence[str]] = None,
) -> List[_CaptureImageRecord]:
    if selected_images is not None:
        if len(selected_images) != 8:
            raise InvalidImageCountError(
                f"capture {capture_id}: exactly 8 selected images are required; got {len(selected_images)}"
            )
        normalized: List[str] = []
        for selected in selected_images:
            name = str(selected).strip()
            path = Path(name)
            if not name or path.name != name or path.suffix.lower() not in _JPEG_SUFFIXES:
                raise CaptureDataError(
                    f"capture {capture_id}: selected image must be a .jpg/.jpeg filename under images/: {selected!r}"
                )
            if not (images_dir / name).is_file():
                raise MissingCaptureFileError(
                    f"capture {capture_id}: selected image does not exist: {images_dir / name}"
                )
            normalized.append(name)
        if len(set(normalized)) != 8:
            raise CaptureDataError(f"capture {capture_id}: selected image filenames must be unique")
        return [
            _CaptureImageRecord(angle, name, str(index + 1))
            for index, (angle, name) in enumerate(zip(TASK_ANGLES, normalized))
        ]

    image_paths = sorted(
        (path for path in images_dir.iterdir() if path.is_file() and path.suffix.lower() in _JPEG_SUFFIXES),
        key=lambda path: path.name,
    )
    if len(image_paths) == 8:
        return [
            _CaptureImageRecord(angle, path.name, str(index + 1))
            for index, (angle, path) in enumerate(zip(TASK_ANGLES, image_paths))
        ]

    if not metadata_path.is_file():
        raise InvalidImageCountError(
            f"capture {capture_id}: found {len(image_paths)} JPEGs; select exactly 8 with --image"
        )

    try:
        with metadata_path.open("r", newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            required_fields = {"frame_id", "angle_deg", "image_name"}
            actual_fields = set(reader.fieldnames or [])
            missing_fields = sorted(required_fields - actual_fields)
            if missing_fields:
                raise CaptureDataError(
                    f"capture {capture_id}: {metadata_path} is missing fields: {', '.join(missing_fields)}"
                )
            rows = list(reader)
    except UnicodeError as exc:
        raise CaptureDataError(f"capture {capture_id}: cannot decode {metadata_path}: {exc}") from exc
    except OSError as exc:
        raise CaptureDataError(f"capture {capture_id}: cannot read {metadata_path}: {exc}") from exc

    if len(rows) < 8:
        raise InvalidImageCountError(
            f"capture {capture_id}: {metadata_path} has {len(rows)} image records; 8 are required"
        )

    latest_rows = rows[-8:]
    records: List[_CaptureImageRecord] = []
    for row_number, row in enumerate(latest_rows, start=len(rows) - 7):
        raw_angle = (row.get("angle_deg") or "").strip()
        source_filename = (row.get("image_name") or "").strip()
        frame_id = (row.get("frame_id") or "").strip()
        try:
            angle = int(raw_angle)
        except ValueError as exc:
            raise CaptureDataError(
                f"capture {capture_id}: invalid angle_deg {raw_angle!r} at {metadata_path}:{row_number}"
            ) from exc
        if not source_filename:
            raise CaptureDataError(
                f"capture {capture_id}: empty image_name at {metadata_path}:{row_number}"
            )
        source_path = Path(source_filename)
        if source_path.name != source_filename or source_path.suffix.lower() != ".jpg":
            raise CaptureDataError(
                f"capture {capture_id}: invalid image_name {source_filename!r} at {metadata_path}:{row_number}"
            )
        records.append(_CaptureImageRecord(angle, source_filename, frame_id))

    angles = [record.angle for record in records]
    if len(set(angles)) != 8:
        raise CaptureDataError(f"capture {capture_id}: duplicate angles in latest task records: {angles}")
    if angles != TASK_ANGLES:
        raise CaptureDataError(
            f"capture {capture_id}: latest task angles must be {TASK_ANGLES}, got {angles}"
        )
    return records


def _copy_capture_file(
    source: Path,
    destination: Path,
    capture_id: str,
    cancel_check: Optional[CancelCheck] = None,
) -> None:
    try:
        with source.open("rb") as input_stream, destination.open("wb") as output_stream:
            while True:
                _check_cancel(cancel_check)
                chunk = input_stream.read(1024 * 1024)
                if not chunk:
                    break
                output_stream.write(chunk)
        shutil.copystat(source, destination)
    except TaskPackageError:
        destination.unlink(missing_ok=True)
        raise
    except OSError as exc:
        raise TaskPackageError(
            f"capture {capture_id}: failed to copy {source} to {destination}: {exc}"
        ) from exc


def _atomic_write_json(path: Path, payload: Dict[str, Any], capture_id: str) -> None:
    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary_path), str(path))
    except (OSError, TypeError, ValueError) as exc:
        try:
            temporary_path.unlink()
        except OSError:
            pass
        raise TaskPackageError(f"capture {capture_id}: failed to write JSON {path}: {exc}") from exc


def _sha256_file(
    path: Path,
    cancel_check: Optional[CancelCheck] = None,
) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            _check_cancel(cancel_check)
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _describe_files(
    root: Path,
    paths: Sequence[Path],
    cancel_check: Optional[CancelCheck] = None,
) -> List[TaskFile]:
    files = []
    for path in sorted(
        paths,
        key=lambda item: item.relative_to(root).as_posix(),
    ):
        _check_cancel(cancel_check)
        files.append(
            TaskFile(
                relative_path=path.relative_to(root).as_posix(),
                sha256=_sha256_file(path, cancel_check),
                size_bytes=path.stat().st_size,
            )
        )
    return files


def _task_checksum(files: Sequence[TaskFile]) -> str:
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda file: file.relative_path):
        digest.update(f"{item.relative_path}\0{item.size_bytes}\0{item.sha256}\n".encode("utf-8"))
    return digest.hexdigest()


def _load_existing_package(
    staging_dir: Path,
    capture_id: str,
    cancel_check: Optional[CancelCheck] = None,
) -> TaskPackageResult:
    manifest_path = staging_dir / "task.json"
    try:
        _check_cancel(cancel_check)
        manifest = TaskManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if manifest.capture_id != capture_id:
            raise ValueError(f"manifest capture_id is {manifest.capture_id!r}")
        for item in manifest.files:
            _check_cancel(cancel_check)
            path = staging_dir / item.relative_path
            if (
                not path.is_file()
                or path.stat().st_size != item.size_bytes
                or _sha256_file(path, cancel_check) != item.sha256
            ):
                raise ValueError(f"staged file is missing or changed: {item.relative_path}")
        if _task_checksum(manifest.files) != manifest.checksum:
            raise ValueError("task checksum does not match staged files")
        expected_images = {f"{index}.jpg" for index in range(8)}
        actual_images = {path.name for path in (staging_dir / "images").glob("*.jpg")}
        if actual_images != expected_images:
            raise ValueError(f"staging images are incomplete: {sorted(actual_images)}")
    except (OSError, ValueError, ValidationError) as exc:
        raise CaptureDataError(
            f"capture {capture_id}: output directory already exists but is incomplete: {staging_dir}: {exc}"
        ) from exc
    return _result_from_manifest(staging_dir, manifest)


def _check_cancel(cancel_check: Optional[CancelCheck]) -> None:
    if cancel_check is not None and cancel_check():
        raise TaskPackageError("task packaging cancelled")


def _result_from_manifest(staging_dir: Path, manifest: TaskManifest) -> TaskPackageResult:
    return TaskPackageResult(
        capture_id=manifest.capture_id,
        staging_dir=staging_dir,
        images_dir=staging_dir / "images",
        manifest_path=staging_dir / "task.json",
        metadata_json_path=staging_dir / "metadata.json",
        image_count=manifest.image_count,
        checksum=manifest.checksum,
        manifest=manifest,
    )
