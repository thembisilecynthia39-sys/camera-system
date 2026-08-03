"""Progressively disclosed controls for display, camera, look, and output."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from camera_system_app.domain.viewer import (
    AppearanceSettings,
    CameraBookmark,
    CameraMode,
    CameraPose,
    DisplayMode,
    DisplaySettings,
    OutputKind,
    QualityPreset,
    RenderSettings,
)
from camera_system_app.ui.widgets.focus_wheel_spinbox import (
    SafeDoubleSpinBox,
    SafeSpinBox,
)


class CollapsibleSection(QWidget):
    """Keyboard-accessible explicit disclosure section."""

    def __init__(self, title, content, expanded=False, parent=None):
        super().__init__(parent)
        self._title = str(title)
        self._content = content
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._toggle = QToolButton()
        self._toggle.setText(self._title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(bool(expanded))
        self._toggle.setToolButtonStyle(2)
        self._toggle.setArrowType(4 if expanded else 1)
        self._toggle.setAccessibleName("展开或折叠" + self._title)
        layout.addWidget(self._toggle)
        layout.addWidget(content)
        content.setVisible(bool(expanded))
        self._toggle.toggled.connect(self._set_content_visible)

    def title(self):
        return self._title

    @property
    def is_expanded(self):
        return self._toggle.isChecked()

    def set_expanded(self, expanded):
        self._toggle.setChecked(bool(expanded))

    def _set_content_visible(self, expanded):
        self._content.setVisible(bool(expanded))
        self._toggle.setArrowType(4 if expanded else 1)


class ViewerInspector(QWidget):
    """Inspector whose controls map directly to ViewerProject settings."""

    display_settings_changed = Signal(object)
    appearance_settings_changed = Signal(object)
    render_settings_changed = Signal(object)
    fov_changed = Signal(float)
    camera_mode_changed = Signal(str)
    fly_speed_changed = Signal(float)
    bookmark_add_requested = Signal(str)
    bookmark_load_requested = Signal(str)
    bookmark_delete_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("viewerInspector")
        self.setMinimumWidth(280)
        self.setMaximumWidth(360)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(12)
        scroll.setWidget(content)
        root.addWidget(scroll)

        view_content = QWidget()
        view_form = QFormLayout(view_content)
        view_form.setContentsMargins(4, 4, 4, 4)
        view_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItem("Gaussian", DisplayMode.STANDARD.value)
        self.display_mode_combo.addItem("外接球线框", DisplayMode.SPHERE_WIREFRAME.value)
        self.display_mode_combo.addItem("外接球实体", DisplayMode.SPHERE_SOLID.value)
        self.display_mode_combo.addItem("Gaussian + 球体", DisplayMode.OVERLAY.value)
        self.display_mode_combo.setAccessibleName("Inspector Gaussian 显示模式")
        self.quality_combo = QComboBox()
        self.quality_combo.addItem("预览", QualityPreset.PREVIEW.value)
        self.quality_combo.addItem("高质量", QualityPreset.HIGH.value)
        self.quality_combo.addItem("最终", QualityPreset.FINAL.value)
        self.quality_combo.setCurrentIndex(1)
        self.sphere_sigma_multiplier = self._double(0.01, 20.0, 3.0, 0.1)
        self.sphere_opacity = self._double(0.0, 1.0, 0.5, 0.05)
        self.sphere_line_width = self._double(0.1, 8.0, 1.0, 0.1)
        self.sphere_color_mode = QComboBox()
        self.sphere_color_mode.addItem("Gaussian 颜色", "gaussian")
        self.sphere_color_mode.addItem("统一颜色", "uniform")
        view_form.addRow("显示模式", self.display_mode_combo)
        view_form.addRow("质量预设", self.quality_combo)
        view_form.addRow("外接球 σ 倍数", self.sphere_sigma_multiplier)
        view_form.addRow("球体透明度", self.sphere_opacity)
        view_form.addRow("线框宽度", self.sphere_line_width)
        view_form.addRow("球体颜色", self.sphere_color_mode)

        camera_content = QWidget()
        camera_form = QFormLayout(camera_content)
        camera_form.setContentsMargins(4, 4, 4, 4)
        self.fov = self._double(1.0, 179.0, 45.0, 1.0)
        self.camera_mode_combo = QComboBox()
        self.camera_mode_combo.addItem("轨道 Orbit", CameraMode.ORBIT.value)
        self.camera_mode_combo.addItem("飞行 Fly", CameraMode.FLY.value)
        self.camera_mode_combo.setAccessibleName("Inspector 相机导航模式")
        self.fly_speed = self._double(0.05, 20.0, 1.0, 0.1)
        self.bookmark_combo = QComboBox()
        self.bookmark_combo.setAccessibleName("Inspector 相机书签")
        self.bookmark_name_edit = QLineEdit()
        self.bookmark_name_edit.setPlaceholderText("例如：入口、展厅、细节")
        self.bookmark_add_button = QPushButton("保存当前位置")
        self.bookmark_load_button = QPushButton("跳转")
        self.bookmark_delete_button = QPushButton("删除")
        bookmark_actions = QHBoxLayout()
        bookmark_actions.setContentsMargins(0, 0, 0, 0)
        bookmark_actions.setSpacing(4)
        bookmark_actions.addWidget(self.bookmark_load_button)
        bookmark_actions.addWidget(self.bookmark_delete_button)
        camera_form.addRow("视场角", self.fov)
        camera_form.addRow("导航模式", self.camera_mode_combo)
        camera_form.addRow("飞行速度", self.fly_speed)
        camera_form.addRow("书签名称", self.bookmark_name_edit)
        camera_form.addRow("保存书签", self.bookmark_add_button)
        camera_form.addRow("已保存书签", self.bookmark_combo)
        camera_form.addRow("书签操作", bookmark_actions)

        appearance_content = QWidget()
        appearance_form = QFormLayout(appearance_content)
        appearance_form.setContentsMargins(4, 4, 4, 4)
        self.exposure = self._double(-20.0, 20.0, 0.0, 0.1)
        self.contrast = self._double(0.0, 4.0, 1.0, 0.05)
        self.saturation = self._double(0.0, 4.0, 1.0, 0.05)
        self.vignette = self._double(0.0, 1.0, 0.0, 0.05)
        self.sharpening = self._double(0.0, 1.0, 0.0, 0.05)
        appearance_form.addRow("曝光", self.exposure)
        appearance_form.addRow("对比度", self.contrast)
        appearance_form.addRow("饱和度", self.saturation)
        appearance_form.addRow("暗角", self.vignette)
        appearance_form.addRow("锐化", self.sharpening)

        render_content = QWidget()
        render_form = QFormLayout(render_content)
        render_form.setContentsMargins(4, 4, 4, 4)
        self.render_width = SafeSpinBox()
        self.render_width.setRange(1, 8192)
        self.render_width.setValue(1920)
        self.render_height = SafeSpinBox()
        self.render_height.setRange(1, 8192)
        self.render_height.setValue(1080)
        self.render_fps = self._double(1.0, 240.0, 30.0, 1.0)
        self.output_kind = QComboBox()
        self.output_kind.addItem("MP4 视频", OutputKind.MP4.value)
        self.output_kind.addItem("PNG 单帧", OutputKind.PNG.value)
        self.output_kind.addItem("PNG 序列", OutputKind.PNG_SEQUENCE.value)
        self.transparent_background = QCheckBox("透明背景（仅 PNG）")
        render_form.addRow("宽度", self.render_width)
        render_form.addRow("高度", self.render_height)
        render_form.addRow("帧率", self.render_fps)
        render_form.addRow("输出格式", self.output_kind)
        render_form.addRow("", self.transparent_background)

        self.sections = [
            CollapsibleSection("视图", view_content, expanded=True),
            CollapsibleSection("相机", camera_content, expanded=False),
            CollapsibleSection("外观", appearance_content, expanded=False),
            CollapsibleSection("渲染", render_content, expanded=False),
        ]
        for section in self.sections:
            content_layout.addWidget(section)
        content_layout.addStretch(1)

        for control in (
            self.display_mode_combo,
            self.quality_combo,
            self.sphere_sigma_multiplier,
            self.sphere_opacity,
            self.sphere_line_width,
            self.sphere_color_mode,
        ):
            signal = control.currentIndexChanged if isinstance(control, QComboBox) else control.valueChanged
            signal.connect(self._emit_display_settings)
        for control in (self.exposure, self.contrast, self.saturation, self.vignette, self.sharpening):
            control.valueChanged.connect(self._emit_appearance_settings)
        self.fov.valueChanged.connect(lambda value: self.fov_changed.emit(float(value)))
        self.camera_mode_combo.currentIndexChanged.connect(
            lambda _index: self.camera_mode_changed.emit(self.camera_mode_combo.currentData())
        )
        self.fly_speed.valueChanged.connect(
            lambda value: self.fly_speed_changed.emit(float(value))
        )
        self.bookmark_add_button.clicked.connect(
            lambda: self.bookmark_add_requested.emit(self.bookmark_name_edit.text().strip())
        )
        self.bookmark_load_button.clicked.connect(
            lambda: self.bookmark_load_requested.emit(self.bookmark_combo.currentData())
        )
        self.bookmark_delete_button.clicked.connect(
            lambda: self.bookmark_delete_requested.emit(self.bookmark_combo.currentData())
        )
        self.bookmark_name_edit.textChanged.connect(self._update_bookmark_actions)
        self.bookmark_combo.currentIndexChanged.connect(self._update_bookmark_actions)
        self._update_bookmark_actions()
        for control in (self.render_width, self.render_height, self.render_fps, self.output_kind, self.transparent_background):
            signal = (
                control.valueChanged
                if isinstance(control, (SafeSpinBox, SafeDoubleSpinBox))
                else control.currentIndexChanged
                if isinstance(control, QComboBox)
                else control.toggled
            )
            signal.connect(self._emit_render_settings)

    @staticmethod
    def _double(minimum, maximum, value, step):
        box = SafeDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setSingleStep(step)
        box.setValue(value)
        return box

    def _emit_display_settings(self, *_args):
        self.display_settings_changed.emit(self.display_settings())

    def _emit_appearance_settings(self, *_args):
        self.appearance_settings_changed.emit(self.appearance_settings())

    def _emit_render_settings(self, *_args):
        self.render_settings_changed.emit(self.render_settings())

    def _update_bookmark_actions(self, *_args):
        has_name = bool(self.bookmark_name_edit.text().strip())
        has_selection = self.bookmark_combo.currentIndex() >= 0
        self.bookmark_add_button.setEnabled(has_name)
        self.bookmark_load_button.setEnabled(has_selection)
        self.bookmark_delete_button.setEnabled(has_selection)

    def display_settings(self):
        return DisplaySettings(
            mode=self.display_mode_combo.currentData(),
            quality=self.quality_combo.currentData(),
            sphere_sigma_multiplier=self.sphere_sigma_multiplier.value(),
            sphere_opacity=self.sphere_opacity.value(),
            sphere_line_width=self.sphere_line_width.value(),
            sphere_color_mode=self.sphere_color_mode.currentData(),
        )

    def appearance_settings(self):
        return AppearanceSettings(
            exposure=self.exposure.value(),
            contrast=self.contrast.value(),
            saturation=self.saturation.value(),
            vignette=self.vignette.value(),
            sharpening=self.sharpening.value(),
        )

    def render_settings(self):
        return RenderSettings(
            width=self.render_width.value(),
            height=self.render_height.value(),
            fps=self.render_fps.value(),
            output_kind=self.output_kind.currentData(),
            transparent_background=self.transparent_background.isChecked(),
        )

    def set_display_settings(self, settings):
        if not isinstance(settings, DisplaySettings):
            raise ValueError("display settings must be a DisplaySettings value")
        controls = (
            self.display_mode_combo,
            self.quality_combo,
            self.sphere_sigma_multiplier,
            self.sphere_opacity,
            self.sphere_line_width,
            self.sphere_color_mode,
        )
        blockers = [QSignalBlocker(control) for control in controls]
        self.display_mode_combo.setCurrentIndex(self.display_mode_combo.findData(settings.mode.value))
        self.quality_combo.setCurrentIndex(self.quality_combo.findData(settings.quality.value))
        self.sphere_sigma_multiplier.setValue(settings.sphere_sigma_multiplier)
        self.sphere_opacity.setValue(settings.sphere_opacity)
        self.sphere_line_width.setValue(settings.sphere_line_width)
        self.sphere_color_mode.setCurrentIndex(self.sphere_color_mode.findData(settings.sphere_color_mode))
        del blockers

    def set_appearance_settings(self, settings):
        if not isinstance(settings, AppearanceSettings):
            raise ValueError("appearance settings must be an AppearanceSettings value")
        controls = (self.exposure, self.contrast, self.saturation, self.vignette, self.sharpening)
        blockers = [QSignalBlocker(control) for control in controls]
        self.exposure.setValue(settings.exposure)
        self.contrast.setValue(settings.contrast)
        self.saturation.setValue(settings.saturation)
        self.vignette.setValue(settings.vignette)
        self.sharpening.setValue(settings.sharpening)
        del blockers

    def set_render_settings(self, settings):
        if not isinstance(settings, RenderSettings):
            raise ValueError("render settings must be a RenderSettings value")
        controls = (self.render_width, self.render_height, self.render_fps, self.output_kind, self.transparent_background)
        blockers = [QSignalBlocker(control) for control in controls]
        self.render_width.setValue(settings.width)
        self.render_height.setValue(settings.height)
        self.render_fps.setValue(settings.fps)
        self.output_kind.setCurrentIndex(self.output_kind.findData(settings.output_kind.value))
        self.transparent_background.setChecked(settings.transparent_background)
        del blockers

    def set_camera_pose(self, pose):
        if not isinstance(pose, CameraPose):
            raise ValueError("camera pose must be a CameraPose value")
        blocker = QSignalBlocker(self.fov)
        self.fov.setValue(pose.fov_degrees)
        del blocker

    def set_camera_mode(self, mode):
        mode = mode if isinstance(mode, CameraMode) else CameraMode(mode)
        blocker = QSignalBlocker(self.camera_mode_combo)
        self.camera_mode_combo.setCurrentIndex(
            self.camera_mode_combo.findData(mode.value)
        )
        del blocker

    def set_fly_speed(self, speed):
        blocker = QSignalBlocker(self.fly_speed)
        self.fly_speed.setValue(float(speed))
        del blocker

    def set_bookmarks(self, bookmarks):
        bookmarks = tuple(bookmarks)
        if any(not isinstance(bookmark, CameraBookmark) for bookmark in bookmarks):
            raise ValueError("bookmarks must be CameraBookmark values")
        blocker = QSignalBlocker(self.bookmark_combo)
        self.bookmark_combo.clear()
        for bookmark in bookmarks:
            self.bookmark_combo.addItem(bookmark.name, bookmark.bookmark_id)
        del blocker
        self._update_bookmark_actions()


__all__ = ["CollapsibleSection", "ViewerInspector"]
