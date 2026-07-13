"""Shared visual tokens and helpers for the Qt Widgets UI.

The capture console uses a low-glare dark palette so the camera feeds remain
the visual focus.  Tokens are named by role instead of colour to keep status
and interaction semantics consistent across every view.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


class Palette:
    """Semantic colour roles for the capture workstation."""

    BACKGROUND = "#181A1D"
    SURFACE = "#202328"
    SURFACE_RAISED = "#292D33"
    SURFACE_SUNKEN = "#111315"
    SURFACE_HOVER = "#30343A"
    BORDER = "#34383E"
    BORDER_STRONG = "#4A5058"
    TEXT = "#E8EAED"
    TEXT_MUTED = "#A7ABB1"
    TEXT_FAINT = "#777C84"
    INTERACTIVE = "#4D86BA"
    INTERACTIVE_HOVER = "#6398C8"
    INTERACTIVE_PRESSED = "#3D6F9C"
    ON_INTERACTIVE = "#FFFFFF"
    RECORD = "#C85050"
    RECORD_HOVER = "#D65D5D"
    RECORD_PRESSED = "#A84242"
    SUCCESS = "#68A67E"
    WARNING = "#C89B52"
    DANGER = "#D36A6A"
    DISABLED = "#62666C"


class Spacing:
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32


class Radius:
    CONTROL = 3
    CARD = 4
    PANEL = 0


class TypeScale:
    META = 13
    BODY = 15
    SECTION = 18
    TITLE = 24


def app_stylesheet() -> str:
    """Return the application-wide Qt stylesheet."""
    return f"""
        QWidget {{
            background: {Palette.BACKGROUND};
            color: {Palette.TEXT};
            font-family: "Inter", "Noto Sans CJK SC", "Noto Sans", sans-serif;
            font-size: {TypeScale.BODY}px;
        }}
        QMainWindow,
        QStackedWidget {{
            background: {Palette.BACKGROUND};
        }}
        QStackedWidget#sidePanelStack {{
            background: transparent;
            border: none;
        }}
        QWidget#gridSurface,
        QWidget#focusSurface {{
            background: {Palette.BACKGROUND};
        }}
        QWidget#controlPanelSurface,
        QWidget#sourceTileBody,
        QWidget#videoWall,
        QWidget#sidePanelPage {{
            background: transparent;
        }}
        QFrame#topNavigation {{
            background: #1D2024;
            border: none;
            border-bottom: 1px solid {Palette.BORDER};
            border-radius: 0;
        }}
        QFrame#contextPanel,
        QFrame#sidePanel {{
            background: {Palette.SURFACE};
            border: 1px solid {Palette.BORDER};
            border-radius: 10px;
        }}
        QFrame#globalStatusBar {{
            background: transparent;
            border: none;
            border-bottom: 1px solid {Palette.BORDER};
            border-radius: 0;
        }}
        QFrame#statusBadge {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: {Radius.CONTROL}px;
        }}
        QFrame#statusBadge:hover {{
            background: {Palette.SURFACE_HOVER};
            border-color: transparent;
        }}
        QLabel#statusIcon,
        QLabel#statusText {{
            color: {Palette.TEXT_MUTED};
            font-size: {TypeScale.META}px;
            background: transparent;
        }}
        QFrame#statusDot {{
            background: {Palette.TEXT_FAINT};
            border: none;
            border-radius: 3px;
        }}
        QFrame#statusBadge[state="good"] QFrame#statusDot {{ background: {Palette.SUCCESS}; }}
        QFrame#statusBadge[state="warn"] QFrame#statusDot {{ background: {Palette.WARNING}; }}
        QFrame#statusBadge[state="bad"] QFrame#statusDot {{ background: {Palette.DANGER}; }}
        QFrame#statusBadge[state="record"] QFrame#statusDot {{ background: {Palette.RECORD}; }}
        QFrame#statusBadge[state="record"] QLabel#statusText {{ color: {Palette.RECORD_HOVER}; }}
        QFrame#sidePanel,
        QFrame#infoCard,
        QFrame#controlBand,
        QFrame#statusBand {{
            background: {Palette.SURFACE};
            border: 1px solid {Palette.BORDER};
            border-radius: 12px;
        }}
        QFrame#cameraTile {{
            background: {Palette.SURFACE};
            border: 1px solid {Palette.BORDER};
            border-radius: {Radius.CARD}px;
        }}
        QFrame#cameraTile[ignored="true"] {{
            background: {Palette.SURFACE};
            border-color: {Palette.BORDER};
        }}
        QFrame#videoShell {{
            background: {Palette.SURFACE_SUNKEN};
            border: 1px solid #2C3035;
            border-radius: 3px;
        }}
        QLabel#videoPreview {{
            background: {Palette.SURFACE_SUNKEN};
            color: {Palette.TEXT_MUTED};
            border: none;
            border-radius: 2px;
        }}
        QLabel#videoPreview[ignored="true"] {{
            background: #25282C;
            border: 1px dashed {Palette.BORDER};
        }}
        QFrame#modelViewportControls {{
            background: #D90B1118;
            border: 1px solid {Palette.BORDER_STRONG};
            border-radius: 9px;
        }}
        QFrame#metricStrip {{
            background: transparent;
            border: none;
            border-top: 1px solid {Palette.BORDER};
            border-radius: 0;
        }}
        QFrame#sectionDivider {{
            background: {Palette.BORDER};
            border: none;
            min-height: 1px;
            max-height: 1px;
        }}
        QScrollArea {{
            border: none;
            background: transparent;
        }}
        QScrollArea > QWidget > QWidget {{
            background: transparent;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 2px 0;
        }}
        QScrollBar::handle:vertical {{
            background: {Palette.BORDER_STRONG};
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QLabel {{
            background: transparent;
        }}
        QLabel#brandMark {{
            color: {Palette.TEXT_MUTED};
            font-size: 13px;
            font-weight: 600;
        }}
        QLabel#pageTitle {{
            color: {Palette.TEXT};
            font-size: {TypeScale.TITLE}px;
            font-weight: 600;
        }}
        QLabel#sectionTitle {{
            color: {Palette.TEXT};
            font-size: {TypeScale.SECTION}px;
            font-weight: 600;
        }}
        QLabel#cameraName {{
            color: {Palette.TEXT};
            font-size: {TypeScale.BODY}px;
            font-weight: 600;
        }}
        QLabel#sideLabel {{
            color: {Palette.TEXT_FAINT};
            font-size: 12px;
            font-weight: 600;
        }}
        QLabel#navLabel {{
            color: {Palette.TEXT_FAINT};
            font-size: 12px;
            font-weight: 600;
        }}
        QLabel#sideSectionTitle {{
            color: {Palette.TEXT};
            font-size: {TypeScale.SECTION}px;
            font-weight: 600;
            padding-top: 3px;
        }}
        QLabel#cameraChip {{
            background: #30343A;
            color: {Palette.TEXT};
            border: 1px solid {Palette.BORDER_STRONG};
            border-radius: 3px;
            padding: 3px 7px;
            font-size: 12px;
            font-weight: 600;
        }}
        QLabel#stateChip {{
            background: transparent;
            color: {Palette.SUCCESS};
            border: none;
            border-radius: 0;
            padding: 3px 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        QLabel#stateChip[status="muted"] {{
            background: transparent;
            color: {Palette.TEXT_MUTED};
            border: none;
        }}
        QLabel#liveBadge {{
            background: #153529;
            color: {Palette.SUCCESS};
            border: 1px solid #27664F;
            border-radius: 8px;
            padding: 5px 10px;
            font-size: 11px;
            font-weight: 800;
        }}
        QLabel#metaLabel,
        QLabel#captionLabel {{
            color: {Palette.TEXT_MUTED};
            font-size: {TypeScale.META}px;
        }}
        QLabel#qualityLabel,
        QLabel#queueDepthLabel {{
            color: {Palette.TEXT_MUTED};
            font-size: {TypeScale.META}px;
        }}
        QLabel#qualityLabel[level="good"] {{ color: {Palette.SUCCESS}; font-weight: 700; }}
        QLabel#qualityLabel[level="warn"] {{ color: {Palette.WARNING}; font-weight: 700; }}
        QLabel#qualityLabel[level="bad"] {{ color: {Palette.DANGER}; font-weight: 700; }}
        QLabel#queueDepthLabel[warning="true"] {{ color: {Palette.WARNING}; font-weight: 700; }}
        QLabel#mutedLabel {{
            color: {Palette.TEXT_FAINT};
        }}
        QLabel#statusPill {{
            background: #25282D;
            color: {Palette.TEXT};
            border: 1px solid {Palette.BORDER};
            border-radius: 3px;
            padding: 7px 9px;
            font-weight: 500;
        }}
        QLabel#statusPill[status="muted"] {{
            color: {Palette.TEXT_MUTED};
        }}
        QLabel#statusPill[status="good"] {{
            background: #252B27;
            color: {Palette.SUCCESS};
            border-color: #3E5546;
        }}
        QLabel#statusPill[status="warn"] {{
            background: #2D2922;
            color: {Palette.WARNING};
            border-color: #5D4C32;
        }}
        QLabel#statusPill[status="bad"] {{
            background: #302426;
            color: {Palette.DANGER};
            border-color: #613D42;
        }}
        QLabel#overviewStatus {{
            background: transparent;
            color: {Palette.TEXT};
            border: none;
            border-bottom: 1px solid {Palette.BORDER};
            border-radius: 0;
            padding: 9px 2px;
            font-weight: 500;
        }}
        QLabel#overviewStatus[status="muted"] {{ color: {Palette.TEXT_MUTED}; }}
        QLabel#overviewStatus[status="good"] {{ color: {Palette.SUCCESS}; }}
        QLabel#overviewStatus[status="warn"] {{ color: {Palette.WARNING}; }}
        QLabel#overviewStatus[status="bad"] {{ color: {Palette.DANGER}; }}
        QLabel#timerLabel {{
            background: {Palette.SURFACE_SUNKEN};
            color: {Palette.TEXT};
            border: 1px solid {Palette.BORDER_STRONG};
            border-radius: 3px;
            padding: 9px 12px;
            font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
            font-size: 18px;
            font-weight: 700;
        }}
        QLabel#destinationPath {{
            background: {Palette.SURFACE_SUNKEN};
            color: {Palette.TEXT_MUTED};
            border: 1px solid {Palette.BORDER};
            border-radius: 3px;
            padding: 9px 10px;
            font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
            font-size: 11px;
        }}
        QLineEdit,
        QComboBox,
        QSpinBox {{
            background: {Palette.SURFACE_RAISED};
            color: {Palette.TEXT};
            border: 1px solid {Palette.BORDER_STRONG};
            border-radius: 3px;
            min-height: 34px;
            padding: 4px 9px;
            selection-background-color: {Palette.INTERACTIVE};
            selection-color: {Palette.ON_INTERACTIVE};
        }}
        QLineEdit:hover,
        QComboBox:hover,
        QSpinBox:hover {{
            border-color: #587085;
        }}
        QLineEdit:focus,
        QComboBox:focus,
        QSpinBox:focus {{
            border: 2px solid {Palette.INTERACTIVE};
        }}
        QLineEdit:disabled,
        QComboBox:disabled,
        QSpinBox:disabled {{
            background: #0E151D;
            color: {Palette.DISABLED};
            border-color: #24313D;
        }}
        QComboBox QAbstractItemView {{
            background: {Palette.SURFACE_RAISED};
            color: {Palette.TEXT};
            border: 1px solid {Palette.BORDER_STRONG};
            selection-background-color: {Palette.INTERACTIVE};
            selection-color: {Palette.ON_INTERACTIVE};
            outline: none;
        }}
        QPushButton {{
            background: {Palette.SURFACE_RAISED};
            color: {Palette.TEXT};
            border: 1px solid {Palette.BORDER_STRONG};
            border-radius: 3px;
            min-height: 34px;
            padding: 6px 14px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background: {Palette.SURFACE_HOVER};
            border-color: #60798F;
        }}
        QPushButton:focus {{
            border: 2px solid {Palette.INTERACTIVE};
        }}
        QPushButton:pressed {{
            background: {Palette.SURFACE_SUNKEN};
        }}
        QPushButton:disabled {{
            background: #0E151D;
            color: {Palette.DISABLED};
            border-color: #24313D;
        }}
        QPushButton[variant="primary"] {{
            background: {Palette.INTERACTIVE};
            border-color: {Palette.INTERACTIVE};
            color: {Palette.ON_INTERACTIVE};
            font-weight: 750;
        }}
        QPushButton[variant="primary"]:hover {{
            background: {Palette.INTERACTIVE_HOVER};
            border-color: {Palette.INTERACTIVE_HOVER};
            color: {Palette.ON_INTERACTIVE};
        }}
        QPushButton[variant="primary"]:pressed {{
            background: {Palette.INTERACTIVE_PRESSED};
        }}
        QPushButton[variant="record"] {{
            background: {Palette.RECORD};
            border-color: {Palette.RECORD};
            color: #FFFFFF;
            font-weight: 750;
        }}
        QPushButton[variant="record"]:hover {{
            background: {Palette.RECORD_HOVER};
            border-color: {Palette.RECORD_HOVER};
            color: #FFFFFF;
        }}
        QPushButton[variant="record"]:pressed {{
            background: {Palette.RECORD_PRESSED};
        }}
        QPushButton[variant="ghost"] {{
            background: transparent;
            border-color: {Palette.BORDER};
            color: {Palette.TEXT_MUTED};
        }}
        QPushButton[variant="ghost"]:hover {{
            background: {Palette.SURFACE_HOVER};
            border-color: {Palette.BORDER_STRONG};
            color: {Palette.TEXT};
        }}
        QPushButton#navButton {{
            background: transparent;
            border: 1px solid transparent;
            color: {Palette.TEXT_MUTED};
            text-align: center;
            padding: 7px 12px;
            min-height: 38px;
            font-size: 14px;
            icon-size: 18px;
            border-radius: 6px;
        }}
        QPushButton#navButton:hover {{
            background: {Palette.SURFACE_HOVER};
            border-color: {Palette.BORDER};
            color: {Palette.TEXT};
        }}
        QPushButton#navButton:checked {{
            background: #203C3A;
            border-color: #2E6D67;
            border-bottom: 2px solid {Palette.INTERACTIVE};
            color: {Palette.TEXT};
            font-weight: 600;
        }}
        QPushButton#tileFocusButton {{
            min-height: 26px;
            padding: 3px 9px;
            font-size: 12px;
        }}
        QCheckBox {{
            color: {Palette.TEXT_MUTED};
            spacing: 8px;
            min-height: 26px;
        }}
        QCheckBox:hover {{
            color: {Palette.TEXT};
        }}
        QCheckBox:disabled {{
            color: {Palette.DISABLED};
        }}
        QCheckBox::indicator {{
            width: 17px;
            height: 17px;
            border: 1px solid {Palette.BORDER_STRONG};
            border-radius: 4px;
            background: {Palette.SURFACE_RAISED};
        }}
        QCheckBox::indicator:checked {{
            background: {Palette.INTERACTIVE};
            border-color: {Palette.INTERACTIVE};
        }}
        QSlider::groove:horizontal {{
            background: #263543;
            border: none;
            border-radius: 3px;
            height: 6px;
        }}
        QSlider::handle:horizontal {{
            background: {Palette.INTERACTIVE};
            border: 2px solid #B8FFF2;
            border-radius: 8px;
            width: 16px;
            margin: -6px 0;
        }}
        QSlider::sub-page:horizontal {{
            background: {Palette.INTERACTIVE};
            border-radius: 3px;
        }}
        QToolTip {{
            background: {Palette.SURFACE_RAISED};
            color: {Palette.TEXT};
            border: 1px solid {Palette.BORDER_STRONG};
            padding: 5px;
        }}
    """


def set_variant(widget: QWidget, variant: str) -> None:
    widget.setProperty("variant", variant)


def status_style(level: str, *, bold: bool = True) -> str:
    color = {
        "good": Palette.SUCCESS,
        "success": Palette.SUCCESS,
        "warn": Palette.WARNING,
        "warning": Palette.WARNING,
        "bad": Palette.DANGER,
        "danger": Palette.DANGER,
        "muted": Palette.TEXT_MUTED,
    }.get(level, Palette.TEXT)
    weight = "font-weight: 700;" if bold else ""
    return f"color: {color}; background: transparent; {weight}"
