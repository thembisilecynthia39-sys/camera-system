"""Persistent state banner using symbol, colour, and text."""

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


class StatusBanner(QFrame):
    def __init__(self, text: str, status: str = "warning", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("statusBanner")
        self.setProperty("status", status)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        self._symbol = QLabel("△" if status == "warning" else "●")
        self._text = QLabel(text)
        self._text.setWordWrap(True)
        layout.addWidget(self._symbol)
        layout.addWidget(self._text, 1)

    def set_status(self, text: str, status: str) -> None:
        self._text.setText(text)
        self._symbol.setText("✓" if status == "success" else "△")
        self.setProperty("status", status)
        self.style().unpolish(self)
        self.style().polish(self)

