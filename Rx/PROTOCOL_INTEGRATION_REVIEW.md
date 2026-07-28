# WSL Rx 与 Jetson 协议联调审查报告

审查范围：

```text
/home/yp/GaussianObject/camera_system/Tx
/home/yp/GaussianObject/camera_system/Rx
/home/yp/GaussianObject/baseline
```

当前协议的核心结论：WSL 端使用 TCP 上的 HTTP/1.1 服务，不是自定义 `struct` 定长二进制图片协议。Jetson 一次上传包含完整拍摄批次的 ZIP；WSL 校验 8 张图片后创建任务，通过独立工作线程启动 baseline 子进程，最后在同一个 HTTP 端口提供 PLY 分块下载和结果 ACK。

## 1. WSL Rx 启动命令

生产配置启动命令：

```bash
cd /home/yp/GaussianObject/camera_system/Rx

PYTHONPATH=. /home/yp/miniconda3/envs/mvsplat/bin/python \
  -m gaussianobject_rx.server \
  --config config.yaml
```

入口文件：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/__main__.py:15
```

WSL 是服务端，执行 `listen/bind`，不会主动连接 Jetson：

```python
ReceiverHTTPServer((config.listen_host, config.listen_port), ...)
```

对应代码：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/application.py:13
```

重复启动同一端口会得到操作系统的明确错误：

```text
OSError: [Errno 98] Address already in use
```

构造 HTTP Server 失败时，已创建的重建 worker 会被停止，避免线程泄漏：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/application.py:17
```

## 2. 配置文件路径

生产配置：

```text
/home/yp/GaussianObject/camera_system/Rx/config.yaml
```

主要配置：

```yaml
listen_host: 0.0.0.0
listen_port: 8000
task_root: /home/yp/GaussianObject/rx_tasks
baseline_path: /home/yp/GaussianObject/baseline
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

模拟联调配置：

```text
/home/yp/GaussianObject/camera_system/Rx/config.simulation.yaml
```

配置模型及字段限制：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/config.py:18
```

Jetson 客户端配置：

```text
/home/yp/GaussianObject/camera_system/Tx/config.yaml
```

部署时必须把其中的 `server_url` 从 `127.0.0.1` 修改为 Jetson 可访问的 WSL/服务器地址。

## 3. 图片上传端口

```text
传输层：TCP
应用层：HTTP/1.1
WSL 监听：0.0.0.0:8000
图片上传：POST /upload
```

路由入口：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/http_server.py:66
```

当前不是“每台相机分别发送一条图片消息”的协议。Jetson 必须先形成一个完整任务 ZIP，再通过一次 `/upload` 上传整个 capture。

## 4. PLY 回传端口

PLY 回传与图片上传共用 TCP 8000：

```text
GET  /result/<task_id>/metadata
GET  /result/<task_id>
POST /result/<task_id>/ack
```

没有单独的结果端口。上传和下载可以使用不同 HTTP 连接，但均访问同一个 HTTP 服务。

PLY 使用 HTTP Range 分块下载。服务端按 64 KiB 小块读取和写入 socket，不会将整个 PLY 一次放入内存：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/http_server.py:186
```

## 5. 完整协议字段表

### 5.1 连接与编码

| 项目 | 当前定义 |
|---|---|
| 连接方向 | Jetson 主动连接 WSL |
| WSL 角色 | TCP/HTTP 服务端 |
| 传输层 | TCP |
| 应用层 | HTTP/1.1 |
| 默认地址 | `0.0.0.0:8000` |
| 图片上传端口 | 8000 |
| PLY 回传端口 | 8000 |
| 字节序 | 不适用；没有二进制定长整数包头 |
| HTTP Header 编码 | ASCII/ISO-8859-1 |
| JSON 编码 | UTF-8 |
| HTTP 换行 | `\r\n` |
| 消息长度 | 十进制 `Content-Length` |
| 图片 payload | ZIP 中的 JPEG 文件 |
| PLY payload | `application/octet-stream`，作为不透明字节传输 |

### 5.2 图片上传消息

```http
POST /upload HTTP/1.1
Host: <wsl-ip>:8000
Content-Type: multipart/form-data; boundary=<ASCII boundary>
Content-Length: <decimal>
```

multipart 必须正好包含：

| 字段 | 类型 | 长度和约束 |
|---|---|---|
| `file` | ZIP 二进制 | 整个 HTTP body 默认最大 512 MiB |
| `checksum` | ASCII 字符串 | 正好 64 字节、小写 SHA-256 hex |

multipart 流式解析代码：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/multipart.py:64
```

