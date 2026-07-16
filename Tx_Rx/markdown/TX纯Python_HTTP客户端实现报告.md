# Jetson TX 纯 Python HTTP 客户端实现报告

> [!NOTE]
> 文档性质：当前实现和测试验证快照。它面向开发审查，不替代 [`Tx_Rx/README.md`](../README.md)中的安装与使用说明。报告中的模拟 HTTP 测试不等同于真实 Jetson/WSL 跨设备联调。

## 1. 修改文件

- `tx_rx/config.py`：增加结果目录、请求/轮询/重建/下载超时和 PLY 大小上限。
- `config.yaml`：补全纯 Python 客户端配置，不再使用 `127.0.0.1`。
- `config.example.yaml`：补全示例配置。
- `tx_rx/protocol/models.py`：补全上传、重建、状态、PLY metadata 和 ACK 响应模型。
- `tx_rx/protocol/__init__.py`：导出新增协议模型。
- `tx_rx/jetson_client/uploader.py`：multipart `checksum` 使用已确认的任务文件集合摘要，严格验证响应，立即持久化 `task_id`。
- `tx_rx/jetson_client/transfer.py`：新增轮询、metadata、Range 下载、ACK 和 CLI 闭环。
- `tx_rx/jetson_client/__init__.py`：保持包导入无 CLI 重复加载副作用。
- `README.md`：增加 CLI 使用和 Python 3 测试命令。
- `tests/test_uploader.py`：按真实上传/重建响应协议更新测试。
- `tests/test_http_protocol.py`：新增最小真实 HTTP WSL 模拟服务端及闭环/失败测试。

## 2. multipart checksum 位置

`tx_rx/jetson_client/uploader.py` 的 `upload_staged_task()`：

```text
创建 ZIP
→ multipart checksum=package.checksum
```

multipart `checksum` 与 `task.json.checksum` 均使用 `task_manifest.py` 中 `_task_checksum()` 生成的任务文件集合摘要，符合本次确认的 WSL 协议。

## 3. task_id 持久化位置

`tx_rx/jetson_client/uploader.py:63-65`在上传响应验证成功后立即调用 `_write_upload_receipt()`，然后才请求 `/reconstruct`。

回执位置：

```text
<staging_dir>/upload.json
```

保存字段：

```text
task_id
capture_id
server_url
checksum
upload_response
created_at
```

写入使用临时文件、`flush`、`fsync` 和 `os.replace`。即使 `/reconstruct` 失败，上传回执仍然保留。

## 4. 状态轮询接口

公共函数：

```python
poll_status(task_id, capture_id, config, session=None,
            cancel_check=None, progress_callback=None)
```

位置：`tx_rx/jetson_client/transfer.py:29`。

请求：

```http
GET /status/<task_id>
```

支持 `queued`、`running_colmap`、`running_3dgs`、`finished`、`failed`，并支持请求超时、总超时、可中断等待和外部取消检查。`progress` 可为整数或浮点数，服务器额外字段会安全忽略。

## 5. PLY 下载接口

- `get_ply_metadata()`：`tx_rx/jetson_client/transfer.py:64`。
- `download_ply()`：`tx_rx/jetson_client/transfer.py:97`。
- `acknowledge_result()`：`tx_rx/jetson_client/transfer.py:167`。

Range 下载验证：

- HTTP 206。
- `Content-Range` 和 `Content-Length`。
- `X-GO-Task-ID`、`X-GO-Capture-ID`。
- `X-GO-Chunk-Index`、`X-GO-Chunk-Count`。
- `X-GO-Chunk-SHA256`。
- `X-GO-File-Size`、`X-GO-SHA256`。
- 每块实际接收长度和 SHA-256。
- 整文件长度和流式 SHA-256。

下载过程流式写入 `.part`，不会把整个 PLY 读入内存。完整校验后使用 `os.replace` 原子发布。失败或取消时保留 `.part` 便于诊断，但不会生成正式 `.ply`。

已存在的正式文件若长度和 SHA-256 一致，则幂等返回，不重复下载。

## 6. result_root

配置默认值：

```yaml
result_root: /home/jetson/3DGS/results
```

最终路径：

```text
<result_root>/<capture_id>/<task_id>/3DGS.ply
```

临时路径：

```text
<result_root>/<capture_id>/<task_id>/3DGS.ply.part
```

## 7. CLI 启动命令

首先将 `config.yaml` 中的 `server_url` 改为 WSL 实际 IP，再执行：

```bash
python3 -m tx_rx.jetson_client.transfer \
  --capture-dir <capture目录> \
  --config config.yaml
```

CLI 链路：

```text
构建任务
→ 创建 ZIP
→ 上传并立即保存 task_id
→ 启动重建
→ 轮询状态
→ 获取 PLY metadata
→ Range 下载和校验
→ 原子保存
→ ACK
```

输出包含 `capture_id`、`task_id`、上传状态、stage、progress、下载字节进度、最终路径、SHA-256 和 ACK 状态。

## 8. 实际测试命令

```bash
python3 -m compileall -q .
pytest -q
python3 -m tx_rx.jetson_client.transfer --help
```

真实 HTTP 模拟测试会在 `127.0.0.1` 随机端口启动最小 WSL 服务端，实际经过 multipart、JSON、HTTP Range 和 ACK，没有自创第二套测试协议。

## 9. 实际测试结果

```text
python3 -m compileall -q . : PASS
pytest -q                    : 53 passed in 7.31s
```

已覆盖：

- multipart `checksum` 与 `task.json.checksum` 均为任务文件集合摘要。
- 上传响应验证和立即持久化。
- `/reconstruct` 响应解析。
- 状态轮询。
- PLY metadata。
- 单块和多块 Range。
- `Range` 和带引号的 `If-Range`。
- 分块/整文件 SHA-256 错误。
- `file_size`、`capture_id`、`task_id` 错误。
- 下载截断、取消和 `.part` 策略。
- 原子重命名、ACK 和重复下载幂等。
- 请求超时和主动取消错误。

## 10. 尚未验证内容

- 尚未与真实 WSL `0.0.0.0:8000` 服务进行设备间联调。
- 尚未下载真实大型 GaussianObject PLY；当前用小型模拟 PLY 验证协议和流式代码路径。
- 尚未运行真实 GaussianObject，符合本次限制。
- 尚未接入 Qt UI 或多摄像头工程，符合本次限制。
- `config.yaml` 已配置为已确认的 WSL 地址 `http://10.150.14.62:8000`。

## 11. 从图片池选择任意 8 张照片

`capture_dir/images` 可以包含任意数量的照片。用户通过 CLI 重复传入 8 个 `--image <文件名>`，显式选择要上传的 8 张 `.jpg`，不需要 `metadata.csv` 含有对应角度记录。

8 个 `--image` 的参数顺序就是 index 0～7 的映射顺序，并依次对应固定角度 `0,45,90,135,180,225,270,315`。会拒绝少于/多于 8 张、重复文件名、非 `.jpg`、路径穿越或不存在的文件。

未显式选择时，仍保留原有兼容行为：恰好 8 张时按文件名映射，多轮采集目录则使用 `metadata.csv` 选取。
