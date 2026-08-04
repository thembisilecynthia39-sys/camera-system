"""QLabel subclass for predictable camera preview scaling."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy

class AspectRatioLabel(QLabel):
    """Displays a pixmap scaled to a stable preview viewport.

    In ``contain`` mode, unused space is filled with the neutral preview
    background. In ``cover`` mode, the pixmap fills the preview viewport
    and any overflow is center-cropped.
    """

    def __init__(
        self,
        parent=None,
        *,
        fill_mode: str = "contain",
        smooth_scaling: bool = True,
    ):
        super().__init__(parent)
        self._original_pixmap: QPixmap | None = None
        self._fill_mode = fill_mode
        self._smooth_scaling = smooth_scaling
        self.setObjectName("videoPreview")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(120, 68)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

    def set_fill_mode(self, fill_mode: str) -> None:
        """Set preview scaling mode: ``contain`` or ``cover``."""
        if fill_mode not in {"contain", "cover"}:
            raise ValueError("fill_mode must be 'contain' or 'cover'")
        self._fill_mode = fill_mode
        self._update_scaled()

    def display_pixmap(self, pixmap: QPixmap) -> None:
        """Set the pixmap to display, scaling to fit current size."""
        self._original_pixmap = pixmap
        self._update_scaled()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Re-scale pixmap when the label is resized."""
        super().resizeEvent(event)
        self._update_scaled()

    def _update_scaled(self) -> None:
        if self._original_pixmap is None:
            return
        if self.width() <= 0 or self.height() <= 0:
            return

        aspect_mode = Qt.AspectRatioMode.KeepAspectRatio
        if self._fill_mode == "cover":
            aspect_mode = getattr(
                Qt.AspectRatioMode,
                "KeepAspectRatioByExpanding",
                getattr(Qt, "KeepAspectRatioByExpanding", Qt.AspectRatioMode.KeepAspectRatio),
            )

        transform_mode = (
            Qt.TransformationMode.SmoothTransformation
            if self._smooth_scaling
            else Qt.TransformationMode.FastTransformation
        )
        scaled = self._original_pixmap.scaled(
            self.size(),
            aspect_mode,
            transform_mode,
        )
        if self._fill_mode == "cover" and (scaled.width() > self.width() or scaled.height() > self.height()):
            x = max(0, (scaled.width() - self.width()) // 2)
            y = max(0, (scaled.height() - self.height()) // 2)
            scaled = scaled.copy(x, y, min(self.width(), scaled.width()), min(self.height(), scaled.height()))
        super().setPixmap(scaled)
