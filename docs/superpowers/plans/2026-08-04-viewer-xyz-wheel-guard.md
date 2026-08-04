# 3DGS 查看器 XYZ 开关与参数滚轮保护实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仅为结果查看页右侧参数面板增加明确的 XYZ 坐标显示开关，并阻止面板滚轮误改组合框和数值参数。

**Architecture:** 复用现有 `DisplaySettings.show_axis` 数据链路，不新增项目字段；仅将现有 Inspector 开关文案改为明确的 XYZ 语义。为 Inspector 组合框增加独立的滚轮安全控件，沿用现有 `SafeSpinBox` / `SafeDoubleSpinBox` 的数值框保护，忽略未展开控件收到的滚轮事件并把滚动交给外层参数面板。

**Tech Stack:** Python 3、PySide6 Widgets、pytest、现有 `ViewerInspector` / `DisplaySettings` / `SceneOverlayItem`。

## Global Constraints

- 只修改右侧 `ViewerInspector` 的 XYZ 开关文案/提示和参数控件滚轮行为。
- 不修改顶部工具栏组合框、左侧 01–06 导航、3D 场景相机交互或其它页面控件。
- 不新增 `DisplaySettings` 字段，不改变查看器项目文件格式，默认 `show_axis` 状态保持不变。
- 数值框必须继续支持鼠标点击输入框、全选后使用键盘输入并回车提交。
- 组合框滚轮不得改变值；组合框仍可通过鼠标点击下拉选项或键盘选择。
- 每个行为变更先写失败测试并确认失败，再写最小实现。

## File Map

- Modify: `src/camera_system_app/ui/widgets/focus_wheel_spinbox.py` — 增加 `SafeComboBox`，统一定义 Inspector 组合框的滚轮保护。
- Modify: `src/camera_system_app/ui/widgets/__init__.py` — 导出 `SafeComboBox`，保持控件模块的公共导出完整。
- Modify: `src/camera_system_app/ui/widgets/viewer_inspector.py` — 使用 `SafeComboBox`，明确 XYZ 开关文案、accessibility name 和 tooltip。
- Test: `tests/app_shell/test_ui_design_system.py` — 覆盖 Inspector 组合框/数值框滚轮行为、键盘输入和 XYZ 开关语义。

### Task 1: Write failing tests for the allowed UI behavior

**Files:**
- Modify: `tests/app_shell/test_ui_design_system.py` near the existing `_wheel_up_event` helper and timeout spin-box tests.
- Read-only reference: `src/camera_system_app/ui/widgets/viewer_inspector.py` for the Inspector control list.

**Interfaces:**
- Consumes: `ViewerInspector`, `_wheel_up_event()`, PySide6 `QTest`, `Qt`.
- Produces: failing regression tests that require `SafeComboBox` use and explicit XYZ copy.

- [ ] **Step 1: Add a failing test for the explicit XYZ control.**

Add this test after the existing Inspector control tests:

```python
def test_viewer_inspector_exposes_explicit_xyz_overlay_toggle(qapp):
    inspector = ViewerInspector()
    emitted = []
    inspector.display_settings_changed.connect(emitted.append)

    assert inspector.show_axis_checkbox.text() == "显示 XYZ 坐标"
    assert "XYZ" in inspector.show_axis_checkbox.accessibleName()
    assert "X/Y/Z" in inspector.show_axis_checkbox.toolTip()

    inspector.show_axis_checkbox.setChecked(True)
    inspector.show_axis_checkbox.setChecked(False)

    assert [settings.show_axis for settings in emitted[-2:]] == [True, False]
```

- [ ] **Step 2: Add a failing test proving every Inspector combo ignores panel scrolling.**

Add this test near the existing wheel protection tests:

```python
def test_viewer_inspector_combos_ignore_wheel_without_selection(qapp):
    inspector = ViewerInspector()
    combos = (
        inspector.display_mode_combo,
        inspector.quality_combo,
        inspector.sphere_color_mode,
        inspector.camera_mode_combo,
        inspector.bookmark_combo,
        inspector.tone_mapping_combo,
        inspector.sh_degree_combo,
        inspector.resolution_preset_combo,
        inspector.fps_preset_combo,
        inspector.output_kind,
    )
    initial = [combo.currentIndex() for combo in combos]

    for combo in combos:
        qapp.sendEvent(combo, _wheel_up_event())

    assert [combo.currentIndex() for combo in combos] == initial
```

- [ ] **Step 3: Add a failing test proving Inspector numeric entry remains keyboard-editable.**

Add this test next to the combo wheel test:

```python
def test_viewer_inspector_numeric_fields_require_keyboard_entry(qapp):
    inspector = ViewerInspector()
    control = inspector.sphere_sigma_multiplier
    editor = control.lineEdit()
    control.setValue(3.0)

    qapp.sendEvent(control, _wheel_up_event())
    qapp.sendEvent(editor, _wheel_up_event())
    assert control.value() == 3.0

    QTest.mouseClick(editor, Qt.LeftButton)
    editor.selectAll()
    QTest.keyClicks(editor, "4.5")
    QTest.keyClick(editor, Qt.Key_Return)

    assert control.value() == 4.5
```

- [ ] **Step 4: Run only the new tests and verify the failures are expected.**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src:multiwebcam/src:Tx_Rx:3DGSviewer/q3dviewer \
  .venv-jetson/bin/python -m pytest -q \
  tests/app_shell/test_ui_design_system.py::test_viewer_inspector_exposes_explicit_xyz_overlay_toggle \
  tests/app_shell/test_ui_design_system.py::test_viewer_inspector_combos_ignore_wheel_without_selection \
  tests/app_shell/test_ui_design_system.py::test_viewer_inspector_numeric_fields_require_keyboard_entry
