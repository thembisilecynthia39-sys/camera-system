"""Grid view showing all sources simultaneously."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import (
    QIcon,
    QKeySequence,
    QPixmap,
    QRegularExpressionValidator,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from multiwebcam.pipeline.alignment import AlignmentStats
from multiwebcam.pipeline.report import CameraStats
from multiwebcam.profiles import AppSettings, InferenceSettings, RecordingSettings
from multiwebcam.recognition import InferenceStatus
from multiwebcam.ui.fluent import check_box, combo_box, line_edit, push_button
from multiwebcam.ui.components import BottomStatusBar, NumericStepper, ResourceStatusWidget, SystemStatusBar, icon_path
from multiwebcam.ui.recording_intent import GridRecordingIntent
from multiwebcam.ui.theme import set_variant
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
    settings_save_requested = Signal(object)
    upload_staged_tasks_requested = Signal()
    transfer_folder_requested = Signal()
    transfer_upload_requested = Signal(str)

    def __init__(self, parent=None, capture_only: bool = False):
        super().__init__(parent)
        self._capture_only = capture_only
        self._tiles: dict[int, SourceTile] = {}
        self._errored_source_ids: set[int] = set()
        self._ignored_source_ids: set[int] = set()
        self._quality_alerts: list[tuple[str, str]] = []
        self._app_settings = AppSettings()
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
        self._top_navigation.setFixedHeight(74)
        top_layout = QHBoxLayout(self._top_navigation)
        top_layout.setContentsMargins(20, 9, 20, 9)
        top_layout.setSpacing(18)

        brand_icon_frame = QFrame()
        brand_icon_frame.setObjectName("brandIcon")
        brand_icon_frame.setFixedSize(46, 46)
        brand_icon_layout = QVBoxLayout(brand_icon_frame)
        brand_icon_layout.setContentsMargins(9, 9, 9, 9)
        brand_icon = QLabel()
        brand_icon.setPixmap(QPixmap(icon_path("cube")).scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio,
                                                               Qt.TransformationMode.SmoothTransformation))
        brand_icon_layout.addWidget(brand_icon)
        top_layout.addWidget(brand_icon_frame)
        brand_layout = QVBoxLayout()
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(1)
        self._brand = QLabel("边端 3DGS 重建")
        self._brand.setObjectName("brandTitle")
        self._page_title = self._brand
        self._subtitle = QLabel("多机位采集与重建")
        self._subtitle.setObjectName("captionLabel")
        self._subtitle.setWordWrap(True)
        brand_layout.addWidget(self._brand)
        brand_layout.addWidget(self._subtitle)
        top_layout.addLayout(brand_layout)
        top_layout.addSpacing(32)
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
            ("数据传输与接收", "activity", "选择拍摄任务、上传照片并查看进度"),
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
            if index == 5:
                self._model_nav_button = button
            nav_layout.addWidget(button)
            if index == 0:
                button.setChecked(True)
        top_layout.addLayout(nav_layout)
        top_layout.addStretch()
        self._navigation_resources = ResourceStatusWidget()
        top_layout.addWidget(self._navigation_resources)
        root_layout.addWidget(self._top_navigation)

        self._side_panel = QFrame()
        self._side_panel.setObjectName("contextPanel")
        self._side_panel.setMinimumWidth(248)
        self._side_panel.setMaximumWidth(300)
        self._side_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        side_layout = QVBoxLayout(self._side_panel)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)

        self._panel_stack = QStackedWidget()
        self._panel_stack.setObjectName("sidePanelStack")
        # Let narrow sidebars shrink horizontally, but preserve the current
        # page's natural height so the scroll area can scroll instead of
        # compressing status rows below their readable size.
        self._panel_stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self._panel_scroll = QScrollArea()
        self._panel_scroll.setObjectName("sidePanelScroll")
        self._panel_scroll.setWidgetResizable(True)
        self._panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._panel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._panel_scroll.setAlignment(Qt.AlignTop | Qt.AlignLeft)
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
        self._grid_mode_btn = QPushButton()
        self._grid_mode_btn.setObjectName("toolbarButton")
        self._grid_mode_btn.setIcon(QIcon(icon_path("grid")))
        self._grid_mode_btn.setToolTip("网格视图")
        self._grid_mode_btn.setCheckable(True)
        self._grid_mode_btn.setChecked(True)
        self._layout_combo = combo_box()
        self._layout_combo.addItem("布局：2×2")
        self._layout_combo.setFixedWidth(144)
        self._layout_combo.setAccessibleName("视频墙布局")
        self._fullscreen_btn = QPushButton("全屏")
        self._fullscreen_btn.setObjectName("toolbarButton")
        self._fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        self._fullscreen_restore_maximized = False
        self._escape_fullscreen_shortcut = QShortcut(
            QKeySequence(Qt.Key_Escape),
            self,
        )
        self._escape_fullscreen_shortcut.setContext(Qt.ApplicationShortcut)
        self._escape_fullscreen_shortcut.activated.connect(
            self._exit_fullscreen
        )
        content_header.addWidget(self._grid_mode_btn)
        content_header.addWidget(self._layout_combo)
        content_header.addWidget(self._fullscreen_btn)
        content_column.addLayout(content_header)

        self._grid_widget = QWidget()
        self._grid_widget.setObjectName("videoWall")
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(12)
        content_column.addWidget(self._grid_widget, stretch=1)

        overview_page = self._create_panel_page()
        overview_layout = overview_page.layout()
        overview_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._status_label = QLabel("系统就绪")
        self._device_value = QLabel("0 路摄像头")
        self._alignment_label = QLabel("--")
        self._recording_value = QLabel("未录制")
        system_card, system_body = self._dashboard_card("系统状态", "实时")
        system_card.setMaximumHeight(210)
        for icon, name, value in (
            ("camera", "采集设备", self._device_value),
            ("activity", "传输状态", self._status_label),
            ("activity", "系统同步", self._alignment_label),
            ("record", "录制状态", self._recording_value),
        ):
            system_body.addWidget(self._status_row(icon, name, value))
        overview_layout.addWidget(system_card, stretch=1)

        self._inference_label = QLabel("AI: --")
        self._inference_label.setObjectName("overviewStatus")
        self._inference_label.setWordWrap(True)
        self._inference_label.setVisible(False)
        self._ai_latency_value = QLabel("--")
        self._ai_target_value = QLabel("--/--")
        ai_card, ai_body = self._dashboard_card("AI 检测", "YOLO TensorRT · 待机")
        ai_card.setMaximumHeight(140)
        self._ai_backend_label = ai_card.findChild(QLabel, "cardKicker")
        ai_body.addWidget(self._inference_label)
        ai_body.addStretch(1)
        ai_metrics = QHBoxLayout()
        ai_metrics.setSpacing(16)
        ai_metrics.addWidget(self._metric_block(self._ai_latency_value, "ms", "推理延迟"), stretch=1)
        ai_metrics.addWidget(self._metric_block(self._ai_target_value, "", "检测目标"), stretch=1)
        ai_body.addLayout(ai_metrics)
        ai_body.addStretch(1)
        overview_layout.addWidget(ai_card, stretch=1)

        self._data_transmit_value = QLabel("等待上位机")
        self._data_receive_value = QLabel("等待 3DGS 文件")
        data_card, data_body = self._dashboard_card("数据链路", "实时")
        data_card.setMaximumHeight(140)
        data_body.addWidget(self._status_row("activity", "数据传输", self._data_transmit_value))
        data_body.addWidget(self._status_row("cube", "3DGS 接收", self._data_receive_value))
        overview_layout.addWidget(data_card, stretch=1)
        if self._capture_only:
            data_card.hide()

        self._quality_label = QLabel("质量: --")
        self._quality_label.setObjectName("overviewStatus")
        self._quality_label.setVisible(False)
        self._quality_counts = {
            "good": QLabel("0 路 (0%)"),
            "warn": QLabel("0 路 (0%)"),
            "bad": QLabel("0 路 (0%)"),
        }
        quality_card, quality_body = self._dashboard_card("质量监测", "实时分析")
        quality_card.setMaximumHeight(160)
        quality_body.addWidget(self._quality_label)
        for level, name in (("good", "良好"), ("warn", "警告"), ("bad", "严重")):
            quality_body.addWidget(self._quality_row(level, name, self._quality_counts[level]))
        overview_layout.addWidget(quality_card, stretch=1)

        alert_card, alert_body = self._dashboard_card("告警信息", "实时")
        alert_card.setMaximumHeight(160)
        alert_body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._alert_rows = []
        for index in range(3):
            row, dot, message, timestamp = self._alert_row(alert_card)
            if index == 0:
                message.setText("暂无告警")
                dot.setProperty("level", "good")
                timestamp.setText("--:--:--")
            self._alert_rows.append((row, dot, message, timestamp))
            alert_body.addWidget(row)
            row.setVisible(index == 0)
        overview_layout.addWidget(alert_card, stretch=1)
        self._panel_stack.addWidget(overview_page)

        record_page = self._create_panel_page()
        control_layout = record_page.layout()

        # Destination row (above action controls)
        dest_title = QLabel("录制采集")
        dest_title.setObjectName("sideSectionTitle")
        control_layout.addWidget(dest_title)

        self._extrinsic_cb = check_box("外参标定")
        control_layout.addWidget(self._extrinsic_cb)

        self._name_label = QLabel("物体名称:")
        self._name_label.setObjectName("captionLabel")
        control_layout.addWidget(self._name_label)

        self._name_input = line_edit("")
        self._name_input.setPlaceholderText("例如：杯子")
        self._name_input.setValidator(
            QRegularExpressionValidator(r"[A-Za-z0-9][A-Za-z0-9._-]*", self._name_input)
        )
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
        self._upload_staged_btn = push_button("检查并上传")
        self._stop_btn = push_button("停止")
        self._stop_btn.setEnabled(False)
        set_variant(self._record_btn, "record")
        set_variant(self._photo_btn, "primary")
        set_variant(self._upload_staged_btn, "ghost")
        set_variant(self._stop_btn, "ghost")

        self._record_btn.clicked.connect(self._on_record_clicked)
        self._photo_btn.clicked.connect(self.photo_requested.emit)
        self._upload_staged_btn.clicked.connect(self.upload_staged_tasks_requested.emit)
        self._stop_btn.clicked.connect(self.stop_requested.emit)

        action_label = QLabel("采集操作")
        action_label.setObjectName("sideLabel")
        control_layout.addSpacing(8)
        control_layout.addWidget(action_label)
        control_layout.addWidget(self._record_btn)
        control_layout.addWidget(self._photo_btn)
        control_layout.addWidget(self._upload_staged_btn)
        if self._capture_only:
            self._upload_staged_btn.hide()
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

        self._guide_progress_label = QLabel("八角度采集进度")
        self._guide_progress_label.setObjectName("sideLabel")
        guide_layout.addWidget(self._guide_progress_label)
        self._guide_progress = QProgressBar()
        self._guide_progress.setObjectName("captureProgress")
        self._guide_progress.setRange(0, 100)
        self._guide_progress.setValue(0)
        self._guide_progress.setFormat("0 / 8")
        self._guide_progress.setAccessibleName("八角度采集进度")
        guide_layout.addWidget(self._guide_progress)

        angle_steps = QWidget()
        angle_steps.setObjectName("angleSteps")
        angle_steps_layout = QGridLayout(angle_steps)
        angle_steps_layout.setContentsMargins(0, 2, 0, 6)
        angle_steps_layout.setHorizontalSpacing(5)
        angle_steps_layout.setVerticalSpacing(5)
        self._guide_angle_steps = {}
        for index, angle in enumerate(range(0, 360, 45)):
            step = QLabel(f"{angle}°")
            step.setObjectName("angleStep")
            step.setProperty("state", "pending")
            step.setAlignment(Qt.AlignmentFlag.AlignCenter)
            step.setToolTip(f"{angle}° 尚未采集")
            angle_steps_layout.addWidget(step, index // 4, index % 4)
            self._guide_angle_steps[angle] = step
        guide_layout.addWidget(angle_steps)

        self._guide_now_label = QLabel("当前画质: --")
        self._guide_next_label = QLabel("建议下一角度: 0°")
        self._guide_done_label = QLabel("已完成 0 / 8")
        self._guide_warning_label = QLabel("")
        for label in (
            self._guide_now_label,
            self._guide_next_label,
            self._guide_done_label,
            self._guide_warning_label,
        ):
            label.setObjectName("captionLabel")
            label.setWordWrap(True)
            guide_layout.addWidget(label)
        self._guide_done_label.setProperty("status", "muted")
        self._guide_warning_label.setProperty("status", "warn")
        guide_layout.addStretch()
        self._panel_stack.addWidget(guide_page)

        settings_page = self._create_panel_page()
        settings_layout = settings_page.layout()
        settings_title = QLabel("系统设置")
        settings_title.setObjectName("sideSectionTitle")
        settings_layout.addWidget(settings_title)

        settings_hint = QLabel("工作站级参数·按生效范围分组")
        settings_hint.setObjectName("captionLabel")
        settings_hint.setWordWrap(True)
        settings_layout.addWidget(settings_hint)

        preview_group, preview_layout = self._create_settings_group("预览与显示", "即时生效")
        settings_layout.addWidget(preview_group)
        self._fps_combo = combo_box()
        self._fps_combo.addItems(["15 fps", "30 fps", "60 fps"])
        self._fps_combo.setCurrentText("15 fps")
        self._fps_combo.currentTextChanged.connect(self._on_fps_changed)
        self._add_setting_row(preview_layout, "画面刷新率", "视频墙的 UI 更新频率", self._fps_combo)
        self._mirror_cb = check_box("水平镜像预览")
        self._mirror_cb.setObjectName("settingToggle")
        self._mirror_cb.toggled.connect(self.mirror_toggled.emit)
        self._add_setting_row(preview_layout, "预览镜像", "仅改变显示方向", self._mirror_cb)

        recording_group, recording_layout = self._create_settings_group("录制与编码", "下次录制")
        settings_layout.addWidget(recording_group)
        self._recording_backend_combo = combo_box()
        self._recording_backend_combo.addItem("PyAV（通用）", "pyav")
        self._recording_backend_combo.addItem("GStreamer（Jetson）", "gstreamer")
        self._add_setting_row(recording_layout, "录制后端", "选择视频写入管线", self._recording_backend_combo)
        self._codec_combo = combo_box()
        self._codec_combo.addItems(["h264", "hevc"])
        self._add_setting_row(recording_layout, "编码格式", "H.264 兼容性更好", self._codec_combo)
        self._recording_fps = NumericStepper()
        self._recording_fps.setRange(1, 120)
        self._recording_fps.setSuffix(" fps")
        self._add_setting_row(recording_layout, "录制帧率", "输出视频时基", self._recording_fps)
        self._bitrate_mbps = NumericStepper(decimals=1)
        self._bitrate_mbps.setRange(0.5, 100.0)
        self._bitrate_mbps.setDecimals(1)
        self._bitrate_mbps.setSuffix(" Mbps")
        self._add_setting_row(recording_layout, "目标码率", "越高越清晰，文件也越大", self._bitrate_mbps)
        self._maxperf_cb = check_box("启用 Jetson 编码器高性能模式")
        self._maxperf_cb.setObjectName("settingToggle")
        self._add_setting_row(recording_layout, "性能模式", "优先保证多路编码稳定性", self._maxperf_cb)
        self._insert_sps_pps_cb = check_box("定期写入 SPS / PPS")
        self._insert_sps_pps_cb.setObjectName("settingToggle")
        self._add_setting_row(recording_layout, "流恢复", "便于中途接入和损坏恢复", self._insert_sps_pps_cb)

        inference_group, inference_layout = self._create_settings_group("AI 推理", "重启生效")
        settings_layout.addWidget(inference_group)
        self._inference_backend_combo = combo_box()
        self._inference_backend_combo.addItem("内置质量规则", "heuristic")
        self._inference_backend_combo.addItem("TensorRT（进程内）", "ultralytics_tensorrt")
        self._inference_backend_combo.addItem("TensorRT 独立服务", "subprocess")
        self._add_setting_row(inference_layout, "推理后端", "独立服务更利于隔离显存", self._inference_backend_combo)
        self._inference_interval = NumericStepper()
        self._inference_interval.setRange(20, 5000)
        self._inference_interval.setSingleStep(20)
        self._inference_interval.setSuffix(" ms")
        self._add_setting_row(inference_layout, "检测间隔", "较大数值可降低 GPU 负载", self._inference_interval)
        self._confidence = NumericStepper(decimals=1)
        self._confidence.setRange(1.0, 99.0)
        self._confidence.setSuffix(" %")
        self._confidence.setDecimals(0)
        self._add_setting_row(inference_layout, "置信度阈值", "过滤低置信度检测", self._confidence)
        self._input_size = NumericStepper()
        self._input_size.setRange(160, 2048)
        self._input_size.setSingleStep(32)
        self._input_size.setSuffix(" px")
        self._add_setting_row(inference_layout, "模型输入尺寸", "正方形推理分辨率", self._input_size)
        self._device_edit = line_edit()
        self._device_edit.setPlaceholderText("cuda:0")
        self._add_setting_row(inference_layout, "计算设备", "例如 cuda:0 或 0", self._device_edit)
        self._engine_path_edit = line_edit()
        self._engine_path_edit.setPlaceholderText("未指定 TensorRT engine")
        self._add_setting_row(inference_layout, "Engine 路径", "TensorRT .engine 模型文件", self._engine_path_edit)

        self._save_settings_btn = push_button("保存系统设置", primary=True)
        set_variant(self._save_settings_btn, "primary")
        self._save_settings_btn.clicked.connect(self._emit_settings_save)
        settings_layout.addWidget(self._save_settings_btn)
        self._settings_status = QLabel("")
        self._settings_status.setObjectName("captionLabel")
        self._settings_status.setWordWrap(True)
        settings_layout.addWidget(self._settings_status)
        settings_layout.addStretch()
        self._panel_stack.addWidget(settings_page)

        transfer_page = self._create_panel_page()
        transfer_layout = transfer_page.layout()
        transfer_title = QLabel("数据传输与接收")
        transfer_title.setObjectName("sideSectionTitle")
        transfer_layout.addWidget(transfer_title)
        transfer_hint = QLabel("选择一轮完整的8角度拍摄目录，然后上传至 WSL。")
        transfer_hint.setObjectName("captionLabel")
        transfer_hint.setWordWrap(True)
        transfer_layout.addWidget(transfer_hint)
        self._transfer_select_btn = push_button("选择照片文件夹")
        self._transfer_upload_btn = push_button("开始上传", primary=True)
        self._transfer_upload_btn.setEnabled(False)
        transfer_layout.addWidget(self._transfer_select_btn)
        transfer_layout.addWidget(self._transfer_upload_btn)
        transfer_layout.addStretch()
        self._panel_stack.addWidget(transfer_page)

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

        self._content_stack = QStackedWidget()
        video_page = QWidget()
        video_page.setLayout(content_column)
        self._content_stack.addWidget(video_page)
        transfer_content = QWidget()
        transfer_content.setObjectName("transferWorkspace")
        transfer_content_layout = QVBoxLayout(transfer_content)
        transfer_content_layout.setContentsMargins(28, 24, 28, 24)
        transfer_content_layout.setSpacing(16)
        transfer_heading = QLabel("数据传输工作台")
        transfer_heading.setObjectName("sectionTitle")
        transfer_content_layout.addWidget(transfer_heading)
        transfer_description = QLabel("选择照片任务、确认内容并上传；服务端响应、保存位置和异常会保留在本页。")
        transfer_description.setObjectName("captionLabel")
        transfer_description.setWordWrap(True)
        transfer_content_layout.addWidget(transfer_description)
        workspace_grid = QGridLayout()
        workspace_grid.setHorizontalSpacing(16)
        workspace_grid.setVerticalSpacing(16)

        transfer_card, transfer_card_body = self._dashboard_card(
            "① 待发送任务",
            "本机照片",
            object_name="transferCard",
        )
        self._transfer_object_label = QLabel("尚未选择任务")
        self._transfer_object_label.setObjectName("sectionTitle")
        transfer_card_body.addWidget(self._transfer_object_label)
        self._transfer_photo_count = QLabel("照片数量：--")
        self._transfer_photo_count.setObjectName("captionLabel")
        transfer_card_body.addWidget(self._transfer_photo_count)
        self._transfer_folder_label = QLabel("请选择 captures 下的物体文件夹")
        self._transfer_folder_label.setObjectName("destinationPath")
        self._transfer_folder_label.setWordWrap(True)
        transfer_card_body.addWidget(self._transfer_folder_label)
        workspace_grid.addWidget(transfer_card, 0, 0)

        progress_card, progress_body = self._dashboard_card(
            "② 传输进度",
            "实时状态",
            object_name="transferCard",
        )
        self._transfer_progress = QProgressBar()
        self._transfer_progress.setRange(0, 100)
        self._transfer_progress.setValue(0)
        self._transfer_progress.setFormat("等待开始")
        self._transfer_progress.setAccessibleName("照片上传进度")
        progress_body.addWidget(self._transfer_progress)
        self._transfer_status_label = QLabel("等待选择照片任务")
        self._transfer_status_label.setObjectName("statusPill")
        self._transfer_status_label.setWordWrap(True)
        progress_body.addWidget(self._transfer_status_label)
        self._transfer_stage_label = QLabel(
            "○ 校验照片   ○ 上传 WSL   ○ 等待训练   ○ 下载模型   ○ 完整校验"
        )
        self._transfer_stage_label.setObjectName("captionLabel")
        self._transfer_stage_label.setWordWrap(True)
        progress_body.addWidget(self._transfer_stage_label)
        workspace_grid.addWidget(progress_card, 0, 1)

        result_card, result_body = self._dashboard_card(
            "③ 上位机保存位置",
            "上传后显示",
            object_name="transferCard",
        )
        self._transfer_result_name = QLabel("等待上传")
        self._transfer_result_name.setObjectName("sectionTitle")
        result_body.addWidget(self._transfer_result_name)
        self._transfer_remote_path = QLabel("WSL 路径将在服务端确认接收后显示")
        self._transfer_remote_path.setObjectName("destinationPath")
        self._transfer_remote_path.setWordWrap(True)
        result_body.addWidget(self._transfer_remote_path)
        self._copy_remote_path_btn = push_button("复制 WSL 路径")
        self._copy_remote_path_btn.setEnabled(False)
        result_body.addWidget(self._copy_remote_path_btn)
        self._transfer_technical_id = QLabel("内部任务编号：--")
        self._transfer_technical_id.setObjectName("captionLabel")
        self._transfer_technical_id.setWordWrap(True)
        result_body.addWidget(self._transfer_technical_id)
        self._transfer_local_model = QLabel("Jetson 模型：等待接收")
        self._transfer_local_model.setObjectName("destinationPath")
        self._transfer_local_model.setWordWrap(True)
        result_body.addWidget(self._transfer_local_model)
        workspace_grid.addWidget(result_card, 1, 0)

        log_card, log_body = self._dashboard_card(
            "运行日志与成功依据",
            "可追溯",
            object_name="transferCard",
        )
        self._transfer_log = QTextEdit()
        self._transfer_log.setObjectName("transferLog")
        self._transfer_log.setReadOnly(True)
        self._transfer_log.setMinimumHeight(190)
        self._transfer_log.setPlaceholderText("选择任务后，这里会显示校验、HTTP 响应和上传结果。")
        self._transfer_log.setAccessibleName("数据传输运行日志")
        log_body.addWidget(self._transfer_log)
        workspace_grid.addWidget(log_card, 1, 1)
        workspace_grid.setColumnStretch(0, 1)
        workspace_grid.setColumnStretch(1, 1)
        transfer_content_layout.addLayout(workspace_grid, stretch=1)
        self._content_stack.addWidget(transfer_content)
        if self._capture_only:
            self._model_view = QWidget()
        else:
            from multiwebcam.ui.views.gaussian_model_view import GaussianModelView

            self._model_view = GaussianModelView()
            self._model_view.model_loaded.connect(self._on_3dgs_model_loaded)
            self._model_view.load_failed.connect(self._on_3dgs_model_failed)
        self._content_stack.addWidget(self._model_view)

        self._system_status = SystemStatusBar()
        self._system_status.setParent(self)
        self._system_status.hide()
        self._system_status.gpu_percent_changed.connect(self._navigation_resources.set_gpu_percent)
        self._system_status.refresh_gpu()
        self._system_status.set_camera_count(0)
        self._system_status.set_capture_paused(False)
        self._bottom_status = BottomStatusBar(
            enable_network_checks=not self._capture_only
        )
        content_region = QVBoxLayout()
        content_region.setContentsMargins(0, 0, 0, 0)
        content_region.setSpacing(0)
        content_region.addWidget(self._content_stack, stretch=1)

        body_layout = QHBoxLayout()
        body_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        body_layout.setContentsMargins(16, 12, 16, 12)
        body_layout.setSpacing(16)
        body_layout.addWidget(self._side_panel)
        body_layout.addLayout(content_region, stretch=1)

        root_layout.addLayout(body_layout, stretch=1)
        root_layout.addWidget(self._bottom_status)

        # Wire destination controls
        self._extrinsic_cb.toggled.connect(self._on_extrinsic_toggled)
        self._name_input.textChanged.connect(self._update_dest_summary)
        self._open_folder_btn.clicked.connect(self.open_folder_requested.emit)
        self._select_model_btn.clicked.connect(self.model_file_requested.emit)
        self._load_cameras_btn.clicked.connect(self.load_cameras_requested.emit)
        self._pause_video_btn.clicked.connect(self.pause_video_requested.emit)
        self._transfer_select_btn.clicked.connect(self.transfer_folder_requested.emit)
        self._transfer_upload_btn.clicked.connect(
            lambda: self.transfer_upload_requested.emit(self._transfer_folder_label.property("folderPath") or "")
        )
        self._copy_remote_path_btn.clicked.connect(self._copy_transfer_remote_path)

        if self._capture_only:
            for index in (4, 5):
                self._nav_buttons[index].hide()

        self._update_dest_summary()
        QTimer.singleShot(0, lambda: self._panel_scroll.verticalScrollBar().setValue(0))

    def _select_workspace(self, index: int) -> None:
        if self._capture_only and index >= 4:
            return
        self._panel_stack.setCurrentIndex(index)
        content_index = 1 if index == 4 else 2 if index == 5 else 0
        self._content_stack.setCurrentIndex(content_index)
        set_active = getattr(self._model_view, "set_active", None)
        if callable(set_active):
            set_active(index == 5)
        self.workspace_changed.emit(index)

    def set_transfer_folder(self, path: Path) -> None:
        path = Path(path)
        self._transfer_log.clear()
        images_dir = path / "images" if (path / "images").is_dir() else path
        photo_count = len([item for item in images_dir.iterdir() if item.is_file() and item.suffix.lower() in {".jpg", ".jpeg"}])
        self._transfer_object_label.setText(path.name)
        self._transfer_photo_count.setText(f"照片数量：{photo_count} 张")
        self._transfer_folder_label.setText(str(path))
        self._transfer_folder_label.setProperty("folderPath", str(path))
        self._transfer_upload_btn.setEnabled(True)
        self._transfer_result_name.setText("等待上传")
        self._transfer_remote_path.setText("WSL 路径将在服务端确认接收后显示")
        self._transfer_remote_path.setProperty("remotePath", "")
        self._copy_remote_path_btn.setEnabled(False)
        self._transfer_technical_id.setText("内部任务编号：--")
        self._transfer_local_model.setText("Jetson 模型：等待接收")
        self.set_transfer_progress(0, "文件夹已选择，等待上传")
        self.append_transfer_log(f"已选择任务：{path.name}")
        self.append_transfer_log(f"本地目录：{path}")
        self.append_transfer_log(f"检测到 JPEG：{photo_count} 张")

    def set_transfer_progress(self, percent: int, message: str) -> None:
        percent = max(0, min(100, int(percent)))
        self._transfer_progress.setValue(percent)
        self._transfer_progress.setFormat(f"{percent}%")
        self._transfer_status_label.setText(message)
        if percent < 10:
            stages = "● 校验照片   ○ 上传 WSL   ○ 等待训练   ○ 下载模型   ○ 完整校验"
        elif percent < 40:
            stages = "● 校验照片   ● 上传 WSL   ○ 等待训练   ○ 下载模型   ○ 完整校验"
        elif percent < 78:
            stages = "● 校验照片   ● 上传 WSL   ● 等待训练   ○ 下载模型   ○ 完整校验"
        elif percent < 99:
            stages = "● 校验照片   ● 上传 WSL   ● 等待训练   ● 下载模型   ○ 完整校验"
        else:
            stages = "● 校验照片   ● 上传 WSL   ● 等待训练   ● 下载模型   ● 完整校验"
        self._transfer_stage_label.setText(stages)

    def set_transfer_busy(self, busy: bool) -> None:
        self._transfer_select_btn.setEnabled(not busy)
        has_folder = bool(self._transfer_folder_label.property("folderPath"))
        self._transfer_upload_btn.setEnabled(not busy and has_folder)
        self._transfer_upload_btn.setText("正在上传..." if busy else "开始上传")

    def append_transfer_log(self, message: str) -> None:
        timestamp = QTime.currentTime().toString("HH:mm:ss")
        self._transfer_log.append(f"[{timestamp}] {message}")

    def set_transfer_result(self, object_name: str, remote_path: str, technical_id: str) -> None:
        self._transfer_result_name.setText(f"{object_name} 已上传")
        self._transfer_remote_path.setText(remote_path)
        self._transfer_remote_path.setProperty("remotePath", remote_path)
        self._copy_remote_path_btn.setEnabled(True)
        self._transfer_technical_id.setText(f"内部任务编号（排障用）：{technical_id}")

    def set_transfer_download_result(self, final_path: Path) -> None:
        self._transfer_local_model.setText(f"Jetson 模型：{final_path}")
        self.append_transfer_log(f"完整模型已保存到 Jetson：{final_path}")

    def _copy_transfer_remote_path(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self._transfer_remote_path.property("remotePath") or "")
        self.append_transfer_log("已复制 WSL 保存路径")

    def _toggle_fullscreen(self) -> None:
        window = self.window()
        self._set_fullscreen(not window.isFullScreen())

    def _set_fullscreen(self, enabled: bool) -> None:
        window = self.window()
        if enabled:
            self._fullscreen_restore_maximized = window.isMaximized()
            window.showFullScreen()
            self._fullscreen_btn.setText("退出全屏")
            return
        if self._fullscreen_restore_maximized:
            window.showMaximized()
        else:
            window.showNormal()
        self._fullscreen_btn.setText("全屏")

    def _exit_fullscreen(self) -> None:
        if self.window().isFullScreen():
            self._set_fullscreen(False)

    def load_model(self, path: str) -> None:
        if self._capture_only:
            return
        self._model_status_label.setText("正在加载模型...")
        self._data_receive_value.setText("正在接收模型...")
        self._model_view.load_model(Path(path))

    def _on_3dgs_model_loaded(self, name: str) -> None:
        self._model_status_label.setText(f"已加载: {name}")
        self._data_receive_value.setText(f"已接收: {name}")

    def _on_3dgs_model_failed(self, error: str) -> None:
        self._model_status_label.setText(f"加载失败: {error}")
        self._data_receive_value.setText("接收文件异常")

    def set_data_link_status(self, transmit: str | None = None, receive: str | None = None) -> None:
        """Update upstream transfer and reconstructed-model receive states."""
        if transmit is not None:
            self._data_transmit_value.setText(transmit)
        if receive is not None:
            self._data_receive_value.setText(receive)

    def set_staging_upload_busy(self, busy: bool) -> None:
        """Keep the staging action available and visibly acknowledge long work."""
        self._upload_staged_btn.setEnabled(not busy)
        self._upload_staged_btn.setText("检查上传中..." if busy else "检查并上传")

    def shutdown(self) -> None:
        """Release child workers before the view is removed from the stack."""
        self._system_status.shutdown()
        self._bottom_status.shutdown()
        shutdown = getattr(self._model_view, "shutdown", None)
        if callable(shutdown):
            shutdown()

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)

    def set_video_paused(self, paused: bool, message: str = "") -> None:
        self._pause_video_btn.setText("继续视频传输" if paused else "暂停视频传输")
        self._pause_video_btn.setProperty("paused", paused)
        self._system_status.set_capture_paused(paused)
        if message:
            self._status_label.setText(message)
            self._bottom_status.set_runtime(message, "warn" if paused else "good")

    def set_camera_load_busy(self, busy: bool) -> None:
        """Prevent duplicate load requests while V4L2 work runs in a worker."""
        self._load_cameras_btn.setEnabled(not busy)
        self._pause_video_btn.setEnabled(not busy)
        self._load_cameras_btn.setText("连接中..." if busy else "加载摄像头")

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Simplify secondary content and reflow previews on narrow windows."""
        super().resizeEvent(event)
        compact = event.size().width() < 900
        narrow = event.size().width() < 720
        self._side_panel.setFixedWidth(224 if narrow else (260 if compact else 288))
        self._brand.setVisible(not narrow)
        self._subtitle.setVisible(not compact)
        self._wall_hint.setVisible(not compact)
        self._navigation_resources.setVisible(not compact)
        self._panel_scroll.setVisible(True)
        self._panel_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if event.size().height() < 760
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        for button in self._nav_buttons:
            button.setText("" if narrow else button.property("fullText"))
        self._system_status.set_compact(compact)
        self._bottom_status.set_compact(compact)
        self._relayout_tiles()
        # The child video wall receives its final width after this event;
        # reflow once more with the settled geometry.
        QTimer.singleShot(0, self._relayout_tiles)

    def _dashboard_card(
        self,
        title: str,
        kicker: str,
        object_name: str = "dashboardCard",
    ) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName(object_name)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        kicker_label = QLabel(kicker)
        kicker_label.setObjectName("cardKicker")
        header.addWidget(title_label)
        header.addStretch()
        header.addWidget(kicker_label)
        layout.addLayout(header)
        return card, layout

    def _status_row(self, icon_name: str, name: str, value: QLabel) -> QFrame:
        row = QFrame()
        row.setObjectName("statusRow")
        row.setMinimumHeight(34)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)
        icon = QLabel()
        icon.setObjectName("rowIcon")
        icon.setPixmap(QPixmap(icon_path(icon_name)).scaled(15, 15, Qt.AspectRatioMode.KeepAspectRatio,
                                                        Qt.TransformationMode.SmoothTransformation))
        label = QLabel(name)
        label.setObjectName("rowName")
        value.setObjectName("rowValue")
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(icon)
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(value)
        return row

    def _metric_block(self, value: QLabel, unit: str, caption: str) -> QWidget:
        block = QWidget()
        layout = QVBoxLayout(block)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(0)
        value_row = QHBoxLayout()
        value.setObjectName("metricValue")
        value_row.addStretch()
        value_row.addWidget(value)
        if unit:
            unit_label = QLabel(unit)
            unit_label.setObjectName("metricUnit")
            value_row.addWidget(unit_label)
        value_row.addStretch()
        caption_label = QLabel(caption)
        caption_label.setObjectName("metricCaption")
        caption_label.setAlignment(Qt.AlignCenter)
        layout.addLayout(value_row)
        layout.addWidget(caption_label)
        return block

    def _quality_row(self, level: str, name: str, value: QLabel) -> QFrame:
        row = QFrame()
        row.setObjectName("statusRow")
        row.setMinimumHeight(30)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(2, 1, 2, 1)
        dot = QLabel("●")
        dot.setObjectName("qualityDot")
        dot.setProperty("level", level)
        label = QLabel(name)
        label.setObjectName("rowName")
        value.setObjectName("rowValue")
        layout.addWidget(dot)
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(value)
        return row

    def _alert_row(self, parent: QWidget) -> tuple[QFrame, QLabel, QLabel, QLabel]:
        row = QFrame(parent)
        row.setObjectName("statusRow")
        row.setFixedHeight(34)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)
        dot = QLabel("●", row)
        dot.setObjectName("qualityDot")
        message = QLabel(row)
        message.setObjectName("alertText")
        message.setTextFormat(Qt.TextFormat.PlainText)
        message.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        timestamp = QLabel(row)
        timestamp.setObjectName("alertTime")
        layout.addWidget(dot)
        layout.addWidget(message, stretch=1)
        layout.addWidget(timestamp)
        return row, dot, message, timestamp

    def _update_alert_rows(self, alerts: list[tuple[str, str]]) -> None:
        visible_alerts = alerts[: len(self._alert_rows)]
        if not visible_alerts:
            visible_alerts = [("good", "暂无告警")]
        timestamp_text = QTime.currentTime().toString("HH:mm:ss")
        for index, (row, dot, message, timestamp) in enumerate(self._alert_rows):
            visible = index < len(visible_alerts)
            row.setVisible(visible)
            if not visible:
                continue
            level, text = visible_alerts[index]
            dot.setProperty("level", level)
            message.setProperty("level", level)
            message.setText(text)
            timestamp.setText("" if text.startswith("检测到") else timestamp_text)
            for widget in (dot, message):
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    def _refresh_alerts(self) -> None:
        """Merge connectivity and image-quality alerts into one ordered list."""
        alerts: list[tuple[str, str]] = []
        disconnected = len(self._errored_source_ids)
        if disconnected:
            level = "bad" if disconnected == len(self._tiles) else "warn"
            alerts.append(
                (level, f"检测到 {disconnected} 路断连，请检查或重新加载")
            )
        alerts.extend(self._quality_alerts)
        self._update_alert_rows(alerts)

    def _create_panel_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("sidePanelPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        return page

    def _create_settings_group(self, title: str, scope: str) -> tuple[QFrame, QVBoxLayout]:
        group = QFrame()
        group.setObjectName("settingsGroup")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 11, 12, 12)
        layout.setSpacing(9)
        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("settingsGroupTitle")
        scope_label = QLabel(scope)
        scope_label.setObjectName("settingsScope")
        header.addWidget(title_label)
        header.addStretch()
        header.addWidget(scope_label)
        layout.addLayout(header)
        return group, layout

    def _add_setting_row(self, layout: QVBoxLayout, title: str, hint: str, control: QWidget) -> None:
        row = QFrame()
        row.setObjectName("settingsRow")
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(9, 7, 7, 8)
        row_layout.setSpacing(3)
        label = QLabel(title)
        label.setObjectName("settingsLabel")
        description = QLabel(hint)
        description.setObjectName("settingsHint")
        description.setWordWrap(True)
        row_layout.addWidget(label)
        row_layout.addWidget(description)
        row_layout.addWidget(control)
        layout.addWidget(row)

    def set_app_settings(self, settings: AppSettings) -> None:
        """Populate persistent project settings without changing runtime preview state."""
        self._app_settings = settings
        recording = settings.recording
        inference = settings.inference
        self._set_combo_data(self._recording_backend_combo, recording.backend)
        self._codec_combo.setCurrentText(recording.codec)
        self._recording_fps.setValue(recording.fps)
        self._bitrate_mbps.setValue(recording.bitrate / 1_000_000)
        self._maxperf_cb.setChecked(recording.maxperf_enable)
        self._insert_sps_pps_cb.setChecked(recording.insert_sps_pps)
        self._set_combo_data(self._inference_backend_combo, inference.backend)
        self._inference_interval.setValue(inference.interval_ms)
        self._confidence.setValue(inference.confidence_threshold * 100)
        self._input_size.setValue(inference.input_size[0])
        self._device_edit.setText(str(inference.device))
        self._engine_path_edit.setText(inference.engine_path or "")

    @staticmethod
    def _set_combo_data(combo, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _emit_settings_save(self) -> None:
        device_text = self._device_edit.text().strip() or "0"
        device: int | str = int(device_text) if device_text.isdigit() else device_text
        size = self._input_size.value()
        settings = AppSettings(
            recording=replace(
                self._app_settings.recording,
                backend=self._recording_backend_combo.currentData(),
                codec=self._codec_combo.currentText(),
                fps=self._recording_fps.value(),
                bitrate=int(self._bitrate_mbps.value() * 1_000_000),
                insert_sps_pps=self._insert_sps_pps_cb.isChecked(),
                maxperf_enable=self._maxperf_cb.isChecked(),
            ),
            inference=replace(
                self._app_settings.inference,
                backend=self._inference_backend_combo.currentData(),
                engine_path=self._engine_path_edit.text().strip() or None,
                device=device,
                input_size=(size, size),
                confidence_threshold=self._confidence.value() / 100,
                interval_ms=self._inference_interval.value(),
            ),
        )
        self._app_settings = settings
        self.settings_save_requested.emit(settings)

    def show_settings_saved(self) -> None:
        self._settings_status.setText("已保存·录制参数下次录制生效，AI 参数重启后生效")
        self._settings_status.setProperty("status", "good")
        self._settings_status.style().unpolish(self._settings_status)
        self._settings_status.style().polish(self._settings_status)

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
        self._device_value.setText(f"{max(0, connected)} 路摄像头")
        self._refresh_alerts()

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

    def capture_object_name(self) -> str:
        """Return the object name entered for still-image capture."""
        return self._name_input.text()

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
        active_stats = [stat.measured_fps for source_id, stat in stats.items() if source_id in self._tiles]
        if active_stats:
            self._bottom_status.set_framerate(sum(active_stats) / len(active_stats))

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
        counts = {"good": 0, "warn": 0, "bad": 0}
        for quality in qualities.values():
            level = getattr(getattr(quality, "level", None), "value", "")
            if level in counts:
                counts[level] += 1
        total = max(1, sum(counts.values()))
        for level, count in counts.items():
            self._quality_counts[level].setText(f"{count} 路 ({count / total * 100:.0f}%)")
        alerts = []
        for source_id, quality in qualities.items():
            level = getattr(getattr(quality, "level", None), "value", "")
            if level not in {"warn", "bad"}:
                continue
            tile = self._tiles.get(source_id)
            camera_number = tile.display_index if tile is not None else source_id + 1
            severity = "质量严重" if level == "bad" else "画质警告"
            alerts.append((level, f"相机 {camera_number} {severity}"))
        self._quality_alerts = alerts
        self._refresh_alerts()

    def update_guidance(self, guidance: object | None) -> None:
        """Update the lower-right capture guidance panel."""
        if guidance is None:
            self._guide_progress.setValue(0)
            self._guide_progress.setFormat("0 / 8")
            self._guide_now_label.setText("当前画质: --")
            self._guide_next_label.setText("建议下一角度: --")
            self._guide_done_label.setText("已完成 0 / 8")
            self._guide_warning_label.setText("")
            self._update_guide_angle_steps((), None)
            _set_pill_status(self._guide_now_label, "muted")
            return

        completed = tuple(guidance.completed_angles)
        if getattr(guidance, "loop_complete", False) and guidance.next_angle_deg is None:
            next_angle = "360° 完成"
        else:
            next_angle = "--" if guidance.next_angle_deg is None else f"{guidance.next_angle_deg}°"
        self._guide_progress.setValue(round(guidance.progress_percent))
        self._guide_progress.setFormat(f"{len(completed)} / 8")
        self._guide_now_label.setText(
            f"当前画质: {guidance.readiness_percent:.0f}% "
            f"{_zh_readiness_label(guidance.readiness_label)}"
        )
        self._guide_next_label.setText(f"建议下一角度: {next_angle}")
        self._guide_done_label.setText(f"已完成 {len(completed)} / 8")
        self._guide_warning_label.setText(_zh_guidance_warning(guidance.warning))
        self._update_guide_angle_steps(completed, guidance.current_angle_deg)

        if guidance.ready_to_capture:
            _set_pill_status(self._guide_now_label, "good")
        elif guidance.readiness_percent >= 60:
            _set_pill_status(self._guide_now_label, "warn")
        else:
            _set_pill_status(self._guide_now_label, "bad")

    def _update_guide_angle_steps(
        self,
        completed_angles: tuple[int, ...],
        current_angle: int | None,
    ) -> None:
        completed = set(completed_angles)
        for angle, step in self._guide_angle_steps.items():
            if angle in completed:
                state = "done"
                tooltip = f"{angle}° 已完成"
            elif angle == current_angle:
                state = "current"
                tooltip = f"{angle}° 当前选择"
            else:
                state = "pending"
                tooltip = f"{angle}° 尚未采集"
            step.setProperty("state", state)
            step.setToolTip(tooltip)
            step.style().unpolish(step)
            step.style().polish(step)

    def update_alignment(self, alignment: AlignmentStats | None) -> None:
        """Update alignment stats in status bar."""
        if alignment:
            self._alignment_label.setText(
                f"{alignment.mean_spread_ms:.1f} ms"
            )
            if alignment.complete_cluster_pct >= 95 and alignment.mean_spread_ms <= 20:
                _set_pill_status(self._alignment_label, "good")
            elif alignment.complete_cluster_pct >= 80:
                _set_pill_status(self._alignment_label, "warn")
            else:
                _set_pill_status(self._alignment_label, "bad")
            self._bottom_status.set_sync(
                alignment.mean_spread_ms,
                alignment.complete_cluster_pct >= 95 and alignment.mean_spread_ms <= 20,
            )

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
            self._ai_latency_value.setText("--")
            self._ai_target_value.setText("0/0")
            self._bottom_status.set_inference("--", active=False)
            self._set_ai_card_state("YOLO TensorRT · 未启用", "muted")
            return

        if status.warming:
            self._inference_label.setText(f"AI: {backend} 预热中 | 0/{active}")
            _set_pill_status(self._inference_label, "warn")
            self._system_status.set_inference("AI 预热中", active=True, warning=True)
            self._ai_latency_value.setText("--")
            self._ai_target_value.setText(f"0/{active}")
            self._bottom_status.set_inference("预热中", active=True)
            self._set_ai_card_state(f"{backend} · 预热中", "warn")
            return

        latency_text = "--" if latency is None else f"{float(latency):.0f}ms"
        self._inference_label.setText(f"AI: {backend} | {latency_text} | {detected}/{active}")
        _set_pill_status(self._inference_label, "good" if detected else "muted")
        self._system_status.set_inference(f"AI {latency_text}", active=True)
        self._ai_latency_value.setText("--" if latency is None else f"{float(latency):.0f}")
        self._ai_target_value.setText(f"{detected}/{active}")
        self._bottom_status.set_inference(latency_text, active=True)
        self._set_ai_card_state(f"{backend} · 运行中", "good")

    def _set_ai_card_state(self, text: str, status: str) -> None:
        if self._ai_backend_label is None:
            return
        self._ai_backend_label.setText(text)
        self._ai_backend_label.setProperty("status", status)
        self._ai_backend_label.style().unpolish(self._ai_backend_label)
        self._ai_backend_label.style().polish(self._ai_backend_label)

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
        self._recording_value.setText("正在录制" if is_recording else "未录制")
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
        self._status_label.setText("传输运行" if available else "传输不可用")
        self._bottom_status.set_runtime(
            "系统运行正常" if available else "采集不可用",
            "good" if available else "bad",
        )
        for tile in self._tiles.values():
            tile.set_focus_enabled(available, reason="未连接" if not available else "")
        if message:
            self._status_label.setText(message)
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
            tile.set_focus_enabled(False, reason="不可用")
            self._errored_source_ids.add(source_id)
            self._refresh_camera_status()

    def clear_source_error(self, source_id: int) -> None:
        """Mark a source as connected again after a hotplug refresh."""
        if source_id not in self._tiles or source_id not in self._errored_source_ids:
            return
        self._errored_source_ids.discard(source_id)
        self._tiles[source_id].set_focus_enabled(True)
        self._refresh_camera_status()

    def set_storage_available(self, available_bytes: int) -> None:
        self._system_status.set_storage_available(available_bytes)
        self._navigation_resources.set_storage_available(available_bytes)

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
        self._status_label.setText(message)
        _set_pill_status(self._status_label, "good" if ok else "bad")

    def set_photo_busy(self, busy: bool) -> None:
        """Prevent duplicate still requests while JPEG compression is running."""
        self._photo_btn.setEnabled(not busy)
        self._record_btn.setEnabled(not busy)
        self._photo_btn.setText("正在保存..." if busy else "拍摄当前角度")
        if not busy:
            self._update_record_enabled()
            self._photo_btn.setEnabled(not self._stop_btn.isEnabled())

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
