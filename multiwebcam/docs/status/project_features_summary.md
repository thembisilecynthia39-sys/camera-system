# 项目功能总结

> [!NOTE]
> 本文是功能和本地配置快照，不替代用户操作指南。动态硬件问题和未验证风险以[当前错误总结](current_errors_summary.md)为准。

状态内容记录时间：2026-06-26 10:26（Asia/Shanghai）

状态内容最后更新：2026-06-26 10:58（Asia/Shanghai）

文档分类说明更新：2026-07-16（本次未重新验证功能）

## 项目定位

`multiwebcam` 是一个 Linux USB 多摄像头采集、预览、录制和拍照工具，目标是为 Caliscope 等三维重建/标定流程提供多路视频、时间戳和静态图像数据。项目当前处于从 legacy OpenCV 实现向 PyAV/Qt/GStreamer 方向重写的状态。

## 已实现功能

- 多摄像头发现与配置：通过 V4L2 枚举摄像头，按 `bus_info` 绑定稳定的 `source_id`，配置保存在 `multiwebcam.toml`。
- 摄像头 profile 管理：支持 label、ignore、分辨率、像素格式、帧率、采集后端、GStreamer pipeline 和 V4L2 控制项的持久化。
- Qt 图形界面：提供网格预览、单摄像头 focus 视图、摄像头状态展示、录制控制和拍照入口。
- 活跃摄像头池：默认最多 4 路活跃源，支持热插拔/断开后按项目 profile 重新平衡。
- 多线程采集管线：每路摄像头由 producer 线程采集，并分发到 display、recording、alignment 三类队列。
- 帧统计与对齐监控：记录每路帧数、fps、丢帧/间隔统计，并用轻量元数据队列计算跨摄像头时间对齐情况。
- 视频录制：支持按摄像头写入 `cam_N.mp4`，并输出统一 `timestamps.csv`，当前配置默认 `[recording].backend = "pyav"`。
- 录制目标选择：网格界面支持普通命名录制 `recordings/<name>/`，也支持外参标定录制 `calibration/extrinsic/`。
- 快照采集：支持保存一组多摄像头静态图到 `captures/capture_NNN/images/`，同时生成 `metadata.csv`、`quality.csv` 和 `cameras.json`。
- 图像质量评估：基于清晰度、亮度、过曝/欠曝、ORB 特征数、主体区域和跨摄像头时间差计算质量分数。
- 拍摄引导：实现 8 个角度 bin 的捕获进度、下一角度建议、重复/低质量拦截和重拍建议。
- 目标识别抽象：提供 heuristic、Ultralytics TensorRT、subprocess 三类识别后端接口。
- 异步识别：后台识别线程只保留每路最新帧，避免推理阻塞采集。
- 子进程推理服务：主 Qt/Python 环境可通过 stdio 调用独立 Python/conda 环境中的 TensorRT 推理服务。
- Jetson Orin Nano 路径：支持 GStreamer 采集 pipeline、`nvv4l2h264enc` 硬件编码 pipeline、TensorRT `.engine` 配置与 Jetson 验证脚本。
- 诊断与验证脚本：包含 USB 摄像头诊断、OpenCV/GStreamer/Jetson stack 检查、四摄像头采集探测、PyAV 探索脚本和 widget 可视化脚本。
- 自动化验证：当前测试覆盖 profiles、sources、pipeline memory tuning、recording naming、UI import/active pool、snapshot、quality、recognition 和 subprocess detector；Ruff 静态检查聚焦当前维护代码。

## 当前本地配置概况

- `multiwebcam.toml` 中有 4 个摄像头 profile：`source_id` 为 1、2、4、5。
- 当前活跃摄像头为 1、2、4、5；`source_id = 1` 是固定的 USB3.0 摄像头。
- 当前分辨率组合为 1 路 USB2.0 `640x480`、2 路 USB2.0 `1280x720`，以及 1 路 USB3.0 `1280x720`；像素格式为 MJPEG，采集后端为 `opencv_v4l2`。
- 录制后端为 `pyav`，编码设置保留了 Jetson 硬件编码字段。
- 推理后端为 `subprocess`，engine 指向 `yolo11n.engine`，服务环境指向 `multiwebcam-jetson-py38`。

## 输出数据

- 已存在一次静态采集：`captures/capture_001/`，包含 3 张图片、相机信息、元数据和质量数据。
- 已存在三次录制：`recordings/recording_001/`、`recording_002/`、`recording_003/`，均包含 MP4 和 `timestamps.csv`。
- `models/` 目录有 `yolo11n.pt`、`yolo11n.onnx`、`yolo11n.engine`，其中当前配置实际使用 `.engine`。

## 开发验证入口

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check .
```

当前结果：

- 测试：`84 passed`
- Ruff：`All checks passed`

## Jetson 实机状态

- Jetson release：`R35.3.1`。
- 当前项目已验证固定一路 USB3.0 加三路 USB2.0 能同时采集。
- 端到端 smoke test 通过，输出位于 `/tmp/mwc_jetson_smoke_*`。
- 当前可用 USB2.0 分配为 `/dev/video2=640x480`、`/dev/video4=1280x720`、`/dev/video6=1280x720`；把低分辨率放到 `/dev/video6` 会触发 USB 带宽错误。
- Qt 首次连接使用后台 camera-load worker，不阻塞窗口首次显示。
- 子进程 TensorRT 推理可用，CUDA 可见，engine load OK。
- 当前主 `.venv` OpenCV 没有 GStreamer，因此现配置仍使用 `opencv_v4l2` 采集和 `pyav` 录制。
- 质量评估已按廉价 USB2.0 摄像头调宽阈值，重点保证目标检测、基本清晰度和可用采集，而不是按高端相机标准严格拦截。