ZIP 的典型内容：

```text
task.json
images/0.jpg
images/1.jpg
images/2.jpg
images/3.jpg
images/4.jpg
images/5.jpg
images/6.jpg
images/7.jpg
metadata.json
其他由 task.json.files 明确声明的文件
```

`task.json` 字段：

| 字段 | JSON 类型 | 长度和约束 |
|---|---:|---|
| `schema_version` | string | 当前为 `"1.0"` |
| `capture_id` | string | 1～128 字符；`[A-Za-z0-9][A-Za-z0-9._-]*` |
| `image_count` | integer | 必须为 8 |
| `angles` | integer[] | 固定为 `[0,45,90,135,180,225,270,315]` |
| `images[].index` | integer | 0～7，唯一且完整 |
| `images[].angle` | integer | 必须与 index 的固定角度一致 |
| `images[].filename` | string | 固定为 `0.jpg`～`7.jpg` |
| `images[].source_filename` | string | 非空，未额外限制长度 |
| `images[].size_bytes` | integer | 非负，必须与文件一致 |
| `images[].sha256` | string | 64 字节小写 hex |
| `files[].relative_path` | string | 安全、规范化的 POSIX 相对路径 |
| `files[].size_bytes` | integer | 必须与文件一致 |
| `files[].sha256` | string | 64 字节小写 hex，必须与文件一致 |
| `created_at` | string | ISO-8601 datetime |
| `checksum` | string | 64 字节任务文件集合校验值 |

数据模型：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/protocol/models.py:32
```

关于相机字段的准确结论：

- `capture_id` 是 WSL 协议字段，类型为受限制的字符串。
- `camera_id` 当前不属于 WSL 上传协议。
- `frame_id` 不在 `task.json.images[]` 中。
- capture builder 会把 `frame_id` 写进 `metadata.json`，但 Rx 不使用它判断完整性。
- WSL 不根据 `camera_id/frame_id` 在多条网络消息之间聚合图片。

`frame_id` 写入 `metadata.json` 的位置：

```text
/home/yp/GaussianObject/camera_system/Tx/gaussianobject_tx/client/task_manifest.py:200
```

### 5.3 完整批次判断

WSL 不接收零散的单路相机消息。一次 `/upload` 只有在以下条件全部满足后才进入 `ready`：

1. ZIP 中存在合法 `task.json`。
2. `image_count` 为 8。
3. image index 正好覆盖 0～7。
4. 文件名正好覆盖 `0.jpg`～`7.jpg`。
5. 角度固定为 `0,45,90,135,180,225,270,315`，且没有重复。
6. ZIP 文件集合与 manifest 完全一致。
7. 每个文件的长度和 SHA-256 与 manifest 一致。
8. 图片能够解析出 JPEG 尺寸。
9. `capture_id` 满足安全字符和长度要求。
10. ZIP 展开大小、文件数和图片分辨率不超过限制。

校验代码：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/archive_validator.py:41
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/protocol/models.py:74
```

如果缺少任意一路图片，整个 `/upload` 返回 HTTP 400，不创建任务，也不会启动重建。

### 5.4 上传响应

```json
{
  "message_type": "upload_received",
  "task_id": "task-<64位任务checksum>",
  "capture_id": "capture_001",
  "status": "ready",
  "duplicate": false
}
```

`task_id` 的计算规则：

```text
task_id = "task-" + 64位任务checksum
```

相同内容重复上传会返回相同 `task_id`，因此具有幂等性。

### 5.5 重建请求

```http
POST /reconstruct HTTP/1.1
Content-Type: application/json; charset=utf-8
```

```json
{
  "task_id": "task-<64位hex>"
}
```

响应：

```json
{
  "message_type": "reconstruction_queued",
  "task_id": "task-...",
  "capture_id": "capture_001",
  "status": "ready"
}
```

