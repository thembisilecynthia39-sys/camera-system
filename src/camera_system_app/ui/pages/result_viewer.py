"""Embedded local Gaussian Splat result viewer page."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
)

from camera_system_app.ui.pages.base import BasePage
from camera_system_app.ui.widgets import (
    EmptyState,
    StatusBanner,
    ViewerInspector,
    ViewerToolbar,
    ViewerTimelineWidget,
)


class ResultViewerPage(BasePage):
    open_local_result_requested = Signal(str)
    select_local_result_requested = Signal()
    reset_view_requested = Signal()
    fit_view_requested = Signal()
    display_mode_requested = Signal(str)
    quality_requested = Signal(str)
    view_preset_requested = Signal(str)
    display_settings_changed = Signal(object)
    appearance_settings_changed = Signal(object)
    render_settings_changed = Signal(object)
    save_requested = Signal()
    save_as_requested = Signal()
    timeline_changed = Signal(object)
    frame_selected = Signal(int)
    camera_mode_changed = Signal(str)
    fly_speed_changed = Signal(float)
    fov_changed = Signal(float)
    camera_pose_changed = Signal(object)
    bookmark_add_requested = Signal(str)
    bookmark_load_requested = Signal(str)
    bookmark_delete_requested = Signal(str)
    play_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    presentation_requested = Signal()
    render_requested = Signal()

    def __init__(self, result_root: str, viewer_root: str, parent=None) -> None:
        super().__init__(
            "结果查看",
            "使用现有 q3dviewer 查看 Jetson 本地 Gaussian Splat PLY。",
            parent,
            eyebrow="工作流 03 · 查看与检查",
        )
        self.setObjectName("resultPageSurface")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._local_path = None
        self.result_root = Path(result_root).resolve()
        self._viewer_widget = None
        self._narrow_mode = False
        self._sphere_available = True
        self._sphere_error = ""
        self._banner = StatusBanner("当前没有已完成的本地重建结果。")
        self.layout.addWidget(self._banner)

        card = self.add_card(
            "结果工具栏",
            "选择本地 PLY，加载后可重置视角或重新载入。",
        )
        self._source_card = card.parentWidget()
        self._result = QLabel("结果目录：" + result_root)
        self._result.setWordWrap(True)
        viewer = QLabel("q3dviewer 源码：" + viewer_root)
        viewer.setObjectName("mutedText")
        viewer.setWordWrap(True)
        controls = QHBoxLayout()
        self._select = QPushButton("选择本地 PLY")
        self._select.setAccessibleName("选择本地 Gaussian PLY")
        self._select.clicked.connect(self.select_local_result_requested.emit)
        self._action = QPushButton("加载当前 PLY")
        self._action.setObjectName("primaryButton")
        self._action.setEnabled(False)
        self._action.clicked.connect(self.open_current_result)
        self._reset = QPushButton("重置视角")
        self._reset.setEnabled(False)
        self._reset.clicked.connect(self.reset_view_requested.emit)
        hint = QLabel(
            "右键拖动 360° 环视 · 左键拖动平移 · 滚轮缩放 · "
            "移动时快速预览，停下后恢复高质量"
        )
        hint.setObjectName("mutedText")
        hint.setWordWrap(True)
        controls.addWidget(self._select)
        controls.addWidget(self._action)
        controls.addWidget(self._reset)
        controls.addStretch(1)
        controls.addWidget(hint)
        card.addWidget(self._result)
        card.addWidget(viewer)
        card.addLayout(controls)

        self._viewer_frame = QFrame()
        self._viewer_frame.setObjectName("contentCard")
        self._viewer_layout = QVBoxLayout(self._viewer_frame)
        self._viewer_layout.setContentsMargins(2, 2, 2, 2)
        self._toolbar = ViewerToolbar()
        self._toolbar.setEnabled(False)
        self._toolbar.open_requested.connect(self.select_local_result_requested.emit)
        self._toolbar.save_requested.connect(self.save_requested.emit)
        self._toolbar.save_as_requested.connect(self.save_as_requested.emit)
        self._toolbar.reset_requested.connect(self.reset_view_requested.emit)
        self._toolbar.fit_requested.connect(self.fit_view_requested.emit)
        self._toolbar.display_mode_changed.connect(self.display_mode_requested.emit)
        self._toolbar.quality_changed.connect(self.quality_requested.emit)
        self._toolbar.view_preset_changed.connect(self.view_preset_requested.emit)
        self._toolbar.play_requested.connect(self.play_requested.emit)
        self._toolbar.pause_requested.connect(self.pause_requested.emit)
        self._toolbar.stop_requested.connect(self.stop_requested.emit)
        self._toolbar.presentation_requested.connect(self.presentation_requested.emit)
        self._toolbar.render_requested.connect(self.render_requested.emit)
        self._toolbar.inspector_requested.connect(self._toggle_inspector)
        self._toolbar.timeline_requested.connect(self._toggle_timeline)
        self._viewer_layout.addWidget(self._toolbar)

        self._studio_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._studio_splitter.setObjectName("viewerStudioSplitter")
        self._viewport_frame = QFrame()
        self._viewport_frame.setObjectName("viewerViewport")
        self._viewport_layout = QVBoxLayout(self._viewport_frame)
        self._viewport_layout.setContentsMargins(0, 0, 0, 0)
        self._camera_info_label = QLabel()
        self._camera_info_label.setObjectName("viewerCameraInfo")
        self._camera_info_label.setWordWrap(True)
        self._camera_info_label.setVisible(False)
        self._viewport_layout.addWidget(self._camera_info_label)
        self._inspector = ViewerInspector()
        self._inspector.setVisible(False)
        self._inspector.display_settings_changed.connect(
            self.display_settings_changed.emit
        )
        self._inspector.appearance_settings_changed.connect(
            self.appearance_settings_changed.emit
        )
        self._inspector.render_settings_changed.connect(
            self.render_settings_changed.emit
        )
        self._inspector.camera_mode_changed.connect(self.camera_mode_changed.emit)
        self._inspector.fly_speed_changed.connect(self.fly_speed_changed.emit)
        self._inspector.fov_changed.connect(self.fov_changed.emit)
        self._inspector.camera_pose_changed.connect(self.camera_pose_changed.emit)
        self._inspector.bookmark_add_requested.connect(
            self.bookmark_add_requested.emit
        )
        self._inspector.bookmark_load_requested.connect(
            self.bookmark_load_requested.emit
        )
        self._inspector.bookmark_delete_requested.connect(
            self.bookmark_delete_requested.emit
        )
        self._studio_splitter.addWidget(self._viewport_frame)
        self._studio_splitter.addWidget(self._inspector)
        self._studio_splitter.setStretchFactor(0, 1)
        self._studio_splitter.setStretchFactor(1, 0)
        self._viewer_layout.addWidget(self._studio_splitter, 1)
        self._timeline = ViewerTimelineWidget()
        self._timeline.setVisible(False)
        self._timeline.timeline_changed.connect(self.timeline_changed.emit)
        self._timeline.frame_selected.connect(self.frame_selected.emit)
        self._empty_state = EmptyState(
            "◇",
            "尚未加载 Gaussian 结果",
            "重建完成后可直接打开结果，也可以选择 Jetson 本地 PLY。",
            "选择本地 PLY",
        )
        self._empty_state.action_requested.connect(
            self.select_local_result_requested.emit
        )
        self._empty = self._empty_state
        self._viewport_layout.addWidget(self._empty, 1)
        self.layout.addWidget(self._viewer_frame, 1)
        self.layout.addWidget(self._timeline)

    def set_result_available(self, local_path: str) -> None:
        path = Path(local_path).resolve()
        self._local_path = path
        self._result.setText("Jetson 本地结果：" + str(path))
        if path.is_file():
            self._banner.set_status("本地结果文件可用，可以加载。", "success")
            self._action.setEnabled(True)
        else:
            self.show_load_error("结果文件不存在：{}".format(path))

    def open_current_result(self) -> None:
        if self._local_path:
            self.open_local_result_requested.emit(str(self._local_path))

    def show_loading(self, path: str) -> None:
        self._source_card.show()
        self.set_sphere_modes_available(True)
        self._banner.set_status("正在后台解析 PLY：{}".format(path), "success")
        self._action.setEnabled(False)
        self._reset.setEnabled(False)
        self._toolbar.setEnabled(False)
        self._inspector.setVisible(False)
        self._timeline.setVisible(False)

    def set_viewer_widget(self, widget, path: str, gaussian_count: int) -> None:
        if self._viewer_widget is None:
            self._viewport_layout.removeWidget(self._empty)
            self._empty.hide()
            self._viewer_widget = widget
            self._viewport_layout.addWidget(widget, 1)
        self._viewer_widget.show()
        self._source_card.hide()
        self._toolbar.setEnabled(True)
        self._inspector.setVisible(True)
        self._timeline.setVisible(True)
        self._apply_responsive_layout()
        self._update_viewport_size()
        if self._sphere_available:
            self._banner.set_status(
                "已加载 {:,} 个 Gaussian：{}".format(gaussian_count, path),
                "success",
            )
        else:
            self._banner.set_status(
                "外接球显示不可用：{}；已加载 {:,} 个 Gaussian，标准 Gaussian 仍可使用".format(
                    self._sphere_error or "渲染器不支持",
                    gaussian_count,
                ),
                "warning",
            )
        self._action.setEnabled(True)
        self._action.setText("重新加载")
        self._reset.setEnabled(True)

    def set_timeline(self, timeline) -> None:
        self._timeline.set_timeline(timeline)

    def set_current_frame(self, frame: int) -> None:
        self._timeline.set_current_frame(frame)

    def set_current_camera_pose(self, pose) -> None:
        self._timeline.set_current_pose(pose)
        if pose is not None:
            self._camera_info_label.setText(
                "相机 ({:.3f}, {:.3f}, {:.3f})  ·  目标 ({:.3f}, {:.3f}, {:.3f})  ·  FOV {:.1f}°".format(
                    *pose.position,
                    *pose.target,
                    pose.fov_degrees,
                )
            )

    def set_camera_info_visible(self, visible: bool) -> None:
        self._camera_info_label.setVisible(bool(visible))

    def set_camera_pose(self, pose) -> None:
        self._inspector.set_camera_pose(pose)

    def set_camera_mode(self, mode) -> None:
        self._inspector.set_camera_mode(mode)

    def set_fly_speed(self, speed) -> None:
        self._inspector.set_fly_speed(speed)

    def set_bookmarks(self, bookmarks) -> None:
        self._inspector.set_bookmarks(bookmarks)

    def set_sphere_modes_available(self, available, error="") -> None:
        self._sphere_available = bool(available)
        self._sphere_error = str(error or "")
        self._toolbar.set_sphere_modes_available(available, error)
        self._inspector.set_sphere_modes_available(available, error)
        if not available:
            self._banner.set_status(
                "外接球显示不可用：{}；标准 Gaussian 仍可继续使用".format(
                    error or "渲染器不支持"
                ),
                "warning",
            )

    def set_playing(self, playing: bool) -> None:
        self._toolbar.set_playing(playing)

    def set_project_dirty(self, dirty: bool) -> None:
        self._toolbar.set_project_dirty(dirty)

    def set_rendering(self, rendering: bool) -> None:
        """Freeze scene-editing controls while a final frame is being rendered."""

        rendering = bool(rendering)
        self._select.setEnabled(not rendering)
        self._action.setEnabled(not rendering and bool(self._local_path))
        self._reset.setEnabled(not rendering and self._viewer_widget is not None)
        self._toolbar.setEnabled(not rendering and self._viewer_widget is not None)
        self._inspector.setEnabled(not rendering)
        self._timeline.setEnabled(not rendering)

    def _toggle_inspector(self) -> None:
        if self._narrow_mode:
            self._timeline.hide()
            self._inspector.show()
        else:
            self._inspector.setVisible(not self._inspector.isVisible())

    def _toggle_timeline(self) -> None:
        if self._narrow_mode:
            self._inspector.hide()
            self._timeline.show()
        else:
            self._timeline.setVisible(not self._timeline.isVisible())

    def _apply_responsive_layout(self) -> None:
        if self._viewer_widget is None:
            return
        narrow = self.width() < 900
        if narrow and not self._narrow_mode:
            self._narrow_mode = True
            self._inspector.hide()
            self._timeline.show()
        elif not narrow and self._narrow_mode:
            self._narrow_mode = False
            self._inspector.show()
            self._timeline.show()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout()
        self._update_viewport_size()

    def _update_viewport_size(self) -> None:
        if self._viewer_widget is None:
            return
        width = max(1, int(self._viewer_widget.width()))
        height = max(1, int(self._viewer_widget.height()))
        self._inspector.set_viewport_size(width, height)

    def show_load_error(self, message: str) -> None:
        self._source_card.show()
        self._banner.set_status("结果加载失败：{}".format(message), "warning")
        self._action.setEnabled(bool(self._local_path and self._local_path.is_file()))
        self._reset.setEnabled(self._viewer_widget is not None)
