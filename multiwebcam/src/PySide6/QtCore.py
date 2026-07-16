from PyQt5.QtCore import *  # noqa: F401,F403
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot

Signal = pyqtSignal
Slot = pyqtSlot


class _EnumNamespace:
    def __init__(self, **entries):
        self.__dict__.update(entries)


if not hasattr(Qt, "AlignmentFlag"):
    Qt.AlignmentFlag = _EnumNamespace(AlignCenter=Qt.AlignCenter)
if not hasattr(Qt, "AspectRatioMode"):
    Qt.AspectRatioMode = _EnumNamespace(KeepAspectRatio=Qt.KeepAspectRatio)
if not hasattr(Qt, "TransformationMode"):
    Qt.TransformationMode = _EnumNamespace(SmoothTransformation=Qt.SmoothTransformation)
if not hasattr(Qt, "Orientation"):
    Qt.Orientation = _EnumNamespace(Horizontal=Qt.Horizontal, Vertical=Qt.Vertical)
if not hasattr(Qt, "ConnectionType"):
    Qt.ConnectionType = _EnumNamespace(
        AutoConnection=Qt.AutoConnection,
        DirectConnection=Qt.DirectConnection,
        QueuedConnection=Qt.QueuedConnection,
        BlockingQueuedConnection=Qt.BlockingQueuedConnection,
    )
