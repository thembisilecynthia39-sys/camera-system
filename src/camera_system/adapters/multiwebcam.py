"""Compatibility adapter for multiwebcam capture directories.

The existing capture implementation writes one CSV row and one JPEG per
active camera for each accepted angle.  Tx_Rx intentionally accepts exactly
one image per fixed angle.  This adapter selects one complete camera sequence
and delegates the actual package construction to Tx_Rx; it does not open a
camera or duplicate the capture algorithm.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..domain import (
    CaptureProgress,
    CaptureSession,
    ReconstructionTask,
    TaskState,
    TASK_ANGLES,
)
from .errors import ServiceError, make_service_error
from .txrx import task_manifest_from_txrx


class MultiWebcamCaptureAdapter:
    """Expose existing multiwebcam capture output through the domain ports."""

    def inspect_capture(self, capture_dir: Path) -> CaptureSession:
        capture_dir = Path(capture_dir)
        self._require_directory(capture_dir)
        rows = self._read_rows(capture_dir)
        angles = self._valid_angles(rows)
        camera_ids = self._camera_ids(rows)
        state = self._capture_state(capture_dir, rows, angles)
        return CaptureSession(
            session_id=capture_dir.name,
            capture_id=capture_dir.name,
            capture_dir=capture_dir,
            camera_ids=tuple(camera_ids),
            captured_angles=tuple(angles),
            state=state,
        )

    def get_progress(self, capture_dir: Path) -> CaptureProgress:
        session = self.inspect_capture(capture_dir)
        completed = session.captured_angles
        next_angle = next((angle for angle in TASK_ANGLES if angle not in completed), None)
        progress = 100.0 * len(completed) / len(TASK_ANGLES)
        return CaptureProgress(
            session_id=session.session_id,
            state=session.state,
            completed_angles=completed,
            current_angle_deg=next_angle,
            readiness_percent=100.0 if session.state is TaskState.READY else 0.0,
            progress_percent=progress,
            camera_count=len(session.camera_ids),
            message=("eight angles are ready" if session.state is TaskState.READY else "capture is incomplete"),
        )

    def prepare_task(
        self,
        capture_dir: Path,
        *,
        config_path: Optional[Path] = None,
        staging_root: Optional[Path] = None,
        camera_id: Optional[str] = None,
    ) -> ReconstructionTask:
        """Select one complete camera sequence and call the existing Tx_Rx builder."""

        capture_dir = Path(capture_dir)
        session = self.inspect_capture(capture_dir)
        selected_images = self._select_images(capture_dir, camera_id)
        if selected_images is None and session.state is not TaskState.READY:
            raise ServiceError(
                code_error(
                    "capture_incomplete",
                    "capture does not contain a complete eight-angle task",
                    "prepare_task",
                    {"capture_dir": str(capture_dir)},
                )
            )

        try:
            if staging_root is not None:
                from tx_rx.jetson_client.task_manifest import build_task_package

                package = build_task_package(capture_dir, Path(staging_root), selected_images)
            else:
                from tx_rx.jetson_client.task_manifest import build_configured_task_package

                package = build_configured_task_package(capture_dir, config_path, selected_images)
        except ImportError as exc:
            raise make_service_error(
                "txrx_unavailable",
                "Tx_Rx package builder is not importable",
                "prepare_task",
                exc,
            ) from exc
        except Exception as exc:
            raise make_service_error(
                "task_package_failed",
                f"cannot build task package: {exc}",
                "prepare_task",
                exc,
                recoverable=True,
            ) from exc

        manifest = task_manifest_from_txrx(package.manifest)
        return ReconstructionTask(
            capture_id=package.capture_id,
            manifest=manifest,
            staging_dir=package.staging_dir,
            capture_dir=capture_dir,
            source_camera_id=camera_id or self._selected_camera_id(capture_dir),
            state=TaskState.READY,
        )

    @staticmethod
    def _require_directory(capture_dir: Path) -> None:
        if not capture_dir.is_dir():
            raise ServiceError(
                code_error(
                    "capture_not_found",
                    f"capture directory does not exist: {capture_dir}",
                    "inspect_capture",
                    {"capture_dir": str(capture_dir)},
                )
            )

    @staticmethod
    def _images_dir(capture_dir: Path) -> Path:
        nested = capture_dir / "images"
        return nested if nested.is_dir() else capture_dir

    @classmethod
    def _read_rows(cls, capture_dir: Path) -> List[Dict[str, str]]:
        metadata_path = capture_dir / "metadata.csv"
        if not metadata_path.is_file():
            return []
        try:
            with metadata_path.open("r", newline="", encoding="utf-8") as stream:
                return [dict(row) for row in csv.DictReader(stream)]
        except (OSError, UnicodeError, csv.Error) as exc:
            raise make_service_error(
                "capture_metadata_unreadable",
                f"cannot read capture metadata: {metadata_path}",
                "inspect_capture",
                exc,
                recoverable=True,
            ) from exc

    @staticmethod
    def _camera_ids(rows: Sequence[Dict[str, str]]) -> List[str]:
        values = {str(row.get("camera_id", "")).strip() for row in rows}
        return sorted((value for value in values if value), key=MultiWebcamCaptureAdapter._camera_sort_key)

    @staticmethod
    def _camera_sort_key(value: str) -> Tuple[int, str]:
        try:
            return (0, f"{int(value):010d}")
        except ValueError:
            return (1, value)

    @staticmethod
    def _valid_angles(rows: Sequence[Dict[str, str]]) -> List[int]:
        values = set()
        for row in rows:
            try:
                angle = int((row.get("angle_deg") or "").strip())
            except (TypeError, ValueError):
                continue
            if angle in TASK_ANGLES:
                values.add(angle)
        return [angle for angle in TASK_ANGLES if angle in values]

    @classmethod
    def _capture_state(
        cls,
        capture_dir: Path,
        rows: Sequence[Dict[str, str]],
        angles: Sequence[int],
    ) -> TaskState:
        if cls._has_complete_task(capture_dir, rows):
            return TaskState.READY
        if angles:
            return TaskState.CAPTURING
        return TaskState.IDLE

    @classmethod
    def _has_complete_task(cls, capture_dir: Path, rows: Sequence[Dict[str, str]]) -> bool:
        if not rows:
            images_dir = cls._images_dir(capture_dir)
            return images_dir.is_dir() and sum(
                1
                for path in images_dir.iterdir()
                if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}
            ) == len(TASK_ANGLES)
        groups: Dict[str, List[Dict[str, str]]] = {}
        for row in rows:
            camera_id = str(row.get("camera_id", "")).strip()
            if camera_id:
                groups.setdefault(camera_id, []).append(row)
        return any(cls._has_complete_round(camera_rows) for camera_rows in groups.values())

    @classmethod
    def _select_images(cls, capture_dir: Path, camera_id: Optional[str]) -> Optional[List[str]]:
        rows = cls._read_rows(capture_dir)
        images_dir = cls._images_dir(capture_dir)
        if not images_dir.is_dir():
            raise ServiceError(
                code_error(
                    "capture_images_missing",
                    f"capture image directory does not exist: {images_dir}",
                    "prepare_task",
                    {"capture_dir": str(capture_dir)},
                )
            )
        image_paths = sorted(
            path
            for path in images_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}
        )

        # Preserve Tx_Rx's existing exactly-eight fallback for manually
        # prepared folders without multiwebcam metadata.
        if not rows:
            if len(image_paths) == 8:
                return None
            raise ServiceError(
                code_error(
                    "capture_metadata_missing",
                    "multiwebcam metadata.csv is required when the image pool is not exactly eight JPEGs",
                    "prepare_task",
                    {"capture_dir": str(capture_dir), "image_count": len(image_paths)},
                )
            )

        groups: Dict[str, List[Dict[str, str]]] = {}
        for row in rows:
            value = str(row.get("camera_id", "")).strip()
            if value:
                groups.setdefault(value, []).append(row)

        selected_camera = camera_id
        if selected_camera is None:
            complete = [key for key in groups if cls._has_complete_round(groups[key])]
            if not complete:
                raise ServiceError(
                    code_error(
                        "camera_angle_mismatch",
                        "no camera contains one complete fixed-angle sequence",
                        "prepare_task",
                        {"capture_dir": str(capture_dir), "camera_ids": sorted(groups)},
                    )
                )
            selected_camera = sorted(complete, key=cls._camera_sort_key)[0]

        camera_rows = groups.get(str(selected_camera), [])
        selected_rows = cls._latest_complete_round(camera_rows)
        if selected_rows is None:
            raise ServiceError(
                code_error(
                    "camera_angle_mismatch",
                    f"camera {selected_camera!r} does not contain one complete fixed-angle sequence",
                    "prepare_task",
                    {"capture_dir": str(capture_dir), "camera_id": str(selected_camera)},
                )
            )

        selected_names: List[str] = []
        for row in selected_rows:
            name = str(row.get("image_name", "")).strip()
            path = Path(name)
            if not name or path.name != name or path.suffix.lower() not in {".jpg", ".jpeg"}:
                raise ServiceError(
                    code_error(
                        "capture_image_invalid",
                        f"invalid image_name in capture metadata: {name!r}",
                        "prepare_task",
                        {"capture_dir": str(capture_dir), "camera_id": str(selected_camera)},
                    )
                )
            if not (images_dir / name).is_file():
                raise ServiceError(
                    code_error(
                        "capture_image_missing",
                        f"capture image does not exist: {images_dir / name}",
                        "prepare_task",
                        {"capture_dir": str(capture_dir), "image_name": name},
                    )
                )
            selected_names.append(name)
        return selected_names

    @staticmethod
    def _has_complete_round(rows: Sequence[Dict[str, str]]) -> bool:
        return MultiWebcamCaptureAdapter._latest_complete_round(rows) is not None

    @staticmethod
    def _latest_complete_round(rows: Sequence[Dict[str, str]]) -> Optional[List[Dict[str, str]]]:
        if len(rows) < len(TASK_ANGLES):
            return None
        for start in range(len(rows) - len(TASK_ANGLES), -1, -1):
            window = list(rows[start : start + len(TASK_ANGLES)])
            angles = []
            for row in window:
                try:
                    angles.append(int((row.get("angle_deg") or "").strip()))
                except (TypeError, ValueError):
                    angles.append(None)
            if tuple(angles) == TASK_ANGLES:
                return window

        # A retake can create a non-contiguous but still complete set.  Use
        # the newest row for each angle while retaining the protocol order.
        newest: Dict[int, Dict[str, str]] = {}
        for row in rows:
            try:
                angle = int((row.get("angle_deg") or "").strip())
            except (TypeError, ValueError):
                continue
            if angle in TASK_ANGLES:
                newest[angle] = row
        if all(angle in newest for angle in TASK_ANGLES):
            return [newest[angle] for angle in TASK_ANGLES]
        return None

    @classmethod
    def _selected_camera_id(cls, capture_dir: Path) -> Optional[str]:
        rows = cls._read_rows(capture_dir)
        groups: Dict[str, List[Dict[str, str]]] = {}
        for row in rows:
            camera_id = str(row.get("camera_id", "")).strip()
            if camera_id:
                groups.setdefault(camera_id, []).append(row)
        complete = [key for key in groups if cls._has_complete_round(groups[key])]
        return sorted(complete, key=cls._camera_sort_key)[0] if complete else None


def code_error(code: str, message: str, operation: str, details: Dict[str, str]) -> "AppError":
    """Local constructor kept here to keep error creation Qt-free and explicit."""

    from ..domain import AppError

    return AppError(code=code, message=message, operation=operation, recoverable=True, details=details)
