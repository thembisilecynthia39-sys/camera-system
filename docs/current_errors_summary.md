# 当前错误总结

生成时间：2026-06-26 10:26（Asia/Shanghai）

最后更新：2026-06-26 10:58（Asia/Shanghai）

## 测试结果

使用本地虚拟环境运行：

```bash
./.venv/bin/python -m pytest -q
```

结果：

```text
84 passed in 1.80s
```

结论：当前自动化测试全部通过，没有发现 pytest 层面的功能回归。

## 命令环境问题

直接运行：

```bash
pytest -q
```

失败：

```text
/bin/bash: pytest: command not found
```

原因：`pytest` 不在当前 shell 的 PATH 中，但项目 `.venv/bin/pytest` 存在。建议使用 `./.venv/bin/python -m pytest -q` 或先激活 `.venv`。

## Ruff 静态检查问题

运行：

```bash
./.venv/bin/python -m ruff check .
```

当前结果：

```text
All checks passed!
```

已处理：

- 移除了 `src/multiwebcam/pipeline/session.py` 中未使用的 `FrameMetadata` import。
- 移除了 `scripts/inference_service.py` 中未使用的 `Optional` import。
- 修复了 `scripts/pyav_exploration/02_open_single_device.py` 中 `np.ndarray` 类型引用但未导入 `numpy` 的问题。
- 在 `pyproject.toml` 的 Ruff exclude 中排除了 `multiwebcam_legacy`、`scripts/pyav_exploration` 和 `scripts/widget_visualization`。

排除策略说明：

- `multiwebcam_legacy/` 是历史实现，当前重写路径集中在 `src/multiwebcam/`。
- `scripts/pyav_exploration/` 是硬件探索脚本，保留实验记录比强制生产级 lint 更有价值。
- `scripts/widget_visualization/` 为手动 GUI 截图/验证脚本，存在有意的本地路径插入模式，强制 `E402` 会制造噪声。

历史结果：曾失败并发现 71 个 lint 问题，其中 32 个可用 `--fix` 自动修复。历史问题主要类型如下，保留用于说明为什么调整 Ruff 作用域。

主要类型：

- `E501` 行过长。
- `F401` 未使用 import。
- `F841` 局部变量赋值后未使用。
- `F541` 没有占位符的 f-string。
- `E402` module import 不在文件顶部。
- `F821` 未定义名称。

主要集中位置：

- `multiwebcam_legacy/`：legacy 代码存在行过长问题。
- `scripts/pyav_exploration/`：探索脚本中有未使用 import/变量、f-string 和一个类型注解中的 `np` 未定义问题。
- `scripts/widget_visualization/`：可视化脚本因为动态插入路径，触发大量 `E402`，同时有未使用变量/import。
- `scripts/inference_service.py`：`typing.Optional` 未使用。
- `src/multiwebcam/pipeline/session.py`：`FrameMetadata` import 未使用。

## 已处理的关键 lint 明细

- `scripts/pyav_exploration/02_open_single_device.py:25`：`F821 Undefined name np`，已通过导入 `numpy as np` 并使用真实类型注解解决。
- `scripts/inference_service.py:12`：`F401 typing.Optional imported but unused`，已移除。
- `src/multiwebcam/pipeline/session.py:12`：`F401 FrameMetadata imported but unused`，已移除。
- `multiwebcam_legacy/cameras/synchronizer.py`、`multiwebcam_legacy/recording/*.py`：多处 `E501` 行过长。
- `scripts/widget_visualization/*.py`：多处 `E402`，原因是脚本先修改 `sys.path`，再导入 Qt/项目模块。

## Jetson 实机验证结果

在 Jetson 实机上用非沙箱设备访问运行：

```bash
./.venv/bin/python scripts/validate_jetson_stack.py --project /home/lab/3DGS/Multcamera/multiwebcam
./.venv/bin/python scripts/diagnose_usb_cameras.py --max-devices 8 --duration 3
./.venv/bin/python scripts/probe_configured_pipeline.py --project /home/lab/3DGS/Multcamera/multiwebcam --duration 5
./.venv/bin/python scripts/jetson_smoke_pipeline.py --project /home/lab/3DGS/Multcamera/multiwebcam --warmup-seconds 5 --record-seconds 3 --run-inference
```

