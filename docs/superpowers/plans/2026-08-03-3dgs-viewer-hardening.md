# 3DGS 查看器逻辑加固实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven-development when changing production behavior. Steps use checkbox syntax for tracking.

**Goal:** 修复 3DGS 查看器已复现的状态、生命周期、相机、导出和渲染正确性问题。

**Architecture:** 在现有 PySide6 页面、ViewerSession、ViewerRenderController 和
q3dviewer adapter 边界内做小范围修复。加载线程负责 PLY 身份 metadata；adapter
负责 native camera/clear alpha；GaussianItem 负责大模型排序 fallback；页面和
controller 只管理状态恢复，不重写现有 viewer 架构。

**Tech Stack:** Python, PySide6, NumPy, OpenGL/GLSL, pytest。

## Global Constraints

- 保留现有左侧 01–06 主导航和右侧可折叠深色 Inspector。
- 保留现有业务信号、ViewerProject JSON 格式和 q3dviewer 依赖协议。
- 所有生产修改先有能在旧实现上失败的 focused test。
- 不覆盖或回滚现有 `multiwebcam` 工作树改动。

---

### Task 1: 修复加载错误状态与 PLY metadata 线程边界

**Files:**
- Modify: `src/camera_system_app/ui/pages/result_viewer.py`
- Modify: `src/camera_system_app/ui/viewer_bindings.py`
- Modify: `src/camera_system_app/workers/viewer_load_worker.py`
- Test: `tests/app_shell/test_q3dviewer_integration.py`
- Test: `tests/app_shell/test_viewer_ui.py`

- [ ] 写并运行重载失败、首次失败和球体能力保持的失败测试。
- [ ] 让 worker 在后台返回 `source_size` 与 `source_sha256`，GUI 复用 metadata。
- [ ] 让 page 按首次加载/重载恢复正确的控件可见性和 enabled 状态。
- [ ] 运行 focused UI/loader tests。

### Task 2: 修复 encoder cleanup、session 原子提交与相机 canonicalization

**Files:**
- Modify: `src/camera_system_app/ui/viewer_render_controller.py`
- Modify: `src/camera_system_app/application/viewer_session.py`
- Modify: `src/camera_system_app/infrastructure/adapters/q3dviewer_adapter.py`
- Test: `tests/app_shell/test_viewer_render_controller.py`
- Test: `tests/app_shell/test_viewer_session.py`
- Test: `tests/app_shell/test_viewer_adapter.py`

- [ ] 写 encoder 启动后 adapter 失败仍 abort 的测试。
- [ ] 写 adapter 失败不污染 session project 的测试。
- [ ] 写不一致相机姿态 round-trip 的测试。
- [ ] 实现 abort-before-clear、成功后提交和 look-at canonicalization。
- [ ] 运行 focused controller/session/adapter tests。

### Task 3: 修复透明导出、球体混合和大模型排序

**Files:**
- Modify: `src/camera_system_app/infrastructure/adapters/q3dviewer_adapter.py`
- Modify: `src/camera_system_app/ui/viewer_render_controller.py`
- Modify: `3DGSviewer/q3dviewer/q3dviewer/custom_items/gaussian_sphere_pass.py`
- Modify: `3DGSviewer/q3dviewer/q3dviewer/custom_items/gaussian_item.py`
- Modify: `3DGSviewer/q3dviewer/q3dviewer/base_glwidget.py`
- Test: `tests/app_shell/test_viewer_render_controller.py`
- Test: `tests/app_shell/test_q3dviewer_sphere.py`
- Test: `tests/app_shell/test_q3dviewer_integration.py`

- [ ] 写透明 clear alpha、预乘球体混合和大模型排序 fallback 的失败测试。
- [ ] 增加 adapter 的 render background alpha 边界。
- [ ] 修复球体 blend factor；实现 numpy depth order 和 padded SSBO 上传。
- [ ] 修复 native depth picker 边界索引，避免底层点击越界。
- [ ] 运行 focused render/sphere/integration tests。

### Task 4: 全量回归与工作树审计

**Files:**
- No new production files.
- Test: all viewer tests under `tests/app_shell/test_viewer*.py` and `test_q3dviewer*.py`.

- [ ] 运行查看器全量测试和 UI smoke tests。
- [ ] 在 offscreen 环境运行可用的 Qt tests，记录硬件 OpenGL skip 原因。
- [ ] 检查 `git diff --check` 和 `git status`，确认不触碰已有无关改动。
- [ ] 用只读探针验证重载失败、encoder abort、相机 round-trip 和透明 alpha。
