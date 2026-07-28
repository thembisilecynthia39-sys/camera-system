"""Semantic stylesheet shared by the application shell.

The shell deliberately uses a light work surface around a compact navy
navigation rail.  Camera imagery keeps its own low-glare dark presentation in
``multiwebcam``; forms, history and diagnostics remain easy to scan in normal
desktop lighting.
"""


def application_stylesheet() -> str:
    """Return the unified Jetson workstation theme."""

    return """
    QWidget {
        background: #F3F6FA;
        color: #172033;
        font-family: "Noto Sans CJK SC", "Noto Sans", sans-serif;
        font-size: 15px;
    }
    QMainWindow, QStackedWidget, QWidget#pageSurface {
        background: #F3F6FA;
    }
    QWidget#capturePageSurface,
    QWidget#resultPageSurface,
    QStackedWidget#captureHost {
        background: #07131D;
    }
    QWidget#capturePageSurface QLabel,
    QWidget#resultPageSurface QLabel {
        color: #DDE8EF;
    }
    QWidget#capturePageSurface QLabel#mutedText,
    QWidget#resultPageSurface QLabel#mutedText,
    QWidget#resultPageSurface QLabel#pageDescription {
        color: #9FB0BC;
    }
    QWidget#resultPageSurface QLabel#pageTitle {
        color: #EEF5F7;
    }
    QLabel {
        background: transparent;
    }
    QFrame#sidebar {
        background: #142238;
        border: none;
        border-right: 1px solid #22334B;
    }
    QFrame#brandBlock {
        background: #192B44;
        border: 1px solid #2B405C;
        border-radius: 12px;
    }
    QLabel#brandTitle {
        font-size: 20px;
        font-weight: 700;
        color: #FFFFFF;
    }
    QLabel#brandSubtitle {
        color: #B9C7D9;
        font-size: 13px;
    }
    QLabel#pageDescription, QLabel#mutedText {
        color: #65738A;
    }
    QLabel#pageTitle {
        font-size: 26px;
        font-weight: 700;
        color: #172033;
    }
    QListWidget#primaryNavigation {
        background: transparent;
        border: none;
        outline: none;
    }
    QListWidget#primaryNavigation::item {
        min-height: 48px;
        padding: 0 14px;
        margin: 3px 0;
        border-radius: 8px;
        color: #C6D1E0;
    }
    QListWidget#primaryNavigation::item:selected {
        background: #214365;
        color: #FFFFFF;
        border-left: 3px solid #35C6B4;
    }
    QListWidget#primaryNavigation::item:hover:!selected {
        background: #1A304B;
        color: #FFFFFF;
    }
    QLabel#sidebarVersion {
        color: #8FA1B9;
        font-size: 12px;
    }
    QFrame#contentCard, QFrame#statusBanner {
        background: #FFFFFF;
        border: 1px solid #DCE3EC;
        border-radius: 12px;
    }
    QFrame#statusBanner[status="warning"] {
        background: #FFF8E8;
        border-color: #F2D18A;
        color: #674A0C;
    }
    QFrame#statusBanner[status="success"] {
        background: #EAF8F4;
        border-color: #9DD8C9;
        color: #175C50;
    }
    QWidget#capturePageSurface QFrame#statusBanner,
    QWidget#resultPageSurface QFrame#statusBanner {
        background: #0A1B27;
        border-color: #27404F;
        color: #C8D8E1;
    }
    QWidget#capturePageSurface QFrame#statusBanner {
        border-left: none;
        border-right: none;
        border-top: none;
        border-radius: 0;
    }
    QWidget#capturePageSurface QFrame#statusBanner[status="warning"],
    QWidget#resultPageSurface QFrame#statusBanner[status="warning"] {
        background: #2C2418;
        border-color: #72582D;
        color: #F4C96A;
    }
    QWidget#capturePageSurface QFrame#statusBanner[status="success"],
    QWidget#resultPageSurface QFrame#statusBanner[status="success"] {
        background: #0C2A28;
        border-color: #23665E;
        color: #7AECDD;
    }
    QWidget#resultPageSurface QFrame#contentCard {
        background: #0A1823;
        border-color: #203541;
    }
    QWidget#resultPageSurface QPushButton {
        background: #12313A;
        color: #E3EDF2;
        border-color: #35505D;
    }
    QWidget#resultPageSurface QPushButton:hover {
        background: #183F49;
        border-color: #527887;
    }
    QWidget#resultPageSurface QPushButton:disabled {
        color: #6F8491;
        background: #0A161F;
        border-color: #1B303B;
    }
    QWidget#resultPageSurface QPushButton#primaryButton {
        background: #22D7C0;
        color: #07131D;
        border-color: #22D7C0;
    }
    QWidget#resultPageSurface QPushButton#primaryButton:hover {
        background: #43E4CF;
    }
    QLabel#sectionTitle {
        font-size: 18px;
        font-weight: 700;
    }
    QPushButton {
        min-height: 40px;
        padding: 0 16px;
        background: #FFFFFF;
        color: #253047;
        border: 1px solid #C9D3E0;
        border-radius: 8px;
    }
    QPushButton:hover {
        background: #F5F8FC;
        border-color: #8394AA;
    }
    QPushButton:focus {
        border: 2px solid #2878D0;
    }
    QPushButton:disabled {
        color: #98A4B5;
        background: #EEF2F6;
        border-color: #DCE3EC;
    }
    QPushButton#primaryButton {
        background: #1769B0;
        color: #FFFFFF;
        border-color: #1769B0;
        font-weight: 700;
    }
    QPushButton#primaryButton:hover {
        background: #115A99;
    }
    QLineEdit, QComboBox, QPlainTextEdit {
        min-height: 42px;
        background: #FFFFFF;
        color: #172033;
        border: 1px solid #C9D3E0;
        border-radius: 8px;
        padding: 4px 9px;
        selection-background-color: #2878D0;
    }
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {
        border: 2px solid #2878D0;
    }
    QTableWidget {
        background: #FFFFFF;
        alternate-background-color: #F8FAFD;
        color: #253047;
        border: 1px solid #DCE3EC;
        border-radius: 10px;
        gridline-color: transparent;
        selection-background-color: #E4F0FC;
        selection-color: #172033;
        outline: none;
    }
    QTableWidget::item {
        padding: 8px 10px;
        border-bottom: 1px solid #E8EDF3;
    }
    QHeaderView::section {
        background: #EEF3F8;
        color: #46556C;
        border: none;
        border-bottom: 1px solid #D3DCE7;
        padding: 10px;
        font-size: 13px;
        font-weight: 700;
    }
    QFrame#historySummary {
        background: #FFFFFF;
        border: 1px solid #DCE3EC;
        border-radius: 10px;
    }
    QLabel#historyCount {
        color: #26344B;
        font-weight: 700;
    }
    QLabel#historyHint {
        color: #718096;
        font-size: 13px;
    }
    QWidget#historyActions {
        background: transparent;
    }
    QPushButton#tablePrimaryAction {
        min-height: 32px;
        max-height: 32px;
        padding: 0 12px;
        background: #E8F2FC;
        color: #155F9F;
        border: 1px solid #BBD6EE;
        font-size: 13px;
        font-weight: 700;
    }
    QPushButton#tablePrimaryAction:hover {
        background: #DCECFB;
        border-color: #82B5DF;
    }
    QToolButton#tableMoreAction {
        min-width: 34px;
        max-width: 34px;
        min-height: 32px;
        max-height: 32px;
        padding: 0;
        background: #FFFFFF;
        color: #526178;
        border: 1px solid #C9D3E0;
        border-radius: 7px;
        font-weight: 700;
    }
    QToolButton#tableMoreAction:hover {
        background: #F2F6FA;
    }
    QMenu {
        background: #FFFFFF;
        color: #253047;
        border: 1px solid #C9D3E0;
        padding: 5px;
    }
    QMenu::item {
        min-height: 30px;
        padding: 4px 22px 4px 12px;
        border-radius: 5px;
    }
    QMenu::item:selected {
        background: #E8F2FC;
        color: #155F9F;
    }
    QLabel#taskStateBadge {
        border-radius: 10px;
        padding: 4px 9px;
        font-size: 12px;
        font-weight: 700;
    }
    QLabel#taskStateBadge[state="success"] {
        background: #E3F6EF;
        color: #176A56;
        border: 1px solid #A8DDCF;
    }
    QLabel#taskStateBadge[state="danger"] {
        background: #FDECEC;
        color: #A83939;
        border: 1px solid #F1B9B9;
    }
    QLabel#taskStateBadge[state="active"] {
        background: #E7F1FC;
        color: #1764A5;
        border: 1px solid #B7D4EE;
    }
    QLabel#taskStateBadge[state="warning"] {
        background: #FFF4D9;
        color: #805B0B;
        border: 1px solid #EFD18D;
    }
    QLabel#taskStateBadge[state="neutral"] {
        background: #EEF2F6;
        color: #58667A;
        border: 1px solid #D3DCE7;
    }
    QStatusBar {
        background: #FFFFFF;
        color: #56657A;
        border-top: 1px solid #DCE3EC;
    }
    QStatusBar[mode="operational"] {
        background: #0A1823;
        color: #A9B8C2;
        border-top: 1px solid #203541;
    }
    """
