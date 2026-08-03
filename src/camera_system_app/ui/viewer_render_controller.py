"""GUI-thread render scheduler with explicit encoder backpressure."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, QObject, Signal

from camera_system_app.application.viewer_appearance import apply_appearance
from camera_system_app.application.viewer_render_plan import RenderPlan, RenderPlanError
from camera_system_app.domain.viewer import AppearanceSettings
from camera_system_app.infrastructure.viewer_encoder import (
    EncoderBackpressureError,
    EncoderConfig,
    EncoderError,
    EncoderState,
    FrameEncoder,
)


class ViewerRenderControllerError(RuntimeError):
    """Raised when a final render cannot be started or scheduled."""


class ViewerRenderController(QObject):
    """Render one frame per event-loop turn and never advance on backpressure."""

    started = Signal()
    progress_changed = Signal(float)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    state_changed = Signal(str)

    def __init__(self, adapter=None, encoder_factory=FrameEncoder, parent=None):
        super().__init__(parent)
        self.adapter = adapter
        self.encoder_factory = encoder_factory
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._render_next)
        self._plan = None
        self._encoder = None
        self._frame_index = 0
        self._pending_frame = None
        self._running = False
        self._finalizing = False
        self._error = None
        self._restore_callback = None
        self._previous_appearance = None
        self._progress = 0.0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def plan(self):
        return self._plan

    @property
    def current_frame(self) -> int:
        return self._frame_index

    @property
    def progress(self) -> float:
        return self._progress

    @property
    def error(self):
        return self._error

    def start(self, plan: RenderPlan, restore_callback=None) -> None:
        if self._running:
            raise ViewerRenderControllerError("已有一个渲染任务正在运行")
        if not isinstance(plan, RenderPlan):
            raise ViewerRenderControllerError("plan must be a RenderPlan value")
        if self.adapter is None:
            raise ViewerRenderControllerError("渲染器 adapter 尚未连接")
        self._plan = plan
        self._restore_callback = restore_callback
        self._frame_index = 0
        self._pending_frame = None
        self._finalizing = False
        self._error = None
        self._previous_appearance = getattr(
            self.adapter, "appearance_settings", None
        )
        self._set_progress(0.0)
        try:
            encoder_config = EncoderConfig(
                output_path=plan.output_path,
                width=plan.render.width,
                height=plan.render.height,
                fps=plan.render.fps,
                output_kind=plan.render.output_kind,
                transparent_background=plan.render.transparent_background,
                background_color=plan.render.background_color,
                backend="auto",
            )
            self._encoder = self.encoder_factory(encoder_config)
            self._encoder.start()
            self.adapter.set_display_settings(plan.display)
            # The final readback is post-processed once on the CPU. Keep the
            # GPU draw neutral during export so exposure/tone mapping/etc. do
            # not get applied a second time before apply_appearance().
            self.adapter.set_appearance_settings(AppearanceSettings(tone_mapping="none"))
            set_quality = getattr(self.adapter, "set_quality", None)
            if set_quality is not None:
                set_quality(plan.render.quality.value)
        except Exception as exc:
            self._encoder = None
            self._fail(exc)
            raise ViewerRenderControllerError(str(exc)) from exc
        self._running = True
        self.state_changed.emit("running")
        self.started.emit()
        self._schedule()

    def cancel(self) -> None:
        if not self._running:
            return
        self._timer.stop()
        encoder = self._encoder
        self._running = False
        try:
            if encoder is not None:
                encoder.abort()
        except Exception as exc:
            self._error = str(exc)
        self._pending_frame = None
        self._restore()
        self.state_changed.emit("cancelled")
        self.cancelled.emit()

    def _schedule(self) -> None:
        if self._running and not self._timer.isActive():
            self._timer.start(0)

    def _render_next(self) -> None:
        if not self._running or self._finalizing:
            if self._finalizing:
                self._poll_encoder()
            return
        if self._encoder is None or self._plan is None:
            self._fail(ViewerRenderControllerError("渲染任务状态不完整"))
            return
        if self._encoder.state is EncoderState.FAILED:
            self._fail(self._encoder.error or EncoderError("编码器失败"))
            return
        try:
            if self._pending_frame is None:
                if not self._encoder_has_capacity():
                    self._schedule()
                    return
                pose = self._plan.frame_pose(self._frame_index)
                self.adapter.set_camera_pose(pose)
                frame = self.adapter.capture_frame(
                    width=self._plan.render.width,
                    height=self._plan.render.height,
                    camera_pose=pose,
                )
                frame = apply_appearance(frame, self._plan.appearance)
                self._pending_frame = frame
            self._encoder.submit(self._pending_frame, block=False)
        except EncoderBackpressureError:
            self._schedule()
            return
        except Exception as exc:
            self._fail(exc)
            return

        self._pending_frame = None
        self._frame_index += 1
        self._set_progress(float(self._frame_index) / float(self._plan.frame_count))
        if self._frame_index >= self._plan.frame_count:
            self._begin_finalize()
        else:
            self._schedule()

    def _encoder_has_capacity(self) -> bool:
        sink = getattr(self._encoder, "sink", None)
        if sink is None:
            return True
        available = getattr(sink, "available_slots", None)
        if available is None:
            return True
        return int(available) > 0

    def _begin_finalize(self) -> None:
        self._finalizing = True
        sink = getattr(self._encoder, "sink", None)
        if sink is not None:
            sink.close()
        self._schedule()

    def _poll_encoder(self) -> None:
        if not self._running or self._encoder is None:
            return
        state = self._encoder.state
        if state is EncoderState.FINISHED:
            output = Path(self._plan.output_path)
            try:
                finish = getattr(self._encoder, "finish", None)
                if finish is not None:
                    finish(timeout=0)
            except Exception as exc:
                self._fail(exc)
                return
            self._running = False
            self._finalizing = False
            self._restore()
            self.state_changed.emit("finished")
            self.finished.emit(output)
            return
        if state is EncoderState.FAILED:
            self._fail(self._encoder.error or EncoderError("编码器失败"))
            return
        if state is EncoderState.ABORTED:
            self._running = False
            self._finalizing = False
            self._restore()
            self.state_changed.emit("cancelled")
            self.cancelled.emit()
            return
        self._schedule()

    def _fail(self, exc) -> None:
        self._timer.stop()
        self._error = str(exc)
        encoder = self._encoder
        self._running = False
        self._finalizing = False
        if encoder is not None:
            try:
                if encoder.state is EncoderState.RUNNING:
                    encoder.abort()
            except Exception:
                pass
        self._pending_frame = None
        self._restore()
        self.state_changed.emit("failed")
        self.failed.emit(self._error)

    def _restore(self) -> None:
        callback = self._restore_callback
        self._restore_callback = None
        previous_appearance = self._previous_appearance
        self._previous_appearance = None
        callback_succeeded = False
        if callback is not None:
            try:
                callback()
                callback_succeeded = True
            except Exception:
                pass
        if not callback_succeeded and previous_appearance is not None:
            try:
                self.adapter.set_appearance_settings(previous_appearance)
            except Exception:
                pass

    def _set_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, float(value)))
        self.progress_changed.emit(self._progress)


__all__ = ["ViewerRenderController", "ViewerRenderControllerError"]
