# 3DGS 查看器演示导航与坐标显示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 3DGS 查看器在全屏演示中可安全退出、可用键盘环视、支持自动 360°环视，并显示带标签的 XYZ 坐标与相机数值。

**Architecture:** 在 `ViewerBindings` 负责全局键盘和演示状态，在 `ViewerToolbar` 负责环视入口，在 `Q3DViewerAdapter`/`BaseGLWidget` 负责相机轨道旋转；`SceneOverlayItem` 负责世界轴和屏幕标签。所有新状态沿用现有 Qt signals、`ViewerSession` 和 q3dviewer widget，不增加新的持久化字段。

**Tech Stack:** Python 3, PySide6, NumPy, Qt Widgets, q3dviewer OpenGL core profile, pytest。

## Global Constraints

- 保留左侧 01–06 主导航和现有深色浮层 Inspector。
- 普通模式有时间轴时 Left/Right 继续执行 `ViewerPlayback.step_backward/step_forward`。
- 演示模式下 Esc 必须优先退出，不能被文本控件或 QOpenGLWidget 焦点阻断。
- XYZ 轴显示必须保持红 X、绿 Y、蓝 Z 的语义，并用文字标签补充颜色信息。
- 不把环视每一帧写入 sidecar；停止环视时最多提交一次相机状态。

---

### Task 1: 全局键盘与演示模式状态

**Files:**
- Modify: `src/camera_system_app/ui/viewer_bindings.py:__init__, set_presentation_mode, eventFilter, shutdown`
- Modify: `src/camera_system_app/ui/widgets/viewer_toolbar.py:signals and presentation_button state`
- Modify: `src/camera_system_app/ui/pages/result_viewer.py:set_rendering/set_viewer_widget`
- Test: `tests/app_shell/test_viewer_project_integration.py`
- Test: `tests/app_shell/test_viewer_ui.py`

**Interfaces:**
- Produces `ViewerBindings._is_viewer_key_target(watched) -> bool` and a QApplication-level event filter.
- Produces `ViewerToolbar.set_presentation_mode(enabled: bool) -> None`.

- [ ] **Step 1: Write the failing tests**

  Add a test that sends an Esc `QKeyEvent` to a result-page descendant while presentation mode is active and asserts `binding.is_presentation_mode is False`, plus a test that the presentation button changes to an exit label and can toggle the state back.

- [ ] **Step 2: Run the focused tests and verify the expected failure**

  Run:

  ```bash
  QT_QPA_PLATFORM=offscreen PYTHONPATH=src:multiwebcam/src:Tx_Rx:3DGSviewer/q3dviewer .venv-jetson/bin/python -m pytest -q tests/app_shell/test_viewer_project_integration.py::test_presentation_escape_from_viewer_child tests/app_shell/test_viewer_ui.py::test_presentation_button_reflects_active_state
  ```

  Expected: the Escape test remains in presentation mode and the button state does not change because the current filter only accepts `watched is self.window`.

- [ ] **Step 3: Implement the smallest event/state fix**

  Install the binding as an event filter on `QApplication.instance()`. Handle only key events whose watched object is the main window or a descendant. Process Escape before text-focus checks, update the presentation button through `set_presentation_mode`, and restore the saved sidebar/status/fullscreen state on exit. Remove/stop the application event filter and any navigation timers during `shutdown()`.

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run the same command from Step 2, then run `pytest -q tests/app_shell/test_viewer_project_integration.py tests/app_shell/test_viewer_ui.py`.

- [ ] **Step 5: Commit**

  ```bash
  git add src/camera_system_app/ui/viewer_bindings.py src/camera_system_app/ui/widgets/viewer_toolbar.py src/camera_system_app/ui/pages/result_viewer.py tests/app_shell/test_viewer_project_integration.py tests/app_shell/test_viewer_ui.py
  git commit -m "fix: make presentation mode keyboard-dismissible"
  ```

### Task 2: Direction-key orbit and adapter camera API

**Files:**
- Modify: `3DGSviewer/q3dviewer/q3dviewer/base_glwidget.py:orbit helpers`
- Modify: `src/camera_system_app/infrastructure/adapters/q3dviewer_adapter.py:orbit`
- Modify: `src/camera_system_app/ui/viewer_bindings.py:eventFilter and camera sync`
- Test: `tests/app_shell/test_q3dviewer_render_target.py`
- Test: `tests/app_shell/test_viewer_adapter.py`
- Test: `tests/app_shell/test_viewer_project_integration.py`