结果摘要：

- Jetson release：OK，`R35.3.1`。
- GStreamer NVIDIA 插件：OK，`nvv4l2decoder`、`nvv4l2h264enc`、`nvvidconv` 可用。
- 子进程 TensorRT 推理环境：OK，`torch=2.0.0+nv23.05`，`cuda_available=True`，`device_count=1`，engine load OK。
- 摄像头发现：OK，发现 4 个 UVC 采集节点：`/dev/video0`、`/dev/video2`、`/dev/video4`、`/dev/video6`。
- 当前项目启用的三路配置：OK，`/dev/video2`、`/dev/video0`、`/dev/video6` 均能出帧。
- 端到端 smoke：OK，采集、子进程推理、录制和 `timestamps.csv` 输出均通过。

端到端 smoke 的实测帧率：

```text
/dev/video2: fps=30.2
/dev/video0: fps=29.9
/dev/video6: fps=15.2
cam_2: frames=90
cam_4: frames=90
cam_5: frames=45
```

A/B 摄像头替换测试：

- 将 `source_id=1`（`usb-3610000.xhci-2.4.2`，`/dev/video4`，720p）临时启用。
- 将 `source_id=5`（`usb-3610000.xhci-2.4.3`，`/dev/video6`，720p）临时禁用。
- 结果：两路 720p 加一路 640p 全部接近 30fps。

```text
/dev/video4: fps=29.8, cam_1 frames=89
/dev/video2: fps=30.1, cam_2 frames=90
/dev/video0: fps=29.9, cam_4 frames=90
```

结论：当前半速问题集中在 `/dev/video6` 对应的摄像头或 `usb-3610000.xhci-2.4.3` 支路，不是“两路 720p + 一路 640p”这个组合本身不支持 30fps。

关键剩余问题：

- `/dev/video6` 在当前 USB 拓扑和分辨率组合下只能约 15fps，录制 3 秒写入约 44-45 帧。
- 四路同时 `640x480@30 MJPG` 探测不稳定，出现过某一路无帧或 `OSError(28, 'No space left on device')`，属于 USB 带宽/调度瓶颈信号。
- 当前 `.venv` 导入的 OpenCV wheel 没有 GStreamer：`cv2 4.13.0`，`GStreamer: NO`。
- `validate_jetson_stack.py` 中普通 `opencv` 检查会被外部 `PYTHONPATH` 污染到 conda `pose` 环境的 `cv2 4.11.0`，该版本同样没有 GStreamer/CUDA。
- 系统 OpenCV `/usr/bin/python3` 的 `cv2 4.2.0` 有 GStreamer，但 CUDA 为 false。

## 当前未处理风险

- Ruff 已聚焦当前维护代码；legacy、探索脚本和 widget 可视化脚本不再阻塞静态检查。
- 硬件 smoke 已通过，但 GUI 手动流程仍未验证。
- 当前项目配置仍使用 `capture_backend = "opencv_v4l2"` 和 `[recording].backend = "pyav"`，不是 GStreamer 硬件编码路径。
- 如果要切换到 Jetson GStreamer 采集/编码路径，需要先解决主应用 OpenCV 的 GStreamer 支持，或改用系统 Python/OpenCV。

## 建议优先级

1. 优先优化 USB 拓扑或当前启用摄像头组合，让 `/dev/video6` 达到接近 30fps。
2. 决定 Jetson 主应用是否要走 GStreamer；如果要走，修正 `.venv`/`PYTHONPATH`，避免导入无 GStreamer 的 pip/conda OpenCV。
3. 做一次真实 GUI 手动验证：摄像头发现、三路预览、普通录制、外参录制、快照、子进程推理。
4. 如果 legacy 或探索脚本重新变成维护对象，再为对应目录单独建立 lint 策略。
