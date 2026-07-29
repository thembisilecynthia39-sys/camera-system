"""Numbered stage card for transfer and reconstruction progress."""

from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout


class WorkflowStage(QFrame):
    VALID_STATES = {
        "pending",
        "active",
        "completed",
        "warning",
        "failed",
    }
    _SYMBOLS = {
        "pending": "○",
        "active": "●",
        "completed": "✓",
        "warning": "△",
        "failed": "✕",
    }

    def __init__(self, number: str, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("workflowStage")
        self.setProperty("state", "pending")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        self._number = QLabel(number)
        self._number.setObjectName("workflowNumber")
        self._title = QLabel(title)
        self._title.setObjectName("workflowTitle")
        self._status = QLabel("○ 等待")
        self._status.setObjectName("workflowStatus")
        self._status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self._number)
        layout.addWidget(self._title)
        layout.addWidget(self._status)
        layout.addWidget(self.progress)
        self._sync_accessibility()

    def set_progress(self, value, status_text: str) -> None:
        value = max(0, min(100, int(value)))
        self.progress.setValue(value)
        symbol = self._SYMBOLS.get(self.property("state"), "○")
        self._status.setText("{} {}".format(symbol, status_text))
        self._sync_accessibility()

    def set_state(self, state: str) -> None:
        if state not in self.VALID_STATES:
            raise ValueError("Unsupported workflow stage state: " + state)
        current_text = self._status.text()
        if len(current_text) >= 2 and current_text[1] == " ":
            current_text = current_text[2:]
        self.setProperty("state", state)
        self._status.setText(
            "{} {}".format(self._SYMBOLS[state], current_text)
        )
        self.style().unpolish(self)
        self.style().polish(self)
        self._sync_accessibility()

    def _sync_accessibility(self) -> None:
        self.setAccessibleName(
            "{} {}，{}，{}%".format(
                self._number.text(),
                self._title.text(),
                self._status.text(),
                self.progress.value(),
            )
        )
