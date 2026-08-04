# Industrial Workstation UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a task-focused, accessible Qt Widgets workstation UI for capture, reconstruction, and Gaussian result review, then publish the complete branch to GitHub.

**Architecture:** Preserve the six-page stack and all application-layer signals. Introduce a three-layer Python token module consumed by QSS, add presentation-only shared widgets, and refactor each page around those components without moving I/O into the UI thread.

**Tech Stack:** Python 3.8, Qt Widgets through the PySide6 compatibility API, PyQt5/Qt 5.12 runtime, QSS, pytest, Jetson Orin Nano, GitHub CLI

## Global Constraints

- Primary geometry is 1600×900; minimum geometry is 1024×680.
- Body text is 16 px; page titles are 28 px.
- Normal text contrast is at least 4.5:1; components and focus indicators are at least 3:1.
- Buttons are at least 40 px high and keyboard reachable.
- Status uses symbol, text, and colour together.
- Preserve all six stack indexes and existing public signals.
- Preserve the model-backed diagnostics table.
- Do not add Qt, OpenCV, graphics, or UI framework dependencies.
- Do not initialize cameras, network requests, file work, or OpenGL from page constructors.

---

### Task 1: Three-layer design tokens and unified QSS

**Files:**
- Create: `src/camera_system_app/ui/design_tokens.py`
- Modify: `src/camera_system_app/ui/theme.py`
- Create: `tests/app_shell/test_ui_design_system.py`

**Interfaces:**
- Produces: `PRIMITIVES`, `SEMANTIC_LIGHT`, `SEMANTIC_DARK`, `COMPONENT_TOKENS`, and `style_tokens() -> dict`.
- Produces: `application_stylesheet() -> str` with no unresolved placeholders.
- Consumes: no UI widgets.

- [ ] **Step 1: Write failing token and stylesheet tests**

Create independent test helpers that calculate WCAG contrast. Test:

```python
def test_semantic_text_pairs_meet_wcag_contrast():
    assert contrast(SEMANTIC_LIGHT["text"], SEMANTIC_LIGHT["background"]) >= 4.5
    assert contrast(SEMANTIC_LIGHT["text_muted"], SEMANTIC_LIGHT["surface"]) >= 4.5
    assert contrast(SEMANTIC_DARK["text"], SEMANTIC_DARK["background"]) >= 4.5
    assert contrast(SEMANTIC_DARK["text_muted"], SEMANTIC_DARK["background"]) >= 4.5


def test_stylesheet_resolves_tokens_and_styles_model_views():
    stylesheet = application_stylesheet()
    assert "{" not in unresolved_format_fields(stylesheet)
    assert "QTableView" in stylesheet
    assert SEMANTIC_LIGHT["interactive"] in stylesheet
    assert SEMANTIC_DARK["background"] in stylesheet
```

The test helper derives expected ratios independently and must not call a
production contrast function.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_ui_design_system.py
```

Expected: import failure because `design_tokens.py` does not exist.

- [ ] **Step 3: Implement tokens and format the QSS**

Define:

```python
PRIMITIVES = {
    "navy_950": "#07131D",
    "navy_900": "#0B1B27",
    "navy_800": "#12263A",
    "navy_700": "#193853",
    "neutral_50": "#F4F7FA",
    "white": "#FFFFFF",
    "neutral_200": "#D7E0EA",
    "neutral_600": "#5E6D82",
    "neutral_900": "#142033",
    "blue_600": "#0B70C9",
    "blue_700": "#085EAA",
    "focus": "#58A6FF",
    "teal": "#16B8A6",
    "success": "#0F766E",
    "warning": "#9A5B00",
    "danger": "#B42318",
}
```

Build semantic dictionaries from primitives and component tokens from semantic
roles. Return a flat immutable copy from `style_tokens()`.

Move the QSS into a named format template. Cover `QTableWidget, QTableView`,
inputs, spin boxes, progress bars, scroll areas, splitters, empty states,
metric cards, workflow stages, focus states, light pages, dark operational
pages, navigation, and status bar.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_ui_design_system.py
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_no_hardware_startup.py
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add src/camera_system_app/ui/design_tokens.py src/camera_system_app/ui/theme.py tests/app_shell/test_ui_design_system.py
git commit -m "feat: add workstation UI design tokens"
```

### Task 2: Shared workstation components

**Files:**
- Create: `src/camera_system_app/ui/widgets/empty_state.py`
- Create: `src/camera_system_app/ui/widgets/metric_card.py`
- Create: `src/camera_system_app/ui/widgets/workflow_stage.py`
- Modify: `src/camera_system_app/ui/widgets/status_banner.py`
- Modify: `src/camera_system_app/ui/widgets/page_header.py`
- Modify: `src/camera_system_app/ui/widgets/__init__.py`
- Modify: `src/camera_system_app/ui/pages/base.py`
- Modify: `tests/app_shell/test_ui_design_system.py`

