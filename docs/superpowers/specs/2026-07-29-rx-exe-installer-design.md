# RX WSL EXE 自动安装器设计

日期：2026-07-29

## 1. 背景与目标

当前仓库的 Jetson 客户端位于 `Tx_Rx`，完整的 WSL 接收服务位于 GitHub
仓库的 `agent/upload-rx/Rx` 目录。RX 依赖用户已经准备好的 WSL2、Ubuntu、
NVIDIA GPU、Python 环境和 GaussianObject baseline；本功能只负责把 RX 服务
可靠地部署到现有 WSL，不安装、升级、覆盖或修改 GaussianObject。

目标是提供一个 Windows `.exe` 安装器，使用户无需手工执行多条 WSL 命令即可：

1. 发现并验证可用的 WSL 发行版、Python 解释器、baseline 和磁盘空间；
2. 将内置的 RX 源码部署到 WSL；
3. 安装 RX 自身的纯 Python 依赖（`pydantic`、`PyYAML`）；
4. 根据实际 WSL 用户、路径和 Python 解释器生成配置及 systemd 服务；
5. 配置可选的 Windows 入站 TCP 8000 规则/WSL NAT 端口转发；
6. 启动 RX，检查 `GET /health`，展示 Jetson 应使用的服务地址。

## 2. 现状边界

GitHub 的 RX 目录包含：

- `gaussianobject_rx.server` HTTP 服务和重建队列；
- `config.yaml` 和模拟配置；
- `install_service.sh`、`bin/Rx`、systemd 单元；
- `pyproject.toml`，仅声明 `pydantic` 和 `PyYAML` 两项 RX 运行时依赖。

当前服务单元中的 `/home/yp`、`/home/yp/miniconda3/envs/GaussianObject/bin/python`
和 `User=yp` 只适用于原始部署机，不能直接作为通用安装模板。安装器必须在
部署时生成对应值。`Rx/config.yaml` 中的 `baseline_path` 只作为服务调用目标
读取，安装器不得写入该目录。若现有 GaussianObject Python 环境已经包含 RX
依赖，可以只读复用；若缺少依赖，必须创建 RX 自己的 `.venv-rx`，不能向
GaussianObject 环境执行 pip 安装。

## 3. 方案比较与选择

### 方案 A：EXE 内置 RX payload（选用）

EXE 内嵌固定版本的 `Rx` 源码压缩包和 SHA-256 清单。安装时通过 `wsl.exe`
将 payload 解压到 WSL，并生成用户相关的配置和 systemd 单元。

优点是安装包版本稳定、不依赖 GitHub 可用性，用户只需下载一个文件；RX 源码
体积小，不会把 GaussianObject、模型和 baseline 一起复制。缺点是 RX 更新时
需要重新构建 EXE。

### 方案 B：EXE 在线下载 RX 分支

EXE 只包含部署逻辑，安装时从指定 GitHub commit 下载 `Rx` 目录。

优点是 EXE 较小、更新方便；缺点是受网络、GitHub 权限和远程分支变化影响，
无法保证现场安装得到与测试完全一致的代码。因此仅作为开发/诊断模式，不作为
正式发布默认路径。

### 方案 C：只提供 WSL shell 安装脚本

把现有 `install_service.sh` 参数化，由用户在 WSL 中执行。

实现成本最低，但不能满足“EXE 自动检测并安装”的用户体验，作为故障恢复脚本
保留，不作为主入口。

正式实现采用方案 A，并同时保留方案 C 生成的 WSL 端部署脚本，便于无 Windows
界面时排障。

## 4. 安装器形态与用户流程

安装器源码使用 Python 标准库 `tkinter` 实现简洁向导，使用 PyInstaller 构建
为单个 Windows EXE。最终 Windows 主机不需要预装 Python。EXE 只调用 Windows
自带的 `wsl.exe`、PowerShell 和系统网络配置命令。

用户流程如下：

1. 启动 EXE，读取内置 payload 版本和校验值；
2. 列出 WSL 发行版，默认选择默认发行版；
3. 执行预检并逐项显示结果：WSL 版本、systemd、当前 Linux 用户、Python、
   `pydantic`/`yaml`、baseline 可执行文件、配置路径、磁盘空间和 TCP 8000；
4. 自动识别已有 `Tx_Rx` 目录，并将 RX 默认部署到其同级的 `Rx` 目录；若
   无法唯一识别，允许用户选择 WSL 绝对路径；
