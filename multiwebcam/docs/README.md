# 文档索引

最后更新：2026-07-16

## 阅读顺序

1. [项目根 README](../README.md)：先了解用户操作入口和当前项目边界。
2. [项目目录结构](project_structure.md)：了解文件分类和新文件放置规则。
3. [项目功能总结](status/project_features_summary.md)：了解当前已经实现的能力、本地配置和已有输出数据。
4. [Jetson Orin Nano Pipeline](architecture/jetson_orin_pipeline.md)：在 Jetson Orin Nano 上配置 GStreamer、硬件编码和 TensorRT 推理。
5. [YOLO11 角度拍摄引导版本计划](guides/angle_guidance_versions.md)：按 V1/V2/V3/V4 了解目标识别和角度引导。
6. [当前错误总结](status/current_errors_summary.md)：查看测试、静态检查、未验证风险和建议修复顺序。
7. [系统日志总结](status/system_logs_summary.md)：了解本机系统日志中与项目无关但会干扰排查的服务问题。

## 文档分类

### 用户文档

- [项目根 README](../README.md)：安装、启动、基本操作和输出说明。
- [脚本目录说明](../scripts/README.md)：脚本分类和运行位置。

### 架构、指南与规格

- `architecture/`：部署和硬件加速架构。
- `guides/`：开发指南和功能版本计划；其中 Qt 面试文档属于学习/面试材料，不是运行手册。
- `../specs/`：采集引导算法、录制目标目录等行为约束。

### 当前状态记录

- `status/project_features_summary.md`：功能和本地配置快照。
- `status/current_errors_summary.md`：测试、硬件问题和剩余风险；动态状态优先看这里。
- `status/system_logs_summary.md`：系统日志排查记录。

### 研究与历史材料

- `research/`：UI 和方案调研，不作为用户操作步骤。
- `scripts/experiments/`：实验代码和笔记，不属于生产 API。

## 当前状态快照

> 以下是已有状态记录的快照，本次只整理文档入口，没有重新执行硬件验证。具体记录时间以 `docs/status/` 文件中的元数据为准。

- 自动化测试通过：`./.venv/bin/python -m pytest -q`
- Ruff 现在聚焦当前维护代码，排除了 legacy 和探索/可视化脚本。
- Jetson 实机硬件 smoke 已运行并通过；当前剩余硬件瓶颈是 `/dev/video6` 约 15fps。
- 角度拍摄引导 V1 已实现：YOLO/子进程检测必须找到目标，捕获才会被接受。

## 推荐下一步

1. 开发前运行 `./.venv/bin/python -m pytest -q`。
2. 提交前运行 `./.venv/bin/python -m ruff check .`。
3. 改动摄像头、GStreamer 或 TensorRT 路径后，在目标设备以真实设备访问方式运行：

```bash
python scripts/jetson/validate_jetson_stack.py --project /path/to/project
python scripts/jetson/jetson_smoke_pipeline.py --project /path/to/project --run-inference
```
