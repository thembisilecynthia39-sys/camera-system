"""Model-backed Camera Director timeline controls."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from camera_system_app.application.viewer_timeline import timeline_frame_count
from camera_system_app.domain.viewer import CameraPose, CameraShot, CameraTimeline
from camera_system_app.ui.widgets.focus_wheel_spinbox import SafeDoubleSpinBox


class ViewerTimelineWidget(QWidget):
    """Edit shot order, timing, and exact sampled frames for preview."""

    timeline_changed = Signal(object)
    frame_selected = Signal(int)
    shot_selected = Signal(str)
    add_shot_requested = Signal()
    duplicate_shot_requested = Signal()
    delete_shot_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("viewerTimeline")
        self._timeline = CameraTimeline()
        self._selected_shot = -1
        self._current_pose = CameraPose()
        self.shot_markers = []

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(5)

        header = QHBoxLayout()
        self.duration_label = QLabel("时长 0.00 s · 30 FPS")
        self.duration_label.setObjectName("viewerTimelineDuration")
        self.frame_label = QLabel("帧 0 / 0")
        self.frame_label.setObjectName("viewerTimelineFrame")
        header.addWidget(self.duration_label)
        header.addStretch(1)
        header.addWidget(self.frame_label)
        root.addLayout(header)

        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setRange(0, 0)
        self.frame_slider.setAccessibleName("相机漫游帧位置")
        self.frame_slider.valueChanged.connect(self._frame_value_changed)
        root.addWidget(self.frame_slider)

        transport = QHBoxLayout()
        self.previous_frame_button = self._action("上一帧", "选择上一帧")
        self.next_frame_button = self._action("下一帧", "选择下一帧")
        self.previous_shot_button = self._action("上一镜头", "选择上一镜头段")
        self.next_shot_button = self._action("下一镜头", "选择下一镜头段")
        for button in (
            self.previous_frame_button,
            self.next_frame_button,
            self.previous_shot_button,
            self.next_shot_button,
        ):
            transport.addWidget(button)
        transport.addStretch(1)
        transport.addWidget(QLabel("FPS"))
        self.fps_spinbox = SafeDoubleSpinBox()
        self.fps_spinbox.setRange(1.0, 240.0)
        self.fps_spinbox.setSingleStep(1.0)
        self.fps_spinbox.setDecimals(1)
        self.fps_spinbox.setValue(30.0)
        self.fps_spinbox.setAccessibleName("相机时间轴帧率")
        transport.addWidget(self.fps_spinbox)
        self.loop_checkbox = QCheckBox("循环")
        self.loop_checkbox.setAccessibleName("相机时间轴循环播放")
        transport.addWidget(self.loop_checkbox)
        root.addLayout(transport)

        self._marker_layout = QHBoxLayout()
        self._marker_layout.setContentsMargins(0, 0, 0, 0)
        self._marker_layout.setSpacing(4)
        root.addLayout(self._marker_layout)

        controls = QHBoxLayout()
        self.add_button = self._action("添加镜头", "添加当前视角为一个相机镜头段")
        self.duplicate_button = self._action("复制", "复制当前相机镜头段")
        self.delete_button = self._action("删除", "删除当前相机镜头段")
        self.move_left_button = self._action("←", "向前移动当前镜头段")
        self.move_right_button = self._action("→", "向后移动当前镜头段")
        self.update_start_button = self._action("更新起点", "用当前视角更新镜头起点")
        self.update_end_button = self._action("更新终点", "用当前视角更新镜头终点")
        for button in (
            self.add_button,
            self.duplicate_button,
            self.delete_button,
            self.move_left_button,
            self.move_right_button,
            self.update_start_button,
            self.update_end_button,
        ):
            controls.addWidget(button)
        self.shot_editor_toggle = QToolButton()
        self.shot_editor_toggle.setText("镜头参数")
        self.shot_editor_toggle.setCheckable(True)
        self.shot_editor_toggle.setAccessibleName("展开镜头参数编辑")
        controls.addWidget(self.shot_editor_toggle)
        controls.addStretch(1)
        root.addLayout(controls)

        self.shot_editor = QWidget()
        editor_form = QFormLayout(self.shot_editor)
        editor_form.setContentsMargins(4, 2, 4, 2)
        self.shot_name_edit = QLineEdit()
        self.shot_name_edit.setAccessibleName("当前镜头名称")
        self.duration_spinbox = self._seconds_box(3.0, minimum=0.01)
        self.hold_start_spinbox = self._seconds_box(0.0)
        self.hold_end_spinbox = self._seconds_box(0.0)
        self.easing_combo = QComboBox()
        self.easing_combo.addItem("平滑", "smoothstep")
        self.easing_combo.addItem("线性", "linear")
        self.easing_combo.setAccessibleName("当前镜头缓动方式")
        editor_form.addRow("名称", self.shot_name_edit)
        editor_form.addRow("过渡时长（秒）", self.duration_spinbox)
        editor_form.addRow("起始停留（秒）", self.hold_start_spinbox)
        editor_form.addRow("结束停留（秒）", self.hold_end_spinbox)
        editor_form.addRow("缓动", self.easing_combo)
        self.shot_editor.setVisible(False)
        root.addWidget(self.shot_editor)

        self.add_button.clicked.connect(self._add_shot)
        self.duplicate_button.clicked.connect(self._duplicate_shot)
        self.delete_button.clicked.connect(self._delete_shot)
        self.move_left_button.clicked.connect(lambda: self._move_shot(-1))
        self.move_right_button.clicked.connect(lambda: self._move_shot(1))
        self.update_start_button.clicked.connect(lambda: self._update_selected_pose("start"))
        self.update_end_button.clicked.connect(lambda: self._update_selected_pose("end"))
        self.previous_frame_button.clicked.connect(self._previous_frame)
        self.next_frame_button.clicked.connect(self._next_frame)
        self.previous_shot_button.clicked.connect(lambda: self._move_selected_shot(-1))
        self.next_shot_button.clicked.connect(lambda: self._move_selected_shot(1))
        self.fps_spinbox.valueChanged.connect(self._fps_changed)
        self.loop_checkbox.toggled.connect(self._loop_changed)
        self.shot_editor_toggle.toggled.connect(self.shot_editor.setVisible)
        self.shot_name_edit.editingFinished.connect(self._selected_shot_edited)
        for control in (
            self.duration_spinbox,
            self.hold_start_spinbox,
            self.hold_end_spinbox,
        ):
            control.valueChanged.connect(self._selected_shot_edited)
        self.easing_combo.currentIndexChanged.connect(self._selected_shot_edited)
        self._update_action_state()

    @staticmethod
    def _action(text, accessible_name):
        button = QToolButton()
        button.setText(text)
        button.setMinimumHeight(32)
        button.setAccessibleName(accessible_name)
        return button

    @staticmethod
    def _seconds_box(value, minimum=0.0):
        box = SafeDoubleSpinBox()
        box.setRange(minimum, 3600.0)
        box.setSingleStep(0.05)
        box.setDecimals(2)
        box.setValue(value)
        return box

    @property
    def timeline(self):
        return self._timeline

    @property
    def selected_shot_index(self):
        return self._selected_shot

    def set_timeline(self, timeline):
        if not isinstance(timeline, CameraTimeline):
            raise ValueError("timeline must be a CameraTimeline value")
        self._timeline = timeline
        self._selected_shot = (
            min(max(self._selected_shot, 0), len(timeline.shots) - 1)
            if timeline.shots
            else -1
        )
        count = timeline_frame_count(timeline) if timeline.shots else 1
        blocker = QSignalBlocker(self.frame_slider)
        self.frame_slider.setRange(0, max(0, count - 1))
        self.frame_slider.setValue(
            min(self.frame_slider.value(), max(0, count - 1))
        )
        del blocker

        controls = (
            self.fps_spinbox,
            self.loop_checkbox,
            self.shot_name_edit,
            self.duration_spinbox,
            self.hold_start_spinbox,
            self.hold_end_spinbox,
            self.easing_combo,
        )
        blockers = [QSignalBlocker(control) for control in controls]
        self.fps_spinbox.setValue(timeline.fps)
        self.loop_checkbox.setChecked(timeline.loop)
        self._load_selected_shot_controls()
        del blockers

        fps = int(timeline.fps) if timeline.fps.is_integer() else timeline.fps
        self.duration_label.setText(
            "时长 {:.2f} s · {} FPS".format(timeline.duration_seconds, fps)
        )
        self._rebuild_markers()
        self._update_frame_label()
        self._update_action_state()

    def set_current_frame(self, frame):
        self.frame_slider.setValue(int(frame))

    def set_current_pose(self, pose):
        if not isinstance(pose, CameraPose):
            raise ValueError("current camera pose must be a CameraPose value")
        self._current_pose = pose

    def _frame_value_changed(self, frame):
        self._update_frame_label()
        self._update_action_state()
        self.frame_selected.emit(int(frame))

    def _update_frame_label(self):
        self.frame_label.setText(
            "帧 {} / {}".format(self.frame_slider.value(), self.frame_slider.maximum())
        )

    def _rebuild_markers(self):
        while self._marker_layout.count():
            item = self._marker_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.shot_markers = []
        for index, shot in enumerate(self._timeline.shots):
            marker = self._action(shot.name, "选择镜头段 " + shot.name)
            marker.setCheckable(True)
            marker.setChecked(index == self._selected_shot)
            marker.clicked.connect(
                lambda _checked=False, shot_index=index: self._select_shot(shot_index)
            )
            self._marker_layout.addWidget(
                marker, max(1, int(shot.total_seconds * 100))
            )
            self.shot_markers.append(marker)
        self._marker_layout.addStretch(1)

    def _select_shot(self, index):
        if not 0 <= index < len(self._timeline.shots):
            return
        self._selected_shot = index
        for marker_index, marker in enumerate(self.shot_markers):
            marker.setChecked(marker_index == index)
        self._load_selected_shot_controls()
        self.shot_selected.emit(self._timeline.shots[index].shot_id)
        self._update_action_state()

    def _load_selected_shot_controls(self):
        if not self._timeline.shots or self._selected_shot < 0:
            self.shot_name_edit.clear()
            self.duration_spinbox.setValue(3.0)
            self.hold_start_spinbox.setValue(0.0)
            self.hold_end_spinbox.setValue(0.0)
            self.easing_combo.setCurrentIndex(
                self.easing_combo.findData("smoothstep")
            )
            return
        shot = self._timeline.shots[self._selected_shot]
        self.shot_name_edit.setText(shot.name)
        self.duration_spinbox.setValue(shot.duration_seconds)
        self.hold_start_spinbox.setValue(shot.hold_start_seconds)
        self.hold_end_spinbox.setValue(shot.hold_end_seconds)
        self.easing_combo.setCurrentIndex(self.easing_combo.findData(shot.easing))

    def _selected_shot_edited(self, *_args):
        if not self._timeline.shots or self._selected_shot < 0:
            return
        original = self._timeline.shots[self._selected_shot]
        name = self.shot_name_edit.text().strip() or original.name
        shot = CameraShot(
            original.shot_id,
            name,
            original.start,
            original.end,
            duration_seconds=self.duration_spinbox.value(),
            hold_start_seconds=self.hold_start_spinbox.value(),
            hold_end_seconds=self.hold_end_spinbox.value(),
            easing=self.easing_combo.currentData(),
        )
        shots = list(self._timeline.shots)
        shots[self._selected_shot] = shot
        self._replace_timeline(
            CameraTimeline(
                shots=tuple(shots),
                fps=self._timeline.fps,
                loop=self._timeline.loop,
            )
        )

    def _fps_changed(self, value):
        self._replace_timeline(
            CameraTimeline(
                shots=self._timeline.shots,
                fps=float(value),
                loop=self._timeline.loop,
            )
        )

    def _loop_changed(self, enabled):
        self._replace_timeline(
            CameraTimeline(
                shots=self._timeline.shots,
                fps=self._timeline.fps,
                loop=bool(enabled),
            )
        )

    def _previous_frame(self):
        self.frame_slider.setValue(max(0, self.frame_slider.value() - 1))

    def _next_frame(self):
        self.frame_slider.setValue(
            min(self.frame_slider.maximum(), self.frame_slider.value() + 1)
        )

    def _move_selected_shot(self, offset):
        if not self._timeline.shots:
            return
        index = max(0, min(self._selected_shot, len(self._timeline.shots) - 1))
        self._select_shot(
            max(0, min(len(self._timeline.shots) - 1, index + offset))
        )

    def _add_shot(self):
        pose = self._current_pose
        shot_number = len(self._timeline.shots) + 1
        shot = CameraShot(
            self._next_shot_id("shot"),
            "镜头 {}".format(shot_number),
            pose,
            pose,
        )
        shots = list(self._timeline.shots)
        if shots:
            shots[-1] = replace(shots[-1], end=pose)
        shots.append(shot)
        self._selected_shot = len(shots) - 1
        self._replace_timeline(
            CameraTimeline(
                shots=tuple(shots),
                fps=self._timeline.fps,
                loop=self._timeline.loop,
            )
        )
        self.add_shot_requested.emit()

    def _duplicate_shot(self):
        if not self._timeline.shots:
            return
        index = max(0, self._selected_shot)
        original = self._timeline.shots[index]
        shot = replace(
            original,
            shot_id=self._next_shot_id("{}-copy".format(original.shot_id)),
            name=original.name + "副本",
        )
        shots = (
            self._timeline.shots[: index + 1]
            + (shot,)
            + self._timeline.shots[index + 1 :]
        )
        self._selected_shot = index + 1
        self._replace_timeline(
            CameraTimeline(
                shots=shots,
                fps=self._timeline.fps,
                loop=self._timeline.loop,
            )
        )
        self.duplicate_shot_requested.emit()

    def _delete_shot(self):
        if not self._timeline.shots:
            return
        index = max(0, min(self._selected_shot, len(self._timeline.shots) - 1))
        shots = self._timeline.shots[:index] + self._timeline.shots[index + 1 :]
        self._selected_shot = min(index, len(shots) - 1)
        self._replace_timeline(
            CameraTimeline(
                shots=shots,
                fps=self._timeline.fps,
                loop=self._timeline.loop,
            )
        )
        self.delete_shot_requested.emit()

    def _move_shot(self, offset):
        if not self._timeline.shots:
            return
        index = max(0, min(self._selected_shot, len(self._timeline.shots) - 1))
        target = index + offset
        if not 0 <= target < len(self._timeline.shots):
            return
        shots = list(self._timeline.shots)
        shots[index], shots[target] = shots[target], shots[index]
        self._selected_shot = target
        self._replace_timeline(
            CameraTimeline(
                shots=tuple(shots),
                fps=self._timeline.fps,
                loop=self._timeline.loop,
            )
        )

    def _update_selected_pose(self, endpoint):
        if not self._timeline.shots or self._selected_shot < 0:
            return
        if endpoint not in ("start", "end"):
            raise ValueError("unsupported shot endpoint: {}".format(endpoint))
        original = self._timeline.shots[self._selected_shot]
        shot = replace(original, **{endpoint: self._current_pose})
        shots = list(self._timeline.shots)
        shots[self._selected_shot] = shot
        self._replace_timeline(
            CameraTimeline(
                shots=tuple(shots),
                fps=self._timeline.fps,
                loop=self._timeline.loop,
            )
        )

    def _replace_timeline(self, timeline):
        self._timeline = timeline
        self.set_timeline(timeline)
        self.timeline_changed.emit(timeline)

    def _next_shot_id(self, prefix):
        used = {shot.shot_id for shot in self._timeline.shots}
        index = 1
        while "{}-{}".format(prefix, index) in used:
            index += 1
        return "{}-{}".format(prefix, index)

    def _update_action_state(self):
        has_shots = bool(self._timeline.shots)
        self.duplicate_button.setEnabled(has_shots)
        self.delete_button.setEnabled(has_shots)
        self.move_left_button.setEnabled(has_shots and self._selected_shot > 0)
        self.move_right_button.setEnabled(
            has_shots
            and self._selected_shot >= 0
            and self._selected_shot < len(self._timeline.shots) - 1
        )
        self.update_start_button.setEnabled(has_shots and self._selected_shot >= 0)
        self.update_end_button.setEnabled(has_shots and self._selected_shot >= 0)
        self.previous_frame_button.setEnabled(self.frame_slider.value() > 0)
        self.next_frame_button.setEnabled(
            self.frame_slider.value() < self.frame_slider.maximum()
        )
        self.previous_shot_button.setEnabled(has_shots and self._selected_shot > 0)
        self.next_shot_button.setEnabled(
            has_shots
            and self._selected_shot >= 0
            and self._selected_shot < len(self._timeline.shots) - 1
        )


__all__ = ["ViewerTimelineWidget"]
