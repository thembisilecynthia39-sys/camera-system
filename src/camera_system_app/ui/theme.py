"""Token-driven QSS shared by the Jetson workstation shell."""

from string import Template

from camera_system_app.ui.design_tokens import style_tokens


_QSS = Template(
    """
    QWidget {
        background: $light_background;
        color: $light_text;
        font-family: "Noto Sans CJK SC", "Noto Sans", sans-serif;
        font-size: $font_body;
    }
    QMainWindow, QStackedWidget, QWidget#pageSurface {
        background: $light_background;
    }
    QLabel {
        background: transparent;
    }
    QLabel#eyebrow {
        color: $light_interactive;
        font-size: $font_caption;
        font-weight: 700;
    }
    QLabel#pageTitle {
        color: $light_text;
        font-size: $font_title;
        font-weight: 700;
    }
    QLabel#pageDescription, QLabel#mutedText {
        color: $light_text_muted;
    }
    QLabel#sectionTitle {
        color: $light_text;
        font-size: $font_section;
        font-weight: 700;
    }
    QLabel#sectionDescription {
        color: $light_text_muted;
        font-size: $font_caption;
    }

    QFrame#sidebar {
        background: $dark_surface_raised;
        border: none;
        border-right: 1px solid $dark_border;
    }
    QFrame#brandBlock {
        background: $dark_surface_selected;
        border: 1px solid $dark_border;
        border-radius: $radius_lg;
    }
    QLabel#brandTitle {
        color: $dark_text;
        font-size: $font_subtitle;
        font-weight: 700;
    }
    QLabel#brandSubtitle, QLabel#sidebarVersion, QLabel#workstationStatus {
        color: $dark_text_muted;
        font-size: $font_caption;
    }
    QLabel#navigationSection {
        color: $dark_text_muted;
        font-size: $font_caption;
        font-weight: 700;
    }
    QListWidget#primaryNavigation {
        background: transparent;
        border: none;
        outline: none;
    }
    QListWidget#primaryNavigation::item {
        min-height: $nav_item_height;
        padding: 0 $space_4;
        margin: $space_1 0;
        border-radius: $radius_md;
        color: $dark_text_muted;
    }
    QListWidget#primaryNavigation::item:selected {
        background: $dark_surface_selected;
        color: $dark_text;
        border-left: 3px solid $dark_interactive;
    }
    QListWidget#primaryNavigation::item:hover:!selected {
        background: $dark_surface;
        color: $dark_text;
    }
    QListWidget#primaryNavigation::item:focus {
        border: $focus_width solid $dark_focus;
    }

    QFrame#contentCard, QFrame#sectionCard, QFrame#historySummary {
        background: $light_surface;
        border: 1px solid $light_border;
        border-radius: $radius_lg;
    }
    QFrame#statusBanner {
        background: $light_interactive_subtle;
        border: 1px solid $light_interactive_border;
        border-radius: $radius_md;
        color: $light_interactive;
    }
    QFrame#statusBanner[status="info"] {
        background: $light_interactive_subtle;
        border-color: $light_interactive_border;
        color: $light_interactive;
    }
    QFrame#statusBanner[status="success"] {
        background: $light_success_background;
        border-color: $light_operational;
        color: $light_success;
    }
    QFrame#statusBanner[status="warning"] {
        background: $light_warning_background;
        border-color: $light_warning;
        color: $light_warning;
    }
    QFrame#statusBanner[status="danger"] {
        background: $light_danger_background;
        border-color: $light_danger;
        color: $light_danger;
    }
    QFrame#statusBanner QLabel {
        color: inherit;
    }

    QFrame#emptyState {
        background: $light_surface_subtle;
        border: 1px solid $light_border_strong;
        border-radius: $radius_lg;
    }
    QLabel#emptyStateSymbol {
        color: $light_interactive;
        font-size: 32px;
        font-weight: 700;
    }
    QLabel#emptyStateTitle {
        color: $light_text;
        font-size: $font_subtitle;
        font-weight: 700;
    }
    QLabel#emptyStateDescription {
        color: $light_text_muted;
    }
    QLabel#captureEmptyState {
        background: $dark_surface;
        color: $dark_text_muted;
        border: 1px solid $dark_border;
        border-radius: $radius_lg;
        padding: $space_8;
    }
    QLabel#captureEmptyState:focus {
        border: $focus_width solid $dark_focus;
    }
    QLabel#historyEmptyState {
        background: $light_surface_subtle;
        color: $light_text_muted;
        border: 1px solid $light_border_strong;
        border-radius: $radius_lg;
        padding: $space_8;
    }

    QFrame#metricCard {
        background: $light_surface;
        border: 1px solid $light_border;
        border-radius: $radius_md;
    }
    QFrame#metricCard[status="success"] {
        border-left: 4px solid $light_success;
    }
    QFrame#metricCard[status="warning"] {
        border-left: 4px solid $light_warning;
    }
    QFrame#metricCard[status="danger"] {
        border-left: 4px solid $light_danger;
    }
    QLabel#metricValue {
        color: $light_text;
        font-size: $font_subtitle;
        font-weight: 700;
    }
    QLabel#metricLabel {
        color: $light_text_muted;
        font-size: $font_caption;
    }

    QFrame#workflowStage {
        background: $light_surface;
        border: 1px solid $light_border;
        border-radius: $radius_lg;
    }
    QFrame#workflowStage[state="active"] {
        border: 2px solid $light_interactive;
    }
    QFrame#workflowStage[state="completed"] {
        border: 2px solid $light_operational;
        background: $light_success_background;
    }
    QFrame#workflowStage[state="warning"] {
        border: 2px solid $light_warning;
        background: $light_warning_background;
    }
    QFrame#workflowStage[state="failed"] {
        border: 2px solid $light_danger;
        background: $light_danger_background;
    }
    QLabel#workflowNumber {
        color: $light_interactive;
        font-size: $font_caption;
        font-weight: 700;
    }
    QLabel#workflowTitle {
        color: $light_text;
        font-size: $font_section;
        font-weight: 700;
    }
    QLabel#workflowStatus {
        color: $light_text_muted;
        font-size: $font_caption;
    }

    QPushButton {
        min-height: $button_height;
        padding: 0 $space_4;
        background: $light_surface;
        color: $light_text;
        border: 1px solid $light_border_strong;
        border-radius: $radius_md;
    }
    QPushButton:hover {
        background: $light_surface_subtle;
        border-color: $light_text_muted;
    }
    QPushButton:focus, QToolButton:focus {
        border: $focus_width solid $light_focus;
    }
    QPushButton:disabled {
        color: $light_text_muted;
        background: $light_surface_subtle;
        border-color: $light_border;
    }
    QPushButton#primaryButton {
        min-height: $button_primary_height;
        background: $light_interactive;
        color: $light_surface;
        border-color: $light_interactive;
        font-weight: 700;
    }
    QPushButton#primaryButton:hover {
        background: $light_interactive_hover;
        border-color: $light_interactive_hover;
    }
    QPushButton#secondaryButton {
        color: $light_interactive;
        border-color: $light_interactive_border;
    }

    QLineEdit, QComboBox, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
        min-height: $button_height;
        background: $light_surface;
        color: $light_text;
        border: 1px solid $light_border_strong;
        border-radius: $radius_md;
        padding: $space_1 $space_3;
        selection-background-color: $light_interactive;
    }
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus {
        border: $focus_width solid $light_focus;
    }
    QProgressBar {
        min-height: 10px;
        max-height: 10px;
        background: $light_surface_subtle;
        border: none;
        border-radius: 5px;
        text-align: center;
        color: transparent;
    }
    QProgressBar::chunk {
        background: $light_operational;
        border-radius: 5px;
    }
    QTableWidget, QTableView {
        background: $light_surface;
        alternate-background-color: $light_surface_subtle;
        color: $light_text;
        border: 1px solid $light_border;
        border-radius: $radius_md;
        gridline-color: transparent;
        selection-background-color: $light_interactive_subtle;
        selection-color: $light_text;
        outline: none;
    }
    QTableWidget::item, QTableView::item {
        padding: $space_2 $space_3;
        border-bottom: 1px solid $light_border;
    }
    QHeaderView::section {
        background: $light_surface_subtle;
        color: $light_text_muted;
        border: none;
        border-bottom: 1px solid $light_border;
        padding: $space_3;
        font-size: $font_caption;
        font-weight: 700;
    }
    QScrollArea, QScrollArea > QWidget > QWidget {
        background: transparent;
        border: none;
    }
    QSplitter::handle {
        background: $light_border;
        height: 4px;
    }

    QLabel#historyCount {
        color: $light_text;
        font-weight: 700;
    }
    QLabel#historyHint {
        color: $light_text_muted;
        font-size: $font_caption;
    }
    QWidget#historyActions {
        background: transparent;
    }
    QPushButton#tablePrimaryAction {
        min-height: 32px;
        max-height: 32px;
        padding: 0 $space_3;
        background: $light_interactive_subtle;
        color: $light_interactive;
        border: 1px solid $light_interactive_border;
        font-size: $font_caption;
        font-weight: 700;
    }
    QToolButton#tableMoreAction {
        min-width: 34px;
        max-width: 34px;
        min-height: 32px;
        max-height: 32px;
        background: $light_surface;
        color: $light_text_muted;
        border: 1px solid $light_border_strong;
        border-radius: $radius_sm;
        font-weight: 700;
    }
    QMenu {
        background: $light_surface;
        color: $light_text;
        border: 1px solid $light_border_strong;
        padding: $space_1;
    }
    QMenu::item {
        min-height: 30px;
        padding: $space_1 $space_5 $space_1 $space_3;
        border-radius: $radius_sm;
    }
    QMenu::item:selected {
        background: $light_interactive_subtle;
        color: $light_interactive;
    }
    QLabel#taskStateBadge {
        border-radius: $radius_md;
        padding: $space_1 $space_2;
        font-size: $font_caption;
        font-weight: 700;
    }
    QLabel#taskStateBadge[state="success"] {
        background: $light_success_background;
        color: $light_success;
        border: 1px solid $light_operational;
    }
    QLabel#taskStateBadge[state="danger"] {
        background: $light_danger_background;
        color: $light_danger;
        border: 1px solid $light_danger;
    }
    QLabel#taskStateBadge[state="active"] {
        background: $light_interactive_subtle;
        color: $light_interactive;
        border: 1px solid $light_interactive_border;
    }
    QLabel#taskStateBadge[state="warning"] {
        background: $light_warning_background;
        color: $light_warning;
        border: 1px solid $light_warning;
    }
    QLabel#taskStateBadge[state="neutral"] {
        background: $light_surface_subtle;
        color: $light_text_muted;
        border: 1px solid $light_border;
    }

    QWidget#capturePageSurface,
    QWidget#resultPageSurface,
    QStackedWidget#captureHost {
        background: $dark_background;
    }
    QWidget#capturePageSurface QLabel,
    QWidget#resultPageSurface QLabel {
        color: $dark_text;
    }
    QWidget#capturePageSurface QLabel#mutedText,
    QWidget#resultPageSurface QLabel#mutedText,
    QWidget#resultPageSurface QLabel#pageDescription {
        color: $dark_text_muted;
    }
    QWidget#resultPageSurface QLabel#pageTitle {
        color: $dark_text;
    }
    QWidget#capturePageSurface QFrame#statusBanner,
    QWidget#resultPageSurface QFrame#statusBanner {
        background: $dark_surface;
        border-color: $dark_border;
        color: $dark_text_muted;
    }
    QWidget#capturePageSurface QFrame#statusBanner {
        border-left: none;
        border-right: none;
        border-top: none;
        border-radius: 0;
    }
    QWidget#capturePageSurface QFrame#statusBanner[status="warning"],
    QWidget#resultPageSurface QFrame#statusBanner[status="warning"] {
        background: $dark_warning_background;
        border-color: $dark_warning;
        color: $dark_warning;
    }
    QWidget#capturePageSurface QFrame#statusBanner[status="success"],
    QWidget#resultPageSurface QFrame#statusBanner[status="success"] {
        background: $dark_success_background;
        border-color: $dark_interactive;
        color: $dark_success;
    }
    QWidget#capturePageSurface QFrame#statusBanner[status="danger"],
    QWidget#resultPageSurface QFrame#statusBanner[status="danger"] {
        background: $dark_danger_background;
        border-color: $dark_danger;
        color: $dark_danger;
    }
    QWidget#capturePageSurface QFrame#emptyState,
    QWidget#resultPageSurface QFrame#emptyState {
        background: $dark_surface;
        border-color: $dark_border;
    }
    QWidget#capturePageSurface QLabel#emptyStateSymbol,
    QWidget#resultPageSurface QLabel#emptyStateSymbol {
        color: $dark_interactive;
    }
    QWidget#capturePageSurface QLabel#emptyStateTitle,
    QWidget#resultPageSurface QLabel#emptyStateTitle {
        color: $dark_text;
    }
    QWidget#capturePageSurface QLabel#emptyStateDescription,
    QWidget#resultPageSurface QLabel#emptyStateDescription {
        color: $dark_text_muted;
    }
    QWidget#resultPageSurface QFrame#contentCard,
    QWidget#resultPageSurface QFrame#sectionCard {
        background: $dark_surface;
        border-color: $dark_border;
    }
    QWidget#resultPageSurface QPushButton {
        background: $dark_surface_raised;
        color: $dark_text;
        border-color: $dark_border;
    }
    QWidget#resultPageSurface QPushButton:hover {
        background: $dark_surface_selected;
    }
    QWidget#resultPageSurface QPushButton:disabled {
        color: $dark_text_muted;
        background: $dark_surface;
        border-color: $dark_border;
    }
    QWidget#resultPageSurface QPushButton#primaryButton {
        background: $dark_interactive;
        color: $dark_background;
        border-color: $dark_interactive;
    }
    QWidget#resultPageSurface QPushButton#primaryButton:hover {
        background: $dark_interactive_hover;
    }

    QStatusBar {
        background: $light_surface;
        color: $light_text_muted;
        border-top: 1px solid $light_border;
    }
    QStatusBar[mode="operational"] {
        background: $dark_surface;
        color: $dark_text_muted;
        border-top: 1px solid $dark_border;
    }
    """
)


def application_stylesheet() -> str:
    """Return the resolved workstation stylesheet."""

    return _QSS.substitute(style_tokens())
