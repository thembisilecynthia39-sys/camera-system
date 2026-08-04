# Jetson Tx 与 GitHub RX 协议对齐记录

核对日期：2026-07-28

核对来源：

- 仓库：`thembisilecynthia39-sys/camera-system`
- 分支：`agent/upload-rx`
- 提交：`e4268ff9e96619f0386b3d3eb55e02c39e2420a1`
- 服务源码：`Rx/gaussianobject_rx/server/`
- 协议模型：`Rx/gaussianobject_rx/protocol/models.py`
- 闭环测试：`Rx/tests/test_closed_loop.py`

## 实际协议

Jetson 主动访问 WSL 上同一个 HTTP 服务端口：

```text
GET  /health
POST /upload
POST /reconstruct
GET  /status/<task_id>
GET  /result/<task_id>/metadata
GET  /result/<task_id>            (HTTP Range)
POST /result/<task_id>/ack
```

上传为一个完整 ZIP，不是按相机逐帧发送。`task.json` 必须包含固定八个索引、
角度和文件名；multipart 的 `checksum` 与 `task.json.checksum` 一致。RX 据此
生成稳定的 `task-<checksum>`，重复上传返回相同任务。

RX 当前在 `/upload` 校验成功后自动将任务加入重建队列。`POST /reconstruct`
仍保留并具有幂等性。本地 Tx 继续调用它，用于兼容旧 RX，并通过本地任务记录
防止重复点击和不确定失败后的重复启动。

结果下载先读取 metadata，再按服务端声明的 chunk size 使用 HTTP Range。每块
校验 `X-GO-Chunk-SHA256`，完成后再校验整文件 SHA-256，通过后使用
`os.replace` 原子发布，最后发送 ACK。

## 本地实现映射

| RX 约束 | Jetson 实现 |
|---|---|
| 固定 8 角度与 `0.jpg`～`7.jpg` | `Tx_Rx/tx_rx/jetson_client/task_manifest.py` |
| `/health`、上传与幂等重建 | `Tx_Rx/tx_rx/jetson_client/uploader.py` |
| 状态、metadata、Range、ACK | `Tx_Rx/tx_rx/jetson_client/transfer.py` |
| 禁止 UI 主线程网络操作 | `camera_system_app/workers/reconstruction.py` |
| 本地任务恢复与防重复 | `camera_system_app/infrastructure/reconstruction_repository.py` |
| Jetson 本地结果路径 | `camera_system_app/application/reconstruction_service.py` |

WSL 的 `output_ply` 仅作为远端状态信息，不会传给 q3dviewer。查看器只接收
下载、校验并原子保存后的 Jetson 本地路径。

## 兼容性结论

当前 Jetson Tx 与该 RX 源码的主流程字段和端点一致。需要持续注意：

- RX 的自动入队行为不能被误解为必须依赖第二次 `/reconstruct`；
- 新旧 RX 都应保持 `/reconstruct` 幂等；
- multipart checksum 是任务 manifest checksum，不是临时 ZIP 字节哈希；
- 服务端返回的绝对 WSL 路径只能用于诊断，不得作为本地结果路径；
- RX 协议变化时，应先同步闭环测试，再发布 Jetson 客户端。

## 本次验证

本地 `Tx_Rx` 测试 56 项全部通过。另使用下载的真实
`gaussianobject_rx.server.ReceiverApplication` 和假 baseline，执行了本地
`tx_rx` 客户端到 RX 的完整闭环，上传、幂等重建、状态轮询、Range 下载、
SHA-256、原子保存及 ACK 均通过。

RX 分支自带的 `Rx/tests/test_closed_loop.py` 和
`Rx/tests/test_protocol_sync.py` 仍引用 `Tx/gaussianobject_tx`，但该提交实际只
包含 `Tx_Rx/tx_rx`，因此这两份原始测试不能在该提交上直接收集。上述真实服务
闭环使用当前仓库实际存在的 Tx 包完成，未通过复制或伪造旧包名绕过该问题。
