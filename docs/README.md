# 文档索引

最后更新：2026-07-14

## 阅读顺序

1. [项目目录结构](project_structure.md)：了解文件分类和新文件放置规则。
2. [项目功能总结](status/project_features_summary.md)：了解当前已经实现的能力、本地配置和已有输出数据。
3. [Qt 开发技术面试文档](guides/qt_developer_interview_guide.md)：按面试官追问方式讲解 Qt/PySide6、多线程采集、录制、GStreamer 和 Jetson 设计。
4. [YOLO11 角度拍摄引导版本计划](guides/angle_guidance_versions.md)：按 V1/V2/V3/V4 开发目标物体识别和角度引导。
5. [当前错误总结](status/current_errors_summary.md)：查看测试、静态检查、未验证风险和建议修复顺序。
6. [Jetson Orin Nano Pipeline](architecture/jetson_orin_pipeline.md)：在 Jetson Orin Nano 上配置 GStreamer、硬件编码和 TensorRT 推理。
7. [UI 设计研究](research/ui_design_research.md)：记录界面方案和设计调研。
8. [系统日志总结](status/system_logs_summary.md)：了解本机系统日志中与项目无关但会干扰排查的服务问题。

## 当前状态快照

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
