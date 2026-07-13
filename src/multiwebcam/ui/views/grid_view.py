"""Grid view showing all sources simultaneously."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap, QRegularExpressionValidator, QResizeEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from multiwebcam.pipeline.alignment import AlignmentStats
from multiwebcam.pipeline.report import CameraStats
from multiwebcam.recognition import InferenceStatus
from multiwebcam.ui.fluent import check_box, combo_box, line_edit, push_button
from multiwebcam.ui.components import SystemStatusBar, icon_path
from multiwebcam.ui.recording_intent import GridRecordingIntent
from multiwebcam.ui.theme import set_variant, status_style
from multiwebcam.ui.views.source_tile import SourceTile


class GridView(QWidget):
    """Displays all sources in a grid with recording controls.

    Signals:
        focus_requested(int): User wants to focus source with given source_id
        record_requested(object): User clicked record button; emits GridRecordingIntent
    photo_requested: User clicked one-shot still image capture
    stop_requested: User clicked stop button
    poll_interval_changed(int): User changed poll interval (milliseconds)
        ignore_toggled(int, bool): User toggled ignore for a source (source_id, ignored)
        mirror_toggled(bool): User toggled horizontal flip
        angle_changed(int): User changed selected capture angle
        open_folder_requested: User clicked Open Folder button
        model_file_requested: User wants to select a Gaussian-splat PLY model
    """

    focus_requested = Signal(int)  # source_id
    record_requested = Signal(object)  # GridRecordingIntent
    photo_requested = Signal()
    stop_requested = Signal()
    poll_interval_changed = Signal(int)  # milliseconds
    mirror_toggled = Signal(bool)
    ignore_toggled = Signal(int, bool)  # source_id, ignored
    angle_changed = Signal(int)
    open_folder_requested = Signal()
    model_file_requested = Signal()
    workspace_changed = Signal(int)
    load_cameras_requested = Signal()
    pause_video_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tiles: dict[int, SourceTile] = {}
        self._errored_source_ids: set[int] = set()
        self._ignored_source_ids: set[int] = set()
        self.setObjectName("gridSurface")

        # The shell separates global navigation from contextual controls:
        # navigation stays compact at the top, while the left inspector only
        # contains parameters for the selected workspace.
        root_layout = QVBoxLayout(self)
        root_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._top_navigation = QFrame()
        self._top_navigation.setObjectName("topNavigation")
        top_layout = QHBoxLayout(self._top_navigation)
        top_layout.setContentsMargins(20, 12, 20, 10)
        top_layout.setSpacing(16)

        brand_layout = QVBoxLayout()
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(1)
        self._brand = QLabel("边端 3DGS 重建")
        self._brand.setObjectName("brandMark")
        self._page_title = QLabel("采集工作台")
        self._page_title.setObjectName("pageTitle")
        self._subtitle = QLabel("多机位采集与重建")
        self._subtitle.setObjectName("captionLabel")
        self._subtitle.setWordWrap(True)
        brand_layout.addWidget(self._brand)
        brand_layout.addWidget(self._page_title)
        brand_layout.addWidget(self._subtitle)
        top_layout.addLayout(brand_layout)

        self._nav_label = QLabel("工作区")
        self._nav_label.setObjectName("navLabel")
        top_layout.addWidget(self._nav_label)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(4)
        nav_buttons = [
            ("监看总览", "grid", "当前视频墙与基础状态"),
            ("录制采集", "record", "名称、目录、拍照与录制"),
            ("角度引导", "guide", "拍摄角度与质量进度"),
            ("系统设置", "settings", "刷新率、镜像与推理状态"),
            ("3DGS 模型", "cube", "查看重建后的 Gaussian Splat 模型"),
        ]
        self._nav_buttons = []
        for index, (text, icon_name, tip) in enumerate(nav_buttons):
            # Navigation uses the stock button so checked-state styling remains
            # deterministic across desktop PySide6 and the Jetson PyQt5 shim.
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setToolTip(tip)
            button.setIcon(QIcon(icon_path(icon_name)))
            button.setIconSize(QSize(20, 20))
            button.setProperty("fullText", text)
            button.setAccessibleName(text)
            button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda checked=False, i=index: self._select_workspace(i))
            self._nav_group.addButton(button, index)
            self._nav_buttons.append(button)
            if index == 4:
                self._model_nav_button = button
            nav_layout.addWidget(button)
            if index == 0:
                button.setChecked(True)
        top_layout.addLayout(nav_layout)
        top_layout.addStretch()
        root_layout.addWidget(self._top_navigation)

        self._side_panel = QFrame()
        self._side_panel.setObjectName("contextPanel")
        self._side_panel.setMinimumWidth(224)
        self._side_panel.setMaximumWidth(280)
        self._side_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        side_layout = QVBoxLayout(self._side_panel)
        side_layout.setContentsMargins(16, 16, 16, 16)
        side_layout.setSpacing(8)

        self._panel_stack = QStackedWidget()
        self._panel_stack.setObjectName("sidePanelStack")
        self._panel_stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)

        self._panel_scroll = QScrollArea()
        self._panel_scroll.setObjectName("sidePanelScroll")
        self._panel_scroll.setWidgetResizable(True)
        self._panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._panel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._panel_scroll.setWidget(self._panel_stack)
        self._panel_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        side_layout.addWidget(self._panel_scroll, stretch=1)

        content_column = QVBoxLayout()
        content_column.setContentsMargins(0, 0, 0, 0)
        content_column.setSpacing(12)
        content_header = QHBoxLayout()
        content_header.setContentsMargins(2, 0, 2, 0)
        content_header.setSpacing(10)
        wall_title = QLabel("多机位监看")
        wall_title.setObjectName("sectionTitle")
        self._wall_hint = QLabel("点击“画质设置”可分别调整每台相机的分辨率与帧率")
        self._wall_hint.setObjectName("captionLabel")
        content_header.addWidget(wall_title)
        content_header.addSpacing(10)
        content_header.addWidget(self._wall_hint)
        content_header.addStretch()
        content_column.addLayout(content_header)

        self._grid_widget = QWidget()
        self._grid_widget.setObjectName("videoWall")
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(12)
        content_column.addWidget(self._grid_widget, stretch=1)

        overview_page = self._create_panel_page()
        overview_layout = overview_page.layout()

        overview_title = QLabel("系统概况")
        overview_title.setObjectName("sideSectionTitle")
        overview_hint = QLabel("关键采集状态")
        overview_hint.setObjectName("captionLabel")
        overview_hint.setWordWrap(True)
        overview_layout.addWidget(overview_title)
        overview_layout.addWidget(overview_hint)
        overview_layout.addSpacing(4)

        self._status_label = QLabel("状态: 系统就绪")
        self._inference_label = QLabel("AI: --")
        self._alignment_label = QLabel("同步: --")
        self._quality_label = QLabel("质量: --")
        for label in (self._status_label, self._inference_label, self._alignment_label, self._quality_label):
            label.setObjectName("overviewStatus")
            label.setProperty("status", "muted")
            label.setWordWrap(True)
            overview_layout.addWidget(label)
        overview_layout.addStretch()
        self._panel_stack.addWidget(overview_page)

        record_page = self._create_panel_page()
        control_layout = record_page.layout()

        # Destination row (above action controls)
        dest_title = QLabel("录制采集")
        dest_title.setObjectName("sideSectionTitle")
        control_layout.addWidget(dest_title)

        self._extrinsic_cb = check_box("外参标定")
        control_layout.addWidget(self._extrinsic_cb)

        self._name_label = QLabel("任务名称:")
        self._name_label.setObjectName("captionLabel")
        control_layout.addWidget(self._name_label)

        self._name_input = line_edit("")
        self._name_input.setPlaceholderText("例如：产品环拍_上午")
        self._name_input.setValidator(QRegularExpressionValidator(r"[\w\-]+", self._name_input))
        control_layout.addWidget(self._name_input)

        self._dest_summary = QLabel("")
        self._dest_summary.setObjectName("destinationPath")
        self._dest_summary.setWordWrap(True)
        control_layout.addWidget(self._dest_summary)

        self._open_folder_btn = push_button("查看保存目录")
        set_variant(self._open_folder_btn, "ghost")
        control_layout.addWidget(self._open_folder_btn)

        camera_resource_label = QLabel("摄像头资源")
        camera_resource_label.setObjectName("sideLabel")
        control_layout.addSpacing(6)
        control_layout.addWidget(camera_resource_label)
        self._load_cameras_btn = push_button("加载摄像头")
        self._pause_video_btn = push_button("暂停视频传输")
        set_variant(self._load_cameras_btn, "ghost")
        set_variant(self._pause_video_btn, "ghost")
        control_layout.addWidget(self._load_cameras_btn)
        control_layout.addWidget(self._pause_video_btn)

        # Recording controls
        self._record_btn = QPushButton("开始录制")
        self._photo_btn = push_button("拍摄当前角度", primary=True)
        self._stop_btn = push_button("停止")
        self._stop_btn.setEnabled(False)
        set_variant(self._record_btn, "record")
        set_variant(self._photo_btn, "primary")
        set_variant(self._stop_btn, "ghost")

        self._record_btn.clicked.connect(self._on_record_clicked)
        self._photo_btn.clicked.connect(self.photo_requested.emit)
        self._stop_btn.clicked.connect(self.stop_requested.emit)

        action_label = QLabel("采集操作")
        action_label.setObjectName("sideLabel")
        control_layout.addSpacing(8)
        control_layout.addWidget(action_label)
        control_layout.addWidget(self._record_btn)
        control_layout.addWidget(self._photo_btn)
        control_layout.addWidget(self._stop_btn)
        self._duration_label = QLabel("00:00:00")
        self._duration_label.setObjectName("timerLabel")
        control_layout.addWidget(self._duration_label)
        control_layout.addStretch()
        self._panel_stack.addWidget(record_page)

        guide_page = self._create_panel_page()
        guide_layout = guide_page.layout()
        guide_title = QLabel("角度引导")
        guide_title.setObjectName("sideSectionTitle")
        guide_layout.addWidget(guide_title)
        angle_label = QLabel("角度:")
        angle_label.setObjectName("captionLabel")
        guide_layout.addWidget(angle_label)
        self._angle_combo = combo_box()
        self._angle_combo.addItems([f"{angle}°" for angle in range(0, 360, 45)])
        self._angle_combo.currentTextChanged.connect(self._on_angle_changed)
        guide_layout.addWidget(self._angle_combo)

        self._guide_progress_label = QLabel("进度: 0%")
        self._guide_now_label = QLabel("当前: --")
        self._guide_next_label = QLabel("下一角度: 0°")
        self._guide_done_label = QLabel("已完成: --")
        self._guide_warning_label = QLabel("")
        for label in (
            self._guide_progress_label,
            self._guide_now_label,
            self._guide_next_label,
            self._guide_done_label,
            self._guide_warning_label,
        ):
            label.setObjectName("captionLabel")
            label.setWordWrap(True)
            guide_layout.addWidget(label)
        self._guide_done_label.setStyleSheet(status_style("muted", bold=False))
        self._guide_warning_label.setStyleSheet(status_style("warning"))
        guide_layout.addStretch()
        self._panel_stack.addWidget(guide_page)

        settings_page = self._create_panel_page()
        settings_layout = settings_page.layout()
        settings_title = QLabel("系统设置")
        settings_title.setObjectName("sideSectionTitle")
        settings_layout.addWidget(settings_title)
        fps_label = QLabel("刷新:")
        fps_label.setObjectName("captionLabel")
        settings_layout.addWidget(fps_label)
        self._fps_combo = combo_box()
        self._fps_combo.addItems(["15 fps", "30 fps", "60 fps"])
        self._fps_combo.setCurrentText("15 fps")
        self._fps_combo.currentTextChanged.connect(self._on_fps_changed)
        settings_layout.addWidget(self._fps_combo)
        self._mirror_cb = check_box("镜像")
        self._mirror_cb.toggled.connect(self.mirror_toggled.emit)
        settings_layout.addWidget(self._mirror_cb)
        settings_layout.addStretch()
        self._panel_stack.addWidget(settings_page)

        model_page = self._create_panel_page()
        model_layout = model_page.layout()
        model_title = QLabel("3DGS 模型")
        model_title.setObjectName("sideSectionTitle")
        model_layout.addWidget(model_title)
        model_hint = QLabel("在主工作区查看并旋转 Gaussian Splat 模型")
        model_hint.setObjectName("captionLabel")
        model_hint.setWordWrap(True)
        model_layout.addWidget(model_hint)
        model_controls_hint = QLabel("左键拖动：自由环绕\n右键拖动：平移\n滚轮：缩放")
        model_controls_hint.setObjectName("destinationPath")
        model_controls_hint.setWordWrap(True)
        model_layout.addWidget(model_controls_hint)
        self._select_model_btn = push_button("选择 .ply 模型", primary=True)
        set_variant(self._select_model_btn, "primary")
        model_layout.addWidget(self._select_model_btn)
        self._model_status_label = QLabel("尚未加载模型")
        self._model_status_label.setObjectName("statusPill")
        self._model_status_label.setWordWrap(True)
        model_layout.addWidget(self._model_status_label)
        model_layout.addStretch()
        self._panel_stack.addWidget(model_page)

        from multiwebcam.ui.views.gaussian_model_view import GaussianModelView

        self._content_stack = QStackedWidget()
        video_page = QWidget()
        video_page.setLayout(content_column)
        self._content_stack.addWidget(video_page)
        self._model_view = GaussianModelView()
        self._model_view.model_loaded.connect(lambda name: self._model_status_label.setText(f"已加载: {name}"))
        self._model_view.load_failed.connect(lambda error: self._model_status_label.setText(f"加载失败: {error}"))
        self._content_stack.addWidget(self._model_view)

        self._system_status = SystemStatusBar()
        self._system_status.set_camera_count(0)
        self._system_status.set_capture_paused(False)
        content_region = QVBoxLayout()
        content_region.setContentsMargins(0, 0, 0, 0)
        content_region.setSpacing(0)
        content_region.addWidget(self._content_stack, stretch=1)

        status_region = QHBoxLayout()
        status_region.setContentsMargins(16, 10, 16, 0)
        status_region.setSpacing(0)
        status_region.addWidget(self._system_status)

        body_layout = QHBoxLayout()
        body_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        body_layout.setContentsMargins(16, 12, 16, 16)
        body_layout.setSpacing(16)
        body_layout.addWidget(self._side_panel)
        body_layout.addLayout(content_region, stretch=1)

        root_layout.addLayout(status_region)
        root_layout.addLayout(body_layout, stretch=1)

        # Wire destination controls
        self._extrinsic_cb.toggled.connect(self._on_extrinsic_toggled)
        self._name_input.textChanged.connect(self._update_dest_summary)
        self._open_folder_btn.clicked.connect(self.open_folder_requested.emit)
        self._select_model_btn.clicked.connect(self.model_file_requested.emit)
        self._load_cameras_btn.clicked.connect(self.load_cameras_requested.emit)
        self._pause_video_btn.clicked.connect(self.pause_video_requested.emit)

        self._update_dest_summary()

    def _select_workspace(self, index: int) -> None:
        self._panel_stack.setCurrentIndex(index)
        self._content_stack.setCurrentIndex(1 if index == 4 else 0)
        self._model_view.set_active(index == 4)
        self.workspace_changed.emit(index)

    def load_model(self, path: str) -> None:
        self._model_status_label.setText("正在加载模型...")
        self._model_view.load_model(Path(path))

    def set_video_paused(self, paused: bool, message: str = "") -> None:
        self._pause_video_btn.setText("继续视频传输" if paused else "暂停视频传输")
        self._pause_video_btn.setProperty("paused", paused)
        self._system_status.set_capture_paused(paused)
        if message:
            self._status_label.setText(f"状态: {message}")

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Simplify secondary content and reflow previews on narrow windows."""
        super().resizeEvent(event)
        compact = event.size().width() < 900
        narrow = event.size().width() < 720
        self._side_panel.setFixedWidth(210 if narrow else (232 if compact else 248))
        self._brand.setVisible(not compact)
        self._subtitle.setVisible(not compact)
        self._wall_hint.setVisible(not compact)
        self._nav_label.setVisible(not compact)
        self._page_title.setVisible(not narrow)
        self._panel_scroll.setVisible(True)
        self._panel_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if event.size().height() < 760
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        for button in self._nav_buttons:
            button.setText("" if narrow else button.property("fullText"))
        self._system_status.set_compact(compact)
        self._relayout_tiles()
        # The child video wall receives its final width after this event;
        # reflow once more with the settled geometry.
        QTimer.singleShot(0, self._relayout_tiles)

    def _create_panel_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("sidePanelPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        return page

    def _on_fps_changed(self, text: str) -> None:
        fps = int(text.split()[0])
        self.poll_interval_changed.emit(1000 // fps)

    def _on_angle_changed(self, text: str) -> None:
        angle = int(text.replace("°", "").split()[0])
        self.angle_changed.emit(angle)

    def add_source(self, source_id: int, label: str, ignore: bool = False) -> None:
        """Add a source tile to the grid."""
        if source_id in self._tiles:
            self.set_source_ignored(source_id, ignore)
            return

        tile = SourceTile(source_id, label, ignore=ignore, display_index=len(self._tiles) + 1)
        tile.set_compact(True)
        tile.focus_requested.connect(lambda sid=source_id: self.focus_requested.emit(sid))
        tile.ignore_toggled.connect(lambda ignored, sid=source_id: self._on_tile_ignore_toggled(sid, ignored))
        self._tiles[source_id] = tile
        self._errored_source_ids.discard(source_id)
        if ignore:
            self._ignored_source_ids.add(source_id)
            self._update_record_enabled()

        self._relayout_tiles()
        self._refresh_camera_status()

    def _refresh_camera_status(self) -> None:
        connected = len(self._tiles) - len(self._errored_source_ids)
        self._system_status.set_camera_count(max(0, connected))

    def has_source(self, source_id: int) -> bool:
        """True if a tile exists for source_id."""
        return source_id in self._tiles

    def _on_tile_ignore_toggled(self, source_id: int, ignored: bool) -> None:
        if ignored:
            self._ignored_source_ids.add(source_id)
        else:
            self._ignored_source_ids.discard(source_id)
        self._update_record_enabled()
        self.ignore_toggled.emit(source_id, ignored)

    def _relayout_tiles(self) -> None:
        """Lay out tiles according to the video wall's usable width."""
        column_count = self._grid_column_count()
        while self._grid_layout.count():
            self._grid_layout.takeAt(0)
        for index in range(4):
            self._grid_layout.setRowStretch(index, 0)
            self._grid_layout.setColumnStretch(index, 0)
        for idx, tile in enumerate(self._tiles.values()):
            tile.set_display_index(idx + 1)
            tile.set_compact(self._grid_widget.width() / max(1, column_count) < 300)
            row, col = divmod(idx, column_count)
            self._grid_layout.addWidget(tile, row, col)
        row_count = (len(self._tiles) + column_count - 1) // column_count
        for row in range(row_count):
            self._grid_layout.setRowStretch(row, 1)
        for col in range(column_count):
            self._grid_layout.setColumnStretch(col, 1)

    def _grid_column_count(self) -> int:
        tile_count = len(self._tiles)
        available_width = max(1, self._grid_widget.width())
        if tile_count <= 1 or available_width < 380:
            return 1
        if tile_count <= 4 or available_width < 900:
            return 2
        return min(3, tile_count)

    def _update_record_enabled(self) -> None:
        all_ignored = self._tiles and len(self._ignored_source_ids) >= len(self._tiles)
        self._record_btn.setEnabled(not all_ignored)

    def _on_extrinsic_toggled(self, checked: bool) -> None:
        """Hide/show name label and input based on extrinsic checkbox."""
        self._name_label.setVisible(not checked)
        self._name_input.setVisible(not checked)
        self._update_dest_summary()

    def _on_record_clicked(self) -> None:
        """Construct GridRecordingIntent from widget state and emit record_requested."""
        intent = GridRecordingIntent(
            is_extrinsic=self._extrinsic_cb.isChecked(),
            recording_name=self._name_input.text(),
        )
        self.record_requested.emit(intent)

    def _update_dest_summary(self) -> None:
        """Update the destination summary label based on current widget state."""
        if self._extrinsic_cb.isChecked():
            self._dest_summary.setText("保存至  calibration/extrinsic/")
        else:
            name = self._name_input.text() or "untitled"
            self._dest_summary.setText(f"保存至  recordings/{name}/")

    def set_default_recording_name(self, name: str) -> None:
        """Set the recording name line edit text without triggering signals."""
        self._name_input.blockSignals(True)
        self._name_input.setText(name)
        self._name_input.blockSignals(False)
        self._update_dest_summary()

    def confirm_overwrite(self, display_name: str) -> bool:
        """Ask user to confirm overwriting an existing destination."""
        result = QMessageBox.question(
            self,
            "覆盖已有录制?",
            f"'{display_name}' 已经包含文件。\n\n是否覆盖?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    def display_frames(self, frames: dict[int, QPixmap]) -> None:
        """Update frames for multiple sources."""
        for source_id, pixmap in frames.items():
            if source_id in self._tiles:
                self._tiles[source_id].display_frame(pixmap)

    def update_stats(self, stats: dict[int, CameraStats]) -> None:
        """Update stats for multiple sources."""
        for source_id, stat in stats.items():
            if source_id in self._tiles:
                self._tiles[source_id].update_stats(stat.measured_fps, stat.jitter_ms)

    def update_quality(self, qualities: dict[int, object], capture_quality: object) -> None:
        """Update realtime per-camera and global quality labels."""
        for source_id, quality in qualities.items():
            if source_id in self._tiles:
                self._tiles[source_id].update_quality(quality.summary(), quality.level.value)
        readiness = getattr(capture_quality, "readiness_percent", 0.0)
        self._quality_label.setText(
            f"质量: {_zh_quality_summary(capture_quality.summary().replace('Capture ', ''))} | {readiness:.0f}%"
        )
        color = {
            "good": "good",
            "warn": "warn",
            "bad": "bad",
        }.get(capture_quality.level.value, "muted")
        _set_pill_status(self._quality_label, color)

    def update_guidance(self, guidance: object | None) -> None:
        """Update the lower-right capture guidance panel."""
        if guidance is None:
            self._guide_progress_label.setText("进度: 0%")
            self._guide_now_label.setText("当前: --")
            self._guide_next_label.setText("下一角度: --")
            self._guide_done_label.setText("已完成: --")
            self._guide_warning_label.setText("")
            self._guide_now_label.setStyleSheet(status_style("muted", bold=False))
            return

        done = " ".join(f"{angle}" for angle in guidance.completed_angles) or "--"
        if getattr(guidance, "loop_complete", False) and guidance.next_angle_deg is None:
            next_angle = "360° 完成"
        else:
            next_angle = "--" if guidance.next_angle_deg is None else f"{guidance.next_angle_deg}°"
        self._guide_progress_label.setText(f"进度: {guidance.progress_percent:.0f}%")
        self._guide_now_label.setText(
            f"当前: {guidance.readiness_percent:.0f}% {_zh_readiness_label(guidance.readiness_label)}"
        )
        self._guide_next_label.setText(f"下一角度: {next_angle}")
        self._guide_done_label.setText(f"已完成: {done}")
        self._guide_warning_label.setText(_zh_guidance_warning(guidance.warning))

        if guidance.ready_to_capture:
            self._guide_now_label.setStyleSheet(status_style("good"))
        elif guidance.readiness_percent >= 60:
            self._guide_now_label.setStyleSheet(status_style("warn"))
        else:
            self._guide_now_label.setStyleSheet(status_style("bad"))

    def update_alignment(self, alignment: AlignmentStats | None) -> None:
        """Update alignment stats in status bar."""
        if alignment:
            self._alignment_label.setText(
                f"同步: {alignment.mean_spread_ms:.1f}ms | 完整 {alignment.complete_cluster_pct:.0f}%"
            )
            if alignment.complete_cluster_pct >= 95 and alignment.mean_spread_ms <= 20:
                _set_pill_status(self._alignment_label, "good")
            elif alignment.complete_cluster_pct >= 80:
                _set_pill_status(self._alignment_label, "warn")
            else:
                _set_pill_status(self._alignment_label, "bad")

    def update_inference_status(self, status: InferenceStatus) -> None:
        """Update realtime AI inference status in the status bar."""
        backend = _short_backend_name(status.backend)
        detected = status.detected_count
        active = status.active_count
        latency = status.latency_ms

        if active <= 0:
            self._inference_label.setText(f"AI: {backend} | 未启用")
            _set_pill_status(self._inference_label, "muted")
            self._system_status.set_inference("AI 未启用", active=False)
            return

        if status.warming:
            self._inference_label.setText(f"AI: {backend} 预热中 | 0/{active}")
            _set_pill_status(self._inference_label, "warn")
            self._system_status.set_inference("AI 预热中", active=True, warning=True)
            return

        latency_text = "--" if latency is None else f"{float(latency):.0f}ms"
        self._inference_label.setText(f"AI: {backend} | {latency_text} | {detected}/{active}")
        _set_pill_status(self._inference_label, "good" if detected else "muted")
        self._system_status.set_inference(f"AI {latency_text}", active=True)

    def set_recording(self, is_recording: bool) -> None:
        """Update UI for recording state."""
        if not is_recording:
            self._update_record_enabled()
        else:
            self._record_btn.setEnabled(False)
        self._stop_btn.setEnabled(is_recording)
        self._stop_btn.setText("停止")
        self._photo_btn.setEnabled(not is_recording)
        self._extrinsic_cb.setEnabled(not is_recording)
        self._name_input.setEnabled(not is_recording)
        self._open_folder_btn.setEnabled(not is_recording)
        self._model_nav_button.setEnabled(not is_recording)
        self._system_status.set_recording(is_recording)
        for source_id, tile in self._tiles.items():
            tile.set_focus_enabled(not is_recording, reason="录制中..." if is_recording else "")
            if is_recording and source_id not in self._ignored_source_ids:
                tile.set_queue_visible(True)
            else:
                tile.set_queue_visible(False)
        if not is_recording:
            self._duration_label.setText("00:00:00")

    def set_capture_available(self, available: bool, message: str = "") -> None:
        """Enable/disable capture actions when no runtime session exists."""
        self._record_btn.setEnabled(available)
        self._photo_btn.setEnabled(available)
        self._stop_btn.setEnabled(False)
        self._extrinsic_cb.setEnabled(available)
        self._name_input.setEnabled(available)
        self._fps_combo.setEnabled(available)
        self._mirror_cb.setEnabled(available)
        self.set_ignore_controls_enabled(available)
        self._system_status.set_capture_paused(not available)
        for tile in self._tiles.values():
            tile.set_focus_enabled(available, reason="未连接" if not available else "")
        if message:
            self._status_label.setText(f"状态: {message}")
            _set_pill_status(self._status_label, "bad")

    def set_stopping(self) -> None:
        """Recording stop in progress -- disable everything interactive."""
        self._record_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setText("停止中...")
        self._photo_btn.setEnabled(False)
        self._extrinsic_cb.setEnabled(False)
        self._name_input.setEnabled(False)
        self._open_folder_btn.setEnabled(False)
        self._system_status.set_recording(False, stopping=True)
        for tile in self._tiles.values():
            tile.set_focus_enabled(False, reason="停止中...")
            tile.set_ignore_enabled(False)

    def update_duration(self, seconds: float) -> None:
        """Update recording duration display."""
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        self._duration_label.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def update_queue_depth(self, depths: dict[int, int]) -> None:
        """Update per-camera queue depth display."""
        for source_id, tile in self._tiles.items():
            depth = depths.get(source_id, 0)
            tile.set_queue_depth(depth)

    def set_mirror(self, enabled: bool) -> None:
        """Set mirror checkbox state without triggering signal."""
        self._mirror_cb.blockSignals(True)
        self._mirror_cb.setChecked(enabled)
        self._mirror_cb.blockSignals(False)

    def set_tile_resolution(self, source_id: int, resolution: str) -> None:
        """Set resolution label for a tile."""
        if source_id in self._tiles:
            self._tiles[source_id].set_resolution(resolution)

    def set_source_error(self, source_id: int, message: str) -> None:
        """Show an error message on a source tile."""
        tile = self._tiles.get(source_id)
        if tile is not None:
            tile.set_error(message)
            self._errored_source_ids.add(source_id)
            self._refresh_camera_status()

    def clear_source_error(self, source_id: int) -> None:
        """Mark a source as connected again after a hotplug refresh."""
        if source_id not in self._tiles or source_id not in self._errored_source_ids:
            return
        self._errored_source_ids.discard(source_id)
        self._refresh_camera_status()

    def set_storage_available(self, available_bytes: int) -> None:
        self._system_status.set_storage_available(available_bytes)

    def set_source_ignored(self, source_id: int, ignored: bool) -> None:
        """Set ignored state for a tile without emitting ignore_toggled."""
        tile = self._tiles.get(source_id)
        if tile is None:
            return
        tile.set_ignored(ignored)
        if ignored:
            self._ignored_source_ids.add(source_id)
        else:
            self._ignored_source_ids.discard(source_id)
        self._update_record_enabled()

    def set_ignore_controls_enabled(self, enabled: bool) -> None:
        """Enable/disable all source ignore controls."""
        for tile in self._tiles.values():
            tile.set_ignore_enabled(enabled)

    def set_source_ignore_enabled(self, source_id: int, enabled: bool) -> None:
        """Enable/disable the ignore control for one source."""
        tile = self._tiles.get(source_id)
        if tile is not None:
            tile.set_ignore_enabled(enabled)

    def set_photo_capture_result(self, message: str, ok: bool = True) -> None:
        """Show one-shot photo capture result in the status bar."""
        self._status_label.setText(f"状态: {message}")
        _set_pill_status(self._status_label, "good" if ok else "bad")

    def selected_angle_deg(self) -> int:
        """Return the currently selected capture angle."""
        return int(self._angle_combo.currentText().replace("°", "").split()[0])

    def set_selected_angle_deg(self, angle: int) -> None:
        """Set the capture angle without emitting angle_changed."""
        angle %= 360
        if angle == 360:
            angle = 0
        text = f"{angle}°"
        self._angle_combo.blockSignals(True)
        self._angle_combo.setCurrentText(text)
        self._angle_combo.blockSignals(False)


def _zh_readiness_label(label: str) -> str:
    return {
        "READY": "可拍摄",
        "BORDERLINE": "勉强可拍",
        "WAIT": "请等待",
    }.get(label, label)


def _zh_guidance_warning(warning: str | None) -> str:
    if not warning:
        return ""
    if warning.startswith("target not detected"):
        return "未检测到目标，请把物体放到画面中央"
    if warning.startswith("preferred next angle"):
        angle = warning.split("angle", 1)[1].strip().split()[0]
        return f"建议先拍 {angle}°"
    if warning.startswith("duplicate view"):
        return "角度重复，请旋转到下一角度"
    if warning.startswith("low overlap"):
        return "相邻角度重叠不足，请减小旋转或增加纹理"
    return warning


def _zh_quality_summary(summary: str) -> str:
    return (
        summary.replace("GOOD", "良好")
        .replace("WARN", "警告")
        .replace("BAD", "较差")
        .replace("sync", "同步")
        .replace("bad camera(s)", "路摄像头质量差")
        .replace("warning camera(s)", "路摄像头警告")
        .replace("target not detected", "未检测到目标")
    )


def _short_backend_name(backend: str) -> str:
    if "ultralytics_tensorrt" in backend:
        return "YOLO TensorRT"
    if "heuristic" in backend:
        return "启发式"
    if backend == "subprocess":
        return "子进程"
    return backend


def _set_pill_status(label: QLabel, status: str) -> None:
    label.setProperty("status", status)
    label.style().unpolish(label)
    label.style().polish(label)
