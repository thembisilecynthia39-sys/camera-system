# 项目目录结构

最后更新：2026-07-14

## 分类原则

- 可发布的应用代码放在 `src/multiwebcam/`，按采集、录制、识别、质量评估和界面分包。
- 自动化验证放在 `tests/`，目录名称与 `src/multiwebcam/` 的子系统对应。
- 运维和开发工具放在 `scripts/`，按用途分类，不与应用包混放。
- 设计说明和阶段记录放在 `docs/`；具有约束性质的需求放在 `specs/`。
- 模型、采集数据、录制数据和生成物分别存放，避免在项目根目录堆积。
- 旧实现、备份和第三方工具保留在独立目录中，不参与当前应用构建。

## 目录说明

```text
multiwebcam/
├── src/multiwebcam/          # 当前维护的应用源码
├── tests/                    # 自动化测试
├── scripts/
│   ├── setup/                # 摄像头与系统初始化
│   ├── diagnostics/          # USB、V4L2 和采集链路诊断
│   ├── jetson/               # Jetson 环境验证和硬件 smoke test
│   ├── services/             # 独立运行的推理服务
│   ├── testing/              # 手动集成测试
│   ├── experiments/pyav/     # PyAV/V4L2 探索脚本
│   └── visualization/widgets/ # 界面截图和可视化验证
├── docs/
│   ├── architecture/         # 系统与部署架构
│   ├── guides/               # 开发和功能指南
│   ├── research/             # 调研与设计探索
│   └── status/               # 当前状态、错误和日志总结
├── specs/                    # 功能规格和行为约束
├── config/udev/              # Linux udev 规则
├── models/                   # YOLO 权重、ONNX 和 TensorRT engine
├── artifacts/
│   ├── logs/                 # 运行与诊断日志
│   └── reconstructions/      # PLY 等重建结果
├── captures/                 # 本地快照输出
├── recordings/              # 本地视频录制输出
├── archive/backups/          # 历史备份文件
├── multiwebcam_legacy/       # 旧版实现，仅供参考
└── vendor/                   # 本地第三方工具仓库，不纳入版本控制
```

## 根目录保留文件

根目录只保留项目入口和标准工程文件：`README.md`、`LICENSE`、`pyproject.toml`、`uv.lock`、`run_jetson`，以及应用按项目目录约定读取的本地 `multiwebcam.toml`。

## 新文件放置规则

- 新的生产代码进入 `src/multiwebcam/` 对应子包。
- 新的自动化测试进入 `tests/` 对应子目录。
- 一次性硬件排查脚本进入 `scripts/diagnostics/`，验证稳定后再决定是否进入源码包。
- 阶段性故障记录进入 `docs/status/`，长期有效的使用说明进入 `docs/guides/`。
- 大型模型和生成数据不要放到根目录；默认不提交 TensorRT engine、PLY、录制与快照数据。