**Interfaces:**
- Produces: `EmptyState`, `MetricCard`, `WorkflowStage`, enhanced
  `StatusBanner`, enhanced `PageHeader`.
- Produces: `BasePage.add_card(title="", description="") -> QVBoxLayout`.
- Consumes: component object names styled by Task 1.

- [ ] **Step 1: Write failing component behaviour tests**

Test real widgets:

```python
def test_status_banner_exposes_semantic_symbol_and_accessible_text(qapp):
    banner = StatusBanner("网络不可用", "danger")
    assert banner.property("status") == "danger"
    assert banner.symbol_text() == "✕"
    assert "网络不可用" in banner.accessibleName()


def test_empty_state_action_is_optional_and_emits(qapp):
    state = EmptyState("○", "等待摄像头画面", "检查连接", "打开诊断")
    emitted = []
    state.action_requested.connect(lambda: emitted.append(True))
    state.action_button.click()
    assert emitted == [True]


def test_workflow_stage_updates_progress_and_state(qapp):
    stage = WorkflowStage("01", "上传")
    stage.set_progress(42, "正在上传")
    stage.set_state("active")
    assert stage.progress.value() == 42
    assert stage.property("state") == "active"
    assert "正在上传" in stage.accessibleName()
```

Also test `MetricCard.set_value()` and `PageHeader` eyebrow text.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_ui_design_system.py
```

Expected: imports fail because the shared widgets do not exist.

- [ ] **Step 3: Implement the shared components**

Required APIs:

```python
class EmptyState(QFrame):
    action_requested = Signal()
    def __init__(self, symbol, title, description, action_text="", parent=None): ...


class MetricCard(QFrame):
    def __init__(self, label, value="0", status="neutral", parent=None): ...
    def set_value(self, value): ...


class WorkflowStage(QFrame):
    VALID_STATES = {"pending", "active", "completed", "warning", "failed"}
    def __init__(self, number, title, parent=None): ...
    def set_progress(self, value, status_text): ...
    def set_state(self, state): ...
```

`StatusBanner` supports `info`, `success`, `warning`, and `danger`, exposes
`symbol_text()`, and updates its accessible name. `PageHeader` accepts
`eyebrow=""`. `BasePage.add_card` adds optional header labels before returning
the content layout.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_ui_design_system.py
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_stability_features.py
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/camera_system_app/ui/widgets src/camera_system_app/ui/pages/base.py tests/app_shell/test_ui_design_system.py
git commit -m "feat: add workstation UI components"
```

### Task 3: Shell, capture, and viewer workflow

**Files:**
- Modify: `src/camera_system_app/ui/main_window.py`
- Modify: `src/camera_system_app/ui/pages/capture_workspace.py`
- Modify: `src/camera_system_app/ui/pages/result_viewer.py`
- Modify: `tests/app_shell/test_ui_design_system.py`
- Modify: `tests/app_shell/test_stability_features.py`
- Modify: `tests/app_shell/test_q3dviewer_integration.py`

**Interfaces:**
- Consumes: `EmptyState`, enhanced `PageHeader`, and Task 1 QSS.
- Preserves: stack indexes 0–5 and existing result-viewer signals.
- Produces: `CaptureWorkspacePage.open_diagnostics_requested`.

- [ ] **Step 1: Write failing shell and operational-page tests**

Test:

```python
def test_numbered_navigation_preserves_page_indexes(context, qapp):
    window = MainWindow(context.paths, context.settings)
    assert window.navigation.count() == 6
    assert window.navigation.item(0).text().startswith("01")
    window.navigation.setCurrentRow(2)
    assert window.stack.currentWidget() is window.result_page


def test_capture_empty_state_opens_diagnostics(context, qapp):
    window = MainWindow(context.paths, context.settings)
    window.capture_page._empty_state.action_button.click()
    assert window.navigation.currentRow() == 5


def test_result_viewer_has_actionable_empty_state(qapp, tmp_path):
    page = ResultViewerPage(str(tmp_path), str(tmp_path))
    assert page._empty_state.isVisibleTo(page)
    assert "Gaussian" in page._empty_state.title_text()
```

