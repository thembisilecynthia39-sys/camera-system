"""Qt adapter around the existing multiwebcam coordinator and views."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from camera_system.domain import TASK_ANGLES
from camera_system_app.domain import (
    CaptureCompletedEvent,
    CaptureRuntimeState,
    CaptureRuntimeStatus,
)


class MultiWebcamCaptureAdapter(QObject):
    """Own one existing CaptureCoordinator and expose application-level events."""

    state_changed = Signal(object)
    capture_completed = Signal(object)
    view_changed = Signal(object)
    gpu_resources_ready = Signal(bool)

    def __init__(
        self,
        project_root: Path,
        coordinator_factory: Optional[Callable] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        if coordinator_factory is None:
            from multiwebcam.ui.coordinator import CaptureCoordinator

            coordinator_factory = CaptureCoordinator
        self._logger = logging.getLogger("camera_system_app.capture")
        self._coordinator = coordinator_factory(
            Path(project_root).resolve(),
            capture_only=True,
        )
        self._current_view = None
        self._started = False
        self._stopped = False
        self._coordinator_reported_stopped = False
        self._result_review_active = False
        self._gpu_resources_ready = False

        self._coordinator.runtime_state_changed.connect(self._on_runtime_state)
        self._coordinator.capture_progress_changed.connect(self._on_capture_progress)
        self._coordinator.capture_completed.connect(self._on_capture_completed)
        self._coordinator.capture_available.connect(self._on_capture_available)
        resources_released = getattr(
            self._coordinator,
            "model_resources_released",
            None,
        )
        if resources_released is not None:
            resources_released.connect(self._on_gpu_resources_released)

    @property
    def coordinator(self):
        return self._coordinator

    @property
    def current_view(self):
        return self._current_view

    def initialize_view(self) -> None:
        self.show_grid()

    def start(self) -> None:
        if self._started or self._stopped:
            return
        self._started = True
        self.state_changed.emit(
            CaptureRuntimeState(
                CaptureRuntimeStatus.DISCOVERING,
                "正在后台发现摄像头…",
            )
        )
        self._coordinator.start_async()

    def stop(self) -> bool:
        if self._stopped:
            return True
        self._stopped = True
        stopped = self._coordinator.stop()
        if stopped is not False:
            self._release_current_view()
            if not self._coordinator_reported_stopped:
                self.state_changed.emit(
                    CaptureRuntimeState(
                        CaptureRuntimeStatus.STOPPED,
                        "摄像头线程已停止并释放。",
                    )
                )
        else:
            self._stopped = False
        return stopped is not False

    def set_result_review_active(self, active: bool) -> bool:
        """Transfer camera/inference compute to the result viewer."""

        self._result_review_active = bool(active)
        if active:
            self._gpu_resources_ready = False
            self.gpu_resources_ready.emit(False)
        else:
            self._gpu_resources_ready = False
        set_model_mode = getattr(self._coordinator, "set_model_mode", None)
        if not callable(set_model_mode):
            return True
        return set_model_mode(self._result_review_active) is not False

    @property
    def result_review_gpu_ready(self) -> bool:
        return self._result_review_active and self._gpu_resources_ready

    def _on_gpu_resources_released(self, released: bool) -> None:
        self._gpu_resources_ready = bool(
            released and self._result_review_active
        )
        self.gpu_resources_ready.emit(self._gpu_resources_ready)

    def show_grid(self) -> None:
        if self._stopped:
            return
        view = self._coordinator.create_grid_view()
        self._apply_existing_theme(view)
        view.focus_requested.connect(self.show_focus)
        self._replace_view(view)

    def show_focus(self, source_id: int) -> None:
        if self._stopped:
            return
        try:
            view = self._coordinator.create_focus_view(source_id)
        except (RuntimeError, ValueError) as exc:
            self._logger.warning("Cannot enter focus view for source %s: %s", source_id, exc)
            self.state_changed.emit(
                CaptureRuntimeState(
                    CaptureRuntimeStatus.ERROR,
                    "无法打开单路画面：{}".format(exc),
                )
            )
            self.show_grid()
            return
        self._apply_existing_theme(view)
        view.back_requested.connect(self.show_grid)
        self._replace_view(view)

    def _on_capture_available(self) -> None:
        """Recreate the grid after asynchronous discovery creates its presenter.

        The initial grid is intentionally constructed before camera discovery
        so the Qt window can paint immediately.  At that point there is no
        presenter to bind.  Recreating the existing GridView here mirrors the
        standalone multiwebcam window and installs the presenter-to-view frame
        connections once capture is available.
        """
        if not self._stopped:
            self.show_grid()
            self.set_result_review_active(self._result_review_active)

    def _replace_view(self, view) -> None:
        previous = self._current_view
        self._current_view = view
        self.view_changed.emit(view)
        if previous is not None and previous is not view:
            shutdown = getattr(previous, "shutdown", None)
            if callable(shutdown):
                shutdown()
            previous.deleteLater()

    def _release_current_view(self) -> None:
        view = self._current_view
        self._current_view = None
        self.view_changed.emit(None)
        if view is None:
            return
        shutdown = getattr(view, "shutdown", None)
        if callable(shutdown):
            shutdown()
        view.deleteLater()

    @staticmethod
    def _apply_existing_theme(view) -> None:
        from multiwebcam.ui.theme import app_stylesheet

        view.setStyleSheet(app_stylesheet())

    def _on_runtime_state(self, status: str, payload: object) -> None:
        data = dict(payload) if isinstance(payload, dict) else {}
        try:
            runtime_status = CaptureRuntimeStatus(status)
        except ValueError:
            runtime_status = CaptureRuntimeStatus.ERROR
        if runtime_status is CaptureRuntimeStatus.STOPPED:
            self._coordinator_reported_stopped = True
        self.state_changed.emit(
            CaptureRuntimeState(
                status=runtime_status,
                message=str(data.pop("message", status)),
                camera_count=int(data.pop("camera_count", 0)),
                completed_angles=tuple(data.pop("completed_angles", ())),
                current_angle_deg=data.pop("current_angle_deg", None),
                progress_percent=float(data.pop("progress_percent", 0.0)),
                details=data,
            )
        )

    def _on_capture_progress(self, guidance: object) -> None:
        completed = tuple(getattr(guidance, "completed_angles", ()))
        current = getattr(guidance, "current_angle_deg", None)
        self.state_changed.emit(
            CaptureRuntimeState(
                status=CaptureRuntimeStatus.READY,
                message="八角度采集进度：{}/8".format(len(completed)),
                camera_count=len(self._coordinator.get_source_id_lookup()),
                completed_angles=completed,
                current_angle_deg=current,
                progress_percent=float(getattr(guidance, "progress_percent", 0.0)),
            )
        )

    def _on_capture_completed(self, payload: object) -> None:
        data = dict(payload) if isinstance(payload, dict) else {}
        event = CaptureCompletedEvent(
            capture_dir=Path(str(data["capture_dir"])),
            object_name=str(data.get("object_name") or Path(str(data["capture_dir"])).name),
            completed_angles=tuple(data.get("completed_angles", TASK_ANGLES)),
        )
        self.capture_completed.emit(event)
