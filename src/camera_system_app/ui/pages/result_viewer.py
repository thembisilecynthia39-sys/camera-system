"""Embedded local Gaussian Splat result viewer page."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from camera_system_app.ui.pages.base import BasePage
from camera_system_app.ui.widgets import (
    EmptyState,
    StatusBanner,
    ViewerInspector,
    ViewerStage,
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
        self._sphere_available = True
        self._sphere_error = ""
        self._banner = StatusBanner("当前没有已完成的本地重建结果。")
        self._banner.setVisible(False)

        self._action = QPushButton("加载当前 PLY")
        self._action.setObjectName("primaryButton")
        self._action.setEnabled(False)
        self._action.clicked.connect(self.open_current_result)
        self._action.setVisible(False)

        self._viewer_frame = QFrame()
        self._viewer_frame.setObjectName("viewerFrame")
        self._viewer_layout = QVBoxLayout(self._viewer_frame)
        self._viewer_layout.setContentsMargins(0, 0, 0, 0)
        self._viewer_layout.setSpacing(0)
        self._toolbar = ViewerToolbar()
        self._toolbar.setEnabled(False)
        self._reset = self._toolbar._reset
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
        self._inspector.collapsed_changed.connect(self._on_inspector_collapsed)
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
        self._viewer_stage = ViewerStage(self._viewport_frame, self._inspector)
        self._viewer_layout.addWidget(self._viewer_stage, 1)
        self._timeline = ViewerTimelineWidget()
        self._timeline.setVisible(False)
        self._timeline.timeline_changed.connect(self.timeline_changed.emit)
        self._timeline.frame_selected.connect(self.frame_selected.emit)
        self._empty_state = EmptyState(
            "◇",
            "尚未加载 Gaussian 结果",
            "选择本地 PLY 开始查看。",
            "选择本地 PLY",
        )
        self._empty_state.action_requested.connect(
            self.select_local_result_requested.emit
        )
        self._empty = self._empty_state
        self._select = self._empty_state.action_button
        self._select.setAccessibleName("选择本地 Gaussian PLY")
        self._viewport_layout.addWidget(self._empty, 1)
        self._viewer_stage.setVisible(True)
        self.set_page_header_visible(False)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.addWidget(self._banner)
        self.layout.addWidget(self._viewer_frame, 1)
        self.layout.addWidget(self._timeline)

    def set_result_available(self, local_path: str) -> None:
        path = Path(local_path).resolve()
        self._local_path = path
        if path.is_file():
            self._banner.setVisible(False)
            self._action.setEnabled(True)
        else:
            self.show_load_error("结果文件不存在：{}".format(path))

    def open_current_result(self) -> None:
        if self._local_path:
            self.open_local_result_requested.emit(str(self._local_path))

    def show_loading(self, path: str) -> None:
        self.set_sphere_modes_available(True)
        self._set_banner_status("正在后台解析 PLY：{}".format(path), "success")
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
        self._toolbar.setEnabled(True)
        self._inspector.setVisible(True)
        self._timeline.setVisible(True)
        self._viewer_stage.relayout()
        self._update_viewport_size()
        if self._sphere_available:
            self._banner.setVisible(False)
        else:
            self._set_banner_status(
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
            self._set_banner_status(
                "外接球显示不可用：{}；标准 Gaussian 仍可继续使用".format(
                    error or "渲染器不支持"
                ),
                "warning",
            )
        elif self._viewer_widget is not None:
            self._banner.setVisible(False)

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
        if self._viewer_widget is None:
            return
        self._inspector.set_collapsed(not self._inspector.is_collapsed)

    def _on_inspector_collapsed(self, collapsed: bool) -> None:
        self._viewer_stage.relayout()
        self._toolbar.set_inspector_expanded(not collapsed)

    def _toggle_timeline(self) -> None:
        self._timeline.setVisible(not self._timeline.isVisible())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._viewer_stage.relayout()
        self._update_viewport_size()

    def _update_viewport_size(self) -> None:
        if self._viewer_widget is None:
            return
        width = max(1, int(self._viewer_widget.width()))
        height = max(1, int(self._viewer_widget.height()))
        self._inspector.set_viewport_size(width, height)

    def show_load_error(self, message: str) -> None:
        self._set_banner_status("结果加载失败：{}".format(message), "warning")
        self._action.setEnabled(bool(self._local_path and self._local_path.is_file()))
        self._reset.setEnabled(self._viewer_widget is not None)

    def _set_banner_status(self, text: str, status: str) -> None:
        self._banner.set_status(text, status)
        self._banner.setVisible(True)
