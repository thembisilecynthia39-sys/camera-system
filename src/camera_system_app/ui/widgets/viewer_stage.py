"""Viewport host that keeps viewer controls floating above the scene."""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QFrame, QSizePolicy, QWidget


class ViewerStage(QFrame):
    """Lay out a full-size viewport and a non-layout-affecting inspector overlay."""

    _MARGIN = 12

    def __init__(self, viewport: QWidget, inspector: QWidget, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("viewerStage")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(0, 0)
        self._viewport = viewport
        self._inspector = inspector
        viewport.setParent(self)
        inspector.setParent(self)
        viewport.show()
        self.relayout()

    def viewport_rect(self) -> QRect:
        """Return the viewport geometry for layout tests and size reporting."""

        return self._viewport.geometry()

    def relayout(self) -> None:
        """Fill the stage with the viewport and pin the inspector to the right."""

        self._viewport.setGeometry(self.rect())
        width = self._inspector.panel_width_for_host(self.width())
        height = max(0, self.height() - 2 * self._MARGIN)
        x = max(self._MARGIN, self.width() - self._MARGIN - width)
        self._inspector.setGeometry(x, self._MARGIN, width, height)
        self._inspector.raise_()

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.relayout()
        super().resizeEvent(event)


__all__ = ["ViewerStage"]
