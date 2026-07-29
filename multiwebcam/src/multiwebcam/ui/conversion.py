"""Frame conversion utilities for Qt display."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtGui import QImage, QPixmap

from multiwebcam.quality.metrics import MAX_PRIMARY_OBJECT_AREA_RATIO, ObjectRegion


def frame_to_pixmap(
    frame: np.ndarray,
    mirror: bool = False,
    object_region: ObjectRegion | None = None,
    max_size: tuple[int, int] | None = None,
) -> QPixmap:
    """Convert BGR numpy array to QPixmap for display.

    Args:
        frame: BGR image array, shape (H, W, 3), dtype uint8
        mirror: If True, flip horizontally before conversion
        object_region: Optional estimated subject region to draw on preview
    """
    return QPixmap.fromImage(
        frame_to_qimage(
            frame,
            mirror=mirror,
            object_region=object_region,
            max_size=max_size,
        )
    )


def frame_to_qimage(
    frame: np.ndarray,
    mirror: bool = False,
    object_region: ObjectRegion | None = None,
    max_size: tuple[int, int] | None = None,
) -> QImage:
    """Prepare a detached RGB QImage, optionally capped for grid preview."""
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("frame must have shape (height, width, 3)")

    source_height, source_width = frame.shape[:2]
    preview = _resize_to_fit(frame, max_size)
    height, width = preview.shape[:2]
    scale_x = width / max(1, source_width)
    scale_y = height / max(1, source_height)

    if object_region is not None and object_region.area_ratio <= MAX_PRIMARY_OBJECT_AREA_RATIO:
        _draw_object_region(preview, object_region, scale_x, scale_y)
    else:
        _draw_center_guide(preview)
    if mirror:
        preview = cv2.flip(preview, 1)
    height, width, channels = preview.shape
    bytes_per_line = channels * width
    rgb_frame = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
    image = QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
    return image.copy()


def _resize_to_fit(
    frame: np.ndarray,
    max_size: tuple[int, int] | None,
) -> np.ndarray:
    if max_size is None:
        return frame.copy()
    max_width, max_height = max_size
    height, width = frame.shape[:2]
    scale = min(max_width / max(1, width), max_height / max(1, height), 1.0)
    if scale >= 1.0:
        return frame.copy()
    target = (
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    )
    return cv2.resize(frame, target, interpolation=cv2.INTER_AREA)


def _draw_object_region(
    frame: np.ndarray,
    object_region: ObjectRegion,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
) -> None:
    x, y, w, h = object_region.bbox
    x = int(round(x * scale_x))
    y = int(round(y * scale_y))
    w = int(round(w * scale_x))
    h = int(round(h * scale_y))
    color = (0, 220, 0) if object_region.confidence >= 0.45 else (0, 200, 255)
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
    center = (x + w // 2, y + h // 2)
    cv2.drawMarker(frame, center, color, cv2.MARKER_CROSS, 16, 2)


def _draw_center_guide(frame: np.ndarray) -> None:
    height, width = frame.shape[:2]
    box_w = int(width * 0.28)
    box_h = int(height * 0.36)
    x = (width - box_w) // 2
    y = (height - box_h) // 2
    cv2.rectangle(frame, (x, y), (x + box_w, y + box_h), (0, 200, 255), 1)
