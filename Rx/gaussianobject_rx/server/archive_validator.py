"""Safe validation and extraction of existing Tx task archives."""

from __future__ import annotations

import hashlib
import re
import shutil
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Dict, List, Tuple

from pydantic import ValidationError

from gaussianobject_rx.protocol.models import TASK_FILENAMES, TaskManifest
from gaussianobject_rx.server.files import jpeg_dimensions, sha256_file


class ArchiveValidationError(Exception):
    """The uploaded archive is unsafe, incomplete, or corrupt."""


@dataclass(frozen=True)
class ValidatedArchive:
    manifest: TaskManifest
    package_dir: Path
    image_dimensions: Dict[str, Tuple[int, int]]


def _safe_member_name(name: str) -> str:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or name.startswith("./") or "\\" in name:
        raise ArchiveValidationError(f"unsafe archive member: {name!r}")
    normalized = path.as_posix()
    if normalized != name.rstrip("/"):
        raise ArchiveValidationError(f"non-normalized archive member: {name!r}")
    return normalized


def validate_and_extract_archive(
    archive_path: Path,
    destination: Path,
    expected_checksum: str,
    max_extracted_size: int,
) -> ValidatedArchive:
    if destination.exists():
        raise ArchiveValidationError(f"destination already exists: {destination}")
    temporary = destination.with_name(f".{destination.name}.part")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)

    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = _validate_members(archive, max_extracted_size)
            if "task.json" not in members:
                raise ArchiveValidationError("task.json is missing")
            _extract_members(archive, temporary, members)

        try:
            manifest = TaskManifest.model_validate_json((temporary / "task.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, ValidationError) as exc:
            raise ArchiveValidationError(f"invalid task.json: {exc}") from exc
        if manifest.checksum != expected_checksum:
            raise ArchiveValidationError("multipart checksum does not match task.json")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", manifest.capture_id):
            raise ArchiveValidationError("capture_id contains unsafe characters")

        expected_files = {item.relative_path for item in manifest.files} | {"task.json"}
        actual_files = {
            path.relative_to(temporary).as_posix()
            for path in temporary.rglob("*")
            if path.is_file()
        }
        if actual_files != expected_files:
            raise ArchiveValidationError(
                f"archive files do not match manifest: expected {sorted(expected_files)}, got {sorted(actual_files)}"
            )

        _validate_manifest_files(temporary, manifest)
        dimensions = _validate_images(temporary, manifest)
        temporary.rename(destination)
        return ValidatedArchive(manifest, destination, dimensions)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _validate_members(archive: zipfile.ZipFile, max_extracted_size: int) -> Dict[str, zipfile.ZipInfo]:
    members: Dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in archive.infolist():
        if len(members) >= 256:
            raise ArchiveValidationError("archive contains too many files")
        name = _safe_member_name(info.filename)
        if info.is_dir():
            continue
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ArchiveValidationError(f"symbolic links are not allowed: {name}")
        if name in members:
            raise ArchiveValidationError(f"duplicate archive member: {name}")
        if name == "task.json" and info.file_size > 2 * 1024 * 1024:
            raise ArchiveValidationError("task.json exceeds 2 MiB")
        total += info.file_size
        if total > max_extracted_size:
            raise ArchiveValidationError("archive exceeds maximum extracted size")
        members[name] = info
    return members


def _extract_members(
    archive: zipfile.ZipFile,
    root: Path,
    members: Dict[str, zipfile.ZipInfo],
) -> None:
    for name, info in members.items():
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, destination.open("wb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)


def _validate_manifest_files(root: Path, manifest: TaskManifest) -> None:
    digest = hashlib.sha256()
    for item in sorted(manifest.files, key=lambda value: value.relative_path):
        path = root / item.relative_path
        if not path.is_file():
            raise ArchiveValidationError(f"manifest file is missing: {item.relative_path}")
        actual_size = path.stat().st_size
        if actual_size != item.size_bytes:
            raise ArchiveValidationError(f"file length mismatch: {item.relative_path}")
        actual_hash = sha256_file(path)
        if actual_hash != item.sha256:
            raise ArchiveValidationError(f"file SHA-256 mismatch: {item.relative_path}")
        digest.update(f"{item.relative_path}\0{item.size_bytes}\0{item.sha256}\n".encode("utf-8"))
    if digest.hexdigest() != manifest.checksum:
        raise ArchiveValidationError("task checksum does not match manifest files")


def _validate_images(root: Path, manifest: TaskManifest) -> Dict[str, Tuple[int, int]]:
    image_names: List[str] = [image.filename for image in sorted(manifest.images, key=lambda value: value.index)]
    if image_names != TASK_FILENAMES:
        raise ArchiveValidationError("task images cannot be normalized to 0.jpg through 7.jpg")
    dimensions: Dict[str, Tuple[int, int]] = {}
    for image in sorted(manifest.images, key=lambda value: value.index):
        path = root / "images" / image.filename
        if path.stat().st_size != image.size_bytes or sha256_file(path) != image.sha256:
            raise ArchiveValidationError(f"image manifest mismatch: {image.filename}")
        try:
            width, height = jpeg_dimensions(path)
        except ValueError as exc:
            raise ArchiveValidationError(str(exc)) from exc
        if width <= 0 or height <= 0 or width > 16384 or height > 16384 or width * height > 100_000_000:
            raise ArchiveValidationError(f"unsupported JPEG resolution: {image.filename}={width}x{height}")
        dimensions[image.filename] = (width, height)
    return dimensions
