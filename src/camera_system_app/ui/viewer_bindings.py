"""Bind the result page to the existing q3dviewer implementation."""

from __future__ import annotations

import logging
from dataclasses import replace
from math import pi, radians
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QWidget,
)

from camera_system_app.application.viewer_render_plan import RenderPlan, RenderPlanError
from camera_system_app.ui.viewer_render_controller import (
    ViewerRenderController,
    ViewerRenderControllerError,
)
from camera_system_app.ui.widgets.viewer_render_dialog import ViewerRenderDialog
from camera_system_app.application.viewer_session import ViewerSession
from camera_system_app.application.viewer_playback import (
    ViewerPlayback,
    ViewerPlaybackError,
)
from camera_system_app.application.viewer_timeline import sample_timeline
from camera_system_app.domain.viewer import (
    CameraBookmark,
    CameraMode,
    DisplayMode,
    QualityPreset,
    ViewerProject,
)

from camera_system_app.infrastructure.adapters.q3dviewer_adapter import (
    Q3DViewerAdapter,
    prepare_q3dviewer,
)
from camera_system_app.infrastructure.viewer_project_store import (
    ViewerProjectFormatError,
    ViewerProjectNotFoundError,
    ViewerProjectSourceMismatchError,
    ViewerProjectStore,
)
from camera_system_app.workers import ViewerLoadWorker


