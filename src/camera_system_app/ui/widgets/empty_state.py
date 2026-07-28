"""Actionable empty state shared by workstation pages."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout


class EmptyState(QFrame):
    action_requested = Signal()

    def __init__(
        self,
        symbol: str,
        title: str,
        description: str,
        action_text: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("emptyState")
        self.setAccessibleName("{}。{}".format(title, description))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)

        self._symbol = QLabel(symbol)
        self._symbol.setObjectName("emptyStateSymbol")
        self._symbol.setAlignment(Qt.AlignCenter)
        self._title = QLabel(title)
        self._title.setObjectName("emptyStateTitle")
        self._title.setAlignment(Qt.AlignCenter)
        self._description = QLabel(description)
        self._description.setObjectName("emptyStateDescription")
        self._description.setAlignment(Qt.AlignCenter)
        self._description.setWordWrap(True)
        self.action_button = QPushButton(action_text)
        self.action_button.setObjectName("secondaryButton")
        self.action_button.setAccessibleName(action_text or title)
        self.action_button.clicked.connect(self.action_requested.emit)
        self.action_button.setHidden(not bool(action_text))

        layout.addWidget(self._symbol)
        layout.addWidget(self._title)
        layout.addWidget(self._description)
        layout.addWidget(self.action_button, 0, Qt.AlignCenter)

    def title_text(self) -> str:
        return self._title.text()
