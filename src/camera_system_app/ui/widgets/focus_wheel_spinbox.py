"""Spin boxes that cannot be changed accidentally by wheel input."""

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox


class _WheelSafeMixin:
    """Reject wheel editing while preserving typing and arrow buttons."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Wheel:
            event.ignore()
        return super().eventFilter(watched, event)

    def wheelEvent(self, event) -> None:
        event.ignore()


class SafeSpinBox(_WheelSafeMixin, QSpinBox):
    """Integer spin box that rejects wheel changes."""


class SafeDoubleSpinBox(_WheelSafeMixin, QDoubleSpinBox):
    """Decimal spin box that rejects wheel changes."""


class SafeComboBox(QComboBox):
    """A combo box that never changes selection from panel scrolling."""

    def wheelEvent(self, event) -> None:
        event.ignore()