请求体最大 1 MiB：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/http_server.py:134
```

### 5.6 状态协议

请求：

```http
GET /status/<task_id> HTTP/1.1
```

示例响应：

```json
{
  "message_type": "reconstruction_running",
  "task_id": "task-...",
  "capture_id": "capture_001",
  "status": "running_3dgs",
  "stage": "running_3dgs",
  "progress": 55,
  "current_step": 0,
  "total_steps": 0,
  "message": "3DGS training running",
  "output_ply": null,
  "error": null,
  "log_summary": "",
  "created_at": "...",
  "updated_at": "..."
}
```

状态消息映射：

| `message_type` | 当前发送时机 |
|---|---|
| `upload_received` | 上传完成、尚未入队 |
| `reconstruction_queued` | 已进入重建队列 |
| `reconstruction_running` | COLMAP 或 3DGS 子进程运行中 |
| `reconstruction_progress` | 协议模型已预留，当前不主动发送 |
| `reconstruction_failed` | 子进程失败、超时或输出异常 |
| `result_sending` | PLY 响应头 `X-GO-Transfer-State` |
| `result_ready` | 状态为 `finished` |

当前 `progress` 保持原有的 0～100 整数语义；`current_step` 和 `total_steps` 暂时为 0。

状态模型和 HTTP 输出：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/protocol/models.py:103
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/http_server.py:153
```

### 5.7 PLY 文件元数据

请求：

```http
GET /result/<task_id>/metadata HTTP/1.1
```

响应：

```json
{
  "magic": "GOBJ",
  "version": "1.0",
  "message_type": "ply_result",
  "task_id": "task-...",
  "capture_id": "capture_001",
  "filename": "3DGS.ply",
  "file_size": 106,
  "sha256": "<64位小写hex>",
  "chunk_size": 8388608,
  "chunk_count": 1,
  "created_at": "..."
}
```

模型：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/protocol/models.py:126
```

### 5.8 PLY 数据传输方式

Jetson 分块请求：

```http
GET /result/<task_id> HTTP/1.1
Range: bytes=<start>-<end>
If-Range: "<完整PLY SHA-256>"
```

响应：

```http
HTTP/1.1 206 Partial Content
Content-Type: application/octet-stream
Content-Length: <本块长度>
Content-Range: bytes <start>-<end>/<总长度>
ETag: "<完整PLY SHA-256>"
X-GO-Magic: GOBJ
X-GO-Protocol-Version: 1.0
X-GO-Message-Type: ply_result
X-GO-Transfer-State: result_sending
X-GO-Task-ID: task-...
X-GO-Capture-ID: capture_001
X-GO-Filename: 3DGS.ply
X-GO-File-Size: <总长度>
X-GO-SHA256: <整文件SHA>
X-GO-Chunk-Index: <从0开始>
X-GO-Chunk-Count: <总块数>
X-GO-Chunk-SHA256: <本块SHA>
```

Jetson 必须校验：

1. HTTP 状态为 206。
2. 本块长度与请求范围一致。
3. 本块 SHA-256 一致。
4. 最终文件长度与 `file_size` 一致。
5. 最终整文件 SHA-256 一致。

Jetson 结果接收代码先写入：

```text
<result_root>/<capture_id>/<task_id>/3DGS.ply.part
```

只有长度和整文件 SHA-256 均通过后，才执行原子重命名：

```text
<result_root>/<capture_id>/<task_id>/3DGS.ply
```

对应代码：

```text
/home/yp/GaussianObject/camera_system/Tx/gaussianobject_tx/client/result_client.py:123
```

### 5.9 ACK 格式

Jetson 完成长度、SHA-256 和原子保存后发送：

```http
POST /result/<task_id>/ack HTTP/1.1
Content-Type: application/json; charset=utf-8
```

```json
{
  "magic": "GOBJ",
  "version": "1.0",
  "message_type": "result_received",
  "task_id": "task-...",
  "capture_id": "capture_001",
  "filename": "3DGS.ply",
  "file_size": 106,
  "sha256": "<64位小写hex>"
}
```

WSL 验证任务、capture、文件长度和 SHA 后响应：

```json
{
  "message_type": "result_acknowledged",
  "task_id": "task-...",
  "capture_id": "capture_001",
  "acknowledged_at": "2026-07-15T11:10:44.211803+00:00"
}
```

ACK 模型和处理代码：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/protocol/models.py:144
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/http_server.py:179
```

### 5.10 错误消息格式

```json
{
  "message_type": "error",
  "error": "invalid_request",
  "message": "具体错误"
}
```

当前错误代码包括：

