# History and Settings Input Safety V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate nested status-cell clipping, make wheel input incapable of changing timeout configuration, and guarantee fullscreen exit.

**Architecture:** Store history status as native table items instead of nested label widgets, while retaining row action widgets with size-derived row heights. Replace focus-dependent wheel admission with safe spin boxes that reject wheel changes at both the spin-box and embedded-editor event boundaries.

**Tech Stack:** Python 3.8, Qt Widgets through the project PySide6 compatibility layer, JetPack Qt 5.12/PyQt5 runtime, pytest.

## Global Constraints

- Preserve reconstruction states, signals, menus, settings keys, ranges, suffixes, serialization, keyboard entry, and arrow-button editing.
- Support 1600×900 and the 1024×680 minimum window.
- Timeout and polling values must never change from a wheel event.
- Status cells must expose complete symbol-and-text labels through the table model.
- Do not add dependencies or replace the JetPack Qt compatibility stack.
- Escape exits camera fullscreen and restores the prior maximized/windowed state.

---

### Task 1: Native history status cells

**Files:**
- Modify: `tests/app_shell/test_ui_design_system.py`
- Modify: `src/camera_system_app/ui/pages/history.py`
- Modify: `src/camera_system_app/ui/theme.py`

**Interfaces:**
- Consumes: `HistoryPage.set_jobs(jobs)`.
- Produces: `QTableWidgetItem` status cells containing `✕ 失败`,
  `○ 待上传`, and corresponding labels for every reconstruction state.

- [ ] **Step 1: Write a failing native-cell test**

Create failed and ready jobs, call `set_jobs`, and assert:

```python
assert page.table.cellWidget(0, 2) is None
assert page.table.item(0, 2).text() == "✕ 失败"
assert page.table.item(1, 2).text() == "○ 待上传"
```

Also show the page and assert each primary action widget height is at least its
size hint.

- [ ] **Step 2: Verify RED**

```bash
.venv-jetson/bin/python -m pytest -q \
  tests/app_shell/test_ui_design_system.py -k "history_native_status"
```

Expected: failure because column 2 currently contains a nested QWidget and no
table item.

- [ ] **Step 3: Implement native status items**

Add `_state_item(state)` that constructs a non-editable centered
`QTableWidgetItem`, selects the literal symbol/label from a state mapping, and
sets semantic foreground/background brushes from `SEMANTIC_LIGHT`. Replace
`setCellWidget(row, 2, ...)` with `setItem(row, 2, ...)`.

After creating the action widget, calculate:

```python
required_height = max(68, actions.sizeHint().height() + 16)
self.table.setRowHeight(row, required_height)
```

Remove obsolete `taskStateBadge` QSS selectors and `_state_badge`.

- [ ] **Step 4: Verify GREEN**

```bash
.venv-jetson/bin/python -m pytest -q \
  tests/app_shell/test_ui_design_system.py -k "history" \
  tests/app_shell/test_stability_features.py::test_history_exposes_retry_and_result_actions
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/app_shell/test_ui_design_system.py \
  src/camera_system_app/ui/pages/history.py \
  src/camera_system_app/ui/theme.py
git commit -m "fix: render history states as native cells"
```

### Task 2: Wheel-proof timeout controls

**Files:**
- Modify: `tests/app_shell/test_ui_design_system.py`
- Replace: `src/camera_system_app/ui/widgets/focus_wheel_spinbox.py`
- Modify: `src/camera_system_app/ui/widgets/__init__.py`
- Modify: `src/camera_system_app/ui/pages/settings.py`

**Interfaces:**
- Produces: `SafeSpinBox(QSpinBox)` and
  `SafeDoubleSpinBox(QDoubleSpinBox)`.
- Wheel contract: values remain unchanged for a wheel event sent to the outer
  spin box or its `lineEdit()`, whether focused or unfocused.
- Editing contract: mouse selection plus direct key entry and arrow-button
  stepping still update values.

- [ ] **Step 1: Strengthen tests and verify RED**

Replace the focus-dependent expectations with real-event cases covering:

```python
for target in (control, control.lineEdit()):
    control.setValue(10)
    qapp.sendEvent(target, _wheel_up_event())
    assert control.value() == 10
```

Run the same cases after a mouse click. Add a direct `QTest.keyClicks` case
that selects all and enters `25`, then assert the value is 25.

```bash
.venv-jetson/bin/python -m pytest -q \
  tests/app_shell/test_ui_design_system.py -k "timeout_spin"
```

Expected: focused wheel tests fail because the existing class still permits
wheel stepping after selection.

- [ ] **Step 2: Implement wheel-proof classes**

