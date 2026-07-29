"""Persistent state banner using symbol, colour, and text."""

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


class StatusBanner(QFrame):
    _SYMBOLS = {
        "info": "●",
        "success": "✓",
        "warning": "△",
        "danger": "✕",
    }

    def __init__(self, text: str, status: str = "warning", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("statusBanner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        self._symbol = QLabel()
        self._text = QLabel(text)
        self._text.setWordWrap(True)
        layout.addWidget(self._symbol)
        layout.addWidget(self._text, 1)
        self.set_status(text, status)

    def set_status(self, text: str, status: str) -> None:
        if status not in self._SYMBOLS:
            raise ValueError("Unsupported banner status: " + status)
        self._text.setText(text)
        self._symbol.setText(self._SYMBOLS[status])
        self.setProperty("status", status)
        self.setAccessibleName(
            "{} {}".format(self._SYMBOLS[status], text)
        )
        self.style().unpolish(self)
        self.style().polish(self)

    def symbol_text(self) -> str:
        return self._symbol.text()
