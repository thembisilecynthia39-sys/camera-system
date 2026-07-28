# Python 依赖说明

本目录以 Jetson Orin Nano、JetPack 5.1.1 和 Python 3.8 为生产基线。生产
环境使用带 `--system-site-packages` 的 `.venv-jetson`，以复用 NVIDIA 和
Ubuntu 已验证的原生组件。

## 文件用途

| 文件 | 用途 |
|---|---|
| [`jetson.txt`](jetson.txt) | 生产运行时的精确版本锁定，也是安装脚本使用的依赖源 |
| [`../requirements.txt`](../requirements.txt) | 从仓库根目录执行 pip 时的常规入口，引用 `jetson.txt` |
| [`dev.txt`](dev.txt) | 生产依赖加 Python 3.8 兼容的测试工具 |

## 生产环境

推荐由安装脚本创建环境并安装依赖：

```bash
./scripts/jetson/install.sh
```

如系统依赖已经准备好，也可以只安装 Python 依赖：

```bash
/usr/bin/python3 -m venv --system-site-packages .venv-jetson
.venv-jetson/bin/python -m pip install -r requirements.txt
.venv-jetson/bin/python -m pip install --no-deps -e .
```

安装后运行项目诊断：

```bash
./scripts/jetson/diagnose.sh
```

## 开发和测试

```bash
.venv-jetson/bin/python -m pip install -r requirements/dev.txt
.venv-jetson/bin/python -m pytest
```

`requirements/dev.txt` 只增加仓库检查所需的 pytest。三个子项目的独立
开发工具仍以各自的 `pyproject.toml` 为准。

## 必须由系统提供的组件

以下组件不能通过本目录覆盖：

- PyQt5、PySide6 API 兼容层和 Qt 平台插件；
- OpenCV/GStreamer；
- CUDA、TensorRT 和 Jetson 对应的 Torch；
- EGL、OpenGL 和摄像头系统库。

特别不要安装 `opencv-python`、`opencv-contrib-python` 或 PyPI PySide6。
它们可能遮蔽 JetPack 的原生库，导致 GStreamer 消失、Qt 插件冲突或
OpenGL ABI 错误。

## 可选模型工具

运行应用不需要 ONNX。只有转换或编辑模型时才需要 ONNX 和 ONNX
GraphSurgeon；应在与目标 TensorRT 版本匹配的独立环境或容器中完成转换，
再把生成的 `.engine` 文件复制到 Jetson。

`qfluentwidgets` 也不是核心依赖。当前 UI 在它与 JetPack Qt 版本不兼容时
会自动使用项目内置控件和主题。

更多背景和已知的 `pip check` 非核心告警见
[Jetson 依赖策略](../docs/development/JETSON_DEPENDENCIES.md)。