Rename the module classes and remove focus/selection state. Override
`wheelEvent` to ignore the event. Install an event filter on `lineEdit()` and
return `True` for `QEvent.Wheel` after calling `event.ignore()`. Leave all
non-wheel events to Qt.

- [ ] **Step 3: Verify intentional editing**

Run:

```bash
.venv-jetson/bin/python -m pytest -q \
  tests/app_shell/test_ui_design_system.py -k "settings or timeout_spin"
```

Expected: wheel cases preserve values and direct entry changes the selected
field.

- [ ] **Step 4: Commit**

```bash
git add tests/app_shell/test_ui_design_system.py \
  src/camera_system_app/ui/widgets/focus_wheel_spinbox.py \
  src/camera_system_app/ui/widgets/__init__.py \
  src/camera_system_app/ui/pages/settings.py
git commit -m "fix: disable wheel edits for timeout settings"
```

### Task 3: Visual, regression, and publication verification

**Files:**
- Modify: `multiwebcam/tests/ui/test_imports.py`
- Modify: `multiwebcam/src/multiwebcam/ui/views/grid_view.py`

**Interfaces:**
- Produces: an application-scoped Escape shortcut owned by `GridView`.
- Preserves: `_toggle_fullscreen()` button behavior and the top-level window's
  previous maximized/windowed state.

- [ ] **Step 1: Write failing fullscreen tests**

Place `GridView` in a real top-level `QWidget`, show it, call
`_toggle_fullscreen()`, then activate the Escape shortcut and assert:

```python
assert not window.isFullScreen()
assert view._fullscreen_btn.text() == "全屏"
```

Repeat from a maximized starting state and assert `window.isMaximized()` after
exit.

- [ ] **Step 2: Verify RED**

```bash
(cd multiwebcam && LD_PRELOAD=/lib/aarch64-linux-gnu/libGLdispatch.so.0 \
  PYTHONPATH=src .venv-jetson/bin/python -m pytest -q \
  tests/ui/test_imports.py -k "fullscreen")
```

Expected: failure because no Escape/F11 shortcut exists and exit always calls
`showNormal()`.

- [ ] **Step 3: Implement fullscreen state management**

Create an application-scoped `QShortcut` for Escape. Split
fullscreen handling into `_set_fullscreen(enabled)` and
`_exit_fullscreen()`. Record `window.isMaximized()` before entering, restore
with `showMaximized()` or `showNormal()`, and synchronize button text in both
paths.

- [ ] **Step 4: Verify GREEN and commit**

```bash
(cd multiwebcam && LD_PRELOAD=/lib/aarch64-linux-gnu/libGLdispatch.so.0 \
  PYTHONPATH=src .venv-jetson/bin/python -m pytest -q \
  tests/ui/test_imports.py -k "fullscreen")
git add multiwebcam/tests/ui/test_imports.py \
  multiwebcam/src/multiwebcam/ui/views/grid_view.py
git commit -m "fix: make camera fullscreen escapable"
```

### Task 4: Visual, regression, and publication verification

**Files:**
- Update: `docs/images/ui/history.png`
- Update: `docs/images/ui/settings.png` only if rendered pixels change.

**Interfaces:**
- Consumes: completed native history status cells and safe timeout controls.
- Produces: verified screenshot baseline and synchronized draft PR.

- [ ] **Step 1: Render 1600×900 and 1024×680**

Populate history with failed and ready jobs. Confirm complete `✕ 失败`,
`○ 待上传`, `重试`, and `查看详情` text with no nested rounded-border clipping.
Confirm all six columns fit at 1024×680.

- [ ] **Step 2: Run all suites**

```bash
.venv-jetson/bin/python -m pytest -q
(cd Tx_Rx && ../.venv-jetson/bin/python -m pytest -q)
(cd multiwebcam && LD_PRELOAD=/lib/aarch64-linux-gnu/libGLdispatch.so.0 \
  PYTHONPATH=src .venv-jetson/bin/python -m pytest -q)
```

Expected: root suite passes with only the X11 OpenGL hardware skip; Tx_Rx has
63 passing tests; multiwebcam has 170 passing tests.

- [ ] **Step 3: Commit screenshots**

```bash
git add docs/images/ui/history.png
git commit -m "docs: refresh native history status screenshot"
```

- [ ] **Step 4: Push and audit**

```bash
git push origin organize-camera-system
gh pr view 2 --json url,isDraft,headRefOid,mergeable,mergeStateStatus
```

Expected: PR #2 remains an open draft, the remote head matches local `HEAD`,
and GitHub reports it mergeable.
