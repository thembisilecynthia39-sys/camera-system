"""Compact progress dialog for frozen final viewer renders."""

from __future__ import annotations

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
        self.transparency_label = QLabel(
            "开启" if plan.render.transparent_background else "关闭"
        )
        form.addRow("分辨率", self.resolution_label)
        form.addRow("帧率", self.fps_label)
        form.addRow("格式", self.format_label)
        form.addRow("帧数", self.frame_count_label)
        form.addRow("质量", self.quality_label)
        form.addRow("透明背景", self.transparency_label)
        root.addLayout(form)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setAccessibleName("导出进度")
        root.addWidget(self.progress_bar)
        self.status_label = QLabel("等待渲染…")
        self.status_label.setObjectName("mutedText")
        root.addWidget(self.status_label)

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
        self.status_label.setText("已完成 {:.1f}%".format(bounded * 100.0))

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
