"""Project-owned lightweight UI components."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QWidget,
)


_ICON_DIR = Path(__file__).with_name("icons")


class _FocusWheelGuard:
    """Never let a wheel gesture mutate a value control.

    Wheel events are ignored so a containing scroll area can consume them.
    Values must be changed through an explicit click, drag, or text entry.
    """

    def wheelEvent(self, event) -> None:
        event.ignore()


class GuardedComboBox(_FocusWheelGuard, QComboBox):
    """Combo box that never changes from a wheel gesture."""


class GuardedSpinBox(_FocusWheelGuard, QSpinBox):
    """Integer spin box protected from all wheel changes."""


class GuardedDoubleSpinBox(_FocusWheelGuard, QDoubleSpinBox):
    """Floating-point spin box protected from all wheel changes."""


class GuardedSlider(_FocusWheelGuard, QSlider):
    """Slider that changes only through drag or keyboard input."""


class NumericStepper(QWidget):
    """Compact minus/value/plus control used for deliberate settings changes."""

    def __init__(self, *, decimals: int = 0, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("numericStepper")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._minus = QPushButton("−")
        self._minus.setObjectName("stepperButton")
        self._minus.setAccessibleName("减少")
        self._plus = QPushButton("+")
        self._plus.setObjectName("stepperButton")
        self._plus.setAccessibleName("增加")
        if decimals:
            self._editor = GuardedDoubleSpinBox()
            self._editor.setDecimals(decimals)
        else:
            self._editor = GuardedSpinBox()
        self._editor.setObjectName("stepperEditor")
        self._editor.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._minus.clicked.connect(self._editor.stepDown)
        self._plus.clicked.connect(self._editor.stepUp)
        layout.addWidget(self._minus)
        layout.addWidget(self._editor, stretch=1)
        layout.addWidget(self._plus)

    def setRange(self, minimum, maximum) -> None:
        self._editor.setRange(minimum, maximum)

    def setSingleStep(self, step) -> None:
        self._editor.setSingleStep(step)

    def setSuffix(self, suffix: str) -> None:
        self._editor.setSuffix(suffix)

    def setDecimals(self, decimals: int) -> None:
        if isinstance(self._editor, QDoubleSpinBox):
            self._editor.setDecimals(decimals)

    def setValue(self, value) -> None:
        self._editor.setValue(value)

    def value(self):
        return self._editor.value()


def icon_path(name: str) -> str:
    return str(_ICON_DIR / f"{name}.svg")


class StatusBadge(QFrame):
    """Compact icon + state dot + text status indicator."""

    def __init__(self, icon_name: str, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("statusBadge")
        self.setProperty("state", "muted")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 9, 4)
        layout.setSpacing(6)
        icon = QLabel()
        icon.setObjectName("statusIcon")
        icon.setPixmap(QPixmap(icon_path(icon_name)).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation))
        icon.setAccessibleName(icon_name)
        self._dot = QFrame()
        self._dot.setObjectName("statusDot")
        self._dot.setFixedSize(7, 7)
        self._label = QLabel(text)
        self._label.setObjectName("statusText")
        layout.addWidget(icon)
        layout.addWidget(self._dot)
        layout.addWidget(self._label)

    def set_status(self, text: str, state: str = "muted") -> None:
        self._label.setText(text)
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class SystemStatusBar(QFrame):
    """Lightweight summary directly below the primary navigation."""

    gpu_percent_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("globalStatusBar")
        layout = QHBoxLayout(self)
        self.setFixedHeight(46)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(4)

        self.cameras = StatusBadge("camera", "0 路摄像头")
        self.capture = StatusBadge("activity", "传输待机")
        self.recording = StatusBadge("record", "未录制")
        self.inference = StatusBadge("ai", "AI 待机")
        self.gpu = StatusBadge("gpu", "GPU --")
        self.storage = StatusBadge("storage", "存储 --")
        for badge in (self.cameras, self.capture, self.recording, self.inference):
            layout.addWidget(badge)
        layout.addStretch()
        layout.addWidget(self.gpu)
        layout.addWidget(self.storage)

        self._gpu_timer = QTimer(self)
        self._gpu_timer.setInterval(1500)
        self._gpu_timer.timeout.connect(self.refresh_gpu)
        self._gpu_timer.start()
        self.refresh_gpu()

    def set_compact(self, compact: bool) -> None:
        self.gpu.setVisible(not compact)
        self.storage.setVisible(not compact)

    def set_camera_count(self, count: int) -> None:
        state = "good" if count else "bad"
        self.cameras.set_status(f"{count} 路摄像头", state)

    def set_capture_paused(self, paused: bool) -> None:
        self.capture.set_status("传输暂停" if paused else "传输运行", "warn" if paused else "good")

    def set_recording(self, recording: bool, stopping: bool = False) -> None:
        if stopping:
            self.recording.set_status("正在保存", "warn")
        elif recording:
            self.recording.set_status("正在录制", "record")
        else:
            self.recording.set_status("未录制", "muted")

    def set_inference(self, text: str, active: bool, warning: bool = False) -> None:
        self.inference.set_status(text, "warn" if warning else ("good" if active else "muted"))

    def set_storage_available(self, available_bytes: int) -> None:
        gib = available_bytes / (1024 ** 3)
        state = "bad" if gib < 5 else ("warn" if gib < 20 else "good")
        self.storage.set_status(f"可用 {gib:.0f} GB", state)

    def refresh_gpu(self) -> None:
        percent = _read_gpu_percent()
        self.gpu_percent_changed.emit(percent)
        if percent is None:
            self.gpu.set_status("GPU --", "muted")
            return
        state = "warn" if percent >= 85 else "good"
        self.gpu.set_status(f"GPU {percent:.0f}%", state)

    def shutdown(self) -> None:
        self._gpu_timer.stop()


class ResourceStatusWidget(QFrame):
    """GPU and storage telemetry aligned to the right edge of navigation."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("navigationResources")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.gpu = StatusBadge("gpu", "GPU --")
        self.storage = StatusBadge("storage", "可用 --")
        layout.addWidget(self.gpu)
        layout.addWidget(self.storage)

    def set_storage_available(self, available_bytes: int) -> None:
        gib = available_bytes / (1024 ** 3)
        state = "bad" if gib < 5 else ("warn" if gib < 20 else "good")
        self.storage.set_status(f"可用 {gib:.0f} GB", state)

    def set_gpu_percent(self, percent: float | None) -> None:
        if percent is None:
            self.gpu.set_status("GPU --", "muted")
            return
        self.gpu.set_status(f"GPU {percent:.0f}%", "warn" if percent >= 85 else "good")


