"""Latest-command background worker for potentially slow V4L2 controls."""

from __future__ import annotations

import logging
from threading import Condition, Event, Thread

from PySide6.QtCore import QObject, Signal

from multiwebcam.sources.controls import V4L2Control, query_controls, set_control

logger = logging.getLogger(__name__)


class CameraControlWorker(QObject):
    """Run v4l2-ctl outside Qt's GUI thread with bounded pending work."""

    controls_ready = Signal(str, object)
    control_applied = Signal(str, str, int, bool)
    defaults_restored = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._condition = Condition()
        self._shutdown = Event()
        self._thread: Thread | None = None
        self._query_device: str | None = None
        self._pending_sets: dict[tuple[str, str], int] = {}
        self._restore: tuple[str, tuple[V4L2Control, ...]] | None = None

    def query(self, device: str) -> None:
        with self._condition:
            if self._shutdown.is_set():
                return
            self._ensure_started()
            self._query_device = device
            self._condition.notify()

    def set_value(self, device: str, name: str, value: int) -> None:
        with self._condition:
            if self._shutdown.is_set():
                return
            self._ensure_started()
            self._pending_sets[(device, name)] = value
            self._condition.notify()

    def restore_defaults(
        self,
        device: str,
        controls: list[V4L2Control],
    ) -> None:
        with self._condition:
            if self._shutdown.is_set():
                return
            self._ensure_started()
            self._restore = (device, tuple(controls))
            self._condition.notify()

    def clear_pending(self) -> None:
        with self._condition:
            self._query_device = None
            self._pending_sets.clear()
            self._restore = None

    def stop(self, timeout: float = 3.0) -> bool:
        self._shutdown.set()
        with self._condition:
            self._query_device = None
            self._pending_sets.clear()
            self._restore = None
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=max(0.0, timeout))
            if self._thread.is_alive():
                logger.error("Camera control worker did not stop within %.1fs", timeout)
                return False
            self._thread = None
        return True

    def _ensure_started(self) -> None:
        if self._thread is None:
            self._thread = Thread(
                target=self._run,
                name="multiwebcam-controls",
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        while not self._shutdown.is_set():
            with self._condition:
                while not self._has_pending() and not self._shutdown.is_set():
                    self._condition.wait(timeout=0.5)
                if self._shutdown.is_set():
                    return
                query_device = self._query_device
                pending_sets = self._pending_sets
                restore = self._restore
                self._query_device = None
                self._pending_sets = {}
                self._restore = None

            if query_device is not None:
                try:
                    controls = query_controls(query_device)
                except Exception:
                    logger.exception(
                        "Cannot query camera controls for %s",
                        query_device,
                    )
                    controls = []
                if not self._shutdown.is_set():
                    self.controls_ready.emit(query_device, controls)

            if restore is not None:
                device, controls = restore
                for control in controls:
                    if self._shutdown.is_set():
                        return
                    if control.default is not None:
                        try:
                            set_control(device, control.name, control.default)
                        except Exception:
                            logger.exception(
                                "Cannot restore %s on %s",
                                control.name,
                                device,
                            )
                if not self._shutdown.is_set():
                    self.defaults_restored.emit(device)

            for (device, name), value in pending_sets.items():
                if self._shutdown.is_set():
                    return
                try:
                    succeeded = set_control(device, name, value)
                except Exception:
                    logger.exception(
                        "Cannot set %s on %s",
                        name,
                        device,
                    )
                    succeeded = False
                if not self._shutdown.is_set():
                    self.control_applied.emit(device, name, value, succeeded)

    def _has_pending(self) -> bool:
        return (
            self._query_device is not None
            or bool(self._pending_sets)
            or self._restore is not None
        )
