# 3DGSviewer 工作区

`3DGSviewer` 包含两个服务于相机采集与三维重建流程的独立 Git 仓库。

## 项目分类

### `q3dviewer/`

当前由同级 `multiwebcam` 应用集成的 Python、Qt 和 OpenGL 查看器。

- 支持点云、网格、相机画面和 3D Gaussian Splat 渲染。
- 提供可复用的查看器组件和多个图形界面命令行工具。
- Python 包代码位于 `q3dviewer/`，手动示例位于 `examples/`，文档资源位于 `docs/`。
- 虚拟环境、构建输出、缓存和 egg metadata 保持为本地生成物并由 Git 忽略。

`multiwebcam` 默认使用的集成路径为：

```text
camera_system/3DGSviewer/q3dviewer
```

如果移动此仓库，需要设置：

```bash
export MULTIWEBCAM_Q3DVIEWER_ROOT=/path/to/q3dviewer
```

安装和查看器使用方法见 [`q3dviewer/README.md`](q3dviewer/README.md)。

### `qt3d-experiments/`

独立的 Qt3D 示例仓库，包括 Gaussian Splatting、billboard、实例化渲染、边缘检测、MSAA、SSAO、线条、模板轮廓、对数深度和相对中心渲染实验。

- 每个实验继续保留在独立源码目录中。
- 截图和演示视频统一放在 `docs/media/`。
- 本地 CMake/qmake 构建目录由 Git 忽略。

各实验说明见 [`qt3d-experiments/README.md`](qt3d-experiments/README.md)。

## 工作区规则

- 不合并两个仓库，也不要在未同步修改 `multiwebcam` 集成路径时移动 `q3dviewer/`。
- 生产使用的 Python/OpenGL 查看器代码放在 `q3dviewer/`。
- 独立 Qt3D 渲染原型放在 `qt3d-experiments/`。
- 构建产物、虚拟环境、缓存和包 metadata 不纳入版本控制。
- 保留两个仓库各自的许可证和 Git 历史。
