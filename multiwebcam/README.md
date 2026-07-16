# multiwebcam｜边端多摄像头采集与 3DGS 数据制作

`multiwebcam` 是一套运行在 Linux/Jetson 上的多 USB 摄像头采集工作站。它把摄像头管理、实时预览、同步时间戳、视频录制、多视角拍照、图像质量检查和目标角度引导整合到一个 Qt 桌面应用中，为相机标定、COLMAP 和 3D Gaussian Splatting（3DGS）重建准备结构化数据。

项目解决的核心问题是：使用普通、没有硬件同步能力的 USB 摄像头，稳定地完成多路采集，并为每一帧保留可用于后处理对齐的时间信息。它不是 3DGS 训练器，也不直接完成最终三维重建；它负责重建之前的数据采集和质量控制。

> [!IMPORTANT]
> 项目仍处于从旧版 OpenCV 实现向 PyAV、Qt、GStreamer 和 Jetson 加速路径重构的阶段。当前维护代码位于 `src/multiwebcam/`，`multiwebcam_legacy/` 仅保留作历史参考。

> [!NOTE]
> 本 README 是用户使用入口。会随设备、驱动和验证结果变化的内容，以 [`docs/status/`](docs/status/current_errors_summary.md) 下的状态记录为准；长期有效的行为约束放在 [`specs/`](specs/capture_guidance_algorithm.md) 下，研究和历史材料不作为操作步骤。

## 已经实现了什么

目前已经打通从“连接摄像头”到“获得可用于标定或重建的数据”的完整流程：

1. 自动发现 V4L2 摄像头，并按 USB `bus_info` 保存稳定身份。
2. 在 Qt 界面中同时预览最多 4 路摄像头，查看帧率、质量和时间对齐状态。
3. 将每路视频分别录制为 MP4，同时生成统一的逐帧 `timestamps.csv`。
4. 区分普通录制、单摄像头内参标定和多摄像头外参标定输出。
5. 一次拍摄多路静态图像，并保存相机信息、时间戳和质量指标。
6. 检查清晰度、曝光、特征数量、主体位置和跨相机时间差，拦截明显不可用的采集。
7. 通过目标检测引导操作员完成 0°、45°、90° 到 315° 的一圈八角度拍摄。
8. 在 Jetson Orin Nano 上使用 GStreamer、硬件 H.264 编码和 TensorRT 推理；主界面与推理环境不兼容时，支持独立推理子进程。

当前实机已经验证 1 路 USB 3.0 与 3 路 USB 2.0 摄像头同时运行，以及预览、TensorRT 推理、拍照和录制链路。

## 典型使用流程

```text
连接 USB 摄像头
  → 启动应用并生成/读取 multiwebcam.toml
  → 在网格页确认所有画面、帧率和质量状态
  → 在聚焦页调整单路分辨率、帧率、曝光等参数
  → 录制内参/外参视频，或按八角度引导拍摄多视角图片
  → 使用输出的 MP4、图片和时间戳进入标定、COLMAP 或 3DGS 流程
```

## 核心能力

- 通过 V4L2 发现 USB 摄像头，并使用 `bus_info` 将物理设备稳定绑定到 `source_id`。
- 使用 Qt 图形界面提供多路网格预览、单摄像头聚焦、状态监控、拍照和录制控制。
- 默认维护最多 4 路活跃摄像头，支持设备热插拔以及按项目 profile 重新绑定。
- 每路摄像头由独立 producer 线程采集，并分发到预览、录制和时间对齐队列。
- 记录帧率、帧间隔、丢帧和跨摄像头时间差；录制时生成逐相机 MP4 和统一的 `timestamps.csv`。
- 支持普通命名录制、外参标定录制和单摄像头内参标定录制。
- 保存多摄像头快照及相机、质量和时间戳元数据。
- 基于清晰度、曝光、ORB 特征、主体区域和跨摄像头时间差评估采集质量。
- 提供 `heuristic`、Ultralytics TensorRT 和独立子进程三类目标识别后端。
- 实现 0° 到 315° 的八角度拍摄引导、目标检测门控、重复捕获拦截和下一角度建议。
- 支持 Jetson Orin Nano 的 GStreamer 采集、`nvv4l2h264enc` 硬件编码和 TensorRT 推理路径。

## 工作方式

```text
USB 摄像头
    │
    ├── V4L2 / OpenCV / GStreamer 采集
    │        │
    │        ├── Qt 实时预览
    │        ├── PyAV / GStreamer 录制 ──> MP4 + timestamps.csv
    │        ├── 对齐与质量评估
    │        └── 异步目标识别 ──> 拍摄引导
    │
    └── multiwebcam.toml 保存设备身份与运行配置
```

本项目不是硬件同步系统。普通 USB 摄像头没有 genlock，各路画面独立采集，系统依靠单调时钟时间戳记录时序关系，供后续标定或重建流程对齐。

## 环境要求

