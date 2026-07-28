# GaussianObject Rx（WSL/服务器）

该目录是只部署在 WSL/服务器上的独立项目，包含：

```text
gaussianobject_rx/server/     HTTP Rx、校验、任务注册、重建 worker
gaussianobject_rx/protocol/   与 Jetson Tx 对齐的协议模型
config.yaml                   正式 WSL 配置
config.simulation.yaml        假 baseline 联调配置
tools/fake_baseline.py        小型模拟 PLY 生成器
```

该目录不包含 Jetson 摄像头采集、任务上传、PLY 落盘或 Qt UI 代码。

## 正式启动

```bash
cd /home/yp/GaussianObject/camera_system/Rx

PYTHONPATH=. /home/yp/miniconda3/envs/GaussianObject/bin/python \
  -m gaussianobject_rx.server \
  --config config.yaml
```

## 模拟重建启动

```bash
PYTHONPATH=. /home/yp/miniconda3/envs/GaussianObject/bin/python \
  -m gaussianobject_rx.server \
  --config config.simulation.yaml
```

默认图片上传、状态查询和 PLY 回传共用 TCP/HTTP 8000。

完整照片包通过 `/upload` 校验后会立即自动加入重建队列，不再要求 Tx 额外
触发。旧版 Tx 继续调用 `/reconstruct` 也安全，该接口保持幂等兼容。Rx 重启
时会自动恢复此前处于上传、SfM、3DGS 或已排队状态的任务；训练完成后原子
发布校验过的 `result/3DGS.ply`，供 Tx 自动下载和 ACK。

## WSL 开机自启与控制

首次安装一次：

```bash
cd /home/yp/GaussianObject/camera_system/Rx
chmod +x install_service.sh bin/Rx
./install_service.sh
```

之后使用：

```bash
Rx on       # 启动并设置开机自启
Rx off      # 停止并取消开机自启
Rx status   # 查看状态
Rx logs     # 跟踪日志
```

WSL 后台启动时没有可交互终端，因此询问会出现在本次 WSL 启动后的第一个
交互终端中，并且每次启动只询问一次。选择否会执行 `Rx off`；选择是则保持
服务运行。

服务以普通用户 `yp` 运行，并设置低 CPU/IO 优先级、70% 内存软阈值、80%
内存硬上限、512 个任务上限、OOM 停止和重启频率限制。停止服务时 systemd
会清理整个 Rx 进程组，避免遗留训练子进程影响 WSL。

## 测试

闭环测试需要同时把相邻 Tx 项目加入 `PYTHONPATH`，仅作为测试客户端使用；正式 Rx 运行不依赖 Tx：

```bash
PYTHONPATH=.:../Tx /home/yp/miniconda3/envs/GaussianObject/bin/python \
  -m unittest -v tests.test_closed_loop
```

完整协议审查见 `PROTOCOL_INTEGRATION_REVIEW.md`。
