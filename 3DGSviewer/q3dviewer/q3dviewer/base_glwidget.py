"""
Copyright 2024 Panasonic Advanced Technology Development Co.,Ltd. (Liu Yang)
Distributed under MIT license. See LICENSE for more information.
"""

from OpenGL.GL import *
from math import isfinite, radians, tan
import numpy as np
from q3dviewer.Qt import QtCore, QtGui
from q3dviewer.utils.maths import frustum, euler_to_matrix, makeT
from q3dviewer.Qt.QtWidgets import QApplication, QOpenGLWidget


class BaseGLWidget(QOpenGLWidget):
    initialization_failed = QtCore.Signal(str)
    interaction_started = QtCore.Signal()
    interaction_finished = QtCore.Signal()
    frame_rendered = QtCore.Signal(object)

    def __init__(self, parent=None):
        QOpenGLWidget.__init__(self, parent)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        self.reset()
        self._fov = 60
        self.camera_mode = "orbit"
        self.fly_speed = 1.0
        self.items = []
        self.keyTimer = QtCore.QTimer()
        self.color = np.array([0, 0, 0, 1])
        self.dist = 40
        self.euler = np.array([np.pi/3, 0, np.pi/4])
        self.center = np.array([0, 0, 0.])
        self.active_keys = set()
        self.show_center = False
        self.enable_show_center = True
        self.need_recalc_view = True
        self._render_size_override = None
        self.view_matrix = self.get_view_matrix()
        self.projection_matrix = self.get_projection_matrix()
        self._projection_dirty = True
        self._compatibility_pipeline = False
        self._cleanup_done = False
        self._context_cleanup_connected = False
        self._interacting = False
        self._mouse_interacting = False
        self._drag_started = False
        self._drag_start_pos = None
        self._drag_threshold = max(4, QApplication.startDragDistance())
        self._interaction_timer = QtCore.QTimer(self)
        self._interaction_timer.setSingleShot(True)
        self._interaction_timer.setInterval(180)
        self._interaction_timer.timeout.connect(self._finish_interaction)

        # Pre-calculate candidate offsets for depth picking, sorted by distance
        radius = 3
        offset = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                dist_sq = dx * dx + dy * dy
                if dist_sq <= radius * radius:
                    offset.append((dist_sq, dx, dy))
        offset.sort(key=lambda c: c[0])
        self.offset = [(dx, dy) for _, dx, dy in offset]
        self.offset = np.array(self.offset)

    def keyPressEvent(self, ev: QtGui.QKeyEvent):
        if ev.key() == QtCore.Qt.Key_Up or  \
                ev.key() == QtCore.Qt.Key_Down or \
                ev.key() == QtCore.Qt.Key_Left or \
                ev.key() == QtCore.Qt.Key_Right or \
                ev.key() == QtCore.Qt.Key_Z or \
                ev.key() == QtCore.Qt.Key_X or \
                ev.key() == QtCore.Qt.Key_A or \
                ev.key() == QtCore.Qt.Key_D or \
                ev.key() == QtCore.Qt.Key_W or \
                ev.key() == QtCore.Qt.Key_S:
            self.active_keys.add(ev.key())
        self.active_keys.add(ev.key())
        self._begin_interaction()

    def keyReleaseEvent(self, ev: QtGui.QKeyEvent):
        self.active_keys.discard(ev.key())
        if not self.active_keys:
            self._schedule_interaction_finish()

    def current_width(self):
        """
        Return the current width of the widget.
        """
        if self._render_size_override is not None:
            return int(self._render_size_override[0])
        return int(self.width() * self.devicePixelRatioF())

    def current_height(self):
        """
        Return the current height of the widget.
        """
        if self._render_size_override is not None:
            return int(self._render_size_override[1])
        return int(self.height() * self.devicePixelRatioF())

    def reset(self):
        pass

    def add_item(self, item):
        """
        Add the item to the glwidget.
        """
        self.items.append(item)
        item.set_glwidget(self)

    def remove_item(self, item):
        """
        Remove the item from the glwidget.
        """
        self.items.remove(item)
        item.set_glwidget(None)

    def clear(self):
        """
        Remove all items from the glwidget.
        """
        for item in self.items:
            item.set_glwidget(None)
        self.items = []

    def initializeGL(self):
        """
        the method is herted from QOpenGLWidget, 
        and it is called when the widget is first shown.
        """
        try:
            context = self.context()
            surface_format = context.format()
            self._compatibility_pipeline = (
                surface_format.profile() == surface_format.CompatibilityProfile
            )
            if not self._context_cleanup_connected:
                context.aboutToBeDestroyed.connect(self.cleanup_gl)
                self._context_cleanup_connected = True
            glEnable(GL_DEPTH_TEST)
            glDepthFunc(GL_LESS)
            for item in self.items:
                item.initialize()
            self.projection_matrix = self.get_projection_matrix()
            self._projection_dirty = False
            self.view_matrix = self.get_view_matrix()
            self.update_model_projection()
            self.update_model_view()
            self._cleanup_done = False
        except Exception as exc:
            self.initialization_failed.emit(str(exc))
            raise

    def set_view_matrix(self, view_matrix):
        self.view_matrix = view_matrix
        self.need_recalc_view = False

    def get_camera_state(self):
        """Return a serializable camera snapshot in the native orbit model."""

        return {
            "center": [float(value) for value in self.center],
            "euler": [float(value) for value in self.euler],
            "distance": float(self.dist),
            "fov_degrees": float(self._fov),
            "camera_mode": self.camera_mode,
            "fly_speed": float(self.fly_speed),
        }

    def set_camera_state(self, state):
        """Restore a camera snapshot without applying incremental transforms."""

        if not isinstance(state, dict):
            raise ValueError("camera state must be a dictionary")
        required = ("center", "euler", "distance")
        if any(key not in state for key in required):
            raise ValueError("camera state requires center, euler, and distance")
        try:
            center = np.asarray(state["center"], dtype=np.float64)
            euler = np.asarray(state["euler"], dtype=np.float64)
            distance = float(state["distance"])
            fov = float(state.get("fov_degrees", self._fov))
            camera_mode = str(state.get("camera_mode", self.camera_mode)).lower()
            fly_speed = float(state.get("fly_speed", self.fly_speed))
        except (TypeError, ValueError):
            raise ValueError("camera state contains invalid numeric values")
        if center.shape != (3,) or euler.shape != (3,):
            raise ValueError("camera center and euler must contain three values")
        if not np.isfinite(center).all() or not np.isfinite(euler).all():
            raise ValueError("camera center and euler must be finite")
        if not np.isfinite(distance) or distance <= 0.0:
            raise ValueError("camera distance must be positive and finite")
        if not np.isfinite(fov) or not 1.0 <= fov <= 179.0:
            raise ValueError("camera FOV must be between 1 and 179 degrees")
        if camera_mode not in ("orbit", "fly"):
            raise ValueError("camera mode must be orbit or fly")
        if not isfinite(fly_speed) or fly_speed <= 0.0:
            raise ValueError("fly speed must be positive and finite")
        self.center = center.copy()
        self.euler = euler.copy()
        self.dist = distance
        self._fov = fov
        self.camera_mode = camera_mode
        self.fly_speed = fly_speed
        self.need_recalc_view = True
        self._projection_dirty = True
        self.update()

    def mouseReleaseEvent(self, ev):
        self._mouse_interacting = False
        had_drag = self._drag_started
        self._drag_started = False
        self._drag_start_pos = None
        if hasattr(self, 'mousePos'):
            delattr(self, 'mousePos')
        if had_drag:
            self._schedule_interaction_finish()
        super().mouseReleaseEvent(ev)

    def mousePressEvent(self, ev):
        self._mouse_interacting = ev.button() in (
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.MouseButton.RightButton,
        )
        self.mousePos = ev.localPos()
        self._drag_start_pos = ev.localPos()
        self._drag_started = False
        super().mousePressEvent(ev)

    def set_dist(self, dist):
        self.dist = dist
        self.need_recalc_view = True
        self._projection_dirty = True
        self.update()

    def update_dist(self, delta):
        self.dist += delta
        if self.dist < 0.1:
            self.dist = 0.1
        self.need_recalc_view = True
        self._projection_dirty = True
        self.update()

    def wheelEvent(self, ev):
        self._begin_interaction()
        delta = ev.angleDelta().x()
        if delta == 0:
            delta = ev.angleDelta().y()
        self.update_dist(-delta * self.dist * 0.001)
        self.need_recalc_view = True
        self.show_center = True
        self._schedule_interaction_finish()

    def rotate_keep_cam_pos(self, rx=0, ry=0, rz=0):
        """
        Rotate the camera while keeping the current camera position. 
        This updates both the Euler angles and the center point.
        """
        new_euler = self.euler + np.array([rx, ry, rz])
        new_euler = (new_euler + np.pi) % (2 * np.pi) - np.pi

        Rwc_old = euler_to_matrix(self.euler)
        tco = np.array([0, 0, self.dist])
        twc = self.center + Rwc_old @ tco

        Rwc_new = euler_to_matrix(new_euler)
        self.center = twc - Rwc_new @ tco
        self.euler = new_euler
        self.need_recalc_view = True
        self.update()

    def mouseMoveEvent(self, ev):
        lpos = ev.localPos()
        if not hasattr(self, 'mousePos'):
            self.mousePos = lpos
        diff = lpos - self.mousePos
        self.mousePos = lpos
        buttons = ev.buttons()
        if buttons not in (
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.MouseButton.RightButton,
        ):
            return
        if not self._drag_started:
            start = self._drag_start_pos
            if start is None:
                start = lpos
                self._drag_start_pos = start
            total = lpos - start
            if abs(total.x()) + abs(total.y()) < self._drag_threshold:
                return
            self._drag_started = True
            # Apply the full displacement once the gesture crosses the
            # threshold; click jitter before that point changes no camera state.
            diff = total
        if diff.x() == 0 and diff.y() == 0:
            return
        # A press/release is only a click. Enter the reduced-cost interaction
        # path after the camera has actually moved, otherwise a harmless click
        # requests another full-model render and depth sort.
        self._begin_interaction()
        if buttons == QtCore.Qt.MouseButton.RightButton:
            rot_speed = 0.2
            dyaw = radians(-diff.x() * rot_speed)
            droll = radians(-diff.y() * rot_speed)
            if self.camera_mode == "fly" or ev.modifiers() & QtCore.Qt.ShiftModifier:
                self.rotate_keep_cam_pos(droll, 0, dyaw)
            else:
                self.rotate(droll, 0, dyaw)
        elif buttons == QtCore.Qt.MouseButton.LeftButton:
            Rwc = euler_to_matrix(self.euler)
            Kinv = np.linalg.inv(self.get_K())
            dist = max(self.dist, 0.5)
            self.translate(
                Rwc @ Kinv @ np.array([-diff.x(), diff.y(), 0]) * dist)
        self.show_center = True

    def _begin_interaction(self):
        self._interaction_timer.stop()
        if not self._interacting:
            self._interacting = True
            self.interaction_started.emit()

    def _schedule_interaction_finish(self):
        self._interaction_timer.start()

    def finish_interaction(self, notify=True):
        """End a programmatic interaction without waiting for the debounce timer."""

        self._interaction_timer.stop()
        self.active_keys.clear()
        self._mouse_interacting = False
        self._drag_started = False
        self._drag_start_pos = None
        was_interacting = self._interacting
        self._interacting = False
        if was_interacting and notify:
            self.interaction_finished.emit()
        return was_interacting

    def _finish_interaction(self):
        if self._mouse_interacting or self.active_keys:
            return
        if self._interacting:
            self._interacting = False
            self.interaction_finished.emit()

    def set_center(self, center):
        self.center = center
        self.need_recalc_view = True
        self.update()

    def _render_scene(self, width=None, height=None, force_projection=False, include_center=True):
        """Draw the current scene into whichever framebuffer is bound."""

        width = self.current_width() if width is None else max(1, int(width))
        height = self.current_height() if height is None else max(1, int(height))
        if force_projection:
            self.projection_matrix = self.get_projection_matrix(width, height)
            self.update_model_projection()
            for item in self.items:
                if item.is_initialized():
                    item.resize_gl(width, height)
            self._projection_dirty = False
        elif self._projection_dirty:
            self.projection_matrix = self.get_projection_matrix()
            self.update_model_projection()
            for item in self.items:
                if item.is_initialized():
                    item.resize_gl(self.current_width(), self.current_height())
            self._projection_dirty = False
        if self.need_recalc_view:
            self.view_matrix = self.get_view_matrix()
            self.need_recalc_view = False
        self.update_model_view()
        glViewport(0, 0, width, height)
        glClearColor(*self.color)
        glClear(GL_DEPTH_BUFFER_BIT | GL_COLOR_BUFFER_BIT)
        for item in self.items:
            if not item.visible():
                continue
            if not item.is_initialized():
                item.initialize()
            if self._compatibility_pipeline:
                glMatrixMode(GL_MODELVIEW)
                glPushMatrix()
                glPushAttrib(GL_ALL_ATTRIB_BITS)
                try:
                    item.paint()
                finally:
                    glPopAttrib()
                    glMatrixMode(GL_MODELVIEW)
                    glPopMatrix()
            else:
                item.paint()
        if (
            include_center
            and self._compatibility_pipeline
            and self.enable_show_center
            and self.show_center
        ):
            point_size = np.clip((self.get_K()[0, 0] / self.dist), 10, 100)
            glPointSize(point_size)
            glBegin(GL_POINTS)
            glColor3f(1.0, 0.0, 0.0)
            glVertex3f(*self.center)
            glEnd()
            self.show_center = False

    def paintGL(self):
        self._render_scene(include_center=True)

    def update_movement(self):
        """
        Update the movement of the camera based on the active keys.
        """
        if not self.active_keys:
            return
        rot_speed = 0.5
        trans_speed = max(self.dist * 0.005, 0.1)
        if self.camera_mode == "fly":
            trans_speed *= self.fly_speed
        shift_pressed = QtCore.Qt.Key_Shift in self.active_keys
        keep_camera_position = self.camera_mode == "fly" or shift_pressed
        # Handle rotation keys
        if QtCore.Qt.Key_Up in self.active_keys:
            if keep_camera_position:
                self.rotate_keep_cam_pos(radians(rot_speed), 0, 0)
            else:
                self.rotate(radians(rot_speed), 0, 0)
        if QtCore.Qt.Key_Down in self.active_keys:
            if keep_camera_position:
                self.rotate_keep_cam_pos(radians(-rot_speed), 0, 0)
            else:
                self.rotate(radians(-rot_speed), 0, 0)
        if QtCore.Qt.Key_Left in self.active_keys:
            if keep_camera_position:
                self.rotate_keep_cam_pos(0, 0, radians(rot_speed))
            else:
                self.rotate(0, 0, radians(rot_speed))
        if QtCore.Qt.Key_Right in self.active_keys:
            if keep_camera_position:
                self.rotate_keep_cam_pos(0, 0, radians(-rot_speed))
            else:
                self.rotate(0, 0, radians(-rot_speed))
        # Handle zoom keys
        xz_keys = {QtCore.Qt.Key_Z, QtCore.Qt.Key_X}
        if self.active_keys & xz_keys:
            Rwc = euler_to_matrix(self.euler)
            if QtCore.Qt.Key_Z in self.active_keys:
                self.translate(Rwc @ np.array([0, 0, -trans_speed]))
            if QtCore.Qt.Key_X in self.active_keys:
                self.translate(Rwc @ np.array([0, 0, trans_speed]))
        # Handle translation keys on the z plane
        dir_keys = {QtCore.Qt.Key_W, QtCore.Qt.Key_S,
                    QtCore.Qt.Key_A, QtCore.Qt.Key_D}
        if self.active_keys & dir_keys:
            Rz = euler_to_matrix([0, 0, self.euler[2]])
            movement_basis = euler_to_matrix(self.euler) if self.camera_mode == "fly" else Rz
            if QtCore.Qt.Key_W in self.active_keys:
                direction = np.array([0, 0, -trans_speed]) if self.camera_mode == "fly" else np.array([0, trans_speed, 0])
                self.translate(movement_basis @ direction)
            if QtCore.Qt.Key_S in self.active_keys:
                direction = np.array([0, 0, trans_speed]) if self.camera_mode == "fly" else np.array([0, -trans_speed, 0])
                self.translate(movement_basis @ direction)
            if QtCore.Qt.Key_A in self.active_keys:
                self.translate(movement_basis @ np.array([-trans_speed, 0, 0]))
            if QtCore.Qt.Key_D in self.active_keys:
                self.translate(movement_basis @ np.array([trans_speed, 0, 0]))

    def update_model_view(self):
        if not self._compatibility_pipeline:
            return
        glMatrixMode(GL_MODELVIEW)
        glLoadMatrixf(self.view_matrix.T)

    def get_view_matrix(self):
        two = self.center  # the origin(center) in the world frame
        tco = np.array([0, 0, self.dist])  # the origin(center) in camera frame
        Rwc = euler_to_matrix(self.euler)
        twc = two + Rwc @ tco
        Rcw = Rwc.T
        tcw = -Rcw @ twc
        Tcw = makeT(Rcw, tcw)
        return Tcw

    def set_cam_position(self, **kwargs):
        center = kwargs.get('center', None)
        distance = kwargs.get('distance', None)
        euler = kwargs.get('euler', None)
        if center is not None:
            self.set_center(center)
        if distance is not None:
            self.set_dist(distance)
        if euler is not None:
            self.set_euler(euler)

    def set_euler(self, euler):
        self.euler = np.asarray(euler, dtype=np.float64)
        self.need_recalc_view = True
        self.update()

    def set_camera_mode(self, mode):
        mode = str(mode).lower()
        if mode not in ("orbit", "fly"):
            raise ValueError("camera mode must be orbit or fly")
        self.camera_mode = mode
        self.update()

    def set_fly_speed(self, speed):
        try:
            speed = float(speed)
        except (TypeError, ValueError):
            raise ValueError("fly speed must be a number")
        if not isfinite(speed) or speed <= 0.0:
            raise ValueError("fly speed must be positive and finite")
        self.fly_speed = speed
        self.update()

    def set_color(self, color):
        self.color = color
        self.update()

    def update(self):
        self.update_movement()
        super().update()
        # if not self.need_recalc_view:
        #     super().update()
        #     self.need_recalc_view = False

    def update_model_projection(self):
        if not self._compatibility_pipeline:
            return
        glMatrixMode(GL_PROJECTION)
        glLoadMatrixf(self.projection_matrix.T)

    def get_projection_matrix(self, width=None, height=None):
        w = self.current_width() if width is None else max(1, int(width))
        h = self.current_height() if height is None else max(1, int(height))
        dist = self.dist
        near = dist * 0.001
        far = dist * 10000.
        r = near * tan(0.5 * radians(self._fov))
        t = r * h / max(w, 1)
        matrix = frustum(-r, r, -t, t, near, far)
        return matrix

    def get_K(self):
        project_matrix = self.get_projection_matrix()
        width = self.current_width()
        height = self.current_height()
        fx = project_matrix[0, 0] * width / 2
        fy = project_matrix[1, 1] * height / 2
        cx = width / 2
        cy = height / 2
        K = np.array([
            [fx, 0, cx],
            [0, fy, cy],
            [0, 0, 1]
        ])
        return K

    def rotate(self, rx=0, ry=0, rz=0):
        # update the euler angles
        self.euler += np.array([rx, ry, rz])
        # Keep every axis continuous and wrapped instead of clipping pitch to
        # 0..180 degrees. This permits a complete vertical orbit.
        self.euler = (self.euler + np.pi) % (2 * np.pi) - np.pi
        self.need_recalc_view = True
        self.update()

    def orbit(self, delta_yaw=0.0, delta_pitch=0.0):
        """Rotate around the scene center using stable yaw/pitch controls.

        The viewer's native Euler representation uses ``euler[2]`` for the
        horizontal heading and ``euler[0]`` for the vertical orbit angle.
        Keeping this mapping in one public method lets the application layer
        drive keyboard and automatic panorama navigation without duplicating
        camera math.
        """

        try:
            delta_yaw = float(delta_yaw)
            delta_pitch = float(delta_pitch)
        except (TypeError, ValueError):
            raise ValueError("orbit deltas must be numeric")
        if not isfinite(delta_yaw) or not isfinite(delta_pitch):
            raise ValueError("orbit deltas must be finite")
        if delta_yaw == 0.0 and delta_pitch == 0.0:
            return self.get_camera_state()

        self._begin_interaction()
        new_euler = self.euler.copy()
        new_euler[2] = (new_euler[2] + delta_yaw + np.pi) % (2 * np.pi) - np.pi
        # Avoid flipping the camera at the poles while still allowing a full
        # horizontal 360-degree panorama.
        pitch_limit = np.pi / 2.0 - 1e-3
        new_euler[0] = np.clip(
            new_euler[0] + delta_pitch,
            -pitch_limit,
            pitch_limit,
        )
        self.euler = new_euler
        self.need_recalc_view = True
        self.update()
        self._schedule_interaction_finish()
        return self.get_camera_state()

    def translate(self, trans):
        self.center += trans
        self.need_recalc_view = True
        self.update()

    def change_show_center(self, state):
        self.enable_show_center = state

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.need_recalc_view = True
        self.projection_matrix = self.get_projection_matrix()
        self._projection_dirty = True
        self.update_model_projection()

    def resizeGL(self, width, height):
        """Notify initialized items while QOpenGLWidget owns the GL context."""
        super().resizeGL(width, height)
        self.projection_matrix = self.get_projection_matrix()
        self._projection_dirty = False
        for item in self.items:
            if item.is_initialized():
                item.resize_gl(self.current_width(), self.current_height())

    def render_to_array(self, width, height, camera_state=None):
        """Render one GUI-thread frame into an explicit output-sized FBO."""

        from q3dviewer.render_target import RenderTarget

        width, height = RenderTarget.validate_size(width, height)
        old_state = self.get_camera_state()
        old_projection = np.array(self.projection_matrix, copy=True)
        old_view = np.array(self.view_matrix, copy=True)
        old_projection_dirty = self._projection_dirty
        old_need_recalc_view = self.need_recalc_view
        old_override = self._render_size_override
        old_width = max(1, int(self.width() * self.devicePixelRatioF()))
        old_height = max(1, int(self.height() * self.devicePixelRatioF()))
        target = None
        self.makeCurrent()
        try:
            if camera_state is not None:
                self.set_camera_state(camera_state)
            self._render_size_override = (width, height)
            target = RenderTarget(width, height)
            target.bind()
            frame = None
            self._render_scene(
                width,
                height,
                force_projection=True,
                include_center=False,
            )
            frame = target.read_rgba()
            self.frame_rendered.emit(frame)
            return frame
        finally:
            if target is not None:
                target.release()
            glBindFramebuffer(GL_FRAMEBUFFER, 0)
            self._render_size_override = old_override
            self.center = np.asarray(old_state["center"], dtype=np.float64)
            self.euler = np.asarray(old_state["euler"], dtype=np.float64)
            self.dist = float(old_state["distance"])
            self._fov = float(old_state["fov_degrees"])
            self.camera_mode = old_state["camera_mode"]
            self.fly_speed = float(old_state["fly_speed"])
            self.projection_matrix = old_projection
            self.view_matrix = old_view
            self._projection_dirty = old_projection_dirty
            self.need_recalc_view = old_need_recalc_view
            glViewport(0, 0, old_width, old_height)
            for item in self.items:
                if item.is_initialized():
                    item.resize_gl(old_width, old_height)
            self.doneCurrent()

    def capture_frame(self):
        self.makeCurrent()  # Ensure the OpenGL context is current
        width = self.current_width()
        height = self.current_height()
        pixels = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)
        frame = np.frombuffer(pixels, dtype=np.uint8).reshape(height, width, 3)
        frame = np.flip(frame, 0)
        return frame

    def depth_buffer_to_image(self, depth_buffer):
        near = self.dist * 0.001
        far = self.dist * 10000.
        z_ndc = depth_buffer * 2.0 - 1.0
        depth_in_meters = (2.0 * near * far) / \
            (far + near - z_ndc * (far - near))
        return depth_in_meters

    def opengl_to_world(self, p):
        width = self.current_width()
        height = self.current_height()
        x, y, z = p
        gl_y = height - y - 1
        # Explicit matrices work in Core Profile where fixed matrix state does
        # not exist.
        view = np.asarray(self.view_matrix, dtype=np.float32)
        proj = np.asarray(self.projection_matrix, dtype=np.float32)
        # Convert screen (x, y, z) to normalized device coordinates (NDC)
        ndc_x = (x / width) * 2.0 - 1.0
        ndc_y = (gl_y / height) * 2.0 - 1.0
        ndc_z = 2.0 * z - 1.0
        ndc = np.array([ndc_x, ndc_y, ndc_z, 1.0], dtype=np.float32)
        # Transform from NDC to world coordinates
        inv_projview = np.linalg.inv(proj @ view)
        world_p = inv_projview @ ndc
        world_p /= world_p[3]
        return world_p[:3]

    @staticmethod
    def _sample_depth_neighborhood(depth_buffer, x, y, offset):
        """Return only in-bounds depth samples around one pixel."""
        height, width = depth_buffer.shape
        sample_x = x + offset[:, 0]
        sample_y = y + offset[:, 1]
        valid_samples = (
            (sample_x >= 0)
            & (sample_x < width)
            & (sample_y >= 0)
            & (sample_y < height)
        )
        if not np.any(valid_samples):
            return np.empty(0, dtype=depth_buffer.dtype)
        return depth_buffer[
            sample_y[valid_samples], sample_x[valid_samples]
        ]

    def get_point(self, x0, y0):
        """
        Get the 3D point in world coordinates corresponding to the given
        screen coordinates (x0, y0).
        """
        self.makeCurrent()  # Ensure the OpenGL context is current
        width = self.current_width()
        height = self.current_height()

        # Scale mouse coordinates by device pixel ratio
        pixel_ratio = self.devicePixelRatioF()
        x = int(x0 * pixel_ratio)
        y = int(y0 * pixel_ratio)
        if not (0 <= x < width and 0 <= y < height):
            return None

        # Read entire depth buffer (raw values [0,1])
        depth_buffer = glReadPixels(
            0, 0, width, height, GL_DEPTH_COMPONENT, GL_FLOAT)
        depth_buffer = np.frombuffer(
            depth_buffer, dtype=np.float32).reshape((height, width))
        depth_buffer = np.flip(depth_buffer, 0)

        # debug: print depth value at the clicked pixel
        # import imageio
        # depth_image = self.depth_buffer_to_image(depth_buffer)
        # depth_image_uint16 = (depth_image * 1000).astype(np.uint16)
        # imageio.imwrite('/home/liu/depth_debug.png', depth_image_uint16)

        depth_values = self._sample_depth_neighborhood(
            depth_buffer, x, y, self.offset
        )
        if depth_values.size == 0:
            return None
        depth_valid_mask = (depth_values > 0) & (depth_values < 1)
        if not np.any(depth_valid_mask):
            return None

        z = depth_values[depth_valid_mask][0]

        world_p = self.opengl_to_world((x, y, z))

        return world_p

    def cleanup_gl(self):
        """Release item resources exactly once with a current context."""
        if self._cleanup_done:
            return
        context = self.context()
        if context is None or not context.isValid():
            return
        self.makeCurrent()
        try:
            for item in self.items:
                try:
                    item.release_gl()
                except Exception as exc:
                    self.initialization_failed.emit(
                        "OpenGL resource cleanup failed: {}".format(exc)
                    )
        finally:
            self.doneCurrent()
        self._cleanup_done = True

    def closeEvent(self, event):
        self.cleanup_gl()
        setting_window = getattr(self, "setting_window", None)
        if setting_window is not None:
            setting_window.close()
        super().closeEvent(event)
