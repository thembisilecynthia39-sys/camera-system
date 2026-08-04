from PyQt5.QtWidgets import *  # noqa: F401,F403
from PyQt5.QtWidgets import QFrame, QMessageBox


class _EnumNamespace:
    def __init__(self, **entries):
        self.__dict__.update(entries)


QFrame.Shape = _EnumNamespace(HLine=QFrame.HLine, Box=QFrame.Box)
QFrame.Shadow = _EnumNamespace(Sunken=QFrame.Sunken, Raised=QFrame.Raised)
QMessageBox.StandardButton = _EnumNamespace(
    Yes=QMessageBox.Yes,
    No=QMessageBox.No,
    Ok=QMessageBox.Ok,
    Cancel=QMessageBox.Cancel,
    Save=QMessageBox.Save,
    Discard=QMessageBox.Discard,
)
