# Camera System UI 设计系统

本文说明统一 Qt Widgets 界面的视觉规则、组件边界和验证方式。界面面向
Jetson Orin Nano 工作站，主窗口按 `1600×900` 设计，并保证在 `1024×680`
最小尺寸下可用。

## 设计方向

界面采用“工业工作站控制台”结构：

- 深色固定导航栏负责流程定位；
- 采集和 Gaussian 查看使用低眩光深色操作面；
- 传输、历史、设置和诊断使用高可读性的浅色文档面；
- 页面只突出一个主操作，次要操作使用描边按钮；
- 状态始终同时使用符号、文字和颜色，不仅依赖颜色。

六个一级页面保持固定编号：

1. `01 采集工作台`
2. `02 传输与重建`
3. `03 结果查看`
4. `04 历史任务`
5. `05 设置`
6. `06 日志和环境诊断`

## 令牌架构

令牌定义在
[`src/camera_system_app/ui/design_tokens.py`](../../src/camera_system_app/ui/design_tokens.py)，
由 [`theme.py`](../../src/camera_system_app/ui/theme.py) 转换为 QSS。

| 层级 | 用途 | 示例 |
|---|---|---|
| Primitive | 不携带业务含义的基础值 | navy、neutral、blue、teal、4–32 px 间距 |
| Semantic | 浅色/深色表面的语义角色 | background、text、interactive、warning、danger |
| Component | 控件的稳定规格 | 字号、圆角、按钮高度、焦点边框 |

不要在页面类里复制颜色或间距。新增视觉角色时先补充令牌，再让 QSS 和控件
消费该角色。只有富文本本身无法继承 QSS 语义色时，才可直接读取语义令牌。

## 共用组件

共用控件位于
[`src/camera_system_app/ui/widgets`](../../src/camera_system_app/ui/widgets)：

- `PageHeader`：流程眉题、页面标题和说明；
- `StatusBanner`：info、success、warning、danger 四种状态；
- `EmptyState`：符号、标题、说明和可选操作；
- `MetricCard`：诊断数量和语义状态；
- `WorkflowStage`：阶段编号、状态、进度和可访问名称；
- `BasePage.add_card()`：带标题和说明的内容卡片。

控件改变动态属性后必须重新应用样式。表格继续使用模型/视图实现，避免在
JetPack Qt 5.12 上引入不稳定的逐项控件。

## 响应式与可访问性

- 正文 16 px，页面标题 28 px；
- 普通文本对比度至少 4.5:1；
- 按钮最小高度 40 px，主操作 44 px；
- 焦点边框 2 px，键盘顺序与视觉顺序一致；
- 中文说明允许换行，不给用户可见字符串设置固定宽度；
- 内容超过 `1024×680` 可用高度时使用滚动区，不压缩文本或操作；
- 表格和日志可以滚动，关键操作不得被固定高度裁切。

## 截图基线

当前 1600×900 无硬件截图：

- [采集工作台](../images/ui/capture.png)
- [传输与重建](../images/ui/transfer.png)
- [结果查看](../images/ui/result.png)
- [历史任务](../images/ui/history.png)
- [设置](../images/ui/settings.png)
- [日志和环境诊断](../images/ui/diagnostics.png)

截图使用 Qt `offscreen` 平台生成，只代表无摄像头、无在线重建服务时的界面
基线。真实相机画面和 OpenGL Gaussian 渲染必须在 Jetson 图形会话中验收。

## 验证

```bash
.venv-jetson/bin/python -m pytest -q tests/app_shell/test_ui_design_system.py
.venv-jetson/bin/python -m pytest -q tests/app_shell
QT_QPA_PLATFORM=offscreen \
  .venv-jetson/bin/python -m camera_system_app --smoke-test-ms 100
```

设计令牌测试会独立计算关键文本对比度，并验证导航映射、状态色、空状态、
工作流阶段、最小窗口布局和滚动行为。修改页面后还应检查六张截图，并在
Jetson 桌面会话验证摄像头预览、键盘焦点和 OpenGL 查看器。