- Linux，支持 V4L2
- Python `>=3.10,<3.13`
- USB 摄像头
- `v4l2-utils`
- 推荐使用 [uv](https://docs.astral.sh/uv/) 管理 Python 环境

Ubuntu/Jetson 可先安装基础系统工具：

```bash
sudo apt install v4l-utils
```

Jetson 的 GStreamer、CUDA、TensorRT 和硬件编码要求见 [Jetson Orin Nano Pipeline](docs/architecture/jetson_orin_pipeline.md)。

## 快速开始

### 1. 获取代码和系统依赖

```bash
sudo apt update
sudo apt install v4l-utils

git clone https://github.com/thembisilecynthia39-sys/camera-system.git
cd camera-system
```

### 2. 安装 Python 环境

普通 Linux 桌面环境：

```bash
uv sync --extra desktop
```

Jetson 项目目前使用设备上的系统 Python、JetPack 库和本地兼容环境，准备好项目环境后通过 `run_jetson` 启动。Jetson 专用依赖和验证方法见 [Jetson Orin Nano Pipeline](docs/architecture/jetson_orin_pipeline.md)。

### 3. 连接并检查摄像头

```bash
v4l2-ctl --list-devices
```

建议先连接一台摄像头完成首次启动，再逐步增加设备。多路 720p/30 FPS 摄像头应分散到不同 USB 控制器，否则可能因 USB 2.0 带宽不足而无帧或掉帧。

### 4. 启动应用

在仓库内开发运行：

```bash
uv run mwc
```

在当前 Jetson 项目环境运行：

```bash
./run_jetson
```

应用把启动时的当前目录作为采集项目目录，并在这里读取或创建 `multiwebcam.toml`。如果希望把采集数据放到单独目录，可在安装包后切换目录启动：

```bash
mkdir -p ~/capture-projects/object-001
cd ~/capture-projects/object-001
multiwebcam
```

首次启动时，程序发现摄像头并创建 profile；后续启动从 `multiwebcam.toml` 恢复设备标签、分辨率、帧率、像素格式、采集后端和 V4L2 控制项。

命令行入口 `mwc`、`multiwebcam` 和 `python -m multiwebcam` 等价。开发依赖由 `pyproject.toml` 的 `dev` dependency group 管理，包括 pytest、Ruff 和 basedpyright。

## 基本操作

### 网格预览与录制

- 网格页面显示所有活跃摄像头、实时帧率、质量和对齐状态。
- 普通录制保存到 `recordings/<name>/`，名称默认自动递增，也可以手动修改。
- 勾选“外参标定”后，录制保存到 `calibration/extrinsic/`。
- 已存在且非空的目标目录会在覆盖前要求确认。
- “打开目录”可直接打开当前采集项目。

### 单摄像头聚焦

- 进入 focus 页面查看单路大画面并调整支持的分辨率、帧率和 V4L2 控制项。
- focus 页面中的标定录制保存到 `calibration/intrinsic/`。
- 录制期间会锁定可能破坏采集稳定性的配置控件。

### 快照和角度引导

拍摄引导按以下八个角度推进：

```text
0°, 45°, 90°, 135°, 180°, 225°, 270°, 315°
```

操作员按照界面提示旋转目标，等待目标识别和质量检查达到可采集状态，再点击拍照。YOLO 未识别普通盒子等对象时，系统可以回退到轻量中心轮廓检测。完成 315° 后，界面以 360° 表示一轮闭合完成。

详细行为和后续版本计划见 [YOLO11 角度拍摄引导](docs/guides/angle_guidance_versions.md)。

## 配置

配置文件为采集项目根目录下的 `multiwebcam.toml`：

```toml
[[sources]]
source_id = 1
label = "front"
bus_info = "usb-..."
ignore = false
resolution = [1280, 720]
pixel_format = "mjpeg"
capture_fps = 30
capture_backend = "opencv_v4l2"

[recording]
backend = "pyav"
codec = "h264"
fps = 30

[inference]
backend = "subprocess"
engine_path = "/path/to/multiwebcam/models/yolo11n.engine"
device = "cuda:0"
confidence_threshold = 0.25
interval_ms = 100
service_python = "/path/to/python"
service_backend = "ultralytics_tensorrt"
service_script = "/path/to/multiwebcam/scripts/services/inference_service.py"
input_size = [640, 640]
```

常用后端：

| 用途 | 可选值 | 说明 |
| --- | --- | --- |
| `capture_backend` | `opencv_v4l2`、`gstreamer` | 每个摄像头可独立配置 |
| `recording.backend` | `pyav`、`gstreamer` | Jetson 硬件编码使用 GStreamer |
| `inference.backend` | `heuristic`、`ultralytics_tensorrt`、`subprocess` | 子进程模式用于隔离 Jetson Python/TensorRT 环境 |

当前本机配置使用 `opencv_v4l2` 采集、PyAV 录制和独立子进程 TensorRT 推理。不要直接复制其中的绝对路径到其他机器。

## 输出结构

```text
capture-project/
├── multiwebcam.toml
├── recordings/
│   └── recording_001/
│       ├── cam_1.mp4
│       ├── cam_2.mp4
│       └── timestamps.csv
├── calibration/
│   ├── intrinsic/            # 单摄像头内参录制
│   └── extrinsic/            # 多摄像头外参录制
└── captures/
    └── capture_001/
        ├── images/
        ├── metadata.csv
        ├── quality.csv
        └── cameras.json
```

仓库中的 PLY 重建结果统一放在 `artifacts/reconstructions/`，YOLO 模型统一放在 `models/`。

## Jetson Orin Nano

项目支持以下 Jetson 加速路径：

- USB 摄像头通过 `cv2.CAP_GSTREAMER` 采集。
- H.264 通过 `nvv4l2h264enc` 硬件编码。
- TensorRT `.engine` 通过 Ultralytics 执行，并在后台只处理各摄像头最新帧。
- 主 Qt 环境与 Jetson Python 3.8 推理环境不兼容时，可通过 stdio 启动独立推理服务。
- 每路摄像头可以使用不同分辨率，推理输入尺寸由 `inference.input_size` 单独控制。

在目标设备上验证软件栈：

```bash
python scripts/jetson/validate_jetson_stack.py --project /path/to/capture-project
python scripts/jetson/jetson_smoke_pipeline.py \
    --project /path/to/capture-project \
    --run-inference
```

当前实机已验证 1 路 USB 3.0 加 3 路 USB 2.0 同时启动、子进程 TensorRT 推理和端到端录制。具体 USB 拓扑、帧率和剩余风险见[当前错误总结](docs/status/current_errors_summary.md)。

## 诊断

列出 V4L2 设备：

```bash
v4l2-ctl --list-devices
```

生成 USB 摄像头诊断报告：

```bash
python scripts/diagnostics/diagnose_usb_cameras.py \
    --max-devices 4 \
    --duration 8 \
    --output artifacts/logs/camera-diagnostics.txt
```

验证当前 `multiwebcam.toml` 中的摄像头配置：

```bash
python scripts/diagnostics/probe_configured_pipeline.py \
    --project /path/to/capture-project \
    --duration 5
```

摄像头打不开时还应检查：

```bash
# 当前用户是否拥有视频设备权限
groups
sudo usermod -aG video "$USER"

# 曝光控制
v4l2-ctl -d /dev/video0 --get-ctrl=auto_exposure
v4l2-ctl -d /dev/video0 --set-ctrl=auto_exposure=3
```

修改用户组后需要注销并重新登录。USB 带宽不足通常表现为某路无帧、帧率减半或 V4L2 报 `No space left on device`，此时应调整 USB 拓扑、分辨率或活跃摄像头组合。

## 开发与验证

```bash
uv run pytest -q
uv run ruff check .
```

硬件相关测试必须在连接真实摄像头的目标设备上执行，普通单元测试不会验证 USB 带宽、摄像头固件、GStreamer 插件或 TensorRT engine 的实际可用性。

## 项目目录

```text
src/multiwebcam/          当前维护的应用源码
tests/                    按子系统组织的自动化测试
scripts/                  初始化、诊断、Jetson、服务和实验脚本
docs/                     架构、指南、研究和状态文档
specs/                    功能规格和行为约束
config/udev/              Linux 设备规则
models/                   YOLO 权重、ONNX 和 TensorRT engine
artifacts/                日志和重建结果
captures/                 本地快照输出
recordings/               本地视频录制输出
archive/backups/          本地历史备份
multiwebcam_legacy/       旧版实现
vendor/                   不纳入版本控制的第三方工具
```

完整的文件放置规则见[项目目录结构](docs/project_structure.md)，脚本分类见 [scripts/README.md](scripts/README.md)。

## 文档

- [文档索引](docs/README.md)
- [项目功能总结](docs/status/project_features_summary.md)
- [项目目录结构](docs/project_structure.md)
- [Jetson Orin Nano Pipeline](docs/architecture/jetson_orin_pipeline.md)
- [YOLO11 角度拍摄引导](docs/guides/angle_guidance_versions.md)
- [采集引导算法规格](specs/capture_guidance_algorithm.md)
- [录制目标目录规格](specs/recording_destinations.md)
- [UI 设计研究](docs/research/ui_design_research.md)
- [当前错误与实机验证](docs/status/current_errors_summary.md)
- [Qt 开发技术说明](docs/guides/qt_developer_interview_guide.md)

## 摄像头兼容性

结构简单、能稳定输出 MJPEG/YUYV 的 USB 摄像头通常更可靠。带复杂自动对焦、动态曝光或 HDR 固件的型号，在采集中修改 V4L2 控制项时可能冻结，甚至需要重新插拔。

- 已验证较稳定：eMeet C960
- 已知存在固件稳定性风险：Razer Kiyo Pro、部分 Logitech C920/C930e

## 相关项目

- [Caliscope](https://github.com/mprib/caliscope)：多摄像头标定与三维重建
- [COLMAP](https://github.com/colmap/colmap)：Structure-from-Motion 与 Multi-View Stereo

## 许可证

BSD-2-Clause，详见 [LICENSE](LICENSE)。
