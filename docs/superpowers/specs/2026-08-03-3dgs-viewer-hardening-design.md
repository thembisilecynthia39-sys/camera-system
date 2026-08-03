# 3DGS 查看器逻辑加固设计

## 目标

修复结果查看器在加载失败、导出异常、相机状态不一致、透明 PNG、球体混合和
大规模 Gaussian 排序上的已复现问题，同时保持现有左侧 01–06 导航、右侧浮层
Inspector、ViewerProject 信号协议和 q3dviewer 集成方式不变。

## 已确认范围

- 已有结果重载失败时，旧模型继续可用，界面状态必须恢复；首次加载失败仍显示
  空状态错误。
- 编码器一旦启动，任何后续初始化异常都必须终止编码线程和临时输出。
- `CameraPose` 进入 native orbit 前必须能表示真实的 `position`、`target`；不一致
  时采用确定性的 look-at 旋转，不能静默把相机放到另一个位置。
- 透明 PNG 渲染时清屏 alpha 为 0，普通展示和非透明导出仍为 1。
- 球体 shader 的颜色为预乘 alpha，OpenGL 混合因子必须与之匹配。
- 超过 OpenGL bitonic sort 阈值时使用 CPU 深度排序并上传索引，不能静默使用
  原始顺序。
- PLY 文件身份 hash 在加载线程计算一次，GUI 线程复用结果。

## 设计

### 加载状态

`ResultViewerPage` 根据是否已有 `_viewer_widget` 区分首次加载和重载。首次加载
可以隐藏交互控件；重载只锁定“重新加载”入口，保留旧 viewer、Inspector、时间轴
和其它查看操作。失败时恢复旧 viewer 状态并显示紧凑错误 banner。球体可用性由
adapter 的最后状态维护，加载开始不能重置为可用。

### 渲染与状态边界

`ViewerRenderController` 保留活动 encoder 的本地引用，异常路径先 abort、清理
临时输出，再清空 controller 引用。`ViewerSession` 先调用 adapter，成功后才提交
新的 immutable project；失败不污染项目状态。导出开始时通过 adapter 的透明背景
接口设置清屏 alpha，恢复回调仍负责恢复完整 viewer 状态。

### 相机与排序

adapter 抽取 `_camera_state_for_pose()`，以 `position - target` 的方向和长度为
轨道相机位置依据；已有一致旋转继续复用，不一致时构造稳定的正交 basis。标准
Gaussian 的大模型 fallback 使用 numpy 深度排序，生成带 padding 的 uint32 索引
并更新现有 SSBO；排序指标记录 fallback，而不再标记为“跳过”。

### 导出与球体显示

导出透明 PNG 时只改变当前 render pass 的 clear alpha，不改变实时查看器的背景
颜色。球体 pass 改用预乘 alpha blend，wireframe 和 solid 共用同一正确混合协议。

## 验收标准

1. 重载失败后旧模型仍可操作，首次加载失败仍保持空状态。
2. 编码器在后续初始化失败时进入终止状态，不留下运行线程。
3. 任意非共线 position/target/rotation 输入不会改变实际相机位置；失败输入不会
   污染 session project。
4. 透明 PNG 的 render target 清屏 alpha 为 0，普通 PNG/MP4 为 1。
5. 球体颜色不再被 alpha 二次衰减。
6. 大模型排序 fallback 产生有效深度顺序。
7. 相关新测试先在旧实现上失败；查看器回归测试全部通过。