```

Expected result: the XYZ copy test fails because the current text is “显示坐标轴”, and
the combo test fails because at least `quality_combo` and `sh_degree_combo` change index;
the numeric-entry test must either pass or fail only if the existing fixture needs a
test-only focus setup adjustment. Do not modify production code before observing this
expected red result.

### Task 2: Implement the minimal scoped control changes

**Files:**
- Modify: `src/camera_system_app/ui/widgets/focus_wheel_spinbox.py`.
- Modify: `src/camera_system_app/ui/widgets/__init__.py`.
- Modify: `src/camera_system_app/ui/widgets/viewer_inspector.py`.

**Interfaces:**
- Consumes: the failing tests from Task 1 and existing `SafeSpinBox` behavior.
- Produces: `SafeComboBox(QComboBox)` with a `wheelEvent(self, event)` method that calls
  `event.ignore()`, plus the explicit XYZ checkbox copy.

- [ ] **Step 1: Add the smallest safe combo-box class.**

In `focus_wheel_spinbox.py`, import `QComboBox` and add:

```python
class SafeComboBox(QComboBox):
    """A combo box that never changes selection from panel scrolling."""

    def wheelEvent(self, event) -> None:
        event.ignore()
```

Keep `SafeSpinBox` and `SafeDoubleSpinBox` unchanged. Add `SafeComboBox` to
`src/camera_system_app/ui/widgets/__init__.py` exports.

- [ ] **Step 2: Use the safe combo only in `ViewerInspector`.**

Import `SafeComboBox` alongside the existing safe spin boxes. Replace each Inspector
construction of `QComboBox()` with `SafeComboBox()` for these fields only:

```python
self.display_mode_combo
self.quality_combo
self.sphere_color_mode
self.camera_mode_combo
self.bookmark_combo
self.tone_mapping_combo
self.sh_degree_combo
self.resolution_preset_combo
self.fps_preset_combo
self.output_kind
```

Leave `QComboBox` imported for the existing `isinstance(control, QComboBox)` signal
dispatch. Do not change `viewer_toolbar.py` or any other page.

- [ ] **Step 3: Make the existing axis setting explicitly describe XYZ labels.**

Change only the existing checkbox copy in `viewer_inspector.py` to:

```python
self.show_axis_checkbox = QCheckBox("显示 XYZ 坐标")
self.show_axis_checkbox.setAccessibleName("显示 XYZ 坐标轴线和标签")
self.show_axis_checkbox.setToolTip("显示或隐藏场景中的 X/Y/Z 轴线与标签")
```

Keep `show_axis=self.show_axis_checkbox.isChecked()` and all existing
`DisplaySettings`/adapter wiring unchanged.

### Task 3: Run the focused green cycle and inspect the scoped diff

**Files:**
- Test: `tests/app_shell/test_ui_design_system.py`.
- Source: `src/camera_system_app/ui/widgets/focus_wheel_spinbox.py`.
- Source: `src/camera_system_app/ui/widgets/__init__.py`.
- Source: `src/camera_system_app/ui/widgets/viewer_inspector.py`.

- [ ] **Step 1: Run the three new tests after the minimal implementation.**

Run the exact command from Task 1, with expected result `3 passed`.

- [ ] **Step 2: Run the existing focused UI/viewer tests.**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src:multiwebcam/src:Tx_Rx:3DGSviewer/q3dviewer \
  .venv-jetson/bin/python -m pytest -q \
  tests/app_shell/test_ui_design_system.py \
  tests/app_shell/test_viewer_ui.py \
  tests/app_shell/test_q3dviewer_sphere.py
```

Expected result: all tests pass; no test outside the four scoped files is changed.

- [ ] **Step 3: Review the diff for scope before broader validation.**

Run:

```bash
git diff --check
git diff -- src/camera_system_app/ui/widgets/focus_wheel_spinbox.py \
  src/camera_system_app/ui/widgets/__init__.py \
  src/camera_system_app/ui/widgets/viewer_inspector.py \
  tests/app_shell/test_ui_design_system.py
```

Verify there are no edits to `viewer_toolbar.py`, navigation, `ResultViewerPage`,
`ViewerBindings`, `DisplaySettings`, or any non-scoped page.

### Task 4: Full regression and final handoff

**Files:**
- Verify only; no additional source changes expected.

- [ ] **Step 1: Run the full test suite.**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src:multiwebcam/src:Tx_Rx:3DGSviewer/q3dviewer \
  .venv-jetson/bin/python -m pytest -q
```

Expected result: all existing tests pass with the known hardware-only skip.

- [ ] **Step 2: Compile the touched Python packages.**

Run:

```bash
.venv-jetson/bin/python -m compileall -q src/camera_system_app/ui/widgets tests/app_shell
```

- [ ] **Step 3: Capture a final UI screenshot with the Inspector expanded.**

Open the result viewer, expand the right-side “参数” panel, verify the “显示 XYZ 坐标”
checkbox is visible, then scroll over each numeric/combo field. Confirm values do not
change until a field is clicked and edited with the keyboard. Confirm the left 01–06
navigation, top toolbar and 3D viewport remain unchanged.

- [ ] **Step 4: Commit only the scoped implementation files.**

```bash
git add src/camera_system_app/ui/widgets/focus_wheel_spinbox.py \
  src/camera_system_app/ui/widgets/__init__.py \
  src/camera_system_app/ui/widgets/viewer_inspector.py \
  tests/app_shell/test_ui_design_system.py
git commit -m "fix: guard viewer inspector parameter scrolling"
```
