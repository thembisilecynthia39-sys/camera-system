"""Compact progress dialog for frozen final viewer renders."""

from __future__ import annotations

import time

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from camera_system_app.domain.viewer import OutputKind


class ViewerRenderDialog(QDialog):
    """Show exactly what is being rendered and keep cancellation visible."""

    cancel_requested = Signal()

    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self.setObjectName("viewerRenderDialog")
        self.setWindowTitle("导出 3DGS 漫游")
        self.setModal(False)
        self.setMinimumWidth(460)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)
        title = QLabel("正在生成高质量展示输出")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        form = QFormLayout()
        self.resolution_label = QLabel(
            "{} × {}".format(plan.render.width, plan.render.height)
        )
        self.fps_label = QLabel("{} FPS".format(plan.render.fps))
        format_names = {
            OutputKind.PNG: "PNG 单帧",
            OutputKind.PNG_SEQUENCE: "PNG 序列",
            OutputKind.MP4: "MP4 视频",
        }
        self.format_label = QLabel(format_names[plan.render.output_kind])
        self.frame_count_label = QLabel("{} 帧".format(plan.frame_count))
        self.quality_label = QLabel(plan.render.quality.value)
        mode_names = {
            "standard": "Gaussian",
            "sphere_wireframe": "外接球线框",
            "sphere_solid": "外接球实体",
            "overlay": "Gaussian + 球体",
        }
        self.mode_label = QLabel(mode_names.get(plan.display.mode.value, plan.display.mode.value))
        self.sphere_label = QLabel(
            "σ × {:.1f} · 不透明度 {:.0f}%".format(
                plan.display.sphere_sigma_multiplier,
                plan.display.sphere_opacity * 100.0,
            )
        )
        self.duration_label = QLabel(
            "{:.2f} 秒".format(plan.duration_seconds)
            if plan.duration_seconds > 0.0
            else "单帧"
        )
        self.output_label = QLabel(str(plan.output_path))
        self.output_label.setWordWrap(True)
        self.transparency_label = QLabel(
            "开启" if plan.render.transparent_background else "关闭"
        )
        form.addRow("分辨率", self.resolution_label)
        form.addRow("帧率", self.fps_label)
        form.addRow("格式", self.format_label)
        form.addRow("帧数", self.frame_count_label)
        form.addRow("镜头时长", self.duration_label)
        form.addRow("显示模式", self.mode_label)
        form.addRow("球体参数", self.sphere_label)
        form.addRow("质量", self.quality_label)
        form.addRow("透明背景", self.transparency_label)
        form.addRow("输出位置", self.output_label)
        root.addLayout(form)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setAccessibleName("导出进度")
        root.addWidget(self.progress_bar)
        self.status_label = QLabel("等待渲染…")
        self.status_label.setObjectName("mutedText")
        root.addWidget(self.status_label)
        self.frame_progress_label = QLabel("0 / {} 帧".format(plan.frame_count))
        self.frame_progress_label.setObjectName("mutedText")
        root.addWidget(self.frame_progress_label)
        self.elapsed_label = QLabel("已用时 0.0 秒")
        self.elapsed_label.setObjectName("mutedText")
        root.addWidget(self.elapsed_label)
        self.eta_label = QLabel("预计剩余 —")
        self.eta_label.setObjectName("mutedText")
        root.addWidget(self.eta_label)
        self._plan = plan
        self._started_at = time.monotonic()

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("取消导出")
        self.cancel_button.setAccessibleName("取消 3DGS 导出")
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        buttons.addWidget(self.cancel_button)
        root.addLayout(buttons)

    def set_progress(self, progress: float) -> None:
        bounded = max(0.0, min(1.0, float(progress)))
        self.progress_bar.setValue(int(round(bounded * 1000)))
        frame = min(self._plan.frame_count, int(bounded * self._plan.frame_count))
        elapsed = max(0.0, time.monotonic() - self._started_at)
        self.frame_progress_label.setText(
            "{} / {} 帧".format(frame, self._plan.frame_count)
        )
        self.elapsed_label.setText("已用时 {:.1f} 秒".format(elapsed))
        if bounded > 0.0 and bounded < 1.0:
            eta = elapsed * (1.0 - bounded) / bounded
            self.eta_label.setText("预计剩余 {:.1f} 秒".format(eta))
        else:
            self.eta_label.setText("预计剩余 —")
        self.status_label.setText(
            "已完成 {:.1f}% · {} / {} 帧".format(
                bounded * 100.0,
                frame,
                self._plan.frame_count,
            )
        )

    def set_error(self, message: str) -> None:
        self.status_label.setText("导出失败：{}".format(message))
        self.cancel_button.setEnabled(False)

    def set_finished(self, output_path) -> None:
        self.progress_bar.setValue(1000)
        self.status_label.setText("已完成：{}".format(output_path))
        self.cancel_button.setText("关闭")
        self.cancel_button.setEnabled(True)
        try:
            self.cancel_button.clicked.disconnect(self.cancel_requested.emit)
        except (RuntimeError, TypeError):
            pass
        self.cancel_button.clicked.connect(self.accept)


__all__ = ["ViewerRenderDialog"]
