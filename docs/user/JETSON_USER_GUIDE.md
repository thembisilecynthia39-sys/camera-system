# Camera System Jetson 用户操作说明

## 一、安装

1. 将 `camera-system-0.1.0-jetson-arm64.tar.gz` 复制到 Jetson。
2. 校验压缩包：

   ```bash
   sha256sum -c camera-system-0.1.0-jetson-arm64.tar.gz.sha256
   ```

3. 解压并安装：

   ```bash
   tar -xzf camera-system-0.1.0-jetson-arm64.tar.gz
   cd camera-system-0.1.0-jetson-arm64
   ./scripts/jetson/install.sh
   ```

安装过程不会修改 `~/.bashrc`。它会安装系统依赖、创建
`.venv-jetson`、初始化用户配置，并在桌面和应用菜单安装图标。

## 二、配置 WSL 服务

编辑：

```text
~/.config/camera-system/settings.yaml
```

将 `wsl_service_url` 改为 Jetson 能访问的 WSL/服务器地址，例如：

```yaml
wsl_service_url: http://192.168.1.100:8000
```

不要填写 `127.0.0.1` 或 WSL 内部文件路径。Jetson 只通过 HTTP 获取结果，
结果会保存到 Jetson 本地 `result_root` 后再交给查看器。

在 WSL 端确认 RX 已启动：

```bash
Rx status
```

## 三、启动与诊断

- 双击桌面的“边端 3DGS 重建”图标；
- 或从终端运行 `./scripts/jetson/run.sh`；
- 源码/应用目录启动也支持：

  ```bash
  PYTHONPATH=src python -m camera_system_app
  ```

环境诊断：

```bash
./scripts/jetson/diagnose.sh
```

桌面图标右键选择“环境诊断”会弹出同一份报告。无摄像头或 RX 离线时，主界面
仍可打开；对应页面会显示提示。

## 四、完整操作流程

1. 在“采集工作台”启动摄像头。
2. 按界面引导依次完成 `0°、45°、90°、135°、180°、225°、270°、315°`。
3. 八个视角完成后进入“传输与重建”。
4. 点击“上传并重建”。传输期间按钮会禁用，页面显示上传、重建和下载进度。
5. 完成后点击“打开结果”，在内嵌查看器中旋转、缩放、平移或重置视角。
6. “历史任务”可查看任务状态、重试失败任务或重新打开已下载结果。
7. “日志和环境诊断”用于查看错误详情。

## 五、退出与故障处理

正常关闭主窗口即可。应用会停止摄像头、后台网络任务并释放 OpenGL 资源。

常见问题：

- “GStreamer 不可用”：移除 pip 安装的 `opencv-python*`，重新运行安装脚本，
  确保使用 `/usr/lib/python3/dist-packages/cv2`。
- “could not load xcb”：运行诊断，确认 Qt 插件目录和 `libxcb-xinerama0` 已安装。
- WSL 连接失败：确认服务监听 `0.0.0.0:8000`、IP 可达、防火墙放行。
- PLY 校验失败：保留 `.part`/日志信息并重试；只有 SHA-256 成功的文件才会原子发布。
- 黑屏或 OpenGL 错误：在 Jetson 本机桌面会话运行，不要只在无 X11 的 SSH 会话测试。

日志默认位于：

```text
~/.local/state/camera-system/logs/camera-system.log
```
