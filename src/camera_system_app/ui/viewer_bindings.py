"""Bind the result page to the existing q3dviewer implementation."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QFileDialog

from camera_system_app.infrastructure.adapters.q3dviewer_adapter import (
    Q3DViewerAdapter,
    prepare_q3dviewer,
)
from camera_system_app.workers import ViewerLoadWorker


class ViewerBindings(QObject):
    def __init__(self, window, project_root: Path, parent=None) -> None:
        super().__init__(parent)
        self.window = window
        self.project_root = Path(project_root)
        self._adapter = None
        self._worker = None
        self._capture_adapter = None
        self._pending_open_path: str | None = None
        self._logger = logging.getLogger("camera_system_app.ui.viewer")
        window.result_page.open_local_result_requested.connect(self.open_result)
        window.result_page.select_local_result_requested.connect(
            self.select_local_result
        )
        window.result_page.reset_view_requested.connect(self.reset_view)
        window.navigation.currentRowChanged.connect(self._on_page_changed)

    def set_capture_adapter(self, adapter) -> None:
        self._capture_adapter = adapter
        adapter.gpu_resources_ready.connect(self._on_gpu_resources_ready)

    def open_result(self, path: str) -> None:
        if self._worker is not None:
            return
        if (
            self._capture_adapter is not None
            and not self._capture_adapter.result_review_gpu_ready
        ):
            self._pending_open_path = path
            self.window.statusBar().showMessage(
                "● 正在停止推理并释放 GPU，完成后自动加载 3DGS…"
            )
            return
        try:
            # Import q3dviewer/Qt classes on the GUI thread. The worker only
            # performs CPU-side PLY parsing after this point.
            prepare_q3dviewer(self.project_root)
            from q3dviewer.utils.cloud_io import load_gs_ply  # noqa: F401
        except Exception as exc:
            self._on_failed(str(exc))
            return
        self.window.result_page.show_loading(path)
        worker = ViewerLoadWorker(path, self.project_root, self)
        worker.loaded.connect(self._on_loaded)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(lambda current=worker: self._on_finished(current))
        self._worker = worker
        worker.start()

    def _on_gpu_resources_ready(self, ready: bool) -> None:
        if self._adapter is not None:
            self._adapter.set_active(
                ready
                and self.window.stack.currentWidget()
                is self.window.result_page
            )
        if ready and self._pending_open_path is not None:
            path = self._pending_open_path
            self._pending_open_path = None
            self.open_result(path)

    def reset_view(self) -> None:
        if self._adapter is not None:
            self._adapter.reset_view()

    def select_local_result(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self.window,
            "选择本地 Gaussian Splat PLY",
            str(self.window.result_page.result_root),
            "Gaussian Splat PLY (*.ply);;所有文件 (*)",
        )
        if not selected:
            return
        self.window.result_page.set_result_available(selected)
        self.open_result(selected)

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            if not self._worker.wait(timeout_ms):
                self._logger.error("PLY load worker did not stop within %sms", timeout_ms)
                return False
        if self._adapter is not None:
            self._adapter.release()
        return True

    def _on_loaded(self, payload, path: str) -> None:
        try:
            gaussians, bounds = payload
            if self._adapter is None:
                self._adapter = Q3DViewerAdapter(self.project_root, self)
                self._adapter.rendering_failed.connect(self._on_failed)
                self._adapter.set_active(
                    self.window.stack.currentWidget() is self.window.result_page
                )
            count = self._adapter.set_gaussians(gaussians, bounds=bounds)
            self.window.result_page.set_viewer_widget(
                self._adapter.widget, path, count
            )
            self.window.statusBar().showMessage(
                "● q3dviewer 已加载本地结果：{}".format(path)
            )
        except Exception as exc:
            self._logger.exception("Cannot initialize embedded q3dviewer")
            self._on_failed(str(exc))

    def _on_failed(self, message: str) -> None:
        self._logger.error("q3dviewer load/render failed: %s", message)
        self.window.result_page.show_load_error(message)
        self.window.statusBar().showMessage("● 结果加载失败：{}".format(message))

    def _on_finished(self, worker) -> None:
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

    def _on_page_changed(self, index: int) -> None:
        if self._adapter is None:
            return
        active_page = (
            self.window.pages[index]
            if 0 <= index < len(self.window.pages)
            else None
        )
        gpu_ready = (
            self._capture_adapter is None
            or self._capture_adapter.result_review_gpu_ready
        )
        self._adapter.set_active(
            active_page is self.window.result_page and gpu_ready
        )
