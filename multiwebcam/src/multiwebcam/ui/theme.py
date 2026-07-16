"""Shared visual tokens and helpers for the Qt Widgets UI.

The capture console uses a low-glare dark palette so the camera feeds remain
the visual focus.  Tokens are named by role instead of colour to keep status
and interaction semantics consistent across every view.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget


class Primitive:
    """Raw design values; use semantic roles below in widgets and stylesheets."""

    INK_950 = "#07131D"
    INK_925 = "#0A1823"
    INK_900 = "#0C1B27"
    INK_850 = "#102431"
    INK_800 = "#12313A"
    INK_750 = "#183743"
    BORDER = "#203541"
    BORDER_STRONG = "#35505D"
    TEXT = "#EEF5F7"
    TEXT_MUTED = "#A9B8C2"
    TEXT_FAINT = "#6F8491"
    TEAL_700 = "#119D8C"
    TEAL_600 = "#22D7C0"
    TEAL_500 = "#43E4CF"
    TEAL_400 = "#7AECDD"
    TEAL_950 = "#0B2C2E"
    SKY_500 = "#4CA8FF"
    RED_700 = "#C13E48"
    RED_600 = "#E64D56"
    RED_500 = "#FF5D65"
    GREEN_500 = "#28D17C"
    GREEN_950 = "#0C2D25"
    GREEN_700 = "#236B4B"
    AMBER_500 = "#F2B84B"
    AMBER_950 = "#342918"
    AMBER_700 = "#80602B"
    RED_950 = "#321D24"
    RED_800 = "#763641"
    INK_DISABLED = "#0A161F"
    BORDER_DISABLED = "#1B303B"
    BORDER_INTERACTIVE = "#527887"
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
    CAPTION = 12
    META = 13
    BODY = 14
    CARD = 16
    SECTION = 18
    TITLE = 24


def app_stylesheet() -> str:
    """Return the application-wide Qt stylesheet."""
    chevron_down = Path(__file__).with_name("icons") / "chevron-down.svg"
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
        QScrollArea#sidePanelScroll {{
            background: transparent;
            border: none;
        }}
        QScrollArea#sidePanelScroll QScrollBar:vertical {{
            background: transparent;
            width: 7px;
            margin: 2px 0;
        }}
        QScrollArea#sidePanelScroll QScrollBar::handle:vertical {{
            background: {Palette.BORDER_STRONG};
            min-height: 36px;
            border-radius: 3px;
        }}
        QScrollArea#sidePanelScroll QScrollBar::handle:vertical:hover {{
            background: {Palette.INTERACTIVE};
        }}
        QScrollArea#sidePanelScroll QScrollBar::add-line:vertical,
        QScrollArea#sidePanelScroll QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollArea#sidePanelScroll QScrollBar::add-page:vertical,
        QScrollArea#sidePanelScroll QScrollBar::sub-page:vertical {{
            background: transparent;
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
            background: transparent;
            border: none;
            border-radius: 0;
        }}
        QFrame#globalStatusBar {{
            background: {Palette.SURFACE};
            border: 1px solid {Palette.BORDER};
            border-radius: {Radius.CARD}px;
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
        QFrame#settingsGroup {{
            background: {Palette.SURFACE};
            border: 1px solid {Palette.BORDER};
            border-radius: {Radius.CONTROL}px;
        }}
        QFrame#settingsRow {{
            background: {Palette.SURFACE_SUNKEN};
            border: none;
            border-left: 2px solid {Palette.BORDER_STRONG};
            border-radius: 3px;
        }}
        QFrame#cameraControlRow {{
            background: {Palette.SURFACE_SUNKEN};
            border: 1px solid {Palette.BORDER};
            border-radius: {Radius.CONTROL}px;
        }}
        QLabel#cameraControlLabel {{
            background: transparent;
            color: {Palette.TEXT_MUTED};
            font-size: 12px;
            font-weight: 600;
        }}
        QSpinBox#cameraValueEditor {{
            background: {Palette.SURFACE_ELEVATED};
            border: 1px solid {Palette.BORDER_STRONG};
            border-radius: {Radius.CONTROL}px;
            min-height: 32px;
            padding: 2px 6px;
            font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
            font-weight: 600;
        }}
        QSpinBox#cameraValueEditor:focus {{
            border: 2px solid {Palette.INTERACTIVE};
            color: {Palette.INTERACTIVE_HOVER};
        }}
        QComboBox#cameraMenuControl {{
            min-width: 0;
        }}
        QCheckBox#cameraBoolControl {{
            background: {Palette.SURFACE_RAISED};
            border: 1px solid {Palette.BORDER_STRONG};
            border-radius: {Radius.CONTROL}px;
            padding: 5px 8px;
        }}
        QLabel#settingsGroupTitle {{
            color: {Palette.TEXT};
            font-weight: 700;
            font-size: 13px;
        }}
        QLabel#settingsScope {{
            color: {Palette.INTERACTIVE_HOVER};
            background: {Palette.ACCENT_SURFACE};
            border: 1px solid {Palette.ACCENT_BORDER};
            border-radius: 8px;
            padding: 2px 6px;
            font-size: 10px;
        }}
        QLabel#settingsLabel {{
            color: {Palette.TEXT};
            font-weight: 600;
            font-size: 12px;
        }}
        QLabel#settingsHint {{
            color: {Palette.TEXT_FAINT};
            font-size: 10px;
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
            font-weight: 700;
            padding-top: 3px;
        }}
        QLabel#cameraChip {{
            color: {Palette.TEXT};
            background: transparent;
            border: none;
            padding: 0;
            font-size: {TypeScale.CARD}px;
            font-weight: 600;
        }}
        QLabel#stateChip {{
            color: {Palette.SUCCESS};
            background: transparent;
            border: none;
            padding: 2px 0;
            font-size: 12px;
            font-weight: 600;
        }}
        QLabel#stateChip[status="muted"] {{
            color: {Palette.TEXT_MUTED};
        }}
        QLabel#stateChip[status="warn"] {{
            color: {Palette.WARNING};
        }}
        QLabel#stateChip[status="bad"] {{
            color: {Palette.DANGER};
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
        QLabel#captionLabel[status="good"] {{ color: {Palette.SUCCESS}; font-weight: 600; }}
        QLabel#captionLabel[status="warn"] {{ color: {Palette.WARNING}; font-weight: 600; }}
        QLabel#captionLabel[status="bad"] {{ color: {Palette.DANGER}; font-weight: 600; }}
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
            background: transparent;
            color: {Palette.TEXT_MUTED};
            border: none;
            padding: 0;
            font-weight: 400;
        }}
        QLabel#overviewStatus[status="muted"] {{ color: {Palette.TEXT_MUTED}; }}
        QLabel#overviewStatus[status="good"] {{
            color: {Palette.SUCCESS};
        }}
        QLabel#overviewStatus[status="warn"] {{
            color: {Palette.WARNING};
        }}
        QLabel#overviewStatus[status="bad"] {{
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
        QSpinBox,
        QDoubleSpinBox {{
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
        QSpinBox:hover,
        QDoubleSpinBox:hover {{
            border-color: {Palette.INPUT_HOVER_BORDER};
        }}
        QLineEdit:focus,
        QComboBox:focus,
        QSpinBox:focus,
        QDoubleSpinBox:focus {{
            border: 2px solid {Palette.INTERACTIVE};
        }}
        QLineEdit:disabled,
        QComboBox:disabled,
        QSpinBox:disabled,
        QDoubleSpinBox:disabled {{
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
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 32px;
            background: {Palette.SURFACE_ELEVATED};
            border: none;
            border-left: 1px solid {Palette.BORDER_STRONG};
            border-top-right-radius: {Radius.CONTROL}px;
            border-bottom-right-radius: {Radius.CONTROL}px;
        }}
        QComboBox::drop-down:hover {{
            background: {Palette.ACCENT_SURFACE};
        }}
        QComboBox::down-arrow {{
            image: url("{chevron_down}");
            width: 16px;
            height: 16px;
        }}
        QWidget#numericStepper {{
            background: {Palette.SURFACE_RAISED};
            border: 1px solid {Palette.BORDER_STRONG};
            border-radius: {Radius.CONTROL}px;
        }}
        QSpinBox#stepperEditor,
        QDoubleSpinBox#stepperEditor {{
            background: transparent;
            border: none;
            border-radius: 0;
            min-height: 36px;
            padding: 4px 2px;
            font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace;
            font-weight: 600;
        }}
        QSpinBox#stepperEditor:focus,
        QDoubleSpinBox#stepperEditor:focus {{
            border: none;
            color: {Palette.INTERACTIVE_HOVER};
        }}
        QPushButton#stepperButton {{
            background: transparent;
            color: {Palette.TEXT_MUTED};
            border: none;
            border-radius: 0;
            min-height: 36px;
            min-width: 36px;
            max-width: 36px;
            padding: 0;
            font-size: 18px;
            font-weight: 500;
        }}
        QPushButton#stepperButton:hover {{
            background: {Palette.ACCENT_SURFACE};
            color: {Palette.INTERACTIVE_HOVER};
        }}
        QPushButton#stepperButton:pressed {{
            background: {Palette.INTERACTIVE};
            color: {Palette.ON_INTERACTIVE};
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
            background: {Palette.ACCENT_SURFACE};
            border-color: {Palette.ACCENT_BORDER};
            color: {Palette.INTERACTIVE_HOVER};
            font-weight: 600;
        }}
        QPushButton[variant="primary"]:hover {{
            background: {Palette.INTERACTIVE_HOVER};
            border-color: {Palette.INTERACTIVE_HOVER};
            color: {Palette.BACKGROUND};
        }}
        QPushButton[variant="primary"]:pressed {{
            background: {Palette.INTERACTIVE_PRESSED};
        }}
        QPushButton[variant="record"] {{
            background: {Palette.DANGER_SURFACE};
            border-color: {Palette.DANGER_BORDER};
            color: {Palette.DANGER};
            font-weight: 600;
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
            min-height: 42px;
            font-size: 14px;
            icon-size: 18px;
            border-radius: 6px;
        }}
        QPushButton#navButton:hover {{
            background: {Palette.SURFACE_HOVER};
            border-color: transparent;
            color: {Palette.TEXT};
        }}
        QPushButton#navButton:checked {{
            background: {Palette.ACCENT_SURFACE};
            border-color: transparent;
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
        QCheckBox#settingToggle {{
            background: {Palette.SURFACE_RAISED};
            border: 1px solid {Palette.BORDER_STRONG};
            border-radius: {Radius.CONTROL}px;
            padding: 5px 8px;
            color: {Palette.TEXT_MUTED};
        }}
        QCheckBox#settingToggle:hover {{
            background: {Palette.SURFACE_HOVER};
            color: {Palette.TEXT};
        }}
        QCheckBox#settingToggle:checked {{
            background: {Palette.ACCENT_SURFACE};
            border-color: {Palette.ACCENT_BORDER};
            color: {Palette.INTERACTIVE_HOVER};
        }}
        QCheckBox#settingToggle::indicator {{
            width: 24px;
            height: 12px;
            border-radius: 7px;
            background: {Palette.SURFACE_SUNKEN};
            border: 1px solid {Palette.BORDER_STRONG};
        }}
        QCheckBox#settingToggle::indicator:checked {{
            background: {Palette.INTERACTIVE};
            border-color: {Palette.INTERACTIVE_HOVER};
        }}
        QCheckBox#ignoreToggle {{
            background: transparent;
            color: {Palette.TEXT_FAINT};
            border: 1px solid {Palette.BORDER};
            border-radius: 11px;
            min-height: 22px;
            padding: 1px 8px 1px 6px;
            spacing: 6px;
            font-size: 11px;
            font-weight: 600;
        }}
        QCheckBox#ignoreToggle:hover {{
            background: {Palette.WARNING_SURFACE};
            border-color: {Palette.WARNING_BORDER};
            color: {Palette.WARNING};
        }}
        QCheckBox#ignoreToggle:checked {{
            background: {Palette.WARNING_SURFACE};
            border-color: {Palette.WARNING_BORDER};
            color: {Palette.WARNING};
        }}
        QCheckBox#ignoreToggle::indicator {{
            width: 7px;
            height: 7px;
            border: none;
            border-radius: 4px;
            background: {Palette.TEXT_FAINT};
        }}
        QCheckBox#ignoreToggle::indicator:checked {{
            background: {Palette.WARNING};
            border: none;
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
        QFrame#brandIcon {{
            background: {Palette.ACCENT_SURFACE};
            border: 1px solid {Palette.ACCENT_BORDER};
            border-radius: 10px;
        }}
        QLabel#brandTitle {{
            color: {Palette.TEXT};
            font-size: 22px;
            font-weight: 600;
        }}
        QFrame#navigationResources {{
            background: transparent;
            border: none;
        }}
        QFrame#navigationResources QFrame#statusBadge {{
            background: {Palette.SURFACE};
            border: 1px solid {Palette.BORDER};
            border-radius: {Radius.CONTROL}px;
        }}
        QFrame#dashboardCard {{
            background: {Palette.SURFACE};
            border: 1px solid {Palette.BORDER};
            border-radius: {Radius.CARD}px;
        }}
        QLabel#cardTitle {{
            color: {Palette.TEXT};
            font-size: {TypeScale.CARD}px;
            font-weight: 600;
        }}
        QLabel#cardKicker {{
            color: {Palette.TEXT_FAINT};
            font-size: {TypeScale.CAPTION}px;
        }}
        QLabel#cardKicker[status="good"] {{ color: {Palette.SUCCESS}; }}
        QLabel#cardKicker[status="warn"] {{ color: {Palette.WARNING}; }}
        QFrame#statusRow {{
            background: transparent;
            border: none;
            border-bottom: 1px solid {Palette.BORDER};
        }}
        QLabel#rowIcon {{
            color: {Palette.TEXT_FAINT};
            font-size: {TypeScale.META}px;
        }}
        QLabel#rowName {{
            color: {Palette.TEXT_MUTED};
            font-size: {TypeScale.META}px;
        }}
        QLabel#rowValue {{
            color: {Palette.TEXT};
            font-size: {TypeScale.META}px;
            font-weight: 500;
        }}
        QLabel#metricValue {{
            color: {Palette.INTERACTIVE_HOVER};
            font-size: 24px;
            font-weight: 600;
        }}
        QLabel#metricUnit,
        QLabel#metricCaption {{
            color: {Palette.TEXT_FAINT};
            font-size: {TypeScale.CAPTION}px;
        }}
        QLabel#qualityDot[level="good"] {{ color: {Palette.SUCCESS}; }}
        QLabel#qualityDot[level="warn"] {{ color: {Palette.WARNING}; }}
        QLabel#qualityDot[level="bad"] {{ color: {Palette.DANGER}; }}
        QLabel#alertText[level="info"] {{ color: {Palette.INFO}; }}
        QLabel#alertText[level="warn"] {{ color: {Palette.WARNING}; }}
        QLabel#alertText[level="bad"] {{ color: {Palette.DANGER}; }}
        QLabel#alertTime {{
            color: {Palette.TEXT_FAINT};
            font-size: {TypeScale.CAPTION}px;
        }}
        QFrame#cameraHeader,
        QFrame#cameraFooter {{
            background: transparent;
            border: none;
        }}
        QFrame#cameraStateDot {{
            background: {Palette.SUCCESS};
            border: none;
            border-radius: 5px;
        }}
        QFrame#cameraStateDot[status="warn"] {{ background: {Palette.WARNING}; }}
        QFrame#cameraStateDot[status="bad"] {{ background: {Palette.DANGER}; }}
        QFrame#cameraStateDot[status="muted"] {{ background: {Palette.TEXT_FAINT}; }}
        QLabel#parameterChip {{
            background: {Palette.ACCENT_SURFACE};
            color: {Palette.INTERACTIVE_HOVER};
            border: 1px solid {Palette.ACCENT_BORDER};
            border-radius: 6px;
            padding: 2px 6px;
            font-size: {TypeScale.CAPTION}px;
        }}
        QLabel#parameterChip[level="warn"] {{
            background: {Palette.WARNING_SURFACE};
            color: {Palette.WARNING};
            border-color: {Palette.WARNING_BORDER};
        }}
        QLabel#parameterChip[level="bad"] {{
            background: {Palette.DANGER_SURFACE};
            color: {Palette.DANGER};
            border-color: {Palette.DANGER_BORDER};
        }}
        QPushButton#toolbarButton {{
            min-height: 32px;
            padding: 4px 10px;
            background: {Palette.SURFACE};
            border-color: {Palette.BORDER};
        }}
        QFrame#bottomStatusBar {{
            background: {Palette.SURFACE};
            border: none;
            border-top: 1px solid {Palette.BORDER};
            border-radius: 0;
        }}
        QFrame#bottomStatusCell {{
            background: transparent;
            border-right: 1px solid {Palette.BORDER};
            border-radius: 0;
        }}
        QFrame#bottomStatusBar QFrame#statusBadge {{
            border: none;
            border-radius: {Radius.CONTROL}px;
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