**Interfaces:**
- Produces `BaseGLWidget.orbit(delta_yaw: float = 0.0, delta_pitch: float = 0.0) -> None`.
- Produces `Q3DViewerAdapter.orbit(delta_yaw: float = 0.0, delta_pitch: float = 0.0) -> CameraPose`.

- [ ] **Step 1: Write the failing tests**

  Assert that a left/right orbit call changes the adapter camera pose, that applying `2*pi` horizontal orbit returns to the original position within tolerance, and that an Escape/arrow event delivered to a child is routed to the adapter when no timeline is present.

- [ ] **Step 2: Run focused tests and verify they fail**

  Run:

  ```bash
  QT_QPA_PLATFORM=offscreen PYTHONPATH=src:multiwebcam/src:Tx_Rx:3DGSviewer/q3dviewer .venv-jetson/bin/python -m pytest -q tests/app_shell/test_viewer_adapter.py::test_adapter_orbit_can_complete_full_turn tests/app_shell/test_viewer_project_integration.py::test_left_arrow_orbits_without_timeline
  ```

  Expected: `Q3DViewerAdapter` has no orbit method and the binding still calls the empty playback step.

- [ ] **Step 3: Implement the minimal orbit path**

  Add a native orbit helper that updates yaw/pitch in radians, wraps yaw continuously, clamps pitch to `[-pi/2 + 0.05, pi/2 - 0.05]`, marks the view dirty, calls `update()`, and returns the canonical adapter pose. In `eventFilter`, use orbit in presentation mode or when the timeline is empty; retain playback stepping otherwise.

- [ ] **Step 4: Run focused tests and verify they pass**

  Run the same focused command, then `pytest -q tests/app_shell/test_q3dviewer_render_target.py tests/app_shell/test_viewer_adapter.py tests/app_shell/test_viewer_project_integration.py`.

- [ ] **Step 5: Commit**

  ```bash
  git add 3DGSviewer/q3dviewer/q3dviewer/base_glwidget.py src/camera_system_app/infrastructure/adapters/q3dviewer_adapter.py src/camera_system_app/ui/viewer_bindings.py tests/app_shell/test_q3dviewer_render_target.py tests/app_shell/test_viewer_adapter.py tests/app_shell/test_viewer_project_integration.py
  git commit -m "feat: add keyboard orbit navigation"
  ```

### Task 3: Automatic panorama control

**Files:**
- Modify: `src/camera_system_app/ui/widgets/viewer_toolbar.py`
- Modify: `src/camera_system_app/ui/viewer_bindings.py`
- Modify: `src/camera_system_app/ui/pages/result_viewer.py`
- Test: `tests/app_shell/test_viewer_ui.py`
- Test: `tests/app_shell/test_viewer_project_integration.py`

**Interfaces:**
- Produces `ViewerToolbar.panorama_requested = Signal(bool)` and `set_panorama_playing(enabled: bool) -> None`.
- Produces a 33 ms binding timer that calls `Q3DViewerAdapter.orbit(delta_yaw=...)` and stops on page change, render, load, or shutdown.

- [ ] **Step 1: Write the failing tests**

  Assert that the toolbar exposes an accessible checkable “环视” button and that toggling it emits `True`/`False`. Add an integration test using a fake adapter to assert timer ticks call orbit and stopping it commits one final camera update.

- [ ] **Step 2: Run focused tests and verify they fail**

  Run:

  ```bash
  QT_QPA_PLATFORM=offscreen PYTHONPATH=src:multiwebcam/src:Tx_Rx:3DGSviewer/q3dviewer .venv-jetson/bin/python -m pytest -q tests/app_shell/test_viewer_ui.py::test_viewer_toolbar_exposes_panorama_control tests/app_shell/test_viewer_project_integration.py::test_panorama_timer_orbits_and_stops
  ```

  Expected: the toolbar has no panorama control and the binding has no panorama timer.

- [ ] **Step 3: Implement the timer and lifecycle guards**

  Add a checkable toolbar button, connect it to a binding timer, use a fixed `2*pi/20` radians-per-second horizontal speed, and route timer exceptions to a visible status message while stopping the timer. Stop the timer before `set_active(False)`, page changes, `start_render`, `open_result`, and `shutdown`; call `_sync_camera_from_adapter()` once when disabling.

- [ ] **Step 4: Run focused tests and verify they pass**

  Run the same focused command, then all viewer UI/project integration tests.

- [ ] **Step 5: Commit**

  ```bash
  git add src/camera_system_app/ui/widgets/viewer_toolbar.py src/camera_system_app/ui/viewer_bindings.py src/camera_system_app/ui/pages/result_viewer.py tests/app_shell/test_viewer_ui.py tests/app_shell/test_viewer_project_integration.py
  git commit -m "feat: add automatic panorama orbit"
  ```