class ViewerBindings(QObject):
    def __init__(self, window, project_root: Path, parent=None) -> None:
        super().__init__(parent)
        self.window = window
        self.project_root = Path(project_root)
        self._adapter = None
        self._worker = None
        self._capture_adapter = None
        self._session = None
        self._playback = ViewerPlayback(parent=self)
        self._panorama_active = False
        self._panorama_timer = QTimer(self)
        self._panorama_timer.setInterval(33)
        self._panorama_timer.timeout.connect(self._on_panorama_tick)
        self._render_controller = None
        self._render_dialog = None
        self._project_store = ViewerProjectStore()
        self._project_sidecar = None
        self._presentation_state = None
        self._pending_open_path: str | None = None
        self._logger = logging.getLogger("camera_system_app.ui.viewer")
        self._application = QApplication.instance()
        if self._application is not None:
            self._application.installEventFilter(self)
        window.destroyed.connect(self._on_window_destroyed)
        window.result_page.open_local_result_requested.connect(self.open_result)
        window.result_page.select_local_result_requested.connect(
            self.select_local_result
        )
        window.result_page.reset_view_requested.connect(self.reset_view)
        window.result_page.fit_view_requested.connect(self.fit_view)
        window.result_page.display_mode_requested.connect(self.set_display_mode)
        window.result_page.quality_requested.connect(self.set_quality)
        window.result_page.view_preset_requested.connect(self.set_view_preset)
        window.result_page.display_settings_changed.connect(
            self.set_display_settings
        )
        window.result_page.appearance_settings_changed.connect(
            self.set_appearance_settings
        )
        window.result_page.render_settings_changed.connect(
            self.set_render_settings
        )
        window.result_page.camera_mode_changed.connect(self._on_camera_mode_changed)
        window.result_page.fly_speed_changed.connect(self._on_fly_speed_changed)
        window.result_page.fov_changed.connect(self._on_fov_changed)
        window.result_page.camera_pose_changed.connect(self._on_camera_pose_changed)
        window.result_page.bookmark_add_requested.connect(
            self._on_bookmark_add_requested
        )
        window.result_page.bookmark_load_requested.connect(
            self._on_bookmark_load_requested
        )
        window.result_page.bookmark_delete_requested.connect(
            self._on_bookmark_delete_requested
        )
        window.result_page.save_requested.connect(self.save_project)
        window.result_page.save_as_requested.connect(self.save_project_as)
        window.result_page.panorama_requested.connect(self._set_panorama_active)
        window.result_page.render_requested.connect(self.start_render)
        window.result_page.presentation_requested.connect(
            lambda: self.set_presentation_mode(not self.is_presentation_mode)
        )
        self._playback.frame_changed.connect(self._on_playback_frame)
        self._playback.playback_finished.connect(self._on_playback_finished)
        window.navigation.currentRowChanged.connect(self._on_page_changed)
        window.installEventFilter(self)

    def _on_window_destroyed(self, _object=None) -> None:
        self._panorama_active = False
        self._panorama_timer.stop()
        self._detach_event_filters()

    def _detach_event_filters(self) -> None:
        application = getattr(self, "_application", None)
        if application is not None:
            application.removeEventFilter(self)
        window = getattr(self, "window", None)
        if window is not None:
            try:
                window.removeEventFilter(self)
            except RuntimeError:
                pass
        self._application = None
        self.window = None

    @property
    def is_presentation_mode(self) -> bool:
        return self._presentation_state is not None

    def set_capture_adapter(self, adapter) -> None:
        self._capture_adapter = adapter
        adapter.gpu_resources_ready.connect(self._on_gpu_resources_ready)

    def open_result(self, path: str) -> None:
        if self._worker is not None:
            return
        if not self._confirm_dirty_before_open():
            return
        if (
            self._capture_adapter is not None
            and not self._capture_adapter.result_review_gpu_ready
        ):
            self._pending_open_path = path
            self.window.statusBar().showMessage(
                "● 正在停止推理并释放 GPU，完成后自动加载 3DGS…"
            )
            return
        try:
            # Import q3dviewer/Qt classes on the GUI thread. The worker only
            # performs CPU-side PLY parsing after this point.
            prepare_q3dviewer(self.project_root)
            from q3dviewer.utils.cloud_io import load_gs_ply  # noqa: F401
        except Exception as exc:
            self._on_failed(str(exc))
            return
        self._set_panorama_active(False)
        self.window.result_page.show_loading(path)
        worker = ViewerLoadWorker(path, self.project_root, self)
        worker.loaded.connect(self._on_loaded)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(lambda current=worker: self._on_finished(current))
        self._worker = worker
        worker.start()

    def _confirm_dirty_before_open(self) -> bool:
        if self._session is None or not getattr(self._session, "is_dirty", False):
            return True
        answer = QMessageBox.warning(
            self.window,
            "查看器项目有未保存修改",
            "打开另一个 PLY 前，是否保存当前查看器项目？",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save_project() is not None
        if answer == QMessageBox.StandardButton.Discard:
            self._session.mark_clean()
            self.window.result_page.set_project_dirty(False)
            return True
        return False

    def _on_gpu_resources_ready(self, ready: bool) -> None:
        if self._adapter is not None:
            self._adapter.set_active(
                ready
                and self.window.stack.currentWidget()
                is self.window.result_page
            )
        if ready and self._pending_open_path is not None:
            path = self._pending_open_path
            self._pending_open_path = None
            self.open_result(path)

    def reset_view(self) -> None:
        if self._adapter is not None:
            self._adapter.reset_view()
            self._sync_camera_from_adapter()

    def fit_view(self) -> None:
        if self._adapter is not None:
            self._adapter.fit_scene()
            self._sync_camera_from_adapter()

    def set_view_preset(self, preset: str) -> None:
        if self._adapter is None:
            return
        try:
            self._adapter.set_view_preset(preset)
        except (TypeError, ValueError) as exc:
            self.window.statusBar().showMessage("● 标准视角无效：{}".format(exc))
            return
        self._sync_camera_from_adapter()
        self._mark_project_dirty()

    def set_display_mode(self, mode: str) -> None:
        if self._session is None:
            return
        self._session.set_display_settings(
            replace(self._session.project.display, mode=DisplayMode(mode))
        )
        self._mark_project_dirty()

    def set_quality(self, quality: str) -> None:
        if self._session is None:
            return
        self._session.set_display_settings(
            replace(self._session.project.display, quality=QualityPreset(quality))
        )
        self._mark_project_dirty()

    def set_display_settings(self, settings) -> None:
        if self._session is None:
            return
        self._session.set_display_settings(settings)
        self.window.result_page.set_camera_info_visible(settings.show_camera_info)
        if settings.background_color != self._session.project.render.background_color:
            self._session.set_render_settings(
                replace(
                    self._session.project.render,
                    background_color=settings.background_color,
                )
            )
        self._mark_project_dirty()

    def set_appearance_settings(self, settings) -> None:
        if self._session is None:
            return
        self._session.set_appearance_settings(settings)
        self._mark_project_dirty()

    def set_render_settings(self, settings) -> None:
        if self._session is None:
            return
        self._session.set_render_settings(settings)
        self._mark_project_dirty()

    def _on_camera_mode_changed(self, mode: str) -> None:
        if self._session is None:
            return
        try:
            self._session.set_camera_mode(CameraMode(mode))
        except (TypeError, ValueError) as exc:
            self.window.statusBar().showMessage("● 相机模式无效：{}".format(exc))
            return
        self._mark_project_dirty()

    def _on_fly_speed_changed(self, speed: float) -> None:
        if self._session is None:
            return
        try:
            self._session.set_fly_speed(speed)
        except (TypeError, ValueError) as exc:
            self.window.statusBar().showMessage("● 飞行速度无效：{}".format(exc))
            return
        self._mark_project_dirty()

    def _on_fov_changed(self, fov: float) -> None:
        if self._session is None:
            return
        try:
            self._session.set_camera_pose(
                replace(self._session.project.camera, fov_degrees=float(fov))
            )
        except (TypeError, ValueError) as exc:
            self.window.statusBar().showMessage("● 视场角无效：{}".format(exc))
            return
        self.window.result_page.set_current_camera_pose(self._session.project.camera)
        self._mark_project_dirty()

    def _on_camera_pose_changed(self, pose) -> None:
        if self._session is None:
            return
        try:
            applied_pose = self._session.set_camera_pose(pose)
        except (TypeError, ValueError) as exc:
            self.window.statusBar().showMessage("● 相机位置或目标无效：{}".format(exc))
            return
        applied_pose = applied_pose or self._session.project.camera
        self.window.result_page.set_current_camera_pose(applied_pose)
        self.window.result_page.set_camera_pose(applied_pose)
        self._mark_project_dirty()

    def _next_bookmark_id(self) -> str:
        used = {bookmark.bookmark_id for bookmark in self._session.project.bookmarks}
        index = 1
        while "bookmark-{}".format(index) in used:
            index += 1
        return "bookmark-{}".format(index)

    def _on_bookmark_add_requested(self, name: str) -> None:
        if self._session is None or self._adapter is None:
            return
        name = str(name).strip()
        if not name:
            self.window.statusBar().showMessage("● 请输入相机书签名称")
            return
        try:
            pose = self._adapter.get_camera_pose()
            bookmark = CameraBookmark(self._next_bookmark_id(), name, pose)
            bookmarks = self._session.project.bookmarks + (bookmark,)
            self._session.set_bookmarks(bookmarks)
            self.window.result_page.set_bookmarks(bookmarks)
        except (TypeError, ValueError) as exc:
            self.window.statusBar().showMessage("● 无法保存相机书签：{}".format(exc))
            return
        self._mark_project_dirty()

    def _on_bookmark_load_requested(self, bookmark_id: str) -> None:
        if self._session is None:
            return
        bookmark = next(
            (
                item
                for item in self._session.project.bookmarks
                if item.bookmark_id == bookmark_id
            ),
            None,
        )
        if bookmark is None:
            return
        applied_pose = self._session.set_camera_pose(bookmark.pose)
        applied_pose = applied_pose or self._session.project.camera
        self.window.result_page.set_current_camera_pose(applied_pose)
        self.window.result_page.set_camera_pose(applied_pose)
        self._mark_project_dirty()

    def _on_bookmark_delete_requested(self, bookmark_id: str) -> None:
        if self._session is None:
            return
        bookmarks = tuple(
            item
            for item in self._session.project.bookmarks
            if item.bookmark_id != bookmark_id
        )
        if len(bookmarks) == len(self._session.project.bookmarks):
            return
        self._session.set_bookmarks(bookmarks)
        self.window.result_page.set_bookmarks(bookmarks)
        self._mark_project_dirty()

    def _on_timeline_changed(self, timeline) -> None:
        if self._session is None:
            return
        self._session.set_timeline(timeline)
        self._playback.set_timeline(timeline)
        self._mark_project_dirty()

    def _on_frame_selected(self, frame: int) -> None:
        if self._session is None:
            return
        try:
            self._playback.set_frame(frame)
        except ViewerPlaybackError as exc:
            self._logger.warning("Cannot select viewer frame: %s", exc)

    def _on_playback_frame(self, frame: int) -> None:
        if self._session is None or self._adapter is None:
            return
        try:
            pose = sample_timeline(self._session.project.timeline, frame)
        except Exception as exc:
            self._logger.warning("Cannot sample viewer timeline: %s", exc)
            return
        self._adapter.set_camera_pose(pose)

    def play(self) -> None:
        if self._session is None or not self._session.project.timeline.shots:
            self.window.statusBar().showMessage("● 请先在 Camera Director 中添加镜头段")
            return
        try:
            self._playback.play()
        except ViewerPlaybackError as exc:
            self.window.statusBar().showMessage("● 漫游播放失败：{}".format(exc))

    def pause(self) -> None:
        self._playback.pause()

    def stop(self) -> None:
        self._playback.stop()

    def _set_panorama_active(self, active: bool) -> None:
        active = bool(active)
        if getattr(self, "window", None) is None:
            self._panorama_active = False
            self._panorama_timer.stop()
            return
        if active:
            if self._adapter is None or self._session is None:
                self.window.result_page.set_panorama_playing(False)
                self.window.statusBar().showMessage("● 请先加载一个 3DGS 结果")
                return
            if self._panorama_active:
                return
            self._panorama_active = True
            self.window.result_page.set_panorama_playing(True)
            self._panorama_timer.start()
            self.window.statusBar().showMessage("● 自动环视中 · 20 秒一周")
            return

        was_active = self._panorama_active
        self._panorama_active = False
        self._panorama_timer.stop()
        self.window.result_page.set_panorama_playing(False)
        if was_active:
            end_interaction = getattr(self._adapter, "end_interaction", None)
            if callable(end_interaction):
                try:
                    end_interaction()
                except Exception:
                    self._logger.exception("Cannot end panorama interaction cleanly")
            try:
                self._sync_camera_from_adapter()
            except Exception as exc:
                self._logger.exception("Cannot commit panorama camera")
                self.window.statusBar().showMessage(
                    "● 无法保存环视相机：{}".format(exc)
                )

    def _on_panorama_tick(self) -> None:
        if not self._panorama_active or self._adapter is None:
            return
        delta_yaw = (2.0 * pi / 20.0) * (
            self._panorama_timer.interval() / 1000.0
        )
        try:
            pose = self._adapter.orbit(delta_yaw=delta_yaw)
        except Exception as exc:
            self._logger.exception("Automatic panorama failed")
            self._set_panorama_active(False)
            self.window.statusBar().showMessage("● 自动环视失败：{}".format(exc))
            return
        if pose is not None:
            self.window.result_page.set_current_camera_pose(pose)

    def start_render(self, output_path=None):
        if self._session is None or self._adapter is None:
            self.window.statusBar().showMessage("● 请先加载一个 3DGS 结果")
            return None
        if output_path is None:
            output_path = self._select_render_output()
        if not output_path:
            return None
        self._set_panorama_active(False)
        try:
            plan = RenderPlan.from_project(self._session.project, output_path)
        except RenderPlanError as exc:
            self.window.statusBar().showMessage("● 无法开始导出：{}".format(exc))
            return None
        controller = self._ensure_render_controller()
        metrics = {}
        try:
            metrics = self._session.performance_metrics()
        except Exception as exc:
            self._logger.debug("Viewer metrics unavailable before render: %s", exc)
        self._render_dialog = ViewerRenderDialog(
            plan,
            metrics=metrics,
            parent=self.window,
        )
        self._render_dialog.cancel_requested.connect(controller.cancel)
        self._render_dialog.show()
        self.window.result_page.set_rendering(True)
        try:
            controller.start(plan, restore_callback=self._restore_after_render)
        except ViewerRenderControllerError as exc:
            self.window.result_page.set_rendering(False)
            self._render_dialog.set_error(str(exc))
            self.window.statusBar().showMessage("● 导出启动失败：{}".format(exc))
            return None
        self.window.statusBar().showMessage(
            "● 正在导出 {} 帧到 {}".format(plan.frame_count, plan.output_path)
        )
        return plan

    def _ensure_render_controller(self):
        if self._render_controller is not None:
            return self._render_controller
        self._render_controller = ViewerRenderController(
            self._adapter,
            parent=self.window,
        )
        self._render_controller.progress_changed.connect(self._on_render_progress)
        self._render_controller.finished.connect(self._on_render_finished)
        self._render_controller.failed.connect(self._on_render_failed)
        self._render_controller.cancelled.connect(self._on_render_cancelled)
        return self._render_controller

    def _select_render_output(self):
        if self._session is None:
            return None
        settings = self._session.project.render
        source = Path(self._session.project.source_path or "scene.ply")
        if settings.output_kind.value == "png_sequence":
            return QFileDialog.getExistingDirectory(
                self.window,
                "选择 PNG 序列输出目录",
                str(source.parent),
            ) or None
        suffix = ".png" if settings.output_kind.value == "png" else ".mp4"
        selected, _ = QFileDialog.getSaveFileName(
            self.window,
            "选择 3DGS 展示输出路径",
            str(source.with_suffix(suffix)),
            "PNG (*.png);;MP4 视频 (*.mp4);;所有文件 (*)",
        )
        return selected or None

    def _on_render_progress(self, progress: float) -> None:
        if self._render_dialog is not None:
            self._render_dialog.set_progress(progress)

    def _on_render_finished(self, output_path) -> None:
        self.window.result_page.set_rendering(False)
        if self._render_dialog is not None:
            self._render_dialog.set_finished(output_path)
        self.window.statusBar().showMessage("● 3DGS 展示输出已完成：{}".format(output_path))

    def _on_render_failed(self, message: str) -> None:
        self.window.result_page.set_rendering(False)
        if self._render_dialog is not None:
            self._render_dialog.set_error(message)
        self.window.statusBar().showMessage("● 3DGS 展示输出失败：{}".format(message))

    def _on_render_cancelled(self) -> None:
        self.window.result_page.set_rendering(False)
        if self._render_dialog is not None:
            self._render_dialog.status_label.setText("已取消导出，未发布不完整文件")
        self.window.statusBar().showMessage("● 3DGS 展示输出已取消")

    def _restore_after_render(self) -> None:
        if self._session is None or self._adapter is None:
            return
        self._adapter.set_display_settings(self._session.project.display)
        self._adapter.set_appearance_settings(self._session.project.appearance)
        self._adapter.set_camera_pose(self._session.project.camera)
        set_camera_mode = getattr(self._adapter, "set_camera_mode", None)
        if callable(set_camera_mode):
            set_camera_mode(self._session.project.camera_mode)
        set_fly_speed = getattr(self._adapter, "set_fly_speed", None)
        if callable(set_fly_speed):
            set_fly_speed(self._session.project.fly_speed)

    def _on_playback_finished(self) -> None:
        self.window.statusBar().showMessage("● 相机漫游预览完成")

    def _mark_project_dirty(self) -> None:
        if self._session is not None:
            suffix = " · 项目有未保存修改" if self._session.is_dirty else ""
            self.window.result_page.set_project_dirty(self._session.is_dirty)
            self.window.statusBar().showMessage("● 3DGS 查看器就绪" + suffix)

    def _sync_camera_from_adapter(self) -> None:
        if self._session is not None and self._adapter is not None:
            pose = self._adapter.get_camera_pose()
            self._session.record_camera_pose(pose)
            self.window.result_page.set_current_camera_pose(pose)
            self.window.result_page.set_camera_pose(pose)
            self._mark_project_dirty()

    def _load_project_state(
        self,
        source_path: Path,
        fallback: ViewerProject,
        *,
        allow_stale: bool = False,
        prompt_stale: bool = False,
        source_identity=None,
    ) -> ViewerProject:
        sidecar = self._project_store.default_path(source_path)
        self._project_sidecar = sidecar
        if not sidecar.is_file():
            return fallback
        try:
            return self._project_store.load(
                sidecar,
                source_path=source_path,
                allow_source_mismatch=allow_stale,
                source_identity=source_identity,
            )
        except ViewerProjectSourceMismatchError:
            if prompt_stale:
                answer = QMessageBox.question(
                    self.window,
                    "查看器项目源文件已变化",
                    "旁车项目记录的源文件与当前 PLY 不一致。仍然加载旧的相机和显示设置吗？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer == QMessageBox.StandardButton.Yes:
                    return self._project_store.load(
                        sidecar,
                        source_path=source_path,
                        allow_source_mismatch=True,
                        source_identity=source_identity,
                    )
            self._logger.warning("Viewer sidecar source identity mismatch: %s", sidecar)
            return fallback
        except (ViewerProjectNotFoundError, ViewerProjectFormatError) as exc:
            self._logger.warning("Viewer sidecar was not applied: %s", exc)
            return fallback

    def save_project(self):
        if self._session is None:
            return None
        path = self._project_sidecar
        if path is None:
            path = self._project_store.default_path(self._session.project.source_path)
        saved = self._project_store.save(self._session.project, path)
        self._project_sidecar = saved
        self._session.mark_clean()
        self.window.result_page.set_project_dirty(False)
        self.window.statusBar().showMessage("● 3DGS 查看器项目已保存：{}".format(saved))
        return saved

    def save_project_as(self):
        if self._session is None:
            return None
        selected, _ = QFileDialog.getSaveFileName(
            self.window,
            "保存 3DGS 查看器项目",
            str(self._project_sidecar or "scene.splatview.json"),
            "3DGS 查看器项目 (*.splatview.json)",
        )
        if not selected:
            return None
        self._project_sidecar = Path(selected)
        return self.save_project()

    def set_presentation_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled and self._presentation_state is None:
            sidebar = self.window.findChild(type(self.window.centralWidget()), "sidebar")
            if sidebar is None:
                from PySide6.QtWidgets import QFrame

                sidebar = self.window.findChild(QFrame, "sidebar")
            self._presentation_state = {
                "sidebar": sidebar,
                "sidebar_visible": bool(sidebar and sidebar.isVisible()),
                "status_visible": self.window.statusBar().isVisible(),
                "fullscreen": self.window.isFullScreen(),
                "camera_info_visible": self.window.result_page.camera_info_visible,
            }
            if sidebar is not None:
                sidebar.hide()
            self.window.statusBar().hide()
            self.window.showFullScreen()
            self.window.result_page.set_camera_info_visible(True)
            self.window.result_page.set_presentation_mode(True)
            return
        if not enabled and self._presentation_state is not None:
            state = self._presentation_state
            self._presentation_state = None
            if state["fullscreen"]:
                self.window.showFullScreen()
            else:
                self.window.showNormal()
            sidebar = state["sidebar"]
            if sidebar is not None:
                sidebar.setVisible(state["sidebar_visible"])
            self.window.statusBar().setVisible(state["status_visible"])
            self.window.result_page.set_camera_info_visible(
                state["camera_info_visible"]
            )
            self.window.result_page.set_presentation_mode(False)

    def _is_viewer_key_target(self, watched) -> bool:
        window = getattr(self, "window", None)
        if window is None:
            return False
        try:
            if watched is window:
                return True
            if not isinstance(watched, QWidget):
                return False
            return watched is window.result_page or window.result_page.isAncestorOf(watched)
        except RuntimeError:
            # A QApplication-level filter can receive queued events after a
            # test/window has scheduled its native object for destruction.
            return False

    def _orbit_from_keyboard(self, delta_yaw=0.0, delta_pitch=0.0) -> bool:
        if self._adapter is None:
            return False
        orbit = getattr(self._adapter, "orbit", None)
        if not callable(orbit):
            return False
        try:
            pose = orbit(delta_yaw=delta_yaw, delta_pitch=delta_pitch)
        except Exception as exc:
            self._logger.exception("Keyboard orbit failed")
            self.window.statusBar().showMessage("● 视角环视失败：{}".format(exc))
            return True
        if pose is not None:
            if self._session is not None:
                try:
                    self._session.record_camera_pose(pose)
                except (TypeError, ValueError) as exc:
                    self.window.statusBar().showMessage(
                        "● 无法记录环视相机：{}".format(exc)
                    )
                    return True
            self.window.result_page.set_current_camera_pose(pose)
            self.window.result_page.set_camera_pose(pose)
            self._mark_project_dirty()
        return True

    def eventFilter(self, watched, event):
        if (
            self._is_viewer_key_target(watched)
            and event.type() == QEvent.Type.KeyPress
        ):
            if self.is_presentation_mode and event.key() == Qt.Key.Key_Escape:
                self.set_presentation_mode(False)
                return True
            focus = QApplication.focusWidget()
            control_focus = isinstance(
                focus,
                (QAbstractButton, QLineEdit, QAbstractSpinBox, QComboBox),
            )
            if not control_focus:
                if event.key() == Qt.Key.Key_Left:
                    return self._orbit_from_keyboard(delta_yaw=-radians(5.0))
                if event.key() == Qt.Key.Key_Right:
                    return self._orbit_from_keyboard(delta_yaw=radians(5.0))
                if event.key() == Qt.Key.Key_Up:
                    return self._orbit_from_keyboard(delta_pitch=radians(5.0))
                if event.key() == Qt.Key.Key_Down:
                    return self._orbit_from_keyboard(delta_pitch=-radians(5.0))
        return super().eventFilter(watched, event)

    def select_local_result(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self.window,
            "选择本地 Gaussian Splat PLY",
            str(self.window.result_page.result_root),
            "Gaussian Splat PLY (*.ply);;所有文件 (*)",
        )
        if not selected:
            return
        self.window.result_page.set_result_available(selected)
        self.open_result(selected)

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        self._set_panorama_active(False)
        self._detach_event_filters()
        if self._render_controller is not None and self._render_controller.is_running:
            self._render_controller.cancel()
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            if not self._worker.wait(timeout_ms):
                self._logger.error("PLY load worker did not stop within %sms", timeout_ms)
                return False
        if self._adapter is not None:
            self._adapter.release()
        return True

    def _on_loaded(self, payload, path: str) -> None:
        previous_adapter = self._adapter
        previous_session = self._session
        previous_sidecar = self._project_sidecar
        adapter = previous_adapter
        adapter_snapshot = None
        created_adapter = False
        try:
            gaussians, bounds, source_size, source_sha256 = payload
            if adapter is None:
                adapter = Q3DViewerAdapter(self.project_root, self)
                self._adapter = adapter
                created_adapter = True
                adapter.rendering_failed.connect(self._on_failed)
                adapter.sphere_availability_changed.connect(
                    self._on_sphere_availability_changed
                )
                adapter.widget.interaction_finished.connect(
                    self._sync_camera_from_adapter
                )
                adapter.set_active(
                    self.window.stack.currentWidget() is self.window.result_page
                )
            else:
                snapshot_scene = getattr(adapter, "snapshot_scene", None)
                if callable(snapshot_scene):
                    adapter_snapshot = snapshot_scene()
            count = adapter.set_gaussians(gaussians, bounds=bounds)
            source = Path(path).resolve()
            fallback = ViewerProject(
                source_path=str(source),
                source_size=source_size,
                source_sha256=source_sha256,
                camera=adapter.get_camera_pose(),
            )
            project = self._load_project_state(
                source,
                fallback,
                prompt_stale=True,
                source_identity=(source_size, source_sha256),
            )
            session = ViewerSession(adapter, project)
            session.apply_project(project)
            self._session = session
            self.window.result_page.set_project_dirty(False)
            self._ensure_render_controller()
            self._playback.set_timeline(project.timeline)
            self.window.result_page.set_current_camera_pose(project.camera)
            self.window.result_page.set_camera_pose(project.camera)
            self.window.result_page.set_camera_mode(project.camera_mode)
            self.window.result_page.set_fly_speed(project.fly_speed)
            self.window.result_page.set_bookmarks(project.bookmarks)
            self.window.result_page._inspector.set_display_settings(project.display)
            self.window.result_page.set_camera_info_visible(project.display.show_camera_info)
            self.window.result_page._inspector.set_appearance_settings(project.appearance)
            self.window.result_page._inspector.set_render_settings(project.render)
            self.window.result_page.set_viewer_widget(
                adapter.widget, path, count
            )
            self.window.statusBar().showMessage(
                "● q3dviewer 已加载本地结果：{}".format(path)
            )
        except Exception as exc:
            self._session = previous_session
            self._project_sidecar = previous_sidecar
            if created_adapter and adapter is not None:
                try:
                    adapter.release()
                except Exception:
                    self._logger.exception("Cannot release failed q3dviewer adapter")
                self._adapter = previous_adapter
            elif adapter_snapshot is not None and adapter is previous_adapter:
                restore_scene = getattr(adapter, "restore_scene", None)
                if callable(restore_scene):
                    try:
                        restore_scene(adapter_snapshot)
                    except Exception:
                        self._logger.exception("Cannot restore previous q3dviewer scene")
            self._logger.exception("Cannot initialize embedded q3dviewer")
            self._on_failed(str(exc))

    def _on_failed(self, message: str) -> None:
        self._logger.error("q3dviewer load/render failed: %s", message)
        self.window.result_page.show_load_error(message)
        self.window.statusBar().showMessage("● 结果加载失败：{}".format(message))

    def _on_sphere_availability_changed(self, available: bool, error: str) -> None:
        self.window.result_page.set_sphere_modes_available(available, error)
        if not available:
            if self._session is not None and self._session.project.display.mode is not DisplayMode.STANDARD:
                self._session.set_display_settings(
                    replace(
                        self._session.project.display,
                        mode=DisplayMode.STANDARD,
                    )
                )
                self._mark_project_dirty()
            self.window.statusBar().showMessage(
                "● 外接球渲染不可用，已回退标准 Gaussian：{}".format(
                    error or "未知 shader 错误"
                )
            )

    def _on_finished(self, worker) -> None:
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

    def _on_page_changed(self, index: int) -> None:
        self._set_panorama_active(False)
        if self._adapter is None:
            return
        active_page = (
            self.window.pages[index]
            if 0 <= index < len(self.window.pages)
            else None
        )
        gpu_ready = (
            self._capture_adapter is None
            or self._capture_adapter.result_review_gpu_ready
        )
        self._adapter.set_active(
            active_page is self.window.result_page and gpu_ready
        )
