# Camera System 0.1.0 Jetson 发布说明

发布日期：2026-07-28

## 发布目标

本版本面向 Jetson Orin Nano 8GB、Ubuntu 20.04、ARM64、JetPack 5.1.1。
采用“应用目录 + 系统原生运行库”的发布方式，统一提供：

- 八角度采集工作台；
- Jetson 到 WSL 的后台上传、重建状态跟踪与结果下载；
- 内嵌 q3dviewer 的 PLY/Gaussian 结果查看；
- 历史任务、设置、日志和环境诊断；
- 命令行、桌面图标两种启动入口。

## 发布包

在源码目录运行：

```bash
./scripts/jetson/release.sh
```

输出：

```text
dist/camera-system-0.1.0-jetson-arm64/
dist/camera-system-0.1.0-jetson-arm64.tar.gz
dist/camera-system-0.1.0-jetson-arm64.tar.gz.sha256
```

压缩包不包含虚拟环境、Git 数据、测试缓存、采集数据、重建结果和运行日志。
部署后运行 `scripts/jetson/install.sh` 创建本机环境和桌面入口。

## 运行时边界

以下组件来自 JetPack/Ubuntu，发布包不会覆盖：

- PyQt5 5.14.1 / Qt 5.12.8；
- Jetson PySide6 API 兼容层；
- 启用 GStreamer 的系统 OpenCV；
- GStreamer 插件和 V4L2；
- NVIDIA EGL、GLES、OpenGL、CUDA、TensorRT；
- Jetson 平台的 torch/ultralytics（如启用识别）。

`requirements/jetson.txt` 只锁定应用管理的纯 Python 或已验证 wheel 依赖，明确
不安装 pip 版 OpenCV、PySide6 或 PyQt5。

## 为什么不使用 PyInstaller 单文件或 AppImage

本版本不强行制作单文件包。JetPack 5.1.1 的 Qt 平台插件、系统 OpenCV
GStreamer 后端、NVIDIA EGL/OpenGL 驱动、CUDA/TensorRT 和摄像头插件都与
目标系统 ABI 绑定。PyInstaller 单文件会在临时目录展开并容易混入另一套 Qt、
OpenCV 或 GL 库；AppImage 也难以同时隔离用户态库并安全复用宿主 NVIDIA
驱动。两种方式在 ARM64 上还会显著增加包体和现场排障难度。

应用目录发布保留了可审查源码、固定入口、依赖清单和 SHA-256，同时复用
JetPack 原生多媒体与图形栈，是当前硬件上更稳定的方案。

## 已知边界

- 安装脚本需要联网获取 apt/pip 依赖；离线部署需提前制作 apt 缓存和 wheelhouse。
- WSL 服务地址因网络环境不同，安装后必须在设置或 `settings.yaml` 中填写。
- OpenGL 真机测试依赖活动 X11 显示和 NVIDIA 驱动，SSH 无显示环境只能做
  `--diagnose` 与 Qt offscreen 启动测试。
- `packaging/linux/camera-system.desktop` 是模板；桌面规范无法相对自身解析
  应用路径，因此 `scripts/jetson/install.sh` 会写入部署目录的绝对路径。该路径来自运行时探测，不包含
  `/home/jetson` 硬编码。

## 版本与诊断

```bash
./scripts/jetson/run.sh --version
./scripts/jetson/diagnose.sh
./scripts/jetson/diagnose.sh --json
```
