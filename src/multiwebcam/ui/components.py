"""Project-owned lightweight UI components."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget


_ICON_DIR = Path(__file__).with_name("icons")


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
    """Persistent capture workstation health summary."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("globalStatusBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

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
        self._gpu_timer.timeout.connect(self._refresh_gpu)
        self._gpu_timer.start()
        self._refresh_gpu()

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

    def _refresh_gpu(self) -> None:
        try:
            raw = Path("/sys/devices/gpu.0/load").read_text(encoding="ascii").strip()
            percent = max(0.0, min(100.0, int(raw) / 10.0))
        except (OSError, ValueError):
            self.gpu.set_status("GPU --", "muted")
            return
        state = "warn" if percent >= 85 else "good"
        self.gpu.set_status(f"GPU {percent:.0f}%", state)