### Task 4: Labeled XYZ axis and presentation coordinates

**Files:**
- Modify: `3DGSviewer/q3dviewer/q3dviewer/custom_items/scene_overlay_item.py`
- Modify: `src/camera_system_app/ui/viewer_bindings.py`
- Modify: `src/camera_system_app/ui/pages/result_viewer.py`
- Test: `tests/app_shell/test_q3dviewer_sphere.py`
- Test: `tests/app_shell/test_viewer_project_integration.py`

**Interfaces:**
- Produces `SceneOverlayItem.axis_labels(bounds, extent) -> tuple[dict, ...]` with labels `X`, `Y`, `Z`, 3D positions and semantic colors.
- Produces a presentation-state restore for `show_camera_info`.

- [ ] **Step 1: Write the failing tests**

  Assert that axis label metadata contains exactly X/Y/Z with red/green/blue colors and that entering/exiting presentation mode temporarily enables the camera XYZ readout while restoring the original setting.

- [ ] **Step 2: Run focused tests and verify they fail**

  Run:

  ```bash
  QT_QPA_PLATFORM=offscreen PYTHONPATH=src:multiwebcam/src:Tx_Rx:3DGSviewer/q3dviewer .venv-jetson/bin/python -m pytest -q tests/app_shell/test_q3dviewer_sphere.py::test_scene_overlay_exposes_xyz_axis_labels tests/app_shell/test_viewer_project_integration.py::test_presentation_mode_restores_camera_info_visibility
  ```

  Expected: the overlay has no axis-label metadata and presentation mode does not change the camera-info label visibility.

- [ ] **Step 3: Implement labeled overlay and state restore**

  Add deterministic label metadata and project each axis endpoint using `projection_matrix @ view_matrix`; paint the labels with Qt Painter after the OpenGL lines, using a readable dark chip and semantic colors. Save the original camera-info visibility on presentation entry, force it visible, and restore it on exit.

- [ ] **Step 4: Run focused tests and verify they pass**

  Run the same focused command, then all q3dviewer sphere/UI/integration tests.

- [ ] **Step 5: Commit**

  ```bash
  git add 3DGSviewer/q3dviewer/q3dviewer/custom_items/scene_overlay_item.py src/camera_system_app/ui/viewer_bindings.py src/camera_system_app/ui/pages/result_viewer.py tests/app_shell/test_q3dviewer_sphere.py tests/app_shell/test_viewer_project_integration.py
  git commit -m "feat: show labeled xyz axes in presentation"
  ```

### Task 5: Full regression and current-state audit

**Files:**
- Test: all `tests/app_shell/test_viewer*.py` and `tests/app_shell/test_q3dviewer*.py`

- [ ] **Step 1: Run focused viewer regression**

  ```bash
  QT_QPA_PLATFORM=offscreen PYTHONPATH=src:multiwebcam/src:Tx_Rx:3DGSviewer/q3dviewer .venv-jetson/bin/python -m pytest -q tests/app_shell/test_viewer_ui.py tests/app_shell/test_viewer_project_integration.py tests/app_shell/test_q3dviewer_render_target.py tests/app_shell/test_q3dviewer_sphere.py
  ```

- [ ] **Step 2: Run full regression and syntax checks**

  ```bash
  QT_QPA_PLATFORM=offscreen PYTHONPATH=src:multiwebcam/src:Tx_Rx:3DGSviewer/q3dviewer .venv-jetson/bin/python -m pytest -q
  .venv-jetson/bin/python -m compileall -q src 3DGSviewer/q3dviewer/q3dviewer
  git diff --check
  ```

- [ ] **Step 3: Verify hardware limitation is explicit**

  Confirm any skipped hardware test is only `test_q3dviewer_hardware.py` requiring a Jetson X11 OpenGL session; do not claim hardware rendering was validated by offscreen tests.

- [ ] **Step 4: Commit**

  ```bash
  git status --short
  git add 3DGSviewer/q3dviewer/q3dviewer/custom_items/scene_overlay_item.py 3DGSviewer/q3dviewer/q3dviewer/base_glwidget.py src/camera_system_app/ui/viewer_bindings.py src/camera_system_app/ui/pages/result_viewer.py src/camera_system_app/ui/widgets/viewer_toolbar.py src/camera_system_app/infrastructure/adapters/q3dviewer_adapter.py tests/app_shell/test_q3dviewer_render_target.py tests/app_shell/test_q3dviewer_sphere.py tests/app_shell/test_viewer_project_integration.py tests/app_shell/test_viewer_ui.py
  git commit -m "fix: complete 3dgs presentation navigation"
  ```