class BottomStatusBar(QFrame):
    """Persistent operational telemetry at the bottom of the workstation."""

    _PING_ENDPOINTS = {
        1: ("WSL", "10.150.14.62"),
        2: ("Jetson", "10.150.64.23"),
    }

    def __init__(
        self,
        parent: QWidget | None = None,
        enable_network_checks: bool = True,
    ):
        super().__init__(parent)
        self.setObjectName("bottomStatusBar")
        self.setFixedHeight(56)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 7, 14, 7)
        layout.setSpacing(0)

        self.runtime = StatusBadge("activity", "系统就绪")
        self.client_one = StatusBadge("activity", "WSL  --")
        self.client_two = StatusBadge("activity", "Jetson  --")
        self.client_one.setToolTip("WSL · 10.150.14.62")
        self.client_two.setToolTip("Jetson · 10.150.64.23")
        self.sync = StatusBadge("activity", "系统同步 --")
        self.inference = StatusBadge("ai", "AI 推理 --")
        self.framerate = StatusBadge("activity", "平均帧率 --")
        self.logs = StatusBadge("settings", "日志")
        self._cells = []
        for badge in (self.runtime, self.sync, self.inference, self.framerate, self.logs):
            cell = QFrame()
            cell.setObjectName("bottomStatusCell")
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(4, 0, 4, 0)
            cell_layout.setSpacing(0)
            cell_layout.addStretch()
            cell_layout.addWidget(badge)
            cell_layout.addStretch()
            self._cells.append(cell)
            layout.addWidget(cell, stretch=1)

        network_cell = QFrame()
        network_cell.setObjectName("bottomStatusCell")
        network_layout = QHBoxLayout(network_cell)
        network_layout.setContentsMargins(4, 0, 4, 0)
        network_layout.setSpacing(4)
        network_layout.addStretch()
        network_layout.addWidget(self.client_one)
        network_layout.addWidget(self.client_two)
        network_layout.addStretch()
        self._cells.insert(1, network_cell)
        layout.insertWidget(1, network_cell, stretch=2)
        network_cell.setVisible(enable_network_checks)

        self._ping_processes: dict[int, QProcess] = {}
        self._network_checks_enabled = enable_network_checks
        self._network_checks_started = False
        self._ping_timer = QTimer(self)
        self._ping_timer.setInterval(5000)
        self._ping_timer.timeout.connect(self.refresh_client_pings)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._network_checks_enabled and not self._network_checks_started:
            self._network_checks_started = True
            self._ping_timer.start()
            self.refresh_client_pings()

    def set_compact(self, compact: bool) -> None:
        self._cells[1].setVisible(not compact)

    def set_runtime(self, text: str, state: str = "good") -> None:
        self.runtime.set_status(text, state)

    def set_client_ping(self, client: int, latency_ms: float | None) -> None:
        """Update one user endpoint's round-trip latency display."""
        if client not in self._PING_ENDPOINTS:
            raise ValueError("client must be 1 or 2")

        name, _host = self._PING_ENDPOINTS[client]
        badge = self.client_one if client == 1 else self.client_two
        if latency_ms is None:
            badge.set_status(f"{name}  离线", "bad")
            return

        latency_ms = max(0.0, float(latency_ms))
        state = "good" if latency_ms < 80 else ("warn" if latency_ms < 200 else "bad")
        badge.set_status(f"{name}  {latency_ms:.0f} ms", state)

    def refresh_client_pings(self) -> None:
        """Start non-blocking reachability probes for both configured endpoints."""
        for client, (_name, host) in self._PING_ENDPOINTS.items():
            running = self._ping_processes.get(client)
            if running is not None and running.state() != QProcess.NotRunning:
                continue

            process = QProcess(self)
            self._ping_processes[client] = process
            process.finished.connect(
                lambda exit_code, _exit_status, client=client: self._finish_ping(client, exit_code)
            )
            process.errorOccurred.connect(lambda _error, client=client: self._finish_ping(client, 1))
            process.start("ping", ["-n", "-c", "1", "-W", "1", host])

    def _finish_ping(self, client: int, exit_code: int) -> None:
        process = self._ping_processes.pop(client, None)
        if process is None:
            return

        try:
            output = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        except RuntimeError:
            return
        match = re.search(r"time[=<]([0-9]+(?:\.[0-9]+)?)\s*ms", output)
        latency_ms = float(match.group(1)) if exit_code == 0 and match else None
        self.set_client_ping(client, latency_ms)
        process.deleteLater()

    def shutdown(self) -> None:
        """Stop optional probes before the containing capture view is deleted."""
        self._ping_timer.stop()
        self._network_checks_started = False
        processes = list(self._ping_processes.values())
        self._ping_processes.clear()
        for process in processes:
            try:
                process.kill()
                process.waitForFinished(1000)
            except RuntimeError:
                pass
            process.deleteLater()

    def set_sync(self, spread_ms: float, good: bool) -> None:
        self.sync.set_status(f"系统同步 {spread_ms:.1f} ms", "good" if good else "warn")

    def set_inference(self, text: str, active: bool) -> None:
        self.inference.set_status(f"AI 推理 {text}", "good" if active else "muted")

    def set_framerate(self, fps: float) -> None:
        self.framerate.set_status(f"平均帧率 {fps:.1f} fps", "good" if fps > 0 else "muted")


def _read_gpu_percent() -> float | None:
    try:
        raw = Path("/sys/devices/gpu.0/load").read_text(encoding="ascii").strip()
        return max(0.0, min(100.0, int(raw) / 10.0))
    except (OSError, ValueError):
        return None
