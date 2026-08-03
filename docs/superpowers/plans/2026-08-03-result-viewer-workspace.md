# 结果查看工作区重设计实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `03 结果查看` 改造成保留左侧主导航、以 3D 展示为中心、带右侧可折叠深色浮层参数面板的 Qt Widgets 工作区。

**Architecture:** 保留现有 `ResultViewerPage`、`ViewerInspector` 的业务信号和 ViewerProject 绑定，只替换页面壳和横向 `QSplitter`。新增轻量 `ViewerStage` 负责把视口铺满并把 Inspector 以子控件方式定位在右侧，Inspector 自己管理展开/折叠状态；QSS 通过现有语义化 token 为整个 viewer chrome 提供统一深色层级。

**Tech Stack:** Python 3.8-compatible syntax, PySide6 Qt Widgets, Fusion/QSS, pytest, pytest-qt-compatible `qapp` fixture.

## Global Constraints

- 左侧 01–06 主导航保持可见，导航索引和文本不变。
- 主设计尺寸为 1600×900，最小应用窗口仍需可用至 1024×680。
- 进入结果查看页后不展示“工作流 03 · 查看与检查”“结果查看”或重复页面说明；结果来源卡不再占据页面布局。
- Inspector 默认折叠为约 44px 右侧把手，展开宽度约 320px，展开不改变 OpenGL 视口尺寸。
- Inspector、工具栏、下拉菜单、输入框、复选框、滚动区全部使用深色 viewer chrome，不遗留白色控件。
- 保持现有显示、外观、渲染、相机、书签、时间轴、保存和导出信号名称及控制器协议。
- 本次不修改 Gaussian 渲染器、ViewerProject 数据模型或新增 Qt/OpenGL 依赖。
- 主要交互控件保持至少 40px 高度，折叠把手和工具栏入口有可见焦点、AccessibleName 和 tooltip。
- 使用测试先行；每个任务都先运行对应 focused test，再实现，再运行回归测试。
- 使用 `apply_patch` 编辑源文件；每个任务完成后提交独立 commit。

## 文件结构与职责

- Modify `src/camera_system_app/ui/pages/base.py`: 保存页面标题控件并提供只影响目标页面的可见性方法。
- Create `src/camera_system_app/ui/widgets/viewer_stage.py`: 管理视口全铺和 Inspector 右侧浮层几何，不承载渲染或业务信号。
- Modify `src/camera_system_app/ui/widgets/viewer_inspector.py`: 增加标题栏、折叠把手和折叠状态 API；保留现有四组设置控件与信号。
- Modify `src/camera_system_app/ui/widgets/viewer_toolbar.py`: 让参数按钮成为可同步的 checkable 入口，并暴露同步方法。
- Modify `src/camera_system_app/ui/pages/result_viewer.py`: 移除结果来源卡，建立 clean viewer shell，接入 `ViewerStage`，管理加载/错误提示和 Inspector 状态。
- Modify `src/camera_system_app/ui/widgets/__init__.py`: 导出 `ViewerStage`。
- Modify `src/camera_system_app/ui/design_tokens.py`: 增加 viewer overlay、raised surface、hover、border 的语义 token。
- Modify `src/camera_system_app/ui/theme.py`: 完整覆盖 viewer chrome 与 Inspector 内所有 Qt 控件的深色 QSS。
- Modify `tests/app_shell/test_viewer_ui.py`: 覆盖页面壳、浮层尺寸、折叠行为和工具栏同步。
- Modify `tests/app_shell/test_q3dviewer_integration.py`: 保留“无结果文件仍可选择”的行为验证，改用空状态/公开的兼容句柄。

---

### Task 1: 建立 clean viewer shell 与右侧浮层宿主

**Files:**

- Create: `src/camera_system_app/ui/widgets/viewer_stage.py`
- Modify: `src/camera_system_app/ui/pages/base.py`
- Modify: `src/camera_system_app/ui/pages/result_viewer.py`
- Modify: `src/camera_system_app/ui/widgets/__init__.py`
- Test: `tests/app_shell/test_viewer_ui.py`
- Test: `tests/app_shell/test_q3dviewer_integration.py`

**Interfaces:**

- `BasePage.set_page_header_visible(visible: bool) -> None`：只切换页面 header 的可见性。
- `ViewerStage(viewport: QWidget, inspector: QWidget, parent: Optional[QWidget] = None)`：接管两个子控件的 parent 和几何布局。
- `ViewerStage.viewport_rect() -> QRect`：返回当前视口子控件的几何矩形，供测试确认展开浮层不改变视口尺寸。
- `ViewerStage.relayout() -> None`：按 host 尺寸重新定位视口和浮层。

