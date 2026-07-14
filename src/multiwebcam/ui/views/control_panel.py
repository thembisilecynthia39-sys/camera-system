"""Control panel widget for V4L2 camera controls."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
)

from multiwebcam.sources.controls import V4L2Control
from multiwebcam.ui.components import GuardedSlider, GuardedSpinBox
from multiwebcam.ui.fluent import check_box, combo_box, push_button
from multiwebcam.ui.theme import set_variant


class ControlPanel(QWidget):
    """Dynamically builds UI controls for V4L2 camera settings.

    Creates appropriate widgets for each control type:
    - int: QSlider + QSpinBox (bidirectionally linked)
    - bool: QCheckBox
    - menu: QComboBox with menu items

    Signals:
        control_changed: Emitted when any control value changes.
                        Args: (control_name: str, value: int)
        defaults_restore_requested: Emitted when Restore Defaults button clicked.
    """

    control_changed = Signal(str, int)
    defaults_restore_requested = Signal()

    def __init__(self, controls: list[V4L2Control], parent=None):
        super().__init__(parent)
        self._controls = controls
        self._updating = False  # Guard flag to prevent signal loops
        self.setObjectName("controlPanelSurface")

        self._build_ui()

    def _build_ui(self) -> None:
        """Construct the control panel layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create scrollable area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(1, 2, 4, 2)
        scroll_layout.setSpacing(12)

        # Section header
        header = QLabel("摄像头控制")
        header.setObjectName("sectionTitle")
        scroll_layout.addWidget(header)

        description = QLabel("调整会即时作用于当前相机")
        description.setObjectName("captionLabel")
        description.setWordWrap(True)
        scroll_layout.addWidget(description)

        if not self._controls:
            # Show message for empty controls
            empty_label = QLabel("当前摄像头没有可调参数")
            empty_label.setObjectName("captionLabel")
            empty_label.setEnabled(False)
            scroll_layout.addWidget(empty_label)
        else:
            # Stack labels above controls so long names never squeeze the
            # slider or numeric editor into inconsistent widths.
            for control in self._controls:
                label_text = self._format_label(control.name)
                widget = self._create_control_widget(control)
                if widget:
                    row = QFrame()
                    row.setObjectName("cameraControlRow")
                    row_layout = QVBoxLayout(row)
                    row_layout.setContentsMargins(9, 7, 9, 9)
                    row_layout.setSpacing(6)
                    label = QLabel(label_text)
                    label.setObjectName("cameraControlLabel")
                    row_layout.addWidget(label)
                    row_layout.addWidget(widget)
                    scroll_layout.addWidget(row)

            # Add Restore Defaults button
            restore_btn = push_button("恢复默认值")
            set_variant(restore_btn, "ghost")
            restore_btn.clicked.connect(self.defaults_restore_requested.emit)
            scroll_layout.addWidget(restore_btn)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

    def _format_label(self, control_name: str) -> str:
        """Convert control name to readable label.

        Example: "exposure_absolute" -> "Exposure Absolute"
        """
        translated = _CONTROL_LABELS.get(control_name)
        if translated is not None:
            return translated
        return control_name.replace("_", " ").title()

    def _create_control_widget(self, control: V4L2Control) -> QWidget | None:
        """Create appropriate widget for control type."""
        if control.type == "int":
            return self._create_int_control(control)
        elif control.type == "bool":
            return self._create_bool_control(control)
        elif control.type == "menu":
            return self._create_menu_control(control)
        return None

    def _create_int_control(self, control: V4L2Control) -> QWidget:
        """Create slider + spinbox pair for integer control."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Slider
        slider = GuardedSlider()
        slider.setOrientation(Qt.Orientation.Horizontal)
        slider.setMinimum(control.min or 0)
        slider.setMaximum(control.max or 100)
        if control.step:
            slider.setSingleStep(control.step)
        if control.current is not None:
            slider.setValue(control.current)

        # Spinbox
        spinbox = GuardedSpinBox()
        spinbox.setObjectName("cameraValueEditor")
        spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spinbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spinbox.setFixedWidth(72)
        spinbox.setMinimum(control.min or 0)
        spinbox.setMaximum(control.max or 100)
        if control.step:
            spinbox.setSingleStep(control.step)
        if control.current is not None:
            spinbox.setValue(control.current)

        # Connect slider <-> spinbox bidirectionally
        # Use lambda to capture control name and guard against signal loops
        def on_slider_change(value: int) -> None:
            if not self._updating:
                self._updating = True
                spinbox.setValue(value)
                if not slider.isSliderDown():
                    self.control_changed.emit(control.name, value)
                self._updating = False

        def on_slider_released() -> None:
            self.control_changed.emit(control.name, slider.value())

        def on_spinbox_commit() -> None:
            value = spinbox.value()
            if not self._updating:
                self._updating = True
                slider.setValue(value)
                self.control_changed.emit(control.name, value)
                self._updating = False

        slider.valueChanged.connect(on_slider_change)
        slider.sliderReleased.connect(on_slider_released)
        spinbox.editingFinished.connect(on_spinbox_commit)

        layout.addWidget(slider, stretch=3)
        layout.addWidget(spinbox, stretch=1)

        return container

    def _create_bool_control(self, control: V4L2Control) -> QWidget:
        """Create checkbox for boolean control."""
        checkbox = check_box()
        checkbox.setObjectName("cameraBoolControl")
        checkbox.setChecked(control.current != 0 if control.current is not None else False)

        # Connect to control_changed signal
        checkbox.stateChanged.connect(lambda state: self.control_changed.emit(control.name, 1 if state else 0))

        return checkbox

    def _create_menu_control(self, control: V4L2Control) -> QWidget:
        """Create combobox for menu control."""
        combo = combo_box()
        combo.setObjectName("cameraMenuControl")

        if control.menu_items:
            # Populate combo with menu items
            # Store int key as user data, display label text
            for key in sorted(control.menu_items.keys()):
                label = control.menu_items[key]
                combo.addItem(label, userData=key)

            # Set current selection if available
            if control.current is not None:
                index = combo.findData(control.current)
                if index >= 0:
                    combo.setCurrentIndex(index)

        # Connect to control_changed signal
        # userData holds the int key
        combo.currentIndexChanged.connect(lambda: self.control_changed.emit(control.name, combo.currentData()))

        return combo


_CONTROL_LABELS = {
    "brightness": "亮度",
    "contrast": "对比度",
    "saturation": "饱和度",
    "hue": "色调",
    "white_balance_temperature_auto": "自动白平衡",
    "gamma": "伽马",
    "gain": "增益",
    "power_line_frequency": "电源频率",
    "white_balance_temperature": "白平衡温度",
    "sharpness": "锐度",
    "backlight_compensation": "背光补偿",
    "exposure_auto": "自动曝光",
    "exposure_absolute": "曝光时间",
    "exposure_auto_priority": "曝光优先级",
    "focus_absolute": "焦距",
    "focus_auto": "自动对焦",
    "zoom_absolute": "变焦",
    "pan_absolute": "水平转动",
    "tilt_absolute": "垂直转动",
}
