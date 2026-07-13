"""Shared visual tokens and helpers for the Qt Widgets UI.

The capture console uses a low-glare dark palette so the camera feeds remain
the visual focus.  Tokens are named by role instead of colour to keep status
and interaction semantics consistent across every view.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


class Primitive:
    """Raw design values; use semantic roles below in widgets and stylesheets."""

    INK_950 = "#071117"
    INK_925 = "#0B1821"
    INK_900 = "#10232E"
    INK_850 = "#162D39"
    INK_800 = "#1D3947"
    INK_750 = "#274857"
    BORDER = "#27404D"
    BORDER_STRONG = "#426170"
    TEXT = "#F1F7F8"
    TEXT_MUTED = "#B2C4CC"
    TEXT_FAINT = "#7D949F"
    TEAL_700 = "#138E83"
    TEAL_600 = "#1EAF9F"
    TEAL_500 = "#36D0BE"
    TEAL_400 = "#76E4D5"
    TEAL_950 = "#0B2A2A"
    SKY_500 = "#66B8F3"
    RED_700 = "#B74153"
    RED_600 = "#D85868"
    RED_500 = "#EB7180"
    GREEN_500 = "#4BCD96"
    GREEN_950 = "#10352D"
    GREEN_700 = "#2D7259"
    AMBER_500 = "#EABA69"
    AMBER_950 = "#3A2D1A"
    AMBER_700 = "#8A6631"
    RED_950 = "#3A2028"
    RED_800 = "#87404D"
    INK_DISABLED = "#0D1B23"
    BORDER_DISABLED = "#223640"
    BORDER_INTERACTIVE = "#5B8796"
    WHITE = "#FFFFFF"


class Palette:
    """Semantic colour roles for the capture workstation."""

    BACKGROUND = Primitive.INK_950
    SURFACE = Primitive.INK_925
    SURFACE_RAISED = Primitive.INK_850
    SURFACE_ELEVATED = Primitive.INK_800
    SURFACE_SUNKEN = Primitive.INK_950
    SURFACE_HOVER = Primitive.INK_750
    BORDER = Primitive.BORDER
    BORDER_STRONG = Primitive.BORDER_STRONG
    TEXT = Primitive.TEXT
    TEXT_MUTED = Primitive.TEXT_MUTED
    TEXT_FAINT = Primitive.TEXT_FAINT
    INTERACTIVE = Primitive.TEAL_600
    INTERACTIVE_HOVER = Primitive.TEAL_500
    INTERACTIVE_PRESSED = Primitive.TEAL_700
    ON_INTERACTIVE = Primitive.INK_950
    RECORD = Primitive.RED_600
    RECORD_HOVER = Primitive.RED_500
    RECORD_PRESSED = Primitive.RED_700
    RECORD_ON = Primitive.INK_950
    SUCCESS = Primitive.GREEN_500
    WARNING = Primitive.AMBER_500
    DANGER = Primitive.RED_500
    INFO = Primitive.SKY_500
    DISABLED = Primitive.TEXT_FAINT

    # Component semantic roles.
    TOP_NAV = Primitive.INK_925
    VIDEO_BORDER = Primitive.INK_800
    IGNORED_VIDEO = Primitive.INK_900
    CHIP_BACKGROUND = Primitive.INK_800
    CHIP_BORDER = Primitive.BORDER_STRONG
    ACCENT_SURFACE = Primitive.TEAL_950
    ACCENT_BORDER = Primitive.TEAL_700
    SUCCESS_SURFACE = Primitive.GREEN_950
    SUCCESS_BORDER = Primitive.GREEN_700
    WARNING_SURFACE = Primitive.AMBER_950
    WARNING_BORDER = Primitive.AMBER_700
    DANGER_SURFACE = Primitive.RED_950
    DANGER_BORDER = Primitive.RED_800
    DISABLED_SURFACE = Primitive.INK_DISABLED
    DISABLED_BORDER = Primitive.BORDER_DISABLED
    INPUT_HOVER_BORDER = Primitive.BORDER_INTERACTIVE
    SLIDER_TRACK = Primitive.INK_800
    SLIDER_HANDLE_BORDER = Primitive.TEAL_400


class Spacing:
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32


class Radius:
    CONTROL = 7
    CARD = 10
    PANEL = 12


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
            background: {Palette.TOP_NAV};
            border: none;
            border-bottom: 1px solid {Palette.BORDER};
            border-radius: 0;
        }}
        QFrame#contextPanel,
        QFrame#sidePanel {{
            background: {Palette.SURFACE};
            border: 1px solid {Palette.BORDER};
            border-radius: {Radius.PANEL}px;
        }}
        QFrame#globalStatusBar {{
            background: {Palette.SURFACE};
            border: 1px solid {Palette.BORDER};
            border-radius: {Radius.PANEL}px;
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
            border-radius: {Radius.PANEL}px;
        }}
        QFrame#cameraTile {{
            background: {Palette.SURFACE};
            border: 1px solid {Palette.BORDER};
            border-radius: {Radius.CARD}px;
        }}
        QFrame#cameraTile:hover {{
            border-color: {Palette.BORDER_STRONG};
        }}
        QFrame#cameraTile[ignored="true"] {{
            background: {Palette.SURFACE};
            border-color: {Palette.BORDER};
        }}
        QFrame#videoShell {{
            background: {Palette.SURFACE_SUNKEN};
            border: 1px solid {Palette.VIDEO_BORDER};
            border-radius: {Radius.CONTROL}px;
        }}
        QLabel#videoPreview {{
            background: {Palette.SURFACE_SUNKEN};
            color: {Palette.TEXT_MUTED};
            border: none;
            border-radius: {Radius.CONTROL}px;
        }}
        QLabel#videoPreview[ignored="true"] {{
            background: {Palette.IGNORED_VIDEO};
            border: 1px dashed {Palette.BORDER};
        }}
        QFrame#modelViewportControls {{
            background: rgba(7, 17, 23, 230);
            border: 1px solid {Palette.BORDER_STRONG};
            border-radius: {Radius.PANEL}px;
        }}
        QFrame#metricStrip {{
            background: {Palette.SURFACE_RAISED};
            border: none;
            border-top: 1px solid {Palette.BORDER};
            border-radius: {Radius.CONTROL}px;
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
        QScrollBar::handle:vertical:hover {{
            background: {Palette.INTERACTIVE};
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QLabel {{
            background: transparent;
        }}
        QLabel#brandMark {{
            color: {Palette.INTERACTIVE_HOVER};
            font-size: 12px;
            font-weight: 700;
        }}
        QLabel#pageTitle {{
            color: {Palette.TEXT};
            font-size: 22px;
            font-weight: 700;
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
            font-weight: 700;
            padding-top: 3px;
        }}
        QLabel#cameraChip {{
            background: {Palette.CHIP_BACKGROUND};
            color: {Palette.TEXT};
            border: 1px solid {Palette.CHIP_BORDER};
            border-radius: {Radius.CONTROL}px;
            padding: 4px 8px;
            font-size: 12px;
            font-weight: 700;
        }}
        QLabel#stateChip {{
            background: {Palette.SUCCESS_SURFACE};
            color: {Palette.SUCCESS};
            border: 1px solid {Palette.SUCCESS_BORDER};
            border-radius: 9px;
            padding: 3px 8px;
            font-size: 12px;
            font-weight: 600;
        }}
        QLabel#stateChip[status="muted"] {{
            background: {Palette.SURFACE_RAISED};
            color: {Palette.TEXT_MUTED};
            border-color: {Palette.BORDER};
        }}
        QLabel#liveBadge {{
            background: {Palette.SUCCESS_SURFACE};
            color: {Palette.SUCCESS};
            border: 1px solid {Palette.SUCCESS_BORDER};
            border-radius: 10px;
            padding: 6px 11px;
            font-size: 12px;
            font-weight: 700;
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
            background: {Palette.SURFACE_ELEVATED};
            color: {Palette.TEXT};
            border: 1px solid {Palette.BORDER};
            border-radius: {Radius.CONTROL}px;
            padding: 8px 10px;
            font-weight: 500;
        }}
        QLabel#statusPill[status="muted"] {{
            color: {Palette.TEXT_MUTED};
        }}
        QLabel#statusPill[status="good"] {{
            background: {Palette.SUCCESS_SURFACE};
            color: {Palette.SUCCESS};
            border-color: {Palette.SUCCESS_BORDER};
        }}
        QLabel#statusPill[status="warn"] {{
            background: {Palette.WARNING_SURFACE};
            color: {Palette.WARNING};
            border-color: {Palette.WARNING_BORDER};
        }}
        QLabel#statusPill[status="bad"] {{
            background: {Palette.DANGER_SURFACE};
            color: {Palette.DANGER};
            border-color: {Palette.DANGER_BORDER};
        }}
        QLabel#overviewStatus {{
            background: {Palette.SURFACE_RAISED};
            color: {Palette.TEXT};
            border: 1px solid {Palette.BORDER};
            border-radius: {Radius.CONTROL}px;
            padding: 9px 10px;
            font-weight: 500;
        }}
        QLabel#overviewStatus[status="muted"] {{ color: {Palette.TEXT_MUTED}; }}
        QLabel#overviewStatus[status="good"] {{
            background: {Palette.SUCCESS_SURFACE};
            border-color: {Palette.SUCCESS_BORDER};
            color: {Palette.SUCCESS};
        }}
        QLabel#overviewStatus[status="warn"] {{
            background: {Palette.WARNING_SURFACE};
            border-color: {Palette.WARNING_BORDER};
            color: {Palette.WARNING};
        }}
        QLabel#overviewStatus[status="bad"] {{
            background: {Palette.DANGER_SURFACE};
            border-color: {Palette.DANGER_BORDER};
            color: {Palette.DANGER};
        }}
        QLabel#timerLabel {{
            background: {Palette.SURFACE_SUNKEN};
            color: {Palette.TEXT};
            border: 1px solid {Palette.BORDER_STRONG};
            border-radius: {Radius.CONTROL}px;
            padding: 10px 12px;
            font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
            font-size: 20px;
            font-weight: 700;
        }}
        QLabel#destinationPath {{
            background: {Palette.SURFACE_SUNKEN};
            color: {Palette.TEXT_MUTED};
            border: 1px solid {Palette.BORDER};
            border-radius: {Radius.CONTROL}px;
            padding: 9px 10px;
            font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
            font-size: 12px;
        }}
        QLineEdit,
        QComboBox,
        QSpinBox {{
            background: {Palette.SURFACE_RAISED};
            color: {Palette.TEXT};
            border: 1px solid {Palette.BORDER_STRONG};
            border-radius: {Radius.CONTROL}px;
            min-height: 36px;
            padding: 5px 10px;
            selection-background-color: {Palette.INTERACTIVE};
            selection-color: {Palette.ON_INTERACTIVE};
        }}
        QLineEdit:hover,
        QComboBox:hover,
        QSpinBox:hover {{
            border-color: {Palette.INPUT_HOVER_BORDER};
        }}
        QLineEdit:focus,
        QComboBox:focus,
        QSpinBox:focus {{
            border: 2px solid {Palette.INTERACTIVE};
        }}
        QLineEdit:disabled,
        QComboBox:disabled,
        QSpinBox:disabled {{
            background: {Palette.DISABLED_SURFACE};
            color: {Palette.DISABLED};
            border-color: {Palette.DISABLED_BORDER};
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
            border-radius: {Radius.CONTROL}px;
            min-height: 36px;
            padding: 7px 15px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background: {Palette.SURFACE_HOVER};
            border-color: {Palette.INPUT_HOVER_BORDER};
        }}
        QPushButton:focus {{
            border: 2px solid {Palette.INTERACTIVE};
        }}
        QPushButton:pressed {{
            background: {Palette.SURFACE_SUNKEN};
        }}
        QPushButton:disabled {{
            background: {Palette.DISABLED_SURFACE};
            color: {Palette.DISABLED};
            border-color: {Palette.DISABLED_BORDER};
        }}
        QPushButton[variant="primary"] {{
            background: {Palette.INTERACTIVE};
            border-color: {Palette.INTERACTIVE};
            color: {Palette.ON_INTERACTIVE};
            font-weight: 700;
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
            color: {Palette.RECORD_ON};
            font-weight: 700;
        }}
        QPushButton[variant="record"]:hover {{
            background: {Palette.RECORD_HOVER};
            border-color: {Palette.RECORD_HOVER};
            color: {Palette.RECORD_ON};
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
            background: {Palette.ACCENT_SURFACE};
            border-color: {Palette.ACCENT_BORDER};
            border-bottom: 2px solid {Palette.INTERACTIVE};
            color: {Palette.INTERACTIVE_HOVER};
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
            background: {Palette.SLIDER_TRACK};
            border: none;
            border-radius: 3px;
            height: 6px;
        }}
        QSlider::handle:horizontal {{
            background: {Palette.INTERACTIVE};
            border: 2px solid {Palette.SLIDER_HANDLE_BORDER};
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
