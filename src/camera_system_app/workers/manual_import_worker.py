"""Background boundary for importing a manually selected image set."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from camera_system_app.domain import normalize_error


class ManualImportWorker(QThread):
    imported = Signal(object)
    failed = Signal(object)

    def __init__(self, workflow, image_paths, parent=None) -> None:
        super().__init__(parent)
        self.workflow = workflow
        self.image_paths = tuple(image_paths)

    def run(self) -> None:
        try:
            job = self.workflow.import_manual_images(self.image_paths)
        except Exception as exc:
            self.failed.emit(normalize_error(exc, "导入八张照片"))
            return
        self.imported.emit(job)
