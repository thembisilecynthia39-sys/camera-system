"""Render deterministic screenshots of the redesigned capture console.

Usage:
    QT_QPA_PLATFORM=offscreen python scripts/widget_visualization/wv_redesign_preview.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from multiwebcam.ui.fluent import apply_fluent_theme  # noqa: E402
from multiwebcam.sources.controls import V4L2Control  # noqa: E402
from multiwebcam.ui.theme import Palette, app_stylesheet  # noqa: E402
from multiwebcam.ui.views.focus_view import FocusView  # noqa: E402
from multiwebcam.ui.views.grid_view import GridView  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output"


def _settle(app: QApplication) -> None:
    """Flush deferred responsive relayout and the paint it schedules."""
    for _ in range(3):
        app.processEvents()


def _preview_frame(index: int, name: str) -> QPixmap:
    """Create a flat mock frame without relying on camera hardware."""
    colours = ("#1D4650", "#493C60", "#36503B", "#55412D")
    pixmap = QPixmap(960, 540)
    pixmap.fill(QColor(colours[index % len(colours)]))
    painter = QPainter(pixmap)
    painter.setPen(QColor(Palette.TEXT))
    font = painter.font()
    font.setPointSize(24)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, name)
    painter.end()
    return pixmap


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    apply_fluent_theme()
    app.setStyleSheet(app_stylesheet())

    view = GridView()
    view.resize(1440, 900)
    for index, name in enumerate(("正面", "左前", "右前", "顶部")):
        view.add_source(index, name)
        view.set_tile_resolution(index, "1920×1080")
        view._tiles[index].display_frame(_preview_frame(index, name))
        view._tiles[index].update_stats(29.8 - index * 0.2, 1.4 + index * 0.3)
        view._tiles[index].update_quality("GOOD | sharp 0.86 | exp 0.78 | feat 120", "good")

    view._alignment_label.setText("同步: 4.8ms | 完整 99%")
    view._alignment_label.setProperty("status", "good")
    view._quality_label.setText("质量: 良好 | 92%")
    view._quality_label.setProperty("status", "good")
    view.show()
    _settle(app)
    view.grab().save(str(OUTPUT_DIR / "redesign_overview.png"))

    view._nav_group.button(1).click()
    view.set_default_recording_name("scan_session_07")
    _settle(app)
    view.grab().save(str(OUTPUT_DIR / "redesign_recording.png"))

    # Keep a deterministic narrow-window artifact so responsive regressions
    # (overlapping navigation, status, or camera tiles) are visible in review.
    view._nav_group.button(0).click()
    view.resize(900, 650)
    _settle(app)
    view.grab().save(str(OUTPUT_DIR / "redesign_compact.png"))
    view.resize(640, 560)
    _settle(app)
    view.grab().save(str(OUTPUT_DIR / "redesign_narrow.png"))
    view.close()

    focus = FocusView(0, "正面主相机")
    focus.resize(1440, 900)
    focus.populate_resolutions(["1920x1080", "1280x720", "640x480"])
    focus.populate_framerates(["15", "30", "60"])
    focus.set_current_config("1920x1080", "30")
    focus.set_controls(
        [
            V4L2Control("brightness", "int", 0, 255, 1, 128, 138),
            V4L2Control("contrast", "int", 0, 255, 1, 128, 145),
            V4L2Control("exposure_absolute", "int", 3, 2047, 1, 250, 166),
            V4L2Control("focus_auto", "bool", 0, 1, 1, 1, 1),
        ]
    )
    focus._frame_label.display_pixmap(_preview_frame(0, "正面主相机 / 1920×1080"))
    focus.show()
    _settle(app)
    focus.grab().save(str(OUTPUT_DIR / "redesign_focus.png"))
    focus.close()


if __name__ == "__main__":
    main()
