"""Focus view for single source with detailed controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from multiwebcam.pipeline.report import CameraStats
from multiwebcam.sources.controls import V4L2Control
from multiwebcam.ui.fluent import combo_box, push_button
from multiwebcam.ui.theme import set_variant, status_style
from multiwebcam.ui.views.aspect_ratio_label import AspectRatioLabel
from multiwebcam.ui.views.control_panel import ControlPanel


class FocusView(QWidget):
    """Large preview of single source with configuration panel.

    Format is locked to MJPEG (lower USB bandwidth, universal support).
    Only resolution and framerate are user-configurable.

    Signals:
        back_requested: User wants to return to grid view
        resolution_selected: User changed resolution combo
        apply_requested: User clicked Apply button
    """

    back_requested = Signal()
    resolution_selected = Signal(str)
    apply_requested = Signal()
    record_requested = Signal()
    stop_requested = Signal()

    def __init__(self, source_id: int, label: str, parent=None):
        super().__init__(parent)
        self._source_id = source_id
        self._control_panel: ControlPanel | None = None
        self.setObjectName("focusSurface")

        # Main horizontal layout: video on left, settings panel on right
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # Left: Video display (75% width)
        preview_column = QVBoxLayout()
        preview_column.setContentsMargins(0, 0, 0, 0)
        preview_column.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        brand = QLabel("边端 3DGS 重建")
        brand.setObjectName("brandMark")
        title = QLabel("单机位画质设置")
        title.setObjectName("pageTitle")
        title_block.addWidget(brand)
        title_block.addWidget(title)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.addLayout(title_block)
        title_row.addStretch()
        self._info_label = QLabel(f"●  {label} · 信号 {source_id}")
        self._info_label.setObjectName("liveBadge")
        title_row.addWidget(self._info_label)
        preview_column.addLayout(title_row)

        video_shell = QFrame()
        video_shell.setObjectName("videoShell")
        video_layout = QVBoxLayout(video_shell)
        video_layout.setContentsMargins(3, 3, 3, 3)
        self._frame_label = AspectRatioLabel()
        self._frame_label.setMinimumSize(240, 180)
        video_layout.addWidget(self._frame_label)
        preview_column.addWidget(video_shell, stretch=1)
        main_layout.addLayout(preview_column, stretch=3)

        # Right: Settings panel (25% width)
        side_panel = QFrame()
        side_panel.setObjectName("sidePanel")
        side_panel.setMinimumWidth(230)
        side_panel.setMaximumWidth(320)
        side_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._panel_layout = QVBoxLayout(side_panel)
        self._panel_layout.setContentsMargins(16, 16, 16, 14)
        self._panel_layout.setSpacing(11)
        main_layout.addWidget(side_panel)

        # Configuration section header
        config_kicker = QLabel("当前相机")
        config_kicker.setObjectName("sideLabel")
        self._panel_layout.addWidget(config_kicker)

        config_header = QLabel("视频格式")
        config_header.setObjectName("sectionTitle")
        self._panel_layout.addWidget(config_header)

        config_hint = QLabel("每台相机可独立选择分辨率与帧率，修改后点击应用")
        config_hint.setObjectName("captionLabel")
        config_hint.setWordWrap(True)
        self._panel_layout.addWidget(config_hint)

        # Configuration controls using QFormLayout
        config_form = QFormLayout()
        config_form.setHorizontalSpacing(10)
        config_form.setVerticalSpacing(10)
        self._panel_layout.addLayout(config_form)

        self._resolution_combo = combo_box()
        config_form.addRow("分辨率", self._resolution_combo)

        self._framerate_combo = combo_box()
        config_form.addRow("帧率", self._framerate_combo)

        # Apply button
        self._apply_btn = push_button("应用视频格式", primary=True)
        set_variant(self._apply_btn, "primary")
        self._panel_layout.addWidget(self._apply_btn)

        self._config_status_label = QLabel("")
        self._config_status_label.setObjectName("captionLabel")
        self._panel_layout.addWidget(self._config_status_label)

        recording_title = QLabel("录制控制")
        recording_title.setObjectName("sideLabel")
        self._panel_layout.addSpacing(4)
        self._panel_layout.addWidget(recording_title)

        # Recording buttons
        recording_layout = QHBoxLayout()
        recording_layout.setContentsMargins(0, 0, 0, 0)
        self._record_btn = QPushButton("开始录制")
        self._stop_btn = push_button("停止")
        self._stop_btn.setEnabled(False)
        set_variant(self._record_btn, "record")
        set_variant(self._stop_btn, "ghost")
        recording_layout.addWidget(self._record_btn)
        recording_layout.addWidget(self._stop_btn)
        self._panel_layout.addLayout(recording_layout)

        self._panel_layout.addSpacing(8)

        # Stats label
        self._stats_label = QLabel("-- fps | -- jitter")
        self._stats_label.setObjectName("statusPill")
        self._panel_layout.addWidget(self._stats_label)

        # Push back button to bottom
        self._panel_layout.addStretch()

        # Back button
        self._back_btn = push_button("返回视频墙")
        set_variant(self._back_btn, "ghost")
        self._panel_layout.addWidget(self._back_btn)

        # Wire up signals
        self._resolution_combo.currentTextChanged.connect(self.resolution_selected.emit)
        self._apply_btn.clicked.connect(self._on_apply_clicked)
        self._record_btn.clicked.connect(self.record_requested.emit)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        self._back_btn.clicked.connect(self.back_requested.emit)

    @property
    def source_id(self) -> int:
        return self._source_id

    def display_frame(self, pixmap: QPixmap) -> None:
        """Update the displayed frame."""
        self._frame_label.display_pixmap(pixmap)

    def update_stats(self, stats: CameraStats) -> None:
        """Update stats display."""
        self._stats_label.setText(f"{stats.measured_fps:.1f} fps | 抖动 {stats.jitter_ms:.1f}ms")

    def populate_resolutions(self, resolutions: list[str]) -> None:
        """Populate resolution combo. Blocks signals during population."""
        self._resolution_combo.blockSignals(True)
        self._resolution_combo.clear()
        self._resolution_combo.addItems(resolutions)
        self._resolution_combo.blockSignals(False)

    def populate_framerates(self, framerates: list[str]) -> None:
        """Populate framerate combo. Blocks signals during population."""
        self._framerate_combo.blockSignals(True)
        self._framerate_combo.clear()
        self._framerate_combo.addItems(framerates)
        self._framerate_combo.blockSignals(False)

    def set_current_config(self, resolution: str, framerate: str) -> None:
        """Set current selection in combos without triggering signals."""
        self._resolution_combo.blockSignals(True)
        self._framerate_combo.blockSignals(True)

        self._resolution_combo.setCurrentText(resolution)
        self._framerate_combo.setCurrentText(framerate)

        self._resolution_combo.blockSignals(False)
        self._framerate_combo.blockSignals(False)

    def set_config_enabled(self, enabled: bool) -> None:
        """Enable/disable all config controls (disabled during recording)."""
        self._resolution_combo.setEnabled(enabled)
        self._framerate_combo.setEnabled(enabled)
        self._apply_btn.setEnabled(enabled)

    def _on_apply_clicked(self) -> None:
        self._config_status_label.setText("正在应用配置...")
        self._config_status_label.setStyleSheet(status_style("muted", bold=False))
        self.apply_requested.emit()

    @property
    def selected_resolution(self) -> tuple[int, int]:
        """Parse 'WxH' string back to tuple."""
        text = self._resolution_combo.currentText()
        if not text or "x" not in text:
            return (0, 0)
        w, h = text.split("x")
        return (int(w), int(h))

    @property
    def selected_framerate(self) -> int:
        """Return currently selected framerate."""
        text = self._framerate_combo.currentText()
        return int(text) if text else 0

    def set_controls(self, controls: list[V4L2Control]) -> None:
        """Create and embed the control panel in the side panel.

        Inserts below the config section, above info/stats labels.
        Replaces any existing control panel.
        """
        # Remove existing panel if any
        if self._control_panel is not None:
            self._panel_layout.removeWidget(self._control_panel)
            self._control_panel.deleteLater()

        self._control_panel = ControlPanel(controls, self)
        # Insert before the live stats block.
        idx = self._panel_layout.indexOf(self._stats_label)
        self._panel_layout.insertWidget(idx, self._control_panel)

    @property
    def control_panel(self) -> ControlPanel | None:
        """The embedded control panel, or None if not yet created."""
        return self._control_panel

    def set_config_applied(self, config: object) -> None:
        """Show successful resolution/framerate application feedback."""
        resolution = getattr(config, "resolution", self.selected_resolution)
        fps = getattr(config, "fps", self.selected_framerate)
        w, h = resolution
        self._config_status_label.setText(f"已应用: {w}x{h} @ {fps}fps")
        self._config_status_label.setStyleSheet(status_style("success"))

    def set_config_error(self, error: str) -> None:
        """Show failed configuration application feedback."""
        self._config_status_label.setText(f"应用失败: {error}")
        self._config_status_label.setStyleSheet(status_style("danger"))

    def set_recording(self, recording: bool) -> None:
        """Update UI state for recording mode.

        During recording: disable config controls, record, and back.
        Control panel stays functional (adjust exposure mid-recording).
        """
        self._record_btn.setEnabled(not recording)
        self._stop_btn.setEnabled(recording)
        self._stop_btn.setText("停止")
        self.set_config_enabled(not recording)
        self._back_btn.setEnabled(not recording)

    def set_stopping(self) -> None:
        """Recording stop in progress -- disable everything interactive."""
        self._record_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setText("停止中...")
        self._back_btn.setEnabled(False)
