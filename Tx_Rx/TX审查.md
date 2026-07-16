# Jetson TX 与 WSL HTTP 协议兼容性审查

> [!WARNING]
> 文档性质：历史 Jetson 端兼容性审查报告，记录的是审查时点的实现基线，不是当前用户操作指南。当前纯 Python 客户端状态和测试结果以 [`README.md`](README.md) 及[实现报告](markdown/TX纯Python_HTTP客户端实现报告.md)为准；真实 Jetson/WSL 跨设备联调仍需单独确认。

## 审查范围

本次仅审查当前 Jetson `Tx_Rx` 项目，未修改 WSL 协议，未运行真实 GaussianObject，也未对现有通信代码进行大规模修改。

审查结论：当前项目已具备“8 图标准化打包、`task.json`、ZIP 上传、保存 `task_id`、调用 `/reconstruct`”的雏形，但还不是完整的 Jetson 多摄像头/Qt 客户端。状态轮询、PLY metadata、Range 下载、ACK、Qt 工作线程和退出管理均不存在。现有上传还有一个阻断性错误：multipart 的 `checksum` 发送的是任务文件清单摘要，不是最终 ZIP 文件 SHA-256。

## 一、关键审查发现

### 阻断问题

1. **ZIP checksum 错误**

   `tx_rx/jetson_client/uploader.py:34` 的 `upload_staged_task()` 在第 53 行发送 `package.checksum`。该值由 `tx_rx/jetson_client/task_manifest.py:361` 的 `_task_checksum()` 根据“路径、长度、文件哈希”计算，并非 ZIP 字节的 SHA-256。

2. **默认地址使用 `127.0.0.1`**

   `config.yaml:3` 和 `tx_rx/config.py:25` 的默认值都是 `http://127.0.0.1:8000`，无法连接另一台设备中的 WSL 服务。

3. **PLY 接收协议完全未实现**

   没有 metadata 请求、HTTP Range、`If-Range`、分块校验、整文件校验、`.part`、原子重命名和 ACK。

4. **状态模型与 WSL 返回结构不兼容**

   `tx_rx/protocol/models.py:103` 的 `StatusResponse` 缺少 `message_type`、`capture_id`、`stage`、`current_step`、`total_steps`、`log_summary`；反而强制要求 WSL 协议基准中未列为必需的 `created_at`、`updated_at`。`progress` 也被限定为整数。

5. **没有 Qt/后台网络线程**

   全项目未找到 `QObject`、`QThread`、`Signal`、`Slot`、PySide 或 PyQt。调用 `upload_staged_task()` 的线程将同步执行健康检查、ZIP、上传及 `/reconstruct`；如果直接从 UI 调用，会冻结主线程。

### 重要问题

- `task_id` 仅在 `/reconstruct` 成功后写入 `upload.json`。若上传成功但 `/reconstruct` 超时，服务器返回的 `task_id` 会丢失。位置：`tx_rx/jetson_client/uploader.py:60-66`。
- 上传响应只读取 `task_id`，没有验证 `message_type`、`capture_id`、`status`、`duplicate`。
- `/reconstruct` 响应没有解析。
- 非手工采集包会把 `metadata.csv`、`quality.csv`、`cameras.json` 也放进 ZIP。若 WSL 只允许协议列出的 10 个文件，需要排除这些额外文件。
- `capture_id` 直接取目录名，没有字符格式、唯一性或时间格式校验。
- README 提到“desktop UI”，但当前仓库内没有对应 UI 代码或启动入口。

## 二、当前实现位置