- [ ] **Step 1: 写页面壳和浮层布局的失败测试**

```python
def test_result_page_is_a_clean_viewer_shell_with_right_overlay(qapp, tmp_path):
    page = ResultViewerPage(str(tmp_path / "results"), str(tmp_path / "viewer"))
    page.resize(900, 640)
    page.show()
    qapp.processEvents()

    assert page._page_header.isVisible() is False
    assert page._viewer_stage is not None

    viewport = QWidget()
    viewport.setMinimumSize(480, 320)
    page.set_viewer_widget(viewport, "scene.ply", 1)
    qapp.processEvents()
    before = page._viewer_stage.viewport_rect().size()

    assert page._inspector.is_collapsed is True
    page._inspector.set_collapsed(False)
    qapp.processEvents()

    assert page._inspector.width() > 44
    assert page._viewer_stage.viewport_rect().size() == before
    page.hide()
```

- [ ] **Step 2: 运行 focused test，确认当前实现因缺少 `_page_header`、`_viewer_stage` 和折叠 API 失败**

Run: `pytest -q tests/app_shell/test_viewer_ui.py::test_result_page_is_a_clean_viewer_shell_with_right_overlay`

Expected: FAIL with an attribute/layout assertion before implementation.

- [ ] **Step 3: 暴露 BasePage header 并新增 ViewerStage**

在 `BasePage.__init__` 中保存 `PageHeader`：

```python
self._page_header = PageHeader(title, description, eyebrow)
root_layout.addWidget(self._page_header)

def set_page_header_visible(self, visible: bool) -> None:
    self._page_header.setVisible(bool(visible))
```

`ViewerStage` 不使用 `QSplitter` 或 host layout 挤压视口，使用显式子控件几何：

```python
class ViewerStage(QFrame):
    def resizeEvent(self, event):
        self._viewport.setGeometry(self.rect())
        margin = 12
        width = self._inspector.panel_width_for_host(self.width())
        height = max(0, self.height() - margin * 2)
        x = max(margin, self.width() - margin - width)
        self._inspector.setGeometry(x, margin, width, height)
        self._inspector.raise_()
        super().resizeEvent(event)
```

视口保持 `QFrame#viewerViewport` 子控件，Inspector 只覆盖右侧，不作为布局项参与视口尺寸协商。

- [ ] **Step 4: 在 ResultViewerPage 中移除来源卡并接入 ViewerStage**

保留 `result_root` 和 `viewer_root` 参数用于现有加载流程，但删除页面内的结果目录、源码路径和三按钮卡片。创建顺序调整为：`viewer_frame → toolbar → viewport_frame → inspector → viewer_stage`。将空状态继续加入 `viewport_layout`，空状态按钮仍发出 `select_local_result_requested`。

在构造结尾执行：

```python
self.set_page_header_visible(False)
self.layout.setContentsMargins(0, 0, 0, 0)
self.layout.setSpacing(0)
```

`_viewer_frame` 只包含 toolbar 和 `ViewerStage`；时间轴仍作为 viewer frame 后的独立控件。删除 `_studio_splitter` 和 `_narrow_mode` 的布局分支，`resizeEvent` 只调用 stage relayout 与已有 viewport-size 更新。

为现有测试和内部调用保留兼容句柄：`_select` 指向空状态的 `action_button`，`_reset` 指向 toolbar 的重置按钮；`_action` 保留为不可见的“加载当前 PLY”命令按钮并继续由 `open_current_result` 管理，不把它加入任何可见布局。

- [ ] **Step 5: 更新无结果和窄窗口测试并运行回归**

将旧的 `QSplitter`/互斥显示断言改为：空状态按钮可用、结果页 header 隐藏、Inspector 默认折叠；在 720×600 和 900×640 下验证 `viewport_rect().size()` 在展开前后不变。

Run: `pytest -q tests/app_shell/test_viewer_ui.py tests/app_shell/test_q3dviewer_integration.py`

Expected: focused viewer tests PASS，旧的分栏/窄模式断言被替换为浮层断言。

- [ ] **Step 6: Commit**

```bash
git add src/camera_system_app/ui/pages/base.py src/camera_system_app/ui/pages/result_viewer.py src/camera_system_app/ui/widgets/viewer_stage.py src/camera_system_app/ui/widgets/__init__.py tests/app_shell/test_viewer_ui.py tests/app_shell/test_q3dviewer_integration.py
git commit -m "feat: make result viewer a clean overlay workspace"
```

