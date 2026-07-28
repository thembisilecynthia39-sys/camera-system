"""Base helpers for shell pages."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from camera_system_app.ui.widgets import PageHeader


class BasePage(QWidget):
    def __init__(
        self,
        title: str,
        description: str,
        parent=None,
        eyebrow: str = "",
        scrollable: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageSurface")
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(18)
        root_layout.addWidget(PageHeader(title, description, eyebrow))

        self._scroll = None
        if scrollable:
            self._scroll = QScrollArea()
            self._scroll.setObjectName("pageScroll")
            self._scroll.setFrameShape(QFrame.NoFrame)
            self._scroll.setWidgetResizable(True)
            self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            content = QWidget()
            content.setObjectName("pageScrollContent")
            self.layout = QVBoxLayout(content)
            self.layout.setContentsMargins(0, 0, 8, 0)
            self.layout.setSpacing(18)
            self._scroll.setWidget(content)
            root_layout.addWidget(self._scroll, 1)
        else:
            self.layout = root_layout

    def add_card(
        self,
        title: str = "",
        description: str = "",
    ) -> QVBoxLayout:
        card = QFrame()
        card.setObjectName("contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)
        if title:
            title_label = QLabel(title)
            title_label.setObjectName("sectionTitle")
            card_layout.addWidget(title_label)
        if description:
            description_label = QLabel(description)
            description_label.setObjectName("sectionDescription")
            description_label.setWordWrap(True)
            card_layout.addWidget(description_label)
        self.layout.addWidget(card)
        return card_layout

    def finish(self) -> None:
        self.layout.addStretch(1)