The production break caught is a navigation reindex, a dead recovery action,
or regression to a non-actionable empty label.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_ui_design_system.py tests/app_shell/test_stability_features.py tests/app_shell/test_q3dviewer_integration.py
```

Expected: missing numbered labels and empty-state APIs.

- [ ] **Step 3: Implement shell and operational pages**

- Prefix navigation labels `01` through `06` without adding list rows.
- Add page eyebrows and a bottom `workstationStatus` block.
- Connect `capture_page.open_diagnostics_requested` to
  `navigation.setCurrentRow(5)`.
- Replace the capture placeholder with a dark `EmptyState`.
- Replace the result viewer empty label with a dark `EmptyState`.
- Keep result actions ordered Select → Load → Reset and preserve enable rules.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_ui_design_system.py tests/app_shell/test_stability_features.py tests/app_shell/test_q3dviewer_integration.py
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/camera_system_app/ui/main_window.py src/camera_system_app/ui/pages/capture_workspace.py src/camera_system_app/ui/pages/result_viewer.py tests/app_shell
git commit -m "feat: clarify capture and viewer workflow"
```

### Task 4: Transfer stages and history empty state

**Files:**
- Modify: `src/camera_system_app/ui/pages/transfer_reconstruction.py`
- Modify: `src/camera_system_app/ui/pages/history.py`
- Modify: `tests/app_shell/test_ui_design_system.py`
- Modify: `tests/app_shell/test_reconstruction_workflow.py`
- Modify: `tests/app_shell/test_stability_features.py`

**Interfaces:**
- Consumes: `WorkflowStage`, `EmptyState`, and `BasePage.add_card`.
- Preserves: `start_requested`, `open_result_requested`,
  `select_images_requested`, and all history action signals.
- Produces: `_upload_stage`, `_reconstruction_stage`, `_download_stage`.

- [ ] **Step 1: Write failing workflow and history tests**

Test observable stage states:

```python
def test_transfer_progress_updates_numbered_workflow_stages(qapp, tmp_path):
    page = TransferReconstructionPage("http://host:8000", str(tmp_path))
    page.set_upload_progress(50, 100)
    assert page._upload_stage.progress.value() == 50
    page.set_reconstruction_progress(33.5, "训练")
    assert page._reconstruction_stage.progress.value() == 33
    assert "训练" in page._reconstruction_stage.accessibleName()


def test_history_switches_between_empty_state_and_table(qapp, tmp_path):
    page = HistoryPage()
    assert page._content.currentWidget() is page._empty_state
    page.set_jobs([make_ready_job(tmp_path)])
    assert page._content.currentWidget() is page.table
```

Retain existing retry and result action tests.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_ui_design_system.py tests/app_shell/test_reconstruction_workflow.py tests/app_shell/test_stability_features.py
```

Expected: missing stage and content-stack attributes.

- [ ] **Step 3: Implement transfer and history layouts**

- Split task details and endpoint metadata into a summary card.
- Put three `WorkflowStage` widgets in one equal-stretch row.
- Put manual selection and the single primary action in a footer action row.
- Map reconstruction states to pending, active, completed, warning, or failed
  presentation without changing the domain state machine.
- Put history table and `EmptyState` into one `QStackedWidget`.
- Switch based on `len(jobs)`.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_ui_design_system.py tests/app_shell/test_reconstruction_workflow.py tests/app_shell/test_stability_features.py
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/camera_system_app/ui/pages/transfer_reconstruction.py src/camera_system_app/ui/pages/history.py tests/app_shell
git commit -m "feat: visualize reconstruction workflow"
```

### Task 5: Grouped settings and diagnostic summary

**Files:**
- Modify: `src/camera_system_app/ui/pages/settings.py`
- Modify: `src/camera_system_app/ui/pages/diagnostics_log.py`
- Modify: `tests/app_shell/test_ui_design_system.py`
- Modify: `tests/app_shell/test_app_shell.py`

**Interfaces:**
- Consumes: `MetricCard`, `BasePage.add_card`, and Task 1 QSS.
- Preserves: settings values and save signal; diagnostic refresh signals and
  `DiagnosticTableModel`.
- Produces: settings `_scroll`, diagnostics `_passed_metric`,
  `_warning_metric`, `_failure_metric`, and `_splitter`.

- [ ] **Step 1: Write failing settings and diagnostics tests**

Test:

```python
def test_settings_groups_scroll_without_changing_values(qapp, settings):
    page = SettingsPage(settings, "/tmp/settings.yaml")
    assert page._scroll.widgetResizable()
    assert page.values()["wsl_service_url"] == settings.wsl_service_url
    assert page._save_button.isVisibleTo(page)


def test_diagnostic_metrics_follow_report(qapp):
    page = DiagnosticsLogPage("/tmp/app.log")
    page.set_report(report_with_one_pass_warning_and_failure())
    assert page._passed_metric.value_text() == "1"
    assert page._warning_metric.value_text() == "1"
    assert page._failure_metric.value_text() == "1"
    assert page._splitter.count() == 2
```

