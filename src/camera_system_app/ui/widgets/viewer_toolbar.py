"""Compact high-frequency controls for the 3DGS studio."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QWidget,
)

from camera_system_app.domain.viewer import DisplayMode, QualityPreset


class ViewerToolbar(QWidget):
    """Expose the actions needed while roaming without a modal dialog."""

    open_requested = Signal()
    reset_requested = Signal()
    fit_requested = Signal()
    display_mode_changed = Signal(str)
    quality_changed = Signal(str)
    play_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    presentation_requested = Signal()
    render_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("viewerToolbar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._open = self._button("打开", "打开本地 Gaussian PLY")
        self._reset = self._button("重置", "重置相机视角")
        self._fit = self._button("适配", "适配场景到视口")
        layout.addWidget(self._open)
        layout.addWidget(self._reset)
        layout.addWidget(self._fit)

        display_label = QLabel("显示")
        display_label.setObjectName("viewerToolbarLabel")
        layout.addWidget(display_label)
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.setAccessibleName("Gaussian 显示模式")
        self.display_mode_combo.addItem("Gaussian", DisplayMode.STANDARD.value)
        self.display_mode_combo.addItem("外接球线框", DisplayMode.SPHERE_WIREFRAME.value)
        self.display_mode_combo.addItem("外接球实体", DisplayMode.SPHERE_SOLID.value)
        self.display_mode_combo.addItem("Gaussian + 球体", DisplayMode.OVERLAY.value)
        layout.addWidget(self.display_mode_combo)

        quality_label = QLabel("质量")
        quality_label.setObjectName("viewerToolbarLabel")
        layout.addWidget(quality_label)
        self.quality_combo = QComboBox()
        self.quality_combo.setAccessibleName("查看质量预设")
        self.quality_combo.addItem("预览", QualityPreset.PREVIEW.value)
        self.quality_combo.addItem("高质量", QualityPreset.HIGH.value)
        self.quality_combo.addItem("最终", QualityPreset.FINAL.value)
        self.quality_combo.setCurrentIndex(1)
        layout.addWidget(self.quality_combo)

        self.play_button = self._button("播放", "播放相机漫游")
        self.play_button.setCheckable(True)
        self.stop_button = self._button("停止", "停止相机漫游")
        self.presentation_button = self._button("演示", "进入全屏演示模式")
        self.render_button = self._button("导出", "导出 PNG 或 MP4")
        self.render_button.setObjectName("primaryButton")
        layout.addWidget(self.play_button)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.presentation_button)
        layout.addWidget(self.render_button)
        layout.addStretch(1)

        self._open.clicked.connect(self.open_requested.emit)
        self._reset.clicked.connect(self.reset_requested.emit)
        self._fit.clicked.connect(self.fit_requested.emit)
        self.display_mode_combo.currentIndexChanged.connect(self._emit_mode)
        self.quality_combo.currentIndexChanged.connect(self._emit_quality)
        self.play_button.toggled.connect(self._emit_playback)
        self.stop_button.clicked.connect(self._stop_playback)
        self.presentation_button.clicked.connect(self.presentation_requested.emit)
        self.render_button.clicked.connect(self.render_requested.emit)

    @staticmethod
    def _button(text, accessible_name):
        button = QToolButton()
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setMinimumHeight(40)
        button.setAccessibleName(accessible_name)
        return button

    def _emit_mode(self, index):
        value = self.display_mode_combo.itemData(index)
        if value is not None:
            self.display_mode_changed.emit(str(value))

    def _emit_quality(self, index):
        value = self.quality_combo.itemData(index)
        if value is not None:
            self.quality_changed.emit(str(value))

    def _emit_playback(self, playing):
        if playing:
            self.play_button.setText("暂停")
            self.play_requested.emit()
        else:
            self.play_button.setText("播放")
            self.pause_requested.emit()

    def _stop_playback(self):
        self.play_button.setChecked(False)
        self.stop_requested.emit()

    def set_playing(self, playing):
        self.play_button.setChecked(bool(playing))


__all__ = ["ViewerToolbar"]
