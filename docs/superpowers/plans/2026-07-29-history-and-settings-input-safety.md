# History and Settings Input Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent clipped history-row text and accidental timeout changes during settings-page scrolling.

**Architecture:** Keep history behavior inside `HistoryPage` and its existing QSS selectors. Add two small shared spin-box subclasses that change only wheel-event admission, then use them for the five timeout fields in `SettingsPage`.

**Tech Stack:** Python 3.8, Qt Widgets through the project PySide6 compatibility layer, PyQt5/Qt 5.12 runtime, pytest.

## Global Constraints

- Preserve all reconstruction states, signals, menus, settings keys, ranges, suffixes, and serialization.
- Support the existing 1600×900 primary and 1024×680 minimum window sizes.
- Do not add dependencies or replace the JetPack Qt compatibility stack.
- Every production behavior change starts with a real failing widget test.

---

### Task 1: History row content sizing

**Files:**
- Modify: `tests/app_shell/test_ui_design_system.py`
- Modify: `src/camera_system_app/ui/pages/history.py`
- Modify: `src/camera_system_app/ui/theme.py`

**Interfaces:**
- Consumes: `HistoryPage.set_jobs(jobs)`.
- Produces: row status and primary-action widgets whose rendered height is at least their Qt size hint.

- [ ] **Step 1: Write the failing test**

Create failed and ready `ReconstructionJob` rows, show a real `HistoryPage` with the application stylesheet, and assert:

```python
assert badge.height() >= badge.sizeHint().height()
assert primary.height() >= primary.sizeHint().height()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv-jetson/bin/python -m pytest -q \
  tests/app_shell/test_ui_design_system.py::test_history_row_controls_do_not_clip_text
```

Expected: failure because the badge height is about 21 px while its size hint is about 30 px.

- [ ] **Step 3: Implement the minimal sizing fix**

In `HistoryPage`, set the vertical-header default and each populated row to
68 px. Reduce status and action container vertical margins. In QSS, give the
badge and primary action a 36 px minimum height and remove the primary action
maximum height.

- [ ] **Step 4: Run focused history tests**

Run:

```bash
.venv-jetson/bin/python -m pytest -q \
  tests/app_shell/test_ui_design_system.py::test_history_row_controls_do_not_clip_text \
  tests/app_shell/test_stability_features.py::test_history_exposes_retry_and_result_actions
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add tests/app_shell/test_ui_design_system.py \
  src/camera_system_app/ui/pages/history.py \
  src/camera_system_app/ui/theme.py
git commit -m "fix: prevent history row text clipping"
```

### Task 2: Focus-protected timeout spin boxes

**Files:**
- Create: `src/camera_system_app/ui/widgets/focus_wheel_spinbox.py`
- Modify: `src/camera_system_app/ui/widgets/__init__.py`
- Modify: `src/camera_system_app/ui/pages/settings.py`
- Modify: `tests/app_shell/test_ui_design_system.py`

**Interfaces:**
- Produces: `FocusWheelSpinBox(QSpinBox)` and
  `FocusWheelDoubleSpinBox(QDoubleSpinBox)`.
- Behavior: `wheelEvent(event)` calls the Qt base implementation only when
  `hasFocus()` is true; otherwise it calls `event.ignore()`.
- Consumes: the same `setRange`, `setValue`, `setSuffix`, and `value` APIs as
  standard spin boxes.

- [ ] **Step 1: Write failing real-event tests**

Construct real `QWheelEvent` instances and send them to integer and decimal
timeout widgets. Assert an unfocused widget keeps its literal starting value.
Then click/focus the integer widget, send the same wheel event, and assert its
value increases.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv-jetson/bin/python -m pytest -q \
  tests/app_shell/test_ui_design_system.py -k "timeout_spin"
```

Expected: failure because `SettingsPage` still uses standard Qt spin boxes,
which step on an unfocused wheel event.

- [ ] **Step 3: Implement protected widgets**

Add:

```python
class _FocusWheelMixin:
    def wheelEvent(self, event):
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class FocusWheelSpinBox(_FocusWheelMixin, QSpinBox):
    pass


class FocusWheelDoubleSpinBox(_FocusWheelMixin, QDoubleSpinBox):
    pass
```

Export both classes and replace the five timeout field constructors in
`SettingsPage`.

- [ ] **Step 4: Run focused settings tests**

Run:

```bash
.venv-jetson/bin/python -m pytest -q \
  tests/app_shell/test_ui_design_system.py -k "settings or timeout_spin"
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/camera_system_app/ui/widgets/focus_wheel_spinbox.py \
  src/camera_system_app/ui/widgets/__init__.py \
  src/camera_system_app/ui/pages/settings.py \
  tests/app_shell/test_ui_design_system.py
git commit -m "fix: guard timeout values from page scrolling"
```

### Task 3: Visual and regression verification

**Files:**
- Update: `docs/images/ui/history.png`
- Update: `docs/images/ui/settings.png`

**Interfaces:**
- Consumes: the completed history and settings widgets.
- Produces: updated screenshot baselines and published commits.

- [ ] **Step 1: Run all root tests**

```bash
.venv-jetson/bin/python -m pytest -q
```

Expected: 107 or more tests pass; only the X11/OpenGL hardware test may skip.

- [ ] **Step 2: Run subproject tests**

```bash
(cd Tx_Rx && ../.venv-jetson/bin/python -m pytest -q)
(cd multiwebcam && LD_PRELOAD=/lib/aarch64-linux-gnu/libGLdispatch.so.0 \
  PYTHONPATH=src .venv-jetson/bin/python -m pytest -q)
```

Expected: Tx_Rx 63 pass; multiwebcam 170 pass.

- [ ] **Step 3: Render and inspect screenshots**

Render history with failed and ready rows at 1600×900 and 1024×680. Confirm
badges, `重试`, and `查看详情` have complete glyphs and borders. Render settings
at both sizes and confirm the timeout section remains scrollable.

- [ ] **Step 4: Commit screenshot baselines**

```bash
git add docs/images/ui/history.png docs/images/ui/settings.png
git commit -m "docs: refresh fixed interaction screenshots"
```

- [ ] **Step 5: Push and audit PR**

```bash
git push origin organize-camera-system
gh pr view 2 --json url,isDraft,headRefOid,mergeable
```

Expected: PR #2 stays open as a draft, its head SHA matches local `HEAD`, and
GitHub reports it mergeable.