5. 检测 baseline，默认寻找已有 GaussianObject 工作区中的 `baseline`。找不到
   或不可执行时停止安装，并明确提示“请先准备 GaussianObject”，不下载或修改它；
6. 将 RX payload 写入临时目录，校验每个文件的 SHA-256，通过后原子发布；
7. 生成 `config.yaml`、systemd service 和 `Rx` 控制命令，保留用户已有任务目录
   和配置；
8. 先在候选 Python 中检查 `pydantic` 和 `yaml`；如果现有 GaussianObject 环境
   已满足依赖则只读复用，否则在 RX 目录创建 `.venv-rx`，只向该环境安装 RX
   依赖。不向 GaussianObject 环境执行 pip 安装，不执行 Jetson 的安装脚本，也
   不安装 PyQt、OpenCV、CUDA、Torch 或 GaussianObject。pip 失败时安装终止并
   保留现有服务；
9. 根据 WSL 网络模式配置 TCP 8000 入站规则。NAT 模式创建/更新 Windows
   `portproxy`；mirrored 模式只检查/创建防火墙规则；
10. 启动 `gaussianobject-rx.service`，轮询 `http://127.0.0.1:8000/health`，
    最后显示可复制的 Jetson URL 和日志位置。

安装失败时保留诊断日志，已有运行中的 RX 和已发布任务不被删除。重新安装使用
版本化临时目录，只有完整校验通过后才替换同版本目标；配置和 `rx_tasks` 永不
被清理。

## 5. WSL 部署设计

### 5.1 命令边界

Windows 端负责界面、预检、payload 校验、调用编排和最终结果展示。WSL 端负责
文件安装、Python pip、配置渲染和 systemd 操作。所有 WSL 命令通过参数数组或
严格转义的单一脚本参数传递，不能将路径直接拼接进未经转义的 shell 命令。

### 5.2 动态配置

安装器生成的 RX 配置至少包含：

```yaml
schema_version: "1.0"
listen_host: 0.0.0.0
listen_port: 8000
task_root: ${TASK_ROOT}
baseline_path: ${BASELINE_PATH}
baseline_iterations: 2000
reconstruction_queue_size: 8
max_upload_size_bytes: 536870912
max_extracted_size_bytes: 1073741824
max_ply_size_bytes: 2147483648
result_chunk_size_bytes: 8388608
request_timeout_seconds: 300
reconstruction_timeout_seconds: 21600
process_stop_timeout_seconds: 15
```

默认 `task_root` 为 RX 目录同级的 `rx_tasks`；默认 baseline 为检测到的
GaussianObject 工作区下的 `baseline`。两个路径都允许用户在“高级设置”中修改，
但必须是 WSL 内的绝对路径，且 baseline 必须已存在并具有执行权限。

### 5.3 systemd

安装器根据检测到的 Linux 用户、RX 根目录和 Python 可执行文件生成
`gaussianobject-rx.service`。服务保留当前 RX 设计中的进程组清理、失败重启、
资源限制和 `NoNewPrivileges`，但不硬编码原始部署机用户名或目录。

如果 WSL 尚未启用 systemd，安装器显示需要重启 WSL 的提示，并在用户确认后写入
最小的 `/etc/wsl.conf` 设置。安装阶段状态保存到 Windows 用户目录的安装状态
文件；调用 `wsl --shutdown` 后重新启动 EXE 或其 resume 子进程，继续完成剩余
步骤。若用户拒绝重启，则安装器可完成源码部署，但将状态标记为“未启动”，不
伪造成功。

### 5.4 网络

服务固定监听 `0.0.0.0:8000`。安装器检测端口占用，并在已占用时显示占用进程和
修复建议，不强制终止未知进程。Windows 防火墙规则使用稳定名称
`CameraSystem-RX-8000`，重复安装只更新同名规则。

NAT 模式的 portproxy 目标 WSL IP 可能随 WSL 重启变化，因此安装器记录发行版、
监听端口和目标地址，创建一个稳定名称的 Windows 登录任务自动刷新 portproxy，
并提供“修复网络”操作；不会创建无限重复的 portproxy 规则。Jetson URL 使用
Windows 主机的局域网 IP，而不是 WSL 虚拟 IP。创建或更新防火墙、portproxy 和
登录任务需要 Windows 管理员权限；用户拒绝 UAC 时仍可完成本机安装，但结果必须
明确标记为“仅本机可访问”。

