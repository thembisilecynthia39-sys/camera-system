# camera_system 工作区总览

最后更新：2026-07-16

这个工作区包含从多摄像头采集、任务传输到 3DGS 结果查看的几个相对独立的子项目。各子项目保留自己的源码、配置和测试；其中部分目录还保留独立 Git 历史。本文件只说明它们之间的边界和协作关系。

## 子项目边界

| 子项目 | 职责 | 当前入口 |
|---|---|---|
| [`multiwebcam`](multiwebcam/README.md) | Linux/Jetson 多 USB 摄像头采集、预览、录制、快照、质量检查和角度引导 | [`multiwebcam/README.md`](multiwebcam/README.md) |
| [`Tx_Rx`](Tx_Rx/README.md) | 将完成的 8 图任务打包，向 WSL 发起 HTTP 上传/重建请求，轮询并下载 PLY | [`Tx_Rx/README.md`](Tx_Rx/README.md) |
| [`3DGSviewer`](3DGSviewer/README.md) | 3D 点云、网格、相机和 Gaussian Splat 查看工具及 Qt3D 原型 | [`3DGSviewer/README.md`](3DGSviewer/README.md) |

## 端到端数据流

```text
USB 摄像头
    ↓
multiwebcam
    ├─ MP4 / timestamps.csv
    └─ 多视角 JPEG + 相机、质量和时间戳元数据
            ↓
Tx_Rx
    ├─ staging/ 下生成并校验 task.json
    ├─ HTTP 上传 ZIP 并请求 WSL 重建
    └─ 轮询状态、Range 下载并校验 3DGS.ply
            ↓
3DGSviewer/q3dviewer
    └─ 查看点云、网格和 Gaussian Splat 结果
```

`Tx_Rx` 当前只负责 Jetson 侧任务打包和纯 Python HTTP 客户端，不包含 WSL 接收服务、GaussianObject 重建进程、Qt UI 或摄像头采集入口。真实跨设备联调状态以 [纯 Python 实现报告](Tx_Rx/markdown/TX纯Python_HTTP客户端实现报告.md) 为准。

## 当前状态来源

- `multiwebcam` 的功能、硬件验证和剩余风险记录：[当前错误与实机验证](multiwebcam/docs/status/current_errors_summary.md)
- `Tx_Rx` 的当前实现和模拟 HTTP 测试：[`TX纯Python_HTTP客户端实现报告.md`](Tx_Rx/markdown/TX纯Python_HTTP客户端实现报告.md)
- `q3dviewer` 的安装、工具和库 API：[`3DGSviewer/q3dviewer/README.md`](3DGSviewer/q3dviewer/README.md)
- Qt3D 实验原型：[`3DGSviewer/qt3d-experiments/README.md`](3DGSviewer/qt3d-experiments/README.md)

状态说明：README 是用户入口；`status`、`审查`、`实现报告`和`提示词`文档记录开发过程或验证快照，不能替代用户操作步骤。

## 版本控制边界

统一仓库提交源码、测试、配置模板、脚本、文档和必要的静态资源。以下本地生成或部署相关内容不提交：

- `.venv`、缓存、构建输出和编辑器配置；
- 摄像头采集图片、录制视频、PLY 重建结果和运行日志；
- TensorRT/ONNX/权重等模型二进制；
- `Tx_Rx/staging/` 下的任务包。

如需复现实机环境，应根据各子项目的 `pyproject.toml`、配置示例和 Jetson 文档重新生成这些内容。

## 文档分类

### 用户文档

- [multiwebcam 使用说明](multiwebcam/README.md)
- [Tx_Rx 使用说明](Tx_Rx/README.md)
- [3DGSviewer 工作区说明](3DGSviewer/README.md)

### 开发与规格

- [multiwebcam 文档索引](multiwebcam/docs/README.md)
- [项目目录结构](multiwebcam/docs/project_structure.md)
- [采集引导算法规格](multiwebcam/specs/capture_guidance_algorithm.md)
- [录制目标目录规格](multiwebcam/specs/recording_destinations.md)
- [q3dviewer 发布流程](3DGSviewer/q3dviewer/docs/release.md)

### 状态、协议与历史记录

- [multiwebcam 当前错误与实机验证](multiwebcam/docs/status/current_errors_summary.md)
- [Tx_Rx 当前实现报告](Tx_Rx/markdown/TX纯Python_HTTP客户端实现报告.md)
- [Jetson TX 历史兼容性审查](Tx_Rx/TX审查.md)
- [WSL Rx 协议联调审查](Tx_Rx/RX审查.md)
- [Tx_Rx 开发任务提示词](Tx_Rx/提示词.md)

审查报告保留原审查时点的结论；如果它与 README 或实现报告冲突，应先查看文档性质说明和最新状态来源。
