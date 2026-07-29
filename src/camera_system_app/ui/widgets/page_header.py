"""Consistent page heading."""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PageHeader(QWidget):
    def __init__(
        self,
        title: str,
        description: str,
        eyebrow: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(5)

        self._eyebrow = QLabel(eyebrow)
        self._eyebrow.setObjectName("eyebrow")
        self._eyebrow.setHidden(not bool(eyebrow))
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        description_label = QLabel(description)
        description_label.setObjectName("pageDescription")
        description_label.setWordWrap(True)
        layout.addWidget(self._eyebrow)
        layout.addWidget(title_label)
        layout.addWidget(description_label)
        self.setAccessibleName("{}。{}".format(title, description))

    def eyebrow_text(self) -> str:
        return self._eyebrow.text()
