"""Compact diagnostic metric card."""

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class MetricCard(QFrame):
    def __init__(
        self,
        label: str,
        value="0",
        status: str = "neutral",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setProperty("status", status)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(3)
        self._value = QLabel(str(value))
        self._value.setObjectName("metricValue")
        self._label = QLabel(label)
        self._label.setObjectName("metricLabel")
        layout.addWidget(self._value)
        layout.addWidget(self._label)
        self._sync_accessibility()

    def set_value(self, value) -> None:
        self._value.setText(str(value))
        self._sync_accessibility()

    def value_text(self) -> str:
        return self._value.text()

    def _sync_accessibility(self) -> None:
        self.setAccessibleName(
            "{}：{}".format(self._label.text(), self._value.text())
        )
