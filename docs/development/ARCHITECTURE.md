# 架构与开发约定

## 目标

统一桌面应用负责串起“采集 → 上传/重建 → 下载 → 查看”流程。`multiwebcam`、`Tx_Rx` 和 `3DGSviewer` 继续作为可独立测试的能力包，顶层应用只通过明确的端口和适配器调用它们。

## 依赖方向

```text
camera_system/domain + interfaces
              ↑
camera_system/adapters
              ↑
camera_system_app/domain
              ↑
camera_system_app/application
              ↑
camera_system_app/infrastructure
              ↑
camera_system_app/ui + workers
              ↑
camera_system_app/bootstrap.py
```

箭头表示外层可以依赖内层。例外是 `bootstrap.py`：它是组合根，可以看见所有层并负责创建具体对象。

关键约束：

- `camera_system.domain` 和 `camera_system.interfaces` 不依赖 Qt、应用壳或三个具体子项目。
- `camera_system_app.domain` 只表达状态、事件和错误，不访问文件、网络或 QWidget。
- `application` 编排用例；耗时 I/O 由 `workers` 或具体适配器执行。
- `ui` 只负责展示和用户输入，不能直接实现传输、重建或文件持久化。
- 子项目间不要直接互相导入；跨项目流程由顶层应用协调。

`tests/test_architecture.py` 对最稳定的内层边界做静态检查，防止后续改动反向穿透。

## 文件放置规则

| 变更内容 | 放置位置 |
|---|---|
| 跨实现共享的数据模型或服务契约 | `src/camera_system/domain/`、`src/camera_system/interfaces.py` |
| 对 Tx_Rx、multiwebcam、q3dviewer 的协议适配 | `src/camera_system/adapters/` |
| 桌面应用状态、错误和事件 | `src/camera_system_app/domain/` |
| 完整业务流程编排 | `src/camera_system_app/application/` |
| 路径、配置持久化、日志、仓储 | `src/camera_system_app/infrastructure/` |
| Qt 后台任务 | `src/camera_system_app/workers/` |
| 页面、控件、信号绑定 | `src/camera_system_app/ui/` |
| 摄像头底层行为 | `multiwebcam/` |
| 上传与 HTTP 协议 | `Tx_Rx/` |
| 3D 渲染行为 | `3DGSviewer/q3dviewer/` |

新增代码前先搜索已有端口或工具，避免在应用层复制子项目能力。

## 配置与运行时数据

- 可提交配置只放在 `config/examples/`，不写入真实设备地址、USB bus 信息或密钥。
- 用户设置默认位于 `$XDG_CONFIG_HOME/camera-system/settings.yaml`。
- 状态、日志和缓存遵循 XDG 目录；工作区中的 `runtime/`、`captures/`、`result/` 和顶层 `multiwebcam.toml` 是本机数据，已由 Git 忽略。
- 发布脚本只打包源码、模板、文档和静态资源。

## 验证层次

```bash
# 快速：纯 Python 契约与架构边界
.venv-jetson/bin/python -m pytest tests/protocol tests/test_architecture.py

# 完整：包含 Qt shim、工作流和应用壳
.venv-jetson/bin/python -m pytest

# Jetson 环境与可选硬件
./scripts/jetson/diagnose.sh
```

完整工作流测试会建立本机回环 HTTP 服务；受限容器中可能需要允许本地 socket。真实摄像头和 OpenGL 验证应在 Jetson 图形会话中执行。

## 提交前检查

1. `git status --short` 中没有运行时图片、模型、日志或设备专用配置。
2. 新业务逻辑没有落入 QWidget/Page 类。
3. 后台线程通过信号把结果送回 UI，不直接操作控件。
4. 修改过的层有对应测试，且快速测试通过。
5. 用户行为、配置或发布方式变化时同步更新 `docs/` 和配置模板。
