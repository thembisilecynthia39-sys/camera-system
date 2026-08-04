"""Stable service ports shared by capture, Tx_Rx and viewer adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional, Protocol, Sequence

from .domain import (
    CaptureProgress,
    CaptureSession,
    ReconstructionStatus,
    ReconstructionTask,
    ResultArtifact,
    ViewerDocument,
)


CancelCheck = Callable[[], bool]
ProgressCallback = Callable[[str], None]
StatusCallback = Callable[[ReconstructionStatus], None]


class CaptureService(Protocol):
    """Capture-to-task port; camera implementation remains outside the domain."""

    def inspect_capture(self, capture_dir: Path) -> CaptureSession:
        """Read a multiwebcam capture directory without opening cameras."""

    def get_progress(self, capture_dir: Path) -> CaptureProgress:
        """Return fixed-angle progress derived from capture metadata."""

    def prepare_task(
        self,
        capture_dir: Path,
        *,
        config_path: Optional[Path] = None,
        staging_root: Optional[Path] = None,
        camera_id: Optional[str] = None,
    ) -> ReconstructionTask:
        """Create a protocol task through the existing Tx_Rx package builder."""


class ReconstructionService(Protocol):
    """Port for submit and remote status operations."""

    def submit(
        self,
        task: ReconstructionTask,
        *,
        config_path: Optional[Path] = None,
        session: Any = None,
    ) -> ReconstructionTask:
        """Upload a staged task and request reconstruction."""

    def poll(
        self,
        task: ReconstructionTask,
        *,
        config_path: Optional[Path] = None,
        session: Any = None,
        cancel_check: Optional[CancelCheck] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ReconstructionStatus:
        """Wait for the remote reconstruction endpoint to finish."""


class TransferService(Protocol):
    """Port for verified result transfer and protocol acknowledgement."""

    def download_result(
        self,
        task: ReconstructionTask,
        *,
        config_path: Optional[Path] = None,
        session: Any = None,
        cancel_check: Optional[CancelCheck] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ResultArtifact:
        """Download and verify the remote PLY using the existing Range protocol."""

    def acknowledge_result(
        self,
        task: ReconstructionTask,
        artifact: ResultArtifact,
        *,
        config_path: Optional[Path] = None,
        session: Any = None,
    ) -> None:
        """Send the existing result_received/result_acknowledged handshake."""


class ViewerService(Protocol):
    """Qt-free result inspection port; widget construction stays in UI adapters."""

    def describe(self, artifact: ResultArtifact) -> ViewerDocument:
        """Validate an artifact and return viewer-neutral metadata."""

    def supported_formats(self) -> Sequence[str]:
        """Return formats supported by the concrete viewer adapter."""
