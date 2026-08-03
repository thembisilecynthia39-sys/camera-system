"""Interactive draft playback for a deterministic camera timeline."""

from __future__ import annotations

from PySide6.QtCore import QTimer, QObject, Signal

from camera_system_app.application.viewer_timeline import timeline_frame_count
from camera_system_app.domain.viewer import CameraTimeline, ViewerValidationError


class ViewerPlaybackError(ViewerValidationError):
    """Raised when interactive playback cannot satisfy a requested action."""


class ViewerPlayback(QObject):
    """A small, cancelable state machine for previewing camera shots.

    The timer only advances an integer frame cursor.  Camera interpolation is
    always delegated to :mod:`viewer_timeline`, so preview and final rendering
    use the same sampled poses.
    """

    frame_changed = Signal(int)
    playback_started = Signal()
    playback_paused = Signal()
    playback_stopped = Signal()
    playback_finished = Signal()
    playback_looped = Signal()
    playing_changed = Signal(bool)

    def __init__(self, timeline=None, parent=None):
        super().__init__(parent)
        self._timeline = CameraTimeline()
        self._frame_count = 0
        self._frame_range = (0, -1)
        self._current_frame = 0
        self._playing = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        if timeline is not None:
            self.set_timeline(timeline)

    @property
    def timeline(self):
        return self._timeline

    @property
    def frame_count(self):
        return self._frame_count

    @property
    def current_frame(self):
        return self._current_frame

    @property
    def frame_range(self):
        return self._frame_range

    @property
    def is_playing(self):
        return self._playing

    def set_timeline(self, timeline):
        if not isinstance(timeline, CameraTimeline):
            raise ViewerPlaybackError("timeline must be a CameraTimeline value")
        self.pause()
        self._timeline = timeline
        self._frame_count = timeline_frame_count(timeline) if timeline.shots else 0
        self._frame_range = (
            (0, self._frame_count - 1) if self._frame_count else (0, -1)
        )
        self._set_current_frame(0, emit=True)

    def set_frame_range(self, start, end):
        if self._frame_count <= 0:
            raise ViewerPlaybackError("cannot set a frame range for an empty timeline")
        start = self._integer(start, "range start")
        end = self._integer(end, "range end")
        if start < 0 or end >= self._frame_count or start > end:
            raise ViewerPlaybackError("frame range is outside the timeline")
        self._frame_range = (start, end)
        if self._current_frame < start or self._current_frame > end:
            self._set_current_frame(start, emit=True)

    def set_frame(self, frame):
        if self._frame_count <= 0:
            raise ViewerPlaybackError("cannot select a frame in an empty timeline")
        frame = self._integer(frame, "frame")
        start, end = self._frame_range
        if frame < start or frame > end:
            raise ViewerPlaybackError("frame is outside the active frame range")
        self._set_current_frame(frame, emit=True)

    def play(self):
        if self._frame_count <= 0:
            raise ViewerPlaybackError("cannot play an empty timeline")
        if self._playing:
            return
        start, end = self._frame_range
        if self._current_frame >= end:
            self._set_current_frame(start, emit=True)
        interval_ms = max(1, int(round(1000.0 / self._timeline.fps)))
        self._timer.start(interval_ms)
        self._playing = True
        self.playback_started.emit()
        self.playing_changed.emit(True)

    def pause(self):
        if not self._playing:
            return
        self._timer.stop()
        self._playing = False
        self.playback_paused.emit()
        self.playing_changed.emit(False)

    def stop(self):
        was_playing = self._playing
        if was_playing:
            self._timer.stop()
            self._playing = False
        if self._frame_count:
            self._set_current_frame(self._frame_range[0], emit=True)
        self.playback_stopped.emit()
        if was_playing:
            self.playing_changed.emit(False)

    def step_backward(self):
        """Select one previous frame without starting draft playback."""

        if self._playing:
            self.pause()
        if self._frame_count:
            start, _ = self._frame_range
            self._set_current_frame(max(start, self._current_frame - 1), emit=True)

    def step_forward(self):
        """Select one next frame without starting draft playback."""

        if self._playing:
            self.pause()
        if self._frame_count:
            _, end = self._frame_range
            self._set_current_frame(min(end, self._current_frame + 1), emit=True)

    def tick(self):
        """Advance one frame; public for deterministic tests and render previews."""

        if not self._playing:
            return
        _, end = self._frame_range
        next_frame = self._current_frame + 1
        if self._timeline.loop:
            if next_frame > end:
                self._set_current_frame(self._frame_range[0], emit=True)
                self.playback_looped.emit()
            else:
                self._set_current_frame(next_frame, emit=True)
            return
        if next_frame >= end:
            self._set_current_frame(end, emit=True)
            self._timer.stop()
            self._playing = False
            self.playback_finished.emit()
            self.playing_changed.emit(False)
            return
        self._set_current_frame(next_frame, emit=True)

    def _set_current_frame(self, frame, emit):
        if self._frame_count:
            start, end = self._frame_range
            frame = max(start, min(end, int(frame)))
        else:
            frame = 0
        changed = frame != self._current_frame
        self._current_frame = frame
        if emit and changed:
            self.frame_changed.emit(frame)

    @staticmethod
    def _integer(value, label):
        if isinstance(value, bool):
            raise ViewerPlaybackError("{} must be an integer".format(label))
        try:
            result = int(value)
        except (TypeError, ValueError):
            raise ViewerPlaybackError("{} must be an integer".format(label))
        if result != value:
            raise ViewerPlaybackError("{} must be an integer".format(label))
        return result


__all__ = ["ViewerPlayback", "ViewerPlaybackError"]