| 项目 | 当前实现位置 |
|---|---|
| 1. 多摄像头快照入口 | 当前仓库不存在；只接收已经生成的 capture 目录 |
| 2. 8 图映射 | `tx_rx/protocol/models.py:12` `TASK_ANGLES`；`models.py:40` `TaskImage.validate_fixed_mapping()`；`task_manifest.py:178-195` |
| 3. capture_id | `task_manifest.py:162` `build_task_package()`，取 `capture_dir.name`；手工任务见 `task_manifest.py:67` |
| 4. ZIP 构建 | `tx_rx/jetson_client/uploader.py:98` `_create_task_archive()` |
| 5. task.json | `task_manifest.py:120-130` 和 `task_manifest.py:222-236` |
| 6. ZIP SHA-256 | 未实现；`task_manifest.py:342` `_sha256_file()` 可流式计算文件，但未用于 ZIP |
| 7. multipart 上传 | `uploader.py:49-55` `upload_staged_task()` |
| 8. task_id 保存 | `uploader.py:78` `_write_upload_receipt()`，保存到 `<staging_dir>/upload.json` |
| 9. `/reconstruct` | `uploader.py:60-65` |
| 10. 状态轮询 | 未实现；只有不兼容的 `models.py:103` `StatusResponse` |
| 11. PLY metadata | 未实现 |
| 12. Range 下载 | 未实现 |
| 13. `.part`、文件校验、重命名 | 未实现 |
| 14. ACK | 未实现 |
| 15. Qt Signal/UI 链 | 未实现 |
| 16. 网络线程退出 | 未实现 |

## 三、8 路 index/角度映射

当前代码的固定映射正确：

| index | ZIP 文件 | 角度 |
|---:|---|---:|
| 0 | `images/0.jpg` | 0° |
| 1 | `images/1.jpg` | 45° |
| 2 | `images/2.jpg` | 90° |
| 3 | `images/3.jpg` | 135° |
| 4 | `images/4.jpg` | 180° |
| 5 | `images/5.jpg` | 225° |
| 6 | `images/6.jpg` | 270° |
| 7 | `images/7.jpg` | 315° |

采集目录模式不是按 `camera_id` 排序，而是由 `tx_rx/jetson_client/task_manifest.py:261` 的 `_read_task_records()` 读取 `metadata.csv` 最后 8 行，并要求它们已经严格按上述角度排列。`camera_id` 被忽略。

## 四、协议逐字段对比表

| 协议项目 | WSL 要求 | Jetson 当前实现 | 是否一致 | 修复位置 |
|---|---|---|---|---|
| server_url | WSL 实际 IP | 配置可设置，但默认为 127.0.0.1 | 否 | `config.yaml:3`、`config.py:25` |
| 端口 | TCP 8000 | 示例和默认均为 8000 | 是 | 无 |
| POST /upload | multipart ZIP | 已实现 | 是 | 无 |
| multipart 字段名 | `file`、`checksum` | 字段名正确 | 是 | 无 |
| ZIP SHA-256 | 最终 ZIP 的 SHA-256 | 发送文件清单摘要 | 否 | `uploader.py:48-54` |
| capture_id 格式 | 合法且稳定 | 直接使用目录名 | 部分 | `task_manifest.py:162` |
| task.json schema_version | 正确生成 | 固定 `"1.0"` | 是 | 无 |
| 图片数量 | 8 | 强制 8 | 是 | 无 |
| 文件名 | `images/0.jpg`…`7.jpg` | 正确 | 是 | 无 |
| index 和角度 | 固定对应 | 模型和打包均强制验证 | 是 | 无 |
| 图片大小 | 每图 `size_bytes` | 已生成并复验 | 是 | 无 |
| 图片 SHA-256 | 64 位小写 hex | 流式计算，模型正则验证 | 是 | 无 |
| 任务 checksum | 按 WSL 定义 | 当前为自定义清单摘要 | 待确认/否 | `task_manifest.py:361` |
| task_id 使用方式 | 使用上传响应值 | `/reconstruct` 使用响应值并保存 | 基本一致 | `uploader.py:57-66` |
| POST /reconstruct | JSON `task_id` | 已实现 | 是 | 无 |
| 状态轮询 | GET `/status/<task_id>` | 未实现 | 否 | 新增客户端与模型 |
| PLY metadata | GET metadata 并严格验证 | 未实现 | 否 | 新增客户端与模型 |
| HTTP Range | 每块请求并要求 206 | 未实现 | 否 | 新增 PLY 下载器 |
| If-Range | 完整文件 SHA-256 | 未实现 | 否 | 新增 PLY 下载器 |
| 分块 SHA-256 | 验证响应头 | 未实现 | 否 | 新增 PLY 下载器 |
| 整文件 SHA-256 | 流式验证 | 未实现 | 否 | 新增 PLY 下载器 |
| `.part` 文件 | 下载期间仅 `.part` | 未实现 | 否 | 新增 PLY 下载器 |
| 原子重命名 | 校验成功后替换 | 未实现 | 否 | 新增 PLY 下载器 |
| ACK | POST `/result/<task_id>/ack` | 未实现 | 否 | 新增结果客户端 |

