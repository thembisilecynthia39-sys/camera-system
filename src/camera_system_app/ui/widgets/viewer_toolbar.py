"""Compact high-frequency controls for the 3DGS studio."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QSizePolicy,
    QWidget,
)

from camera_system_app.domain.viewer import DisplayMode, QualityPreset


class ViewerToolbar(QWidget):
    """Expose the actions needed while roaming without a modal dialog."""

    open_requested = Signal()
    save_requested = Signal()
    save_as_requested = Signal()
    reset_requested = Signal()
    fit_requested = Signal()
    display_mode_changed = Signal(str)
    quality_changed = Signal(str)
    view_preset_changed = Signal(str)
    play_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    presentation_requested = Signal()
    render_requested = Signal()
    inspector_requested = Signal()
    timeline_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("viewerToolbar")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        primary_row = QHBoxLayout()
        primary_row.setSpacing(6)
        playback_row = QHBoxLayout()
        playback_row.setSpacing(6)

        self._open = self._button("打开", "打开本地 Gaussian PLY")
        self._reset = self._button("重置", "重置相机视角")
        self._fit = self._button("适配", "适配场景到视口")
        primary_row.addWidget(self._open)
        primary_row.addWidget(self._reset)
        primary_row.addWidget(self._fit)

        self.save_button = self._button("保存", "保存 3DGS 查看器项目")
        self.save_as_button = self._button("另存", "将 3DGS 查看器项目另存为")
        primary_row.addWidget(self.save_button)
        primary_row.addWidget(self.save_as_button)

        display_label = QLabel("显示")
        display_label.setObjectName("viewerToolbarLabel")
        primary_row.addWidget(display_label)
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.setAccessibleName("Gaussian 显示模式")
        self.display_mode_combo.addItem("Gaussian", DisplayMode.STANDARD.value)
        self.display_mode_combo.addItem("外接球线框", DisplayMode.SPHERE_WIREFRAME.value)
        self.display_mode_combo.addItem("外接球实体", DisplayMode.SPHERE_SOLID.value)
        self.display_mode_combo.addItem("Gaussian + 球体", DisplayMode.OVERLAY.value)
        primary_row.addWidget(self.display_mode_combo)

        quality_label = QLabel("质量")
        quality_label.setObjectName("viewerToolbarLabel")
        primary_row.addWidget(quality_label)
        self.quality_combo = QComboBox()
        self.quality_combo.setAccessibleName("查看质量预设")
        self.quality_combo.addItem("预览", QualityPreset.PREVIEW.value)
        self.quality_combo.addItem("高质量", QualityPreset.HIGH.value)
        self.quality_combo.addItem("最终", QualityPreset.FINAL.value)
        self.quality_combo.setCurrentIndex(1)
        primary_row.addWidget(self.quality_combo)

        self._view_label = QLabel("视角")
        self._view_label.setObjectName("viewerToolbarLabel")
        primary_row.addWidget(self._view_label)
        self.view_preset_combo = QComboBox()
        self.view_preset_combo.setAccessibleName("标准相机视角")
        self.view_preset_combo.addItem("当前", "current")
        self.view_preset_combo.addItem("前", "front")
        self.view_preset_combo.addItem("后", "back")
        self.view_preset_combo.addItem("左", "left")
        self.view_preset_combo.addItem("右", "right")
        self.view_preset_combo.addItem("上", "top")
        self.view_preset_combo.addItem("下", "bottom")
        primary_row.addWidget(self.view_preset_combo)

        self.play_button = self._button("播放", "播放相机漫游")
        self.play_button.setCheckable(True)
        self.stop_button = self._button("停止", "停止相机漫游")
        self.presentation_button = self._button("演示", "进入全屏演示模式")
        self.render_button = self._button("导出", "导出 PNG 或 MP4")
        self.render_button.setObjectName("primaryButton")
        playback_row.addWidget(self.play_button)
        playback_row.addWidget(self.stop_button)
        self.inspector_button = self._button("参数", "显示或隐藏查看器参数面板")
        self.inspector_button.setCheckable(True)
        self.timeline_button = self._button("时间轴", "显示或隐藏 Camera Director 时间轴")
        playback_row.addWidget(self.inspector_button)
        playback_row.addWidget(self.timeline_button)
        playback_row.addWidget(self.presentation_button)
        playback_row.addWidget(self.render_button)
        playback_row.addStretch(1)
        layout.addLayout(primary_row)
        layout.addLayout(playback_row)

        self._open.clicked.connect(self.open_requested.emit)
        self.save_button.clicked.connect(self.save_requested.emit)
        self.save_as_button.clicked.connect(self.save_as_requested.emit)
        self._reset.clicked.connect(self.reset_requested.emit)
        self._fit.clicked.connect(self.fit_requested.emit)
        self.display_mode_combo.currentIndexChanged.connect(self._emit_mode)
        self.quality_combo.currentIndexChanged.connect(self._emit_quality)
        self.view_preset_combo.currentIndexChanged.connect(self._emit_view_preset)
        self.play_button.toggled.connect(self._emit_playback)
        self.stop_button.clicked.connect(self._stop_playback)
        self.inspector_button.clicked.connect(self.inspector_requested.emit)
        self.timeline_button.clicked.connect(self.timeline_requested.emit)
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

    def _emit_view_preset(self, index):
        value = self.view_preset_combo.itemData(index)
        if value in (None, "current"):
            return
        self.view_preset_changed.emit(str(value))
        blocker = QSignalBlocker(self.view_preset_combo)
        self.view_preset_combo.setCurrentIndex(0)
        del blocker

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
        blocker = QSignalBlocker(self.play_button)
        self.play_button.setChecked(bool(playing))
        del blocker
        self.play_button.setText("暂停" if playing else "播放")

    def set_project_dirty(self, dirty):
        self.save_button.setText("保存*" if dirty else "保存")

    def set_inspector_expanded(self, expanded):
        blocker = QSignalBlocker(self.inspector_button)
        self.inspector_button.setChecked(bool(expanded))
        del blocker

    def resizeEvent(self, event):
        narrow = event.size().width() < 900
        self._view_label.setVisible(not narrow)
        self.view_preset_combo.setVisible(not narrow)
        super().resizeEvent(event)

    def set_sphere_modes_available(self, available, error=""):
        available = bool(available)
        combo = self.display_mode_combo
        for value in (
            DisplayMode.SPHERE_WIREFRAME.value,
            DisplayMode.SPHERE_SOLID.value,
            DisplayMode.OVERLAY.value,
        ):
            index = combo.findData(value)
            if index >= 0:
                combo.model().item(index).setEnabled(available)
        if not available and combo.currentData() != DisplayMode.STANDARD.value:
            blocker = QSignalBlocker(combo)
            combo.setCurrentIndex(combo.findData(DisplayMode.STANDARD.value))
            del blocker
        combo.setToolTip(
            "外接球显示不可用：{}".format(error)
            if not available and error
            else "Gaussian 显示模式"
        )


__all__ = ["ViewerToolbar"]
