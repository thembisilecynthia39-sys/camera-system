"""Spin boxes that do not consume page-scrolling wheel events."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox


class _FocusWheelMixin:
    """Admit wheel stepping only after explicit pointer selection."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._wheel_selected = False
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if (
            event.type() == QEvent.MouseButtonPress
            and event.button() == Qt.LeftButton
        ):
            self._wheel_selected = True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event) -> None:
        selected = event.button() == Qt.LeftButton
        super().mousePressEvent(event)
        if selected:
            self._wheel_selected = True

    def focusInEvent(self, event) -> None:
        if event.reason() in {
            Qt.TabFocusReason,
            Qt.BacktabFocusReason,
            Qt.ShortcutFocusReason,
        }:
            self._wheel_selected = False
        elif event.reason() == Qt.MouseFocusReason:
            self._wheel_selected = True
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._wheel_selected = False
        super().focusOutEvent(event)

    def wheelEvent(self, event) -> None:
        if not self.hasFocus() or not self._wheel_selected:
            event.ignore()
            return
        super().wheelEvent(event)


class FocusWheelSpinBox(_FocusWheelMixin, QSpinBox):
    """Integer spin box protected from unfocused wheel changes."""


class FocusWheelDoubleSpinBox(_FocusWheelMixin, QDoubleSpinBox):
    """Decimal spin box protected from unfocused wheel changes."""