## 五、项目启动命令

当前项目没有 GUI 或服务进程启动入口，只是 Python 库。现有安装和测试方式：

```bash
python3 -m pip install -e .
pytest -q
```

打包需由其他代码调用：

```python
from tx_rx.jetson_client import build_configured_task_package

result = build_configured_task_package(capture_dir)
```

## 六、配置文件与 server_url

配置文件：

```text
/home/jetson/3DGS/camera_system/Tx_Rx/config.yaml
```

`server_url` 配置应为：

```yaml
server_url: http://<WSL实际IP>:8000
```

当前实际文件仍是 `127.0.0.1`，本次按“先审查”要求未修改。

当前配置模型还没有 `result_root`、轮询周期或下载超时配置。

## 七、模拟测试命令与实际结果

执行：

```bash
pytest -q
```

结果：

```text
34 passed in 0.71s
```

执行用户指定命令：

```bash
python -m compileall .
```

该命令失败，原因是当前机器的解释器映射为：

```text
python  -> Python 2.7.18
python3 -> Python 3.8.10
pytest  -> /usr/bin/python3
```

`python` 会把 Python 3 类型注解和 f-string 当成语法错误。使用正确解释器：

```bash
python3 -m compileall -q .
```

结果：

```text
python3 compileall: PASS
```

当前测试仅覆盖打包、manifest、staging 扫描和模拟 Session 上传；尚未覆盖真实 HTTP 模拟服务端、状态查询、PLY、Range、ACK、UI 和线程退出等要求。

## 八、PLY 最终保存路径

当前未实现 PLY 下载和保存。目标路径应为：

```text
<result_root>/<capture_id>/<task_id>/3DGS.ply.part
```

校验成功后原子重命名为：

```text
<result_root>/<capture_id>/<task_id>/3DGS.ply
```

校验失败时不能生成正式 `.ply`。

## 九、Qt Signal 调用链

当前不存在 Qt Signal/UI 调用链。现有同步链路为：

```text
调用方
→ upload_staged_task()
→ load_staged_task_package()
→ GET /health
→ _create_task_archive()
→ POST /upload
→ 读取 task_id
→ POST /reconstruct
→ _write_upload_receipt()
```

如果调用方是 Qt 主线程，ZIP 和网络请求都会阻塞 UI。

## 十、本次修改文件

本次只新增审查文档：

```text
TX审查.md
```

未修改任何通信、采集或 UI 源代码。

## 十一、建议修复顺序

1. 先明确并修复 ZIP SHA-256 语义。
2. 增加协议响应模型和 `result_root` 配置。
3. 将 ZIP、上传、轮询和 Range 下载放入可取消的 Qt 工作线程。
4. 上传响应一取得 `task_id` 就原子持久化，再启动重建。
5. 流式实现 metadata、Range、分块哈希、整文件哈希、`.part` 和 ACK。
6. 增加最小 HTTP 模拟 WSL 服务端及失败测试。
7. 最后连接现有多摄像头/UI 项目入口；这些代码目前不在本仓库中。

## 十二、与真实 WSL 联调前仍需确认的问题

1. **`task.json.checksum` 的确切语义**

   multipart 中的 `checksum` 明确要求为最终 ZIP 文件 SHA-256。但如果 `task.json.checksum` 也要求等于“包含该 `task.json` 的完整 ZIP SHA-256”，将形成自引用，无法直接构造。建议在 WSL 已有实现中确认 `task.json.checksum` 是文件清单摘要、业务内容摘要，还是其他值。

2. **ZIP 是否允许额外文件**

   当前采集目录模式会额外上传 `metadata.csv`、`quality.csv`、`cameras.json`。需确认 WSL 是只要求 ZIP 包含协议指定文件，还是要求 ZIP 严格只包含协议列出的 10 个文件。

3. **Qt 与多摄像头工程的实际位置**

   当前 `Tx_Rx` 目录中没有 Qt UI、摄像头采集入口或线程生命周期代码。在实现“UI 不冻结”和“关闭后线程停止”前，需要确认这部分源码是否位于其他目录或尚未加入本项目。
