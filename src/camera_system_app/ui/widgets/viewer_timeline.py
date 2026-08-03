"""Model-backed Camera Director timeline controls."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QToolButton, QVBoxLayout, QWidget

from camera_system_app.application.viewer_timeline import timeline_frame_count
from camera_system_app.domain.viewer import CameraPose, CameraShot, CameraTimeline


class ViewerTimelineWidget(QWidget):
    """Edit shot order and select exact sampled frames for preview."""

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

        self.frame_slider = QSlider()
        self.frame_slider.setOrientation(1)
        self.frame_slider.setRange(0, 0)
        self.frame_slider.setAccessibleName("相机漫游帧位置")
        self.frame_slider.valueChanged.connect(self._frame_value_changed)
        root.addWidget(self.frame_slider)

        self._marker_layout = QHBoxLayout()
        self._marker_layout.setContentsMargins(0, 0, 0, 0)
        self._marker_layout.setSpacing(4)
        root.addLayout(self._marker_layout)

        controls = QHBoxLayout()
        self.add_button = self._action("添加镜头", "添加一个相机镜头段")
        self.duplicate_button = self._action("复制", "复制当前相机镜头段")
        self.delete_button = self._action("删除", "删除当前相机镜头段")
        self.move_left_button = self._action("←", "向前移动当前镜头段")
        self.move_right_button = self._action("→", "向后移动当前镜头段")
        for button in (
            self.add_button,
            self.duplicate_button,
            self.delete_button,
            self.move_left_button,
            self.move_right_button,
        ):
            controls.addWidget(button)
        controls.addStretch(1)
        root.addLayout(controls)

        self.add_button.clicked.connect(self._add_shot)
        self.duplicate_button.clicked.connect(self._duplicate_shot)
        self.delete_button.clicked.connect(self._delete_shot)
        self.move_left_button.clicked.connect(lambda: self._move_shot(-1))
        self.move_right_button.clicked.connect(lambda: self._move_shot(1))
        self._update_action_state()

    @staticmethod
    def _action(text, accessible_name):
        button = QToolButton()
        button.setText(text)
        button.setMinimumHeight(32)
        button.setAccessibleName(accessible_name)
        return button

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
        self._selected_shot = min(
            max(self._selected_shot, 0), len(timeline.shots) - 1
        ) if timeline.shots else -1
        count = timeline_frame_count(timeline) if timeline.shots else 1
        blocker = QSignalBlocker(self.frame_slider)
        self.frame_slider.setRange(0, max(0, count - 1))
        self.frame_slider.setValue(min(self.frame_slider.value(), max(0, count - 1)))
        del blocker
        fps = int(timeline.fps) if timeline.fps.is_integer() else timeline.fps
        self.duration_label.setText(
            "时长 {:.2f} s · {} FPS".format(timeline.duration_seconds, fps)
        )
        self._rebuild_markers()
        self._update_frame_label()
        self._update_action_state()

    def set_current_frame(self, frame):
        self.frame_slider.setValue(int(frame))

    def _frame_value_changed(self, frame):
        self._update_frame_label()
        self.frame_selected.emit(int(frame))

    def _update_frame_label(self):
        self.frame_label.setText(
            "帧 {} / {}".format(self.frame_slider.value(), self.frame_slider.maximum())
        )

    def _rebuild_markers(self):
        for marker in self.shot_markers:
            marker.deleteLater()
        self.shot_markers = []
        for index, shot in enumerate(self._timeline.shots):
            marker = self._action(shot.name, "选择镜头段 " + shot.name)
            marker.setCheckable(True)
            marker.setChecked(index == self._selected_shot)
            marker.clicked.connect(
                lambda _checked=False, shot_index=index: self._select_shot(shot_index)
            )
            self._marker_layout.addWidget(marker, max(1, int(shot.total_seconds * 100)))
            self.shot_markers.append(marker)
        self._marker_layout.addStretch(1)

    def _select_shot(self, index):
        if not 0 <= index < len(self._timeline.shots):
            return
        self._selected_shot = index
        for marker_index, marker in enumerate(self.shot_markers):
            marker.setChecked(marker_index == index)
        self.shot_selected.emit(self._timeline.shots[index].shot_id)
        self._update_action_state()

    def _add_shot(self):
        if self._timeline.shots:
            pose = self._timeline.shots[-1].end
        else:
            pose = CameraPose()
        shot_number = len(self._timeline.shots) + 1
        shot = CameraShot(
            "shot-{}".format(shot_number),
            "镜头 {}".format(shot_number),
            pose,
            pose,
        )
        shots = self._timeline.shots + (shot,)
        self._replace_timeline(CameraTimeline(shots=shots, fps=self._timeline.fps, loop=self._timeline.loop))
        self._selected_shot = len(shots) - 1
        self._rebuild_markers()
        self.add_shot_requested.emit()

    def _duplicate_shot(self):
        if not self._timeline.shots:
            return
        index = max(0, self._selected_shot)
        original = self._timeline.shots[index]
        shot = replace(
            original,
            shot_id="{}-copy-{}".format(original.shot_id, len(self._timeline.shots) + 1),
            name=original.name + "副本",
        )
        shots = self._timeline.shots[: index + 1] + (shot,) + self._timeline.shots[index + 1 :]
        self._selected_shot = index + 1
        self._replace_timeline(CameraTimeline(shots=shots, fps=self._timeline.fps, loop=self._timeline.loop))
        self.duplicate_shot_requested.emit()

    def _delete_shot(self):
        if not self._timeline.shots:
            return
        index = max(0, min(self._selected_shot, len(self._timeline.shots) - 1))
        shots = self._timeline.shots[:index] + self._timeline.shots[index + 1 :]
        self._selected_shot = min(index, len(shots) - 1)
        self._replace_timeline(CameraTimeline(shots=shots, fps=self._timeline.fps, loop=self._timeline.loop))
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
        self._replace_timeline(CameraTimeline(shots=tuple(shots), fps=self._timeline.fps, loop=self._timeline.loop))

    def _replace_timeline(self, timeline):
        self._timeline = timeline
        self.set_timeline(timeline)
        self.timeline_changed.emit(timeline)

    def _update_action_state(self):
        has_shots = bool(self._timeline.shots)
        self.duplicate_button.setEnabled(has_shots)
        self.delete_button.setEnabled(has_shots)
        self.move_left_button.setEnabled(has_shots and self._selected_shot > 0)
        self.move_right_button.setEnabled(
            has_shots and self._selected_shot >= 0 and self._selected_shot < len(self._timeline.shots) - 1
        )


__all__ = ["ViewerTimelineWidget"]