### Task 2: 增加 Inspector 折叠状态与工具栏同步

**Files:**

- Modify: `src/camera_system_app/ui/widgets/viewer_inspector.py`
- Modify: `src/camera_system_app/ui/widgets/viewer_toolbar.py`
- Modify: `src/camera_system_app/ui/pages/result_viewer.py`
- Test: `tests/app_shell/test_viewer_ui.py`

**Interfaces:**

- `ViewerInspector.collapsed_changed = Signal(bool)`。
- `ViewerInspector.is_collapsed -> bool`。
- `ViewerInspector.set_collapsed(collapsed: bool) -> None`。
- `ViewerInspector.toggle_collapsed() -> None`。
- `ViewerInspector.panel_width_for_host(host_width: int) -> int`：折叠返回 44；展开返回 `min(320, max(280, int(host_width * 0.4)))`。
- `ViewerToolbar.set_inspector_expanded(expanded: bool) -> None`：通过 `QSignalBlocker` 同步参数按钮，不发出新的命令信号。

- [ ] **Step 1: 写 Inspector 折叠和 toolbar 同步的失败测试**

```python
def test_viewer_inspector_collapses_to_accessible_handle(qapp):
    inspector = ViewerInspector()
    changes = []
    inspector.collapsed_changed.connect(changes.append)

    assert inspector.is_collapsed is True
    assert inspector.panel_width_for_host(900) == 44
    inspector.set_collapsed(False)

    assert inspector.is_collapsed is False
    assert inspector.panel_width_for_host(900) == 320
    assert changes == [False]
    assert inspector.collapse_button.accessibleName()
```

```python
def test_toolbar_inspector_button_tracks_expanded_state_without_emitting(qapp):
    toolbar = ViewerToolbar()
    commands = []
    toolbar.inspector_requested.connect(lambda: commands.append("toggle"))

    toolbar.set_inspector_expanded(True)
    assert toolbar.inspector_button.isChecked() is True
    assert commands == []
```

- [ ] **Step 2: 运行 focused tests，确认当前 Inspector 没有折叠状态和同步 API**

Run: `pytest -q tests/app_shell/test_viewer_ui.py::test_viewer_inspector_collapses_to_accessible_handle tests/app_shell/test_viewer_ui.py::test_toolbar_inspector_button_tracks_expanded_state_without_emitting`

Expected: FAIL with missing signal/property/method.

- [ ] **Step 3: 给 Inspector 增加标题栏、把手和折叠状态**

在现有 root layout 中先加入 `QFrame#viewerInspectorHeader`，包含标题 `参数` 和 `QToolButton#viewerInspectorCollapseButton`。`set_collapsed` 只隐藏/显示 scroll 内容、调整固定宽度并更新 tooltip/accessible name：

```python
def set_collapsed(self, collapsed):
    collapsed = bool(collapsed)
    if collapsed == self._collapsed:
        return
    self._collapsed = collapsed
    self.scroll.setVisible(not collapsed)
    self._title.setVisible(not collapsed)
    self.collapse_button.setText("⚙" if collapsed else "›")
    self.collapse_button.setToolTip("展开参数面板" if collapsed else "折叠参数面板")
    self.collapse_button.setAccessibleName(self.collapse_button.toolTip())
    self.collapsed_changed.emit(collapsed)
```

初始化时将 `_collapsed = True`，首次 `set_collapsed(True)` 时不重复发信号。保留 `sections`、所有 settings getter/setter 和现有业务信号不变。

- [ ] **Step 4: 让 toolbar 参数按钮可同步**

将 `inspector_button` 设为 checkable，并实现：

```python
def set_inspector_expanded(self, expanded):
    blocker = QSignalBlocker(self.inspector_button)
    self.inspector_button.setChecked(bool(expanded))
    del blocker
```

ResultViewerPage 中连接 `collapsed_changed`，使右侧把手和顶部参数按钮状态一致；按钮点击只调用 `_toggle_inspector`，不改变现有 `inspector_requested` 信号。

- [ ] **Step 5: 运行 UI focused tests**

Run: `pytest -q tests/app_shell/test_viewer_ui.py`

Expected: all Inspector and toolbar behavior tests PASS。

- [ ] **Step 6: Commit**