Expected counts are literals from a hand-built report.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_ui_design_system.py tests/app_shell/test_app_shell.py
```

Expected: missing scroll, metric, and splitter attributes.

- [ ] **Step 3: Implement settings and diagnostics layouts**

- Place connection, storage, timeouts, and logging sections in a resizable
  `QScrollArea`.
- Keep Save outside the scroll area and expose it as `_save_button`.
- Keep all existing field widgets and `values()` keys unchanged.
- Add three metrics and update them from `DiagnosticReport`.
- Keep `DiagnosticTableModel`; place table and log frame into a vertical
  `QSplitter` with sensible initial sizes.
- Give refresh controls, metrics, splitter, table, and logs accessible names.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_ui_design_system.py tests/app_shell/test_app_shell.py
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/camera_system_app/ui/pages/settings.py src/camera_system_app/ui/pages/diagnostics_log.py tests/app_shell
git commit -m "feat: improve settings and diagnostics UX"
```

### Task 6: Visual, accessibility, and project verification

**Files:**
- Create: `docs/development/UI_DESIGN_SYSTEM.md`
- Create: `docs/images/ui/capture.png`
- Create: `docs/images/ui/transfer.png`
- Create: `docs/images/ui/result.png`
- Create: `docs/images/ui/history.png`
- Create: `docs/images/ui/settings.png`
- Create: `docs/images/ui/diagnostics.png`
- Modify: `docs/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: completed six-page UI.
- Produces: design-system documentation and current screenshots.

- [ ] **Step 1: Document tokens and component contracts**

Document the three token layers, typography, spacing, semantic colours,
component object names, accessibility rules, operational/light surface rules,
and screenshot regeneration command in `UI_DESIGN_SYSTEM.md`.

- [ ] **Step 2: Generate and inspect screenshots**

Run the shell offscreen at 1600×900 and save each stack page to
`docs/images/ui`. Repeat at 1024×680 to `/tmp` for minimum-size inspection.
Inspect all twelve images for clipping, overlap, invisible focus/controls,
weak hierarchy, and non-actionable empty states. Fix any finding through a new
RED/GREEN test before regenerating the affected screenshot.

- [ ] **Step 3: Run complete verification**

Run:

```bash
.venv-jetson/bin/python -m pytest -q
(cd Tx_Rx && ../.venv-jetson/bin/python -m pytest -q)
(cd multiwebcam && env LD_PRELOAD=/lib/aarch64-linux-gnu/libGLdispatch.so.0 PYTHONPATH=src .venv-jetson/bin/python -m pytest -q)
for run in $(seq 1 20); do .venv-jetson/bin/python -m pytest -q tests/app_shell/test_no_hardware_startup.py || exit 1; done
./scripts/jetson/diagnose.sh --json
.venv-jetson/bin/python -m compileall -q src tests Tx_Rx/tx_rx multiwebcam/src 3DGSviewer/q3dviewer
git diff --check
```

Expected: all non-hardware tests pass, repeated shell test is stable,
diagnostics report zero core failures, and static checks pass.

- [ ] **Step 4: Commit documentation and screenshots**

```bash
git add README.md docs/README.md docs/development/UI_DESIGN_SYSTEM.md docs/images/ui
git commit -m "docs: publish workstation UI guide"
```

### Task 7: Publish complete project to GitHub

**Files:**
- Verify: entire branch diff and commit history.
- External: `origin` GitHub repository and draft pull request.

**Interfaces:**
- Consumes: clean local `organize-camera-system` branch and successful checks.
- Produces: pushed branch and draft PR targeting the remote default branch.

- [ ] **Step 1: Confirm scope and remote state**

Run:

```bash
git status -sb
git diff origin/organize-camera-system...HEAD --stat
git log --oneline origin/organize-camera-system..HEAD
gh auth status
gh repo view --json nameWithOwner,defaultBranchRef
```

Expected: only intended project commits, authenticated GitHub access, and a
known base branch.

- [ ] **Step 2: Push the complete branch**

Run:

```bash
git push -u origin "$(git branch --show-current)"
```

Expected: remote `organize-camera-system` advances to local HEAD.

- [ ] **Step 3: Create a draft PR**

Prefer the GitHub connector. Use a title that summarizes the complete
camera-system hardening and workstation UI, and a body covering changes,
motivation, operator impact, cancellation reliability, UI design, dependency
policy, and all validation results.

- [ ] **Step 4: Audit the GitHub result**

Verify the PR head SHA equals local `HEAD`, the base is the remote default
branch, the PR is draft, and the remote commit list contains every local
commit. Record the PR URL.