```text
invalid_request
queue_full
task_not_found
result_not_ready
internal_error
not_found
```

对应 HTTP 状态为 400、404、409、500 或 503。

### 5.11 半包、粘包与完整消息示例

当前没有适用的 `struct.pack()` 包头。HTTP 使用 `Content-Length`、CRLF 和 multipart boundary 定界。

完整 reconstruct 请求示例：

```python
body = (
    b'{"task_id":"task-'
    + b"0" * 64
    + b'"}'
)
assert len(body) == 83

request = (
    b"POST /reconstruct HTTP/1.1\r\n"
    b"Host: 192.168.1.100:8000\r\n"
    b"Content-Type: application/json; charset=utf-8\r\n"
    b"Content-Length: 83\r\n"
    b"Connection: keep-alive\r\n"
    b"\r\n"
    + body
)

sock.sendall(request)
```

JSON body 十六进制：

```text
7b227461736b5f6964223a227461736b2d
3030303030303030303030303030303030303030303030303030303030303030
3030303030303030303030303030303030303030303030303030303030303030
227d
```

multipart parser 使用剩余长度、内部 buffer 和跨块 boundary 保留区处理半包和粘包：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/multipart.py:15
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/multipart.py:150
```

## 6. 模拟客户端启动命令

终端一，启动假重建 Rx：

```bash
cd /home/yp/GaussianObject/camera_system/Rx

PYTHONPATH=. /home/yp/miniconda3/envs/mvsplat/bin/python \
  -m gaussianobject_rx.server \
  --config config.simulation.yaml
```

终端二，运行模拟 Jetson：

```bash
cd /home/yp/GaussianObject/camera_system/Tx

PYTHONPATH=. /home/yp/miniconda3/envs/mvsplat/bin/python \
  -m gaussianobject_tx.client.simulate \
  --server-url http://127.0.0.1:8000 \
  --work-root simulation_runs \
  --timeout 20
```

模拟客户端：

```text
/home/yp/GaussianObject/camera_system/Tx/gaussianobject_tx/client/simulate.py:145
```

模拟客户端会：

1. 生成唯一 `capture_id`。
2. 生成 8 张逻辑相机 JPEG。
3. 将 HTTP 上传拆成 1、2、7、31、4096 等不规则字节片段。
4. 在同一个 TCP 连接连续写入 upload 和 reconstruct 请求。
5. 独立读取两个 HTTP 响应，验证粘包不会混淆。
6. 轮询重建状态。
7. 使用 Range 下载并校验 PLY。
8. 完成原子保存后发送结果 ACK。

假 baseline：

```text
/home/yp/GaussianObject/camera_system/Rx/tools/fake_baseline.py
```

## 7. 实际执行的测试

执行了用户指定的编译检查：

```bash
cd /home/yp/GaussianObject
python -m compileall camera_system
```

执行了闭环测试：

```bash
cd /home/yp/GaussianObject/camera_system/Rx

PYTHONPATH=. /home/yp/miniconda3/envs/mvsplat/bin/python \
  -m unittest -v tests.test_closed_loop