## 6. 组件划分

### Windows EXE

- `InstallerWindow`：阶段、日志、错误和重试显示；
- `WslRunner`：调用 `wsl.exe`，解析退出码和 stdout/stderr；
- `EnvironmentDetector`：发行版、用户、Python、systemd、baseline、磁盘和端口检测；
- `PayloadInstaller`：清单校验、临时部署、原子切换和回滚；
- `ConfigRenderer`：生成 RX YAML 和 systemd unit；
- `NetworkConfigurator`：防火墙与 portproxy 检查/更新；
- `HealthChecker`：本地 `/health`、服务状态和最终 Jetson 地址验证；
- `ResumeState`：跨 WSL 重启保存和恢复安装阶段；
- `ElevationRunner`：以 UAC 管理员权限执行 Windows 网络变更；
- `EmbeddedPayload`：RX 文件及版本、SHA-256 清单。

### WSL 端脚本

- `install-rx.sh`：可独立执行的无界面部署入口，与 EXE 使用同一参数语义；
- `gaussianobject-rx.service`：由脚本渲染，不直接复用硬编码版本；
- `Rx`：保留 `on/off/status/logs` 控制接口；不默认安装会在交互式登录时询问
  是否开启服务的 `rx-login-prompt`，避免自动安装被终端交互阻塞。

## 7. 错误处理与安全要求

- 找不到 WSL、Python、systemd 或 baseline：停止并给出可执行修复建议；
- pip 失败：显示完整错误，保留现有服务，不删除 RX 目录；
- 现有 GaussianObject 环境缺少依赖时只创建 `.venv-rx`，绝不向其执行 pip；
- 配置解析失败：在启动前验证 YAML/Pydantic 模型；
- 8000 端口冲突：显示进程信息，不自动杀进程；
- `/health` 超时或非 `{"status":"ok"}`：安装失败，提供日志路径；
- payload 必须在部署前完成 SHA-256 校验；
- 不执行从网络直接下载后立即运行的 shell 内容；
- baseline 路径仅作为配置输入，不复制、不覆盖、不升级；
- 所有日志隐藏 WSL 用户密码、token 和完整环境变量；
- 对目标路径做绝对路径、目录边界和符号链接检查，避免写出 RX 安装根目录。

## 8. 测试与验收

### 自动化测试

- WSL 输出解析：发行版、用户名、Python 路径、systemd 状态和路径发现；
- 配置及 systemd 模板渲染：空格、Unicode、特殊字符和不同用户名；
- payload 清单校验、临时发布和失败回滚；
- 重复安装保持 task root、配置和已完成任务；
- NAT/mirrored 网络模式的命令生成；
- 8000 端口占用和健康检查失败；
- 使用假的 `wsl.exe`/PowerShell runner 做 Windows 无环境单元测试。

### 实机验收

1. 干净 Windows 用户上双击 EXE；
2. 已有 WSL、Python、baseline 的环境完成安装；
3. `Rx status` 显示 active；
4. `curl http://127.0.0.1:8000/health` 返回 `status=ok`；
5. Jetson 访问 Windows/WSL 的 8000 端口成功；
6. 使用 8 张图完成真实上传、GaussianObject 重建、PLY 下载和 ACK；
7. 重启 WSL 后服务按配置恢复，已有任务状态保持；
8. 卸载/回滚不会删除 baseline 或 `rx_tasks`。

## 9. 交付物

- Windows EXE 安装器源码；
- 固定 commit 的 RX payload 与 SHA-256 清单，构建元数据记录仓库、分支和 commit；
- 可独立执行的 `install-rx.sh`；
- Windows 构建脚本（PyInstaller）和 Windows CI 产物；
- RX 安装、升级、卸载/回滚和网络修复说明；
- Windows 构建说明及版本校验信息；
- 自动化测试和一份实际 WSL/Jetson 联调报告。

## 10. 非目标

- 不安装或更新 WSL、Ubuntu、NVIDIA 驱动、CUDA、Python 或 GaussianObject；
- 不打包 baseline、模型权重、采集数据或已有重建结果；
- 不修改 Jetson Qt 应用的安装流程；
- 不改变 Tx/Rx HTTP 协议和 GaussianObject baseline 调用约定；
- 不提供公网暴露、TLS、认证或多用户权限管理。
