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

## 五、3DGS Viewer Studio：漫游、外接球和展示输出

打开 PLY 后，“结果查看”会显示 Studio 工具栏、右侧 Inspector 和底部
Camera Director 时间轴。

### 视图和外接球

- `Gaussian`：标准 3DGS 椭圆 splat，适合最终画面；
- `外接球线框`：显示每个 Gaussian 原始椭圆外接球的线框；
- `外接球实体`：使用屏幕空间球体显示外接球实体；
- `Gaussian + 球体`：标准 splat 与半透明球壳叠加，适合检查覆盖范围。

球半径始终按原始 Gaussian 的有效 scale 计算：

```text
radius = sigma_multiplier × max(scale.x, scale.y, scale.z)
```

默认 `sigma_multiplier = 3.0`。它是显示派生值，不会修改 PLY，也不会为每个
Gaussian 创建独立 Qt/网格对象。右侧“视图”面板可调整透明度、线宽和质量预设；
交互时默认使用预览数量，勾选“交互时显示全部外接球”会加载每一个球体实例，适合
检查覆盖范围但可能增加 GPU 压力。模式切换不需要重新加载 PLY。如果当前 GPU/驱动
无法编译球体 shader，球体选项会变灰，查看器会自动回退到标准 Gaussian。

### Camera Director 漫游

1. 右键拖动环视、左键拖动平移、滚轮缩放到第一个视角。
2. 在时间轴点击“添加镜头”，会记录当前视角。
3. 移动到下一个视角，再点击“添加镜头”；前一段会自动连接到新视角。
4. 用时间轴滑块逐帧检查，使用“复制、删除、←、→”整理镜头段。
5. 在 Inspector 的“相机”面板切换 Orbit/Fly，调整飞行速度；可保存命名书签并
   随时跳转或删除。
6. 点击“播放”预览，点击“停止”回到当前时间轴范围的第一帧。窄窗口下工具栏的
   “参数”和“时间轴”按钮会互斥显示两个面板，避免压缩 3D 视口。

时间轴按固定 FPS 采样，最终输出与预览使用同一套位置、目标点和四元数球面
插值，因此同一项目可以重复生成相同帧数的结果。Inspector 中也可以直接编辑相机
位置 XYZ、观察目标 XYZ 和 FOV；背景颜色在“视图”面板编辑。`Escape` 会退出全屏
演示模式。

Inspector 的“外观”参数会同时作用于交互预览和最终导出；锐化在最终 CPU 后处理中
执行，以保证导出画面可重复。

### PNG/MP4 展示输出

在 Inspector 的“渲染”面板设置分辨率、FPS、输出格式和透明背景，再点击工具栏
“导出”：

- PNG：导出当前相机的一张高质量静帧；
- PNG 序列：按时间轴导出完整帧序列，适合后期合成；
- MP4：按时间轴导出视频；透明背景仅对 PNG 有效，MP4 使用配置的背景色。

输出 FPS 会对时间轴重新采样，避免编辑预览 FPS 与最终视频 FPS 不一致造成时长漂移。
导出对话框会显示 Gaussian 数量、估算 GPU 数据、帧缓冲内存预算和编码后端。导出时
OpenGL 只在 GUI 线程渲染，编码在后台线程进行；队列满时会等待，不丢帧。
只有全部帧完成后才发布最终文件，取消或失败不会留下可被误认为完成的半成品。
Jetson 优先使用 `nvv4l2h264enc` GStreamer 路径，不可用时使用 PyAV H.264。

### 项目侧车

保存后的查看器项目默认写在 PLY 同目录的 `scene.splatview.json`。它保存相机、
显示模式、外接球参数（包括“全部实例”）、相机模式/速度/书签、外观、时间轴和渲染设置，使用 PLY 文件大小与 SHA-256
校验源文件身份。源文件变化后不会静默套用旧相机；可选择加载旧设置或回到默认视角。
侧车写入采用临时文件加原子替换，永远不会覆盖源 PLY。

## 六、退出与故障处理

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
