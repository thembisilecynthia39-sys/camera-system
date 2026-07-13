"""Single source tile widget for grid display."""

from __future__ import annotations

import re

from PySide6.QtCore import Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from multiwebcam.ui.views.aspect_ratio_label import AspectRatioLabel
from multiwebcam.ui.fluent import check_box, push_button
from multiwebcam.ui.theme import set_variant

_QUEUE_DEPTH_WARNING = 30  # frames (~1s at 30fps)
_TECHNICAL_LABEL_RE = re.compile(r"^(?:source|camera|cam)[_-]?\d+$", re.IGNORECASE)


class SourceTile(QFrame):
    """Displays a single video source with label and focus button.

    Signals:
        focus_requested: Emitted when user clicks focus button
        ignore_toggled(bool): Emitted when user toggles the ignore checkbox
    """

    focus_requested = Signal()  # User wants to focus this source
    ignore_toggled = Signal(bool)

    def __init__(
        self,
        source_id: int,
        label: str,
        ignore: bool = False,
        parent=None,
        *,
        display_index: int | None = None,
    ):
        super().__init__(parent)
        self._source_id = source_id
        self._display_index = display_index or source_id + 1
        self._ignored = ignore
        self.setObjectName("cameraTile")
        self.setProperty("ignored", "true" if ignore else "false")
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        # Frame display
        self._frame_label = AspectRatioLabel(fill_mode="cover")
        self._frame_label.setMinimumSize(120, 68)

        # Source label + resolution on one line
        self._camera_chip = QLabel(self._camera_title())
        self._camera_chip.setObjectName("cameraChip")
        self._name_label = QLabel(_friendly_label(label))
        self._name_label.setObjectName("cameraName")
        self._name_label.setVisible(bool(self._name_label.text()))
        self._resolution_label = QLabel("")
        self._resolution_label.setObjectName("captionLabel")
        self._state_chip = QLabel("在线")
        self._state_chip.setObjectName("stateChip")
        self._state_chip.setProperty("status", "online")

        self._ignore_cb = check_box("忽略")
        self._ignore_cb.setChecked(ignore)
        self._ignore_cb.toggled.connect(self._on_ignore_toggled)

        info_row = QHBoxLayout()
        info_row.setContentsMargins(0, 0, 0, 0)
        info_row.setSpacing(7)
        info_row.addWidget(self._camera_chip)
        info_row.addWidget(self._name_label)
        info_row.addStretch()
        info_row.addWidget(self._resolution_label)
        info_row.addWidget(self._state_chip)

        # Stats label
        self._stats_label = QLabel("-- fps")
        self._stats_label.setObjectName("captionLabel")
        self._quality_label = QLabel("质量: --")
        self._quality_label.setObjectName("qualityLabel")
        self._quality_label.setProperty("level", "muted")

        # Queue depth label (hidden when not recording)
        self._queue_label = QLabel("未保存帧: 0")
        self._queue_label.setObjectName("queueDepthLabel")
        self._queue_label.setProperty("warning", "false")
        self._queue_label.setVisible(False)
        self._queue_warning = False

        # Focus button
        self._focus_btn = push_button("画质设置")
        self._focus_btn.setToolTip("调整此相机的分辨率、帧率和画面参数")
        self._focus_btn.setObjectName("tileFocusButton")
        set_variant(self._focus_btn, "ghost")
        self._focus_btn.clicked.connect(self.focus_requested.emit)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 9)
        layout.setSpacing(8)
        layout.addLayout(info_row)
        info_row.addWidget(self._focus_btn)

        video_shell = QFrame()
        video_shell.setObjectName("videoShell")
        video_layout = QVBoxLayout(video_shell)
        video_layout.setContentsMargins(2, 2, 2, 2)
        video_layout.addWidget(self._frame_label)
        layout.addWidget(video_shell, stretch=1)

        metric_strip = QFrame()
        metric_strip.setObjectName("metricStrip")
        metric_layout = QHBoxLayout(metric_strip)
        metric_layout.setContentsMargins(9, 4, 6, 4)
        metric_layout.setSpacing(8)
        metric_layout.addWidget(self._stats_label)
        metric_layout.addWidget(self._quality_label, stretch=1)
        metric_layout.addWidget(self._queue_label)
        metric_layout.addWidget(self._ignore_cb)
        layout.addWidget(metric_strip)
        self._apply_ignored_state(ignore)

    def set_compact(self, compact: bool) -> None:
        """Reduce secondary chrome when the grid gives this tile little room."""
        self._name_label.setVisible(not compact and bool(self._name_label.text()))
        self._resolution_label.setVisible(not compact)
        self._quality_label.setVisible(not compact)
        self._focus_btn.setText("设置" if compact else "画质设置")

    @property
    def source_id(self) -> int:
        return self._source_id

    @property
    def display_index(self) -> int:
        return self._display_index

    def set_display_index(self, display_index: int) -> None:
        """Set the user-facing camera number shown in the tile header."""
        self._display_index = display_index
        self._camera_chip.setText(self._camera_title())

    def display_frame(self, pixmap: QPixmap) -> None:
        """Update the displayed frame. No-op when ignored."""
        if self._ignored:
            return
        if self._state_chip.text() != "在线":
            self._state_chip.setText("在线")
            self._state_chip.setProperty("status", "online")
            self._state_chip.style().unpolish(self._state_chip)
            self._state_chip.style().polish(self._state_chip)
        self._frame_label.display_pixmap(pixmap)

    def update_stats(self, fps: float, jitter_ms: float = 0.0) -> None:
        """Update stats display."""
        self._stats_label.setText(f"{fps:.1f} fps | 抖动 {jitter_ms:.1f}ms")

    def update_quality(self, summary: str, level: str) -> None:
        """Update realtime capture quality display."""
        compact = _compact_quality_summary(summary)
        self._quality_label.setText(f"质量: {compact}")
        self._quality_label.setToolTip(summary)
        self._quality_label.setProperty("level", level if level in {"good", "warn", "bad"} else "muted")
        self._repolish(self._quality_label)

    def set_queue_visible(self, visible: bool) -> None:
        """Show/hide queue label based on recording state."""
        self._queue_label.setVisible(visible)
        if not visible:
            self._queue_label.setText("未保存帧: 0")
            if self._queue_warning:
                self._queue_label.setProperty("warning", "false")
                self._repolish(self._queue_label)
                self._queue_warning = False

    def set_queue_depth(self, depth: int) -> None:
        """Update unsaved frame count. Does not change visibility."""
        self._queue_label.setText(f"未保存帧: {depth}")
        warning = depth >= _QUEUE_DEPTH_WARNING
        if warning != self._queue_warning:
            self._queue_label.setProperty("warning", "true" if warning else "false")
            self._repolish(self._queue_label)
            self._queue_warning = warning

    def set_resolution(self, resolution: str) -> None:
        """Show camera resolution (e.g., '1920x1080')."""
        self._resolution_label.setText(resolution)

    def set_error(self, message: str) -> None:
        """Show error state (e.g., disconnected)."""
        self._frame_label.setText(message)
        self._stats_label.setText("--")
        self._state_chip.setText("离线")
        self._state_chip.setProperty("status", "muted")
        self._state_chip.style().unpolish(self._state_chip)
        self._state_chip.style().polish(self._state_chip)

    def set_focus_enabled(self, enabled: bool, reason: str = "") -> None:
        """Enable/disable focus button. Shows reason text when disabled."""
        self._focus_btn.setEnabled(enabled and not self._ignored)
        self._ignore_cb.setEnabled(enabled)
        if enabled:
            self._focus_btn.setText("画质设置")
        elif reason:
            self._focus_btn.setText(reason)

    def set_ignore_enabled(self, enabled: bool) -> None:
        """Enable/disable the ignore checkbox."""
        self._ignore_cb.setEnabled(enabled)

    def set_ignored(self, ignored: bool) -> None:
        """Set ignored state without emitting ignore_toggled."""
        self._ignore_cb.blockSignals(True)
        self._ignore_cb.setChecked(ignored)
        self._ignore_cb.blockSignals(False)
        self._apply_ignored_state(ignored)

    def _on_ignore_toggled(self, checked: bool) -> None:
        self._apply_ignored_state(checked)
        self.ignore_toggled.emit(checked)

    def _apply_ignored_state(self, checked: bool) -> None:
        self._ignored = checked
        self.setProperty("ignored", "true" if checked else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        if checked:
            self._frame_label.clear()
            self._frame_label.setText("摄像头已忽略")
            self._state_chip.setText("忽略")
            self._state_chip.setProperty("status", "muted")
            self._frame_label.setProperty("ignored", "true")
            self._focus_btn.setEnabled(False)
        else:
            self._frame_label.setText("")
            self._state_chip.setText("在线")
            self._state_chip.setProperty("status", "online")
            self._frame_label.setProperty("ignored", "false")
            self._focus_btn.setEnabled(True)
        self._repolish(self._frame_label)
        self._state_chip.style().unpolish(self._state_chip)
        self._state_chip.style().polish(self._state_chip)

    def _camera_title(self) -> str:
        return f"相机 {self._display_index}"

    @staticmethod
    def _repolish(widget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def _friendly_label(label: str) -> str:
    """Hide default source labels that duplicate the camera number."""
    normalized = label.strip()
    if not normalized or _TECHNICAL_LABEL_RE.match(normalized):
        return ""
    return normalized


def _compact_quality_summary(summary: str) -> str:
    """Shorten detailed quality text so tiles do not grow horizontally."""
    parts = [part.strip() for part in summary.split("|")]
    if not parts:
        return "--"

    level = parts[0]
    compact_parts = [_zh_quality_level(level)]
    for part in parts[1:]:
        if part.startswith("sharp "):
            compact_parts.append("S" + part.split(" ", 1)[1])
        elif part.startswith("exp "):
            compact_parts.append("B" + part.split(" ", 1)[1])
        elif part.startswith("feat "):
            compact_parts.append("F" + part.split(" ", 1)[1])
    return " ".join(compact_parts[:4])


def _zh_quality_level(level: str) -> str:
    return {
        "GOOD": "良好",
        "WARN": "警告",
        "BAD": "较差",
    }.get(level, level)