```bash
git add src/camera_system_app/ui/widgets/viewer_inspector.py src/camera_system_app/ui/widgets/viewer_toolbar.py src/camera_system_app/ui/pages/result_viewer.py tests/app_shell/test_viewer_ui.py
git commit -m "feat: add collapsible viewer inspector"
```

### Task 3: 完成深色 viewer chrome 与输入控件主题

**Files:**

- Modify: `src/camera_system_app/ui/design_tokens.py`
- Modify: `src/camera_system_app/ui/theme.py`
- Test: `tests/app_shell/test_viewer_ui.py`
- Test: `tests/app_shell/test_ui_design_system.py`

**Interfaces:**

- `style_tokens()` 新增 `dark_viewer_overlay`、`dark_viewer_raised`、`dark_viewer_hover`、`dark_viewer_border`。
- QSS 保持通过 `application_stylesheet()` 统一注入，不在 Python widget 中散落颜色字面量。

- [ ] **Step 1: 写主题 token 和控件覆盖的失败测试**

```python
from camera_system_app.ui.design_tokens import style_tokens

def test_viewer_tokens_define_dark_overlay_roles():
    tokens = style_tokens()
    assert tokens["dark_viewer_overlay"] != tokens["light_surface"]
    assert tokens["dark_viewer_raised"] != tokens["light_surface"]
    assert tokens["dark_viewer_border"]
```

```python
def test_viewer_controls_have_dark_scope_object_names(qapp):
    inspector = ViewerInspector()
    assert inspector.objectName() == "viewerInspector"
    assert inspector.scroll.objectName() == "viewerInspectorScroll"
    assert inspector.content.objectName() == "viewerInspectorContent"
    assert inspector.background_color_edit.objectName() == "viewerInspectorInput"
```

- [ ] **Step 2: 运行 focused tests，确认新增 token/objectName 尚不存在**

Run: `pytest -q tests/app_shell/test_ui_design_system.py::test_viewer_tokens_define_dark_overlay_roles tests/app_shell/test_viewer_ui.py::test_viewer_controls_have_dark_scope_object_names`

Expected: FAIL with missing token or objectName assertion.

- [ ] **Step 3: 增加语义化 viewer token**

在 `SEMANTIC_DARK` 中用现有 primitive 组合出 viewer 角色：overlay 取 `navy_900`，raised 取 `navy_800`，hover 取 `navy_700`，border 取 `dark_border`；在 `style_tokens()` 里以 `dark_` 前缀展开。禁止在 QSS 外再新增任意硬编码色值。

- [ ] **Step 4: 完整覆盖 viewer QSS**

在 `QWidget#resultPageSurface` 作用域下覆盖以下对象和控件：

```css
QWidget#resultPageSurface QWidget#viewerStage,
QWidget#resultPageSurface QWidget#viewerInspector {
    background: $dark_viewer_overlay;
    border: 1px solid $dark_viewer_border;
}
QWidget#resultPageSurface QWidget#viewerInspector QLineEdit,
QWidget#resultPageSurface QWidget#viewerInspector QComboBox,
QWidget#resultPageSurface QWidget#viewerInspector QSpinBox,
QWidget#resultPageSurface QWidget#viewerInspector QDoubleSpinBox,
QWidget#resultPageSurface QWidget#viewerInspector QPushButton,
QWidget#resultPageSurface QWidget#viewerInspector QToolButton {
    background: $dark_viewer_raised;
    color: $dark_text;
    border: 1px solid $dark_viewer_border;
}
QWidget#resultPageSurface QWidget#viewerInspector QComboBox QAbstractItemView {
    background: $dark_viewer_raised;
    color: $dark_text;
    selection-background-color: $dark_interactive;
}
```

同时给 `QScrollArea#viewerInspectorScroll`、`QWidget#viewerInspectorContent`、`QCheckBox`、disabled/focus/hover/checked 状态设置深色背景、文本和边框，避免 `QLineEdit`、按钮或下拉 popup 回落到全局白色样式。工具栏、时间轴和 viewport 使用同一套 raised/overlay/border token。

- [ ] **Step 5: 运行主题和全 UI 测试**

Run: `pytest -q tests/app_shell/test_ui_design_system.py tests/app_shell/test_viewer_ui.py`

Expected: PASS；不能只检查 stylesheet 字符串存在，必须让 offscreen widget 完成 polish。

- [ ] **Step 6: Commit**

```bash
git add src/camera_system_app/ui/design_tokens.py src/camera_system_app/ui/theme.py src/camera_system_app/ui/widgets/viewer_inspector.py tests/app_shell/test_ui_design_system.py tests/app_shell/test_viewer_ui.py
git commit -m "style: apply dark viewer chrome to all controls"
```

