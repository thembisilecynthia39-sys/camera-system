from __future__ import annotations
"""Frame conversion utilities for Qt display."""

import cv2
import numpy as np
from PySide6.QtGui import QImage, QPixmap

from multiwebcam.quality.metrics import ObjectRegion


def frame_to_pixmap(
    frame: np.ndarray,
    mirror: bool = False,
    object_region: ObjectRegion | None = None,
) -> QPixmap:
    """Convert BGR numpy array to QPixmap for display.

    Args:
        frame: BGR image array, shape (H, W, 3), dtype uint8
        mirror: If True, flip horizontally before conversion
        object_region: Optional estimated subject region to draw on preview
    """
    frame = frame.copy()
    if object_region is not None:
        _draw_object_region(frame, object_region)
    else:
        _draw_center_guide(frame)
    if mirror:
        frame = frame[:, ::-1, :]
    height, width, channels = frame.shape
    bytes_per_line = channels * width
    # Convert BGR to RGB for Qt
    rgb_frame = frame[..., ::-1].copy()
    image = QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
    # Copy into QImage's internal buffer before rgb_frame goes out of scope
    return QPixmap.fromImage(image.copy())


def _draw_object_region(frame: np.ndarray, object_region: ObjectRegion) -> None:
    x, y, w, h = object_region.bbox
    color = (0, 220, 0) if object_region.confidence >= 0.45 else (0, 200, 255)
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
    center = (x + w // 2, y + h // 2)
    cv2.drawMarker(frame, center, color, cv2.MARKER_CROSS, 16, 2)


def _draw_center_guide(frame: np.ndarray) -> None:
    height, width = frame.shape[:2]
    box_w = int(width * 0.35)
    box_h = int(height * 0.45)
    x = (width - box_w) // 2
    y = (height - box_h) // 2
    cv2.rectangle(frame, (x, y), (x + box_w, y + box_h), (0, 200, 255), 1)
