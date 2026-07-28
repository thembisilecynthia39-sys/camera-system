"""Base helpers for shell pages."""

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from camera_system_app.ui.widgets import PageHeader


class BasePage(QWidget):
    def __init__(
        self,
        title: str,
        description: str,
        parent=None,
        eyebrow: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageSurface")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(28, 24, 28, 24)
        self.layout.setSpacing(18)
        self.layout.addWidget(PageHeader(title, description, eyebrow))

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
