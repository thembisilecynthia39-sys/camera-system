"""Progressively disclosed controls for display, camera, look, and output."""

from __future__ import annotations

from dataclasses import replace

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
    camera_pose_changed = Signal(object)
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
        self.sphere_all_instances = QCheckBox("交互时显示全部外接球")
        self.sphere_all_instances.setAccessibleName("交互时显示全部外接球")
        self.sphere_color_mode = QComboBox()
        self.sphere_color_mode.addItem("Gaussian 颜色", "gaussian")
        self.sphere_color_mode.addItem("统一颜色", "uniform")
        self.show_grid_checkbox = QCheckBox("显示地面网格")
        self.show_grid_checkbox.setAccessibleName("显示地面网格")
        self.show_axis_checkbox = QCheckBox("显示坐标轴")
        self.show_axis_checkbox.setAccessibleName("显示坐标轴")
        self.show_bounds_checkbox = QCheckBox("显示包围盒")
        self.show_bounds_checkbox.setAccessibleName("显示场景包围盒")
        self.show_center_checkbox = QCheckBox("显示场景中心")
        self.show_center_checkbox.setAccessibleName("显示场景中心")
        self.show_camera_info_checkbox = QCheckBox("显示相机信息")
        self.show_camera_info_checkbox.setAccessibleName("显示相机信息")
        self._background_color = DisplaySettings().background_color
        self.background_color_edit = QLineEdit(
            self._color_to_hex(self._background_color)
        )
        self.background_color_edit.setPlaceholderText("#RRGGBB")
        self.background_color_edit.setAccessibleName("查看器背景颜色")
        view_form.addRow("显示模式", self.display_mode_combo)
        view_form.addRow("质量预设", self.quality_combo)
        view_form.addRow("外接球 σ 倍数", self.sphere_sigma_multiplier)
        view_form.addRow("球体透明度", self.sphere_opacity)
        view_form.addRow("线框宽度", self.sphere_line_width)
        view_form.addRow("交互显示", self.sphere_all_instances)
        view_form.addRow("球体颜色", self.sphere_color_mode)
        view_form.addRow("网格", self.show_grid_checkbox)
        view_form.addRow("坐标轴", self.show_axis_checkbox)
        view_form.addRow("包围盒", self.show_bounds_checkbox)
        view_form.addRow("中心标记", self.show_center_checkbox)
        view_form.addRow("相机叠加", self.show_camera_info_checkbox)
        view_form.addRow("背景颜色", self.background_color_edit)

        camera_content = QWidget()
        camera_form = QFormLayout(camera_content)
        camera_form.setContentsMargins(4, 4, 4, 4)
        self._camera_pose = CameraPose()
        self.fov = self._double(1.0, 179.0, 45.0, 1.0)
        self.position_x = self._coordinate()
        self.position_y = self._coordinate()
        self.position_z = self._coordinate()
        self.target_x = self._coordinate()
        self.target_y = self._coordinate()
        self.target_z = self._coordinate()
        position_row = self._coordinate_row(
            self.position_x, self.position_y, self.position_z
        )
        target_row = self._coordinate_row(
            self.target_x, self.target_y, self.target_z
        )
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
        camera_form.addRow("相机位置 XYZ", position_row)
        camera_form.addRow("观察目标 XYZ", target_row)
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
        self.tone_mapping_combo = QComboBox()
        self.tone_mapping_combo.addItem("ACES", "aces")
        self.tone_mapping_combo.addItem("Reinhard", "reinhard")
        self.tone_mapping_combo.addItem("关闭", "none")
        self.sh_degree_combo = QComboBox()
        self.sh_degree_combo.addItem("DC（0 阶）", 0)
        self.sh_degree_combo.addItem("SH 1 阶", 1)
        self.sh_degree_combo.addItem("SH 2 阶", 2)
        self.sh_degree_combo.addItem("SH 3 阶", 3)
        self.sh_degree_combo.setCurrentIndex(self.sh_degree_combo.findData(3))
        self.sh_degree_combo.setAccessibleName("球谐颜色质量")
        appearance_form.addRow("曝光", self.exposure)
        appearance_form.addRow("色调映射", self.tone_mapping_combo)
        appearance_form.addRow("球谐质量", self.sh_degree_combo)
        appearance_form.addRow("对比度", self.contrast)
        appearance_form.addRow("饱和度", self.saturation)
        appearance_form.addRow("暗角", self.vignette)
        appearance_form.addRow("锐化", self.sharpening)

        render_content = QWidget()
        render_form = QFormLayout(render_content)
        render_form.setContentsMargins(4, 4, 4, 4)
        self.resolution_preset_combo = QComboBox()
        self._viewport_size = (1920, 1080)
        self.resolution_preset_combo.addItem("当前视口 · 1920×1080", "viewport")
        self.resolution_preset_combo.addItem("720p · 1280×720", "720p")
        self.resolution_preset_combo.addItem("1080p · 1920×1080", "1080p")
        self.resolution_preset_combo.addItem("自定义", "custom")
        self.resolution_preset_combo.setCurrentIndex(
            self.resolution_preset_combo.findData("1080p")
        )
        self.resolution_preset_combo.setAccessibleName("导出分辨率预设")
        self.render_width = SafeSpinBox()
        self.render_width.setRange(1, 8192)
        self.render_width.setValue(1920)
        self.render_height = SafeSpinBox()
        self.render_height.setRange(1, 8192)
        self.render_height.setValue(1080)
        self.render_fps = self._double(1.0, 240.0, 30.0, 1.0)
        self.fps_preset_combo = QComboBox()
        self.fps_preset_combo.addItem("24 FPS", 24.0)
        self.fps_preset_combo.addItem("25 FPS", 25.0)
        self.fps_preset_combo.addItem("30 FPS", 30.0)
        self.fps_preset_combo.addItem("60 FPS", 60.0)
        self.fps_preset_combo.addItem("自定义", None)
        self.fps_preset_combo.setCurrentIndex(self.fps_preset_combo.findData(30.0))
        self.fps_preset_combo.setAccessibleName("导出帧率预设")
        self.output_kind = QComboBox()
        self.output_kind.addItem("MP4 视频", OutputKind.MP4.value)
        self.output_kind.addItem("PNG 单帧", OutputKind.PNG.value)
        self.output_kind.addItem("PNG 序列", OutputKind.PNG_SEQUENCE.value)
        self.transparent_background = QCheckBox("透明背景（仅 PNG）")
        render_form.addRow("分辨率预设", self.resolution_preset_combo)
        render_form.addRow("宽度", self.render_width)
        render_form.addRow("高度", self.render_height)
        render_form.addRow("帧率预设", self.fps_preset_combo)
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
            self.show_grid_checkbox,
            self.show_axis_checkbox,
            self.show_bounds_checkbox,
            self.show_center_checkbox,
            self.show_camera_info_checkbox,
        ):
            signal = (
                control.currentIndexChanged
                if isinstance(control, QComboBox)
                else control.toggled
                if isinstance(control, QCheckBox)
                else control.valueChanged
            )
            signal.connect(self._emit_display_settings)
        self.sphere_all_instances.toggled.connect(self._emit_display_settings)
        self.background_color_edit.editingFinished.connect(
            self._background_color_edited
        )
        for control in (self.exposure, self.contrast, self.saturation, self.vignette, self.sharpening):
            control.valueChanged.connect(self._emit_appearance_settings)
        self.tone_mapping_combo.currentIndexChanged.connect(
            self._emit_appearance_settings
        )
        self.sh_degree_combo.currentIndexChanged.connect(
            self._emit_appearance_settings
        )
        self.fov.valueChanged.connect(self._fov_value_changed)
        for control in (
            self.position_x,
            self.position_y,
            self.position_z,
            self.target_x,
            self.target_y,
            self.target_z,
        ):
            control.valueChanged.connect(self._emit_camera_pose)
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
        for control in (
            self.render_width,
            self.render_height,
            self.render_fps,
            self.output_kind,
            self.transparent_background,
        ):
            signal = (
                control.valueChanged
                if isinstance(control, (SafeSpinBox, SafeDoubleSpinBox))
                else control.currentIndexChanged
                if isinstance(control, QComboBox)
                else control.toggled
            )
            signal.connect(self._emit_render_settings)
        self.resolution_preset_combo.currentIndexChanged.connect(
            self._resolution_preset_changed
        )
        self.fps_preset_combo.currentIndexChanged.connect(self._fps_preset_changed)
        self.output_kind.currentIndexChanged.connect(self._update_transparency_state)
        self._update_transparency_state()

    @staticmethod
    def _double(minimum, maximum, value, step):
        box = SafeDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setSingleStep(step)
        box.setValue(value)
        return box

    @staticmethod
    def _coordinate():
        box = SafeDoubleSpinBox()
        box.setRange(-1000000.0, 1000000.0)
        box.setDecimals(3)
        box.setSingleStep(0.1)
        return box

    @staticmethod
    def _coordinate_row(*controls):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        for control in controls:
            row.addWidget(control)
        return row

    @staticmethod
    def _color_to_hex(color):
        return "#{:02x}{:02x}{:02x}".format(
            *(max(0, min(255, int(round(component * 255.0)))) for component in color)
        )

    @staticmethod
    def _parse_color(text):
        value = str(text).strip().lstrip("#")
        if len(value) != 6:
            return None
        try:
            return tuple(int(value[index : index + 2], 16) / 255.0 for index in (0, 2, 4))
        except ValueError:
            return None

    def _background_color_edited(self):
        parsed = self._parse_color(self.background_color_edit.text())
        if parsed is None:
            self.background_color_edit.setToolTip("请输入 #RRGGBB 格式的颜色")
            return
        self._background_color = parsed
        self.background_color_edit.setToolTip("查看器背景颜色")
        self._emit_display_settings()

    def _emit_display_settings(self, *_args):
        self.display_settings_changed.emit(self.display_settings())

    def _emit_appearance_settings(self, *_args):
        self.appearance_settings_changed.emit(self.appearance_settings())

    def _emit_render_settings(self, *_args):
        self.render_settings_changed.emit(self.render_settings())

    def _resolution_preset_changed(self, index):
        values = {
            "viewport": self._viewport_size,
            "720p": (1280, 720),
            "1080p": (1920, 1080),
        }
        size = values.get(self.resolution_preset_combo.itemData(index))
        if size is None:
            return
        blockers = [QSignalBlocker(self.render_width), QSignalBlocker(self.render_height)]
        self.render_width.setValue(size[0])
        self.render_height.setValue(size[1])
        del blockers
        self._emit_render_settings()

    def set_viewport_size(self, width, height):
        width = max(1, int(width))
        height = max(1, int(height))
        self._viewport_size = (width, height)
        self.resolution_preset_combo.setItemText(
            0, "当前视口 · {}×{}".format(width, height)
        )

    def _fps_preset_changed(self, index):
        value = self.fps_preset_combo.itemData(index)
        if value is None:
            return
        blocker = QSignalBlocker(self.render_fps)
        self.render_fps.setValue(float(value))
        del blocker
        self._emit_render_settings()

    def _sync_render_presets(self):
        size = (self.render_width.value(), self.render_height.value())
        known_sizes = {
            (1280, 720): "720p",
            (1920, 1080): "1080p",
        }
        size_key = (
            "viewport"
            if size == self._viewport_size
            else known_sizes.get(size, "custom")
        )
        fps_value = float(self.render_fps.value())
        fps_key = fps_value if fps_value in (24.0, 25.0, 30.0, 60.0) else None
        blockers = [
            QSignalBlocker(self.resolution_preset_combo),
            QSignalBlocker(self.fps_preset_combo),
        ]
        self.resolution_preset_combo.setCurrentIndex(
            self.resolution_preset_combo.findData(size_key)
        )
        self.fps_preset_combo.setCurrentIndex(
            self.fps_preset_combo.findData(fps_key)
            if fps_key is not None
            else self.fps_preset_combo.findData(None)
        )
        del blockers

    def _fov_value_changed(self, value):
        self._camera_pose = replace(self._camera_pose, fov_degrees=float(value))
        self.fov_changed.emit(float(value))

    def _emit_camera_pose(self, *_args):
        self._camera_pose = CameraPose(
            position=(
                self.position_x.value(),
                self.position_y.value(),
                self.position_z.value(),
            ),
            target=(
                self.target_x.value(),
                self.target_y.value(),
                self.target_z.value(),
            ),
            rotation_xyzw=self._camera_pose.rotation_xyzw,
            fov_degrees=self.fov.value(),
        )
        self.camera_pose_changed.emit(self._camera_pose)

    def _update_bookmark_actions(self, *_args):
        has_name = bool(self.bookmark_name_edit.text().strip())
        has_selection = self.bookmark_combo.currentIndex() >= 0
        self.bookmark_add_button.setEnabled(has_name)
        self.bookmark_load_button.setEnabled(has_selection)
        self.bookmark_delete_button.setEnabled(has_selection)

    def _update_transparency_state(self, *_args):
        png_output = self.output_kind.currentData() in (
            OutputKind.PNG.value,
            OutputKind.PNG_SEQUENCE.value,
        )
        if not png_output and self.transparent_background.isChecked():
            blocker = QSignalBlocker(self.transparent_background)
            self.transparent_background.setChecked(False)
            del blocker
        self.transparent_background.setEnabled(png_output)

    def display_settings(self):
        return DisplaySettings(
            mode=self.display_mode_combo.currentData(),
            quality=self.quality_combo.currentData(),
            sphere_sigma_multiplier=self.sphere_sigma_multiplier.value(),
            sphere_opacity=self.sphere_opacity.value(),
            sphere_line_width=self.sphere_line_width.value(),
            sphere_color_mode=self.sphere_color_mode.currentData(),
            sphere_all_instances=self.sphere_all_instances.isChecked(),
            background_color=self._background_color,
            show_grid=self.show_grid_checkbox.isChecked(),
            show_axis=self.show_axis_checkbox.isChecked(),
            show_bounds=self.show_bounds_checkbox.isChecked(),
            show_center=self.show_center_checkbox.isChecked(),
            show_camera_info=self.show_camera_info_checkbox.isChecked(),
        )

    def appearance_settings(self):
        return AppearanceSettings(
            exposure=self.exposure.value(),
            tone_mapping=self.tone_mapping_combo.currentData(),
            sh_degree=self.sh_degree_combo.currentData(),
            contrast=self.contrast.value(),
            saturation=self.saturation.value(),
            vignette=self.vignette.value(),
            sharpening=self.sharpening.value(),
        )

    def render_settings(self):
        output_kind = self.output_kind.currentData()
        return RenderSettings(
            width=self.render_width.value(),
            height=self.render_height.value(),
            fps=self.render_fps.value(),
            output_kind=output_kind,
            transparent_background=(
                self.transparent_background.isChecked()
                and output_kind in (OutputKind.PNG.value, OutputKind.PNG_SEQUENCE.value)
            ),
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
            self.sphere_all_instances,
            self.sphere_color_mode,
            self.background_color_edit,
            self.show_grid_checkbox,
            self.show_axis_checkbox,
            self.show_bounds_checkbox,
            self.show_center_checkbox,
            self.show_camera_info_checkbox,
        )
        blockers = [QSignalBlocker(control) for control in controls]
        self.display_mode_combo.setCurrentIndex(self.display_mode_combo.findData(settings.mode.value))
        self.quality_combo.setCurrentIndex(self.quality_combo.findData(settings.quality.value))
        self.sphere_sigma_multiplier.setValue(settings.sphere_sigma_multiplier)
        self.sphere_opacity.setValue(settings.sphere_opacity)
        self.sphere_line_width.setValue(settings.sphere_line_width)
        self.sphere_all_instances.setChecked(settings.sphere_all_instances)
        self.sphere_color_mode.setCurrentIndex(self.sphere_color_mode.findData(settings.sphere_color_mode))
        self._background_color = settings.background_color
        self.background_color_edit.setText(self._color_to_hex(settings.background_color))
        self.show_grid_checkbox.setChecked(settings.show_grid)
        self.show_axis_checkbox.setChecked(settings.show_axis)
        self.show_bounds_checkbox.setChecked(settings.show_bounds)
        self.show_center_checkbox.setChecked(settings.show_center)
        self.show_camera_info_checkbox.setChecked(settings.show_camera_info)
        del blockers

    def set_appearance_settings(self, settings):
        if not isinstance(settings, AppearanceSettings):
            raise ValueError("appearance settings must be an AppearanceSettings value")
        controls = (
            self.exposure,
            self.tone_mapping_combo,
            self.sh_degree_combo,
            self.contrast,
            self.saturation,
            self.vignette,
            self.sharpening,
        )
        blockers = [QSignalBlocker(control) for control in controls]
        self.exposure.setValue(settings.exposure)
        self.tone_mapping_combo.setCurrentIndex(
            self.tone_mapping_combo.findData(settings.tone_mapping)
        )
        self.sh_degree_combo.setCurrentIndex(
            self.sh_degree_combo.findData(settings.sh_degree)
        )
        self.contrast.setValue(settings.contrast)
        self.saturation.setValue(settings.saturation)
        self.vignette.setValue(settings.vignette)
        self.sharpening.setValue(settings.sharpening)
        del blockers

    def set_render_settings(self, settings):
        if not isinstance(settings, RenderSettings):
            raise ValueError("render settings must be a RenderSettings value")
        controls = (
            self.resolution_preset_combo,
            self.render_width,
            self.render_height,
            self.fps_preset_combo,
            self.render_fps,
            self.output_kind,
            self.transparent_background,
        )
        blockers = [QSignalBlocker(control) for control in controls]
        self.render_width.setValue(settings.width)
        self.render_height.setValue(settings.height)
        self.render_fps.setValue(settings.fps)
        self.output_kind.setCurrentIndex(self.output_kind.findData(settings.output_kind.value))
        self.transparent_background.setChecked(settings.transparent_background)
        del blockers
        self._sync_render_presets()
        self._update_transparency_state()

    def set_camera_pose(self, pose):
        if not isinstance(pose, CameraPose):
            raise ValueError("camera pose must be a CameraPose value")
        self._camera_pose = pose
        controls = (
            self.fov,
            self.position_x,
            self.position_y,
            self.position_z,
            self.target_x,
            self.target_y,
            self.target_z,
        )
        blockers = [QSignalBlocker(control) for control in controls]
        self.fov.setValue(pose.fov_degrees)
        self.position_x.setValue(pose.position[0])
        self.position_y.setValue(pose.position[1])
        self.position_z.setValue(pose.position[2])
        self.target_x.setValue(pose.target[0])
        self.target_y.setValue(pose.target[1])
        self.target_z.setValue(pose.target[2])
        del blockers

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

    def set_sphere_modes_available(self, available, error=""):
        available = bool(available)
        for value in (
            DisplayMode.SPHERE_WIREFRAME.value,
            DisplayMode.SPHERE_SOLID.value,
            DisplayMode.OVERLAY.value,
        ):
            index = self.display_mode_combo.findData(value)
            if index >= 0:
                self.display_mode_combo.model().item(index).setEnabled(available)
        controls = (
            self.sphere_sigma_multiplier,
            self.sphere_opacity,
            self.sphere_line_width,
            self.sphere_all_instances,
            self.sphere_color_mode,
        )
        for control in controls:
            control.setEnabled(available)
        if not available and self.display_mode_combo.currentData() != DisplayMode.STANDARD.value:
            blocker = QSignalBlocker(self.display_mode_combo)
            self.display_mode_combo.setCurrentIndex(
                self.display_mode_combo.findData(DisplayMode.STANDARD.value)
            )
            del blocker
        self.display_mode_combo.setToolTip(
            "外接球显示不可用：{}".format(error)
            if not available and error
            else "Gaussian 显示模式"
        )


__all__ = ["CollapsibleSection", "ViewerInspector"]
