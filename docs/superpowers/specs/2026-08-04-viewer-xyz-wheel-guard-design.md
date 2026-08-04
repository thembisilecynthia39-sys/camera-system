# 3DGS 查看器 XYZ 坐标开关与参数滚轮保护设计

## 背景

结果查看页的 3D 场景已经由 `SceneOverlayItem` 绘制 X/Y/Z 轴线和标签，右侧
`ViewerInspector` 也已经把 `show_axis` 纳入 `DisplaySettings`。但现有文案
“显示坐标轴”没有明确说明它同时控制 XYZ 标签；同时，右侧参数面板中的部分
`QComboBox` 仍保留 Qt 默认滚轮行为，用户滚动面板时会误改参数。

## 目标

1. 提供明确的“显示 XYZ 坐标”开关，控制场景中的 X/Y/Z 轴线与标签显示/隐藏。
2. 保持该状态沿现有 `DisplaySettings → ViewerSession → Q3DViewerAdapter →
   SceneOverlayItem` 链路更新，并随查看器项目保存与恢复。
3. 右侧参数面板滚动时不改变参数值。
4. 参数只能通过显式交互修改：数值框点击后键盘输入；组合框点击展开后用鼠标点选
   或键盘选择。
5. 不影响左侧 01–06 导航、顶部工具栏组合框和参数面板自身的滚动。

## 已确认的根因

复现 `ViewerInspector` 后，向未聚焦控件发送一个向上滚轮事件得到：

- `quality_combo` 从“高质量”切换为“预览”；
- `sh_degree_combo` 从“SH 3 阶”切换为“SH 2 阶”；
- 已有 `SafeDoubleSpinBox` 数值框在直接控件和内部 `lineEdit` 上均不改变值。

因此问题边界是右侧参数面板中的组合框仍使用 Qt 默认 `QComboBox.wheelEvent`，
不是 XYZ 数据链路或数值框键盘编辑链路的问题。

## 方案

### XYZ 坐标开关

复用已有 `show_axis` 布尔状态，不新增并行字段。将复选框和表单标签明确命名为
“显示 XYZ 坐标”，并设置说明性 tooltip/accessibility name，表达它同时控制轴线
和 X/Y/Z 标签。默认值与现有 `DisplaySettings` 保持一致，避免加载旧项目时改变
画面。

### 参数控件滚轮保护

在现有 `focus_wheel_spinbox.py` 中增加一个轻量的安全组合框类型，用于
`ViewerInspector` 内的所有 `QComboBox`：

- 关闭下拉菜单时忽略滚轮事件，让事件继续交给外层 `QScrollArea`，因此滚动面板
  仍然可用；
- 组合框通过鼠标点击打开后，仍可鼠标点击选项；键盘上下键和回车仍可用；
- 不修改顶部工具栏组合框，缩小行为变化范围。

现有 `SafeSpinBox` / `SafeDoubleSpinBox` 继续负责数值框滚轮保护；通过回归测试
确保点击输入框、选中文本后用键盘输入仍然能够提交值。

## 数据流

```text
显示 XYZ 坐标复选框
        ↓
ViewerInspector.display_settings_changed
        ↓
ViewerBindings.set_display_settings
        ↓
ViewerSession.set_display_settings
        ↓
Q3DViewerAdapter.set_display_settings(show_axis=...)
        ↓
SceneOverlayItem.options["axis"]
        ↓
轴线与 XYZ 标签同时绘制/隐藏
```

## 测试设计

新增或调整以下行为测试：

- Inspector 的 XYZ 开关文案、accessibility name 和 tooltip 明确包含 XYZ；
- 切换开关产生 `DisplaySettings.show_axis` 的 true/false 值；
- Inspector 中所有组合框收到滚轮事件后保持原选项；
- Inspector 数值框收到滚轮事件后保持原值；
- 点击数值框、全选并键盘输入后，数值仍能正确提交；
- 现有场景覆盖测试继续验证 `SceneOverlayItem` 的轴线与 XYZ 标签共用同一开关。

## 非目标

- 不恢复结果页底部时间轴、FPS、帧切换或镜头编辑控件。
- 不改变顶部工具栏的组合框交互。
- 不新增独立的 XYZ 数据模型或改变查看器项目文件格式。
