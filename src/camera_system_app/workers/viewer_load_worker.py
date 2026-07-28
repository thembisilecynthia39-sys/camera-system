"""Background CPU loader for potentially large Gaussian PLY files."""

from pathlib import Path

import numpy as np
from PySide6.QtCore import QThread, Signal

from camera_system_app.infrastructure.adapters.q3dviewer_adapter import (
    load_gaussian_ply,
)


class ViewerLoadWorker(QThread):
    loaded = Signal(object, str)
    failed = Signal(str)

    def __init__(self, path: str, project_root: Path, parent=None) -> None:
        super().__init__(parent)
        self.path = str(path)
        self.project_root = Path(project_root)

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            data = load_gaussian_ply(
                Path(self.path),
                self.project_root,
                cancel_check=self.isInterruptionRequested,
            )
            if self.isInterruptionRequested():
                return
            points = np.asarray(data["pw"], dtype=np.float32)
            if points.shape[0] > 200000:
                indices = np.linspace(
                    0,
                    points.shape[0] - 1,
                    200000,
                    dtype=np.int64,
                )
                points = points[indices]
            if self.isInterruptionRequested():
                return
            bounds = (
                np.percentile(points, 1, axis=0),
                np.percentile(points, 99, axis=0),
            )
        except InterruptedError:
            return
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        if not self.isInterruptionRequested():
            self.loaded.emit((data, bounds), self.path)