### Task 4: 整合加载状态、回归验证与需求审计

**Files:**

- Modify: `src/camera_system_app/ui/pages/result_viewer.py`
- Modify: `tests/app_shell/test_viewer_ui.py`
- Modify: `tests/app_shell/test_q3dviewer_integration.py`
- Test: `tests/app_shell/test_viewer_project_integration.py`

**Interfaces:**

- `ResultViewerPage._set_banner_status(text: str, status: str, visible: bool = True) -> None`：仅在 loading/warning/error 等真实状态显示提示。
- `ResultViewerPage._toggle_inspector() -> None`：只切换 Inspector collapsed 状态。
- `ResultViewerPage._update_viewport_size() -> None`：继续把实际 OpenGL widget 尺寸同步给 Inspector 的当前视口分辨率 preset。

- [ ] **Step 1: 写成功状态隐藏、警告状态保留和导航不变的回归测试**

```python
def test_loaded_result_hides_page_copy_and_success_banner(qapp, tmp_path):
    page = ResultViewerPage(str(tmp_path / "results"), str(tmp_path / "viewer"))
    page.set_viewer_widget(QLabel(), "scene.ply", 1)
    qapp.processEvents()

    assert page._page_header.isVisible() is False
    assert page._banner.isVisible() is False
    assert page._inspector.is_collapsed is True
    page.hide()
```

```python
def test_sphere_warning_remains_visible_without_restoring_source_card(qapp, tmp_path):
    page = ResultViewerPage(str(tmp_path / "results"), str(tmp_path / "viewer"))
    page.set_sphere_modes_available(False, "shader unavailable")
    page.set_viewer_widget(QLabel(), "scene.ply", 1)
    qapp.processEvents()

    assert page._banner.isVisible() is True
    assert "外接球显示不可用" in page._banner._text.text()
    page.hide()
```

- [ ] **Step 2: 运行回归测试，确认当前状态提示仍常驻或旧分栏断言失败**

Run: `pytest -q tests/app_shell/test_viewer_ui.py tests/app_shell/test_q3dviewer_integration.py tests/app_shell/test_viewer_project_integration.py`

Expected: FAIL until status visibility and old test assumptions are updated.

- [ ] **Step 3: 收敛 ResultViewerPage 状态逻辑**

初始化隐藏 `_banner`；成功加载时隐藏 banner；`show_loading` 和 `show_load_error` 显示 banner；sphere shader warning 保持可见。`set_result_available` 的成功信息不作为常驻提示显示，错误仍保留文字和符号。`_toggle_inspector` 改为：

```python
def _toggle_inspector(self):
    if self._viewer_widget is None:
        return
    self._inspector.set_collapsed(not self._inspector.is_collapsed)
```

删除 narrow mode 下的“Inspector/Timeline 互斥隐藏”逻辑；Timeline 可以继续显示，Inspector 展开时只覆盖右侧，符合不挤压视口的要求。

- [ ] **Step 4: 运行完整相关测试**

Run: `pytest -q tests/app_shell/test_viewer_ui.py tests/app_shell/test_q3dviewer_integration.py tests/app_shell/test_viewer_project_integration.py tests/app_shell/test_ui_design_system.py`

Expected: PASS。

- [ ] **Step 5: 运行完整测试套件并检查差异**

Run: `pytest -q`

Expected: PASS；随后运行 `git diff --check`，并用 `rg` 确认结果查看页不再保留旧的 `_studio_splitter`、页面说明文案或旧来源卡 layout 引用。

- [ ] **Step 6: Commit**

```bash
git add src/camera_system_app/ui/pages/result_viewer.py tests/app_shell/test_viewer_ui.py tests/app_shell/test_q3dviewer_integration.py
git commit -m "test: verify clean result viewer workspace behavior"
```

## 计划自检

- 页面标题、说明、来源卡和常驻成功提示：Task 1、Task 4。
- 左侧导航保持：Task 4 的 MainWindow 回归检查及完整 shell 测试。
- 右侧浮层默认折叠、展开不挤压视口：Task 1、Task 2、Task 4。
- 深色控件与 popup 覆盖：Task 3。
- 键盘、可访问名称、折叠把手：Task 2、Task 3。
- 现有信号、设置对象和控制器协议：Task 2、Task 4 的全量回归。
- Completeness scan：计划没有悬而未决的步骤；所有步骤给出具体文件、API、命令或代码。