```

还执行了原有测试兼容运行，覆盖：

```text
tests/test_config.py
tests/test_models.py
tests/test_manual_staging.py
tests/test_task_manifest.py
tests/test_uploader.py
```

并实际启动了模拟 Rx 和独立模拟 Jetson CLI。

关键测试位置：

| 测试内容 | 文件和行号 |
|---|---|
| 完整上传、输入适配、PLY、ACK | `tests/test_closed_loop.py:234` |
| 两个 capture 隔离 | `tests/test_closed_loop.py:276` |
| 传输中断不产生完整 PLY | `tests/test_closed_loop.py:318` |
| 缺少图片时拒绝任务 | `tests/test_closed_loop.py:355` |
| 分段上传和同连接管线请求 | `tests/test_closed_loop.py:438` |
| 重复监听端口 | `tests/test_closed_loop.py:454` |
| stop 释放端口、线程和子进程 | `tests/test_closed_loop.py:470` |

## 8. 测试结果

编译检查：

```text
python -m compileall camera_system
通过，无语法错误
```

闭环测试：

```text
Ran 16 tests in 16.273s
OK
```

原有兼容测试：

```text
COMPATIBILITY_TESTS=34 PASS
```

实际模拟客户端结果：

```text
capture_id: sim_20260715T191043_40f9af2c
file_size: 106
SHA-256: bfb923d2c48bd8c8103813a66b52b03c582a609cab6e986db4c794891ec99f24
ACK: result_acknowledged
wire_test: fragmented upload + pipelined reconstruct
```

测试结束后确认：

- 没有遗留 `gaussianobject_rx.server` 进程。
- 没有遗留 `fake_baseline.py` 进程。
- TCP 8000 没有监听者。
- 模拟输出目录和 `/tmp` 任务目录已清理。

没有运行真实 GaussianObject/COLMAP/3DGS 训练。测试中的 PLY 由明确的假 baseline 生成。

## 9. 修改的文件

本轮新增：

```text
/home/yp/GaussianObject/camera_system/Tx/gaussianobject_tx/client/simulate.py
/home/yp/GaussianObject/camera_system/Rx/tools/fake_baseline.py
/home/yp/GaussianObject/camera_system/Rx/config.simulation.yaml
```

本轮小范围修改：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/protocol/models.py
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/protocol/__init__.py
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/http_server.py
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/task_registry.py
/home/yp/GaussianObject/camera_system/Rx/tests/test_closed_loop.py
/home/yp/GaussianObject/camera_system/Tx/pyproject.toml
/home/yp/GaussianObject/camera_system/Tx/README.md
/home/yp/GaussianObject/camera_system/Rx/pyproject.toml
/home/yp/GaussianObject/camera_system/Rx/README.md
```

没有修改 GaussianObject baseline 核心逻辑，也没有修改 multiwebcam 摄像头采集代码。

## 10. 仍需 Jetson 配合确认的内容

1. Jetson 应确认接受当前“完整任务 ZIP 上传”协议，而不是逐 `camera_id` 上传图片。
2. 当前线上协议没有独立 `camera_id` 字段；如果 Jetson 要求 WSL 按 camera 聚合，必须作为后续协议扩展处理。
3. `frame_id` 当前仅存在于 `metadata.json`，WSL 不使用它判断完整性。
4. Jetson 必须按固定 index/角度关系生成 `0.jpg`～`7.jpg`。
5. 需要确认真实 JPEG 分辨率、编码和单批大小不会超过 WSL 配置限制。
6. 需要确认 Jetson 能访问 WSL 的实际 IP 和 TCP 8000，并正确设置 Windows/WSL 防火墙和端口映射。
7. 需要确认 Jetson 是否采用新增结果 ACK；ACK 是向后兼容的可选接口，不影响旧 Tx 上传。
8. 需要确认 Jetson 结果目录权限，以及 `.part`、`fsync`、SHA-256 和原子重命名行为。
9. 当前没有 TLS、认证或设备身份字段，只适合受信任局域网。
10. 真实 GaussianObject、真实相机 JPEG 和跨机器网络仍需下一阶段实机联调。

## 附录：当前 baseline 调用与 PLY 定位

网络请求线程只做上传校验和任务入队。重建运行在有界队列的独立工作线程和子进程中：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/reconstruction.py:29
```

实际调用等价于：

```bash
SCENE_NAME=<task_id> \
RUN_TAG=<task_id> \
RUN_NAME=baseline_i2000 \
DATA_ROOT=<task_dir>/prepared \
OUT_ROOT=<task_dir>/reconstruction \
/home/yp/GaussianObject/baseline \
  <task_dir>/input/images \
  8 \
  2000
```

baseline 输入目录固定为：

```text
<task_dir>/input/images/
├── 0.jpg
├── 1.jpg
├── 2.jpg
├── 3.jpg
├── 4.jpg
├── 5.jpg
├── 6.jpg
└── 7.jpg
```

输入适配代码：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/baseline_adapter.py:27
```

预先确定的 PLY 路径为：

```text
<task_dir>/reconstruction/
  <task_id>/
    baseline_i2000_shsharp_scale101/
      point_cloud/
        iteration_2000/
          point_cloud.ply
```

路径在启动子进程前根据同一组环境变量计算，不按修改时间搜索“最新 PLY”：

```text
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/baseline_adapter.py:69
/home/yp/GaussianObject/camera_system/Rx/gaussianobject_rx/server/reconstruction.py:174
```

完成后，服务端将该文件通过 `.part`、长度限制、SHA-256 和原子重命名发布为当前任务的：

```text
<task_dir>/result/3DGS.ply
```
