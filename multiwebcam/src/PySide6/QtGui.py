from PyQt5.QtCore import QRegularExpression
from PyQt5.QtGui import *  # noqa: F401,F403
from PyQt5.QtGui import QRegularExpressionValidator as _QRegularExpressionValidator


class QRegularExpressionValidator(_QRegularExpressionValidator):
    def __init__(self, regular_expression=None, parent=None):
        if isinstance(regular_expression, str):
            regular_expression = QRegularExpression(regular_expression)
        if regular_expression is None:
            super().__init__(parent)
        else:
            super().__init__(regular_expression, parent)
