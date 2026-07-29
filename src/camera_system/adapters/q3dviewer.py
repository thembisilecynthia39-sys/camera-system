"""Qt-free facade for q3dviewer result inspection.

The adapter deliberately returns a ``ViewerDocument`` rather than a QWidget.
The future UI adapter may create a q3dviewer OpenGL widget after receiving this
document, while the domain and service contracts stay importable without Qt.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from ..domain import ResultArtifact, ViewerDocument
from .errors import ServiceError, make_service_error


class Q3DViewerAdapter:
    """Inspect Gaussian PLY/NPY artifacts using q3dviewer lazily."""

    def __init__(self, q3dviewer_root: Optional[Path] = None) -> None:
        self._q3dviewer_root = Path(q3dviewer_root) if q3dviewer_root is not None else self._default_root()

    def supported_formats(self) -> Sequence[str]:
        return (".ply", ".npy")

    def describe(self, artifact: ResultArtifact) -> ViewerDocument:
        if not artifact.path.is_file():
            raise ServiceError(
                _artifact_error(
                    "viewer_artifact_missing",
                    f"viewer artifact does not exist: {artifact.path}",
                    "describe",
                )
            )
        suffix = artifact.path.suffix.lower()
        if suffix not in self.supported_formats():
            raise ServiceError(
                _artifact_error(
                    "viewer_format_unsupported",
                    f"q3dviewer Gaussian loader does not support {suffix or '<none>'}",
                    "describe",
                )
            )
        try:
            load_gs = self._load_gs()
            data = load_gs(str(artifact.path))
            point_count = len(data)
        except ImportError as exc:
            raise make_service_error(
                "q3dviewer_unavailable",
                "q3dviewer Gaussian loader is not importable",
                "describe",
                exc,
            ) from exc
        except Exception as exc:
            raise make_service_error(
                "viewer_load_failed",
                f"q3dviewer could not load {artifact.path}: {exc}",
                "describe",
                exc,
                recoverable=True,
            ) from exc
        return ViewerDocument(
            artifact=artifact,
            format="gaussian_splat",
            point_count=point_count,
            capabilities=("orbit", "pan", "zoom", "gaussian_splat"),
            metadata={"q3dviewer_root": str(self._q3dviewer_root)},
        )

    @staticmethod
    def _default_root() -> Path:
        configured = os.environ.get("MULTIWEBCAM_Q3DVIEWER_ROOT")
        if configured:
            return Path(configured).expanduser()
        return Path(__file__).resolve().parents[3] / "3DGSviewer" / "q3dviewer"

    def _load_gs(self):
        root = self._q3dviewer_root
        if not root.is_dir():
            raise ImportError(f"q3dviewer source root does not exist: {root}")
        root_string = str(root)
        if root_string not in sys.path:
            sys.path.insert(0, root_string)
        from q3dviewer.utils.cloud_io import load_gs

        return load_gs


def _artifact_error(code: str, message: str, operation: str):
    from ..domain import AppError

    return AppError(code=code, message=message, operation=operation, recoverable=True)
