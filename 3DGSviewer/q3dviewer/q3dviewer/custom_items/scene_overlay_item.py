"""Core-profile scene inspection overlays for the embedded Gaussian viewer."""

from __future__ import annotations

import ctypes
from pathlib import Path

import numpy as np
from OpenGL.GL import *
from OpenGL.GL import shaders

from q3dviewer.base_item import BaseItem
from q3dviewer.utils import set_uniform


class SceneOverlayItem(BaseItem):
    """Render grid, axes, bounds, and center guides without per-Gaussian objects."""

    _DEFAULT_OPTIONS = {
        "grid": False,
        "axis": False,
        "bounds": False,
        "center": False,
    }

    def __init__(self):
        super().__init__()
        self.bounds = ((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0))
        self.options = dict(self._DEFAULT_OPTIONS)
        self.program = None
        self.vao = 0
        self.vbo = 0
        self._vertex_count = 0
        self._geometry_dirty = True

    def set_bounds(self, lower, upper):
        lo = np.asarray(lower, dtype=np.float32)
        hi = np.asarray(upper, dtype=np.float32)
        if lo.shape != (3,) or hi.shape != (3,):
            raise ValueError("scene overlay bounds must contain three values")
        if not np.isfinite(lo).all() or not np.isfinite(hi).all() or np.any(hi < lo):
            raise ValueError("scene overlay bounds must be finite and ordered")
        equal_axes = hi == lo
        if np.any(equal_axes):
            padding = max(float(np.max(hi - lo)) * 0.05, 1e-3)
            lo = lo.copy()
            hi = hi.copy()
            lo[equal_axes] -= padding
            hi[equal_axes] += padding
        self.bounds = (tuple(float(value) for value in lo), tuple(float(value) for value in hi))
        self._geometry_dirty = True
        self._request_update()
        return self.bounds

    def set_options(self, **changes):
        options = dict(self.options)
        for key, value in changes.items():
            if key not in options:
                raise ValueError("unsupported scene overlay option: {}".format(key))
            options[key] = bool(value)
        self.options = options
        self._geometry_dirty = True
        self._request_update()
        return dict(self.options)

    def _request_update(self):
        widget = self.glwidget()
        if widget is not None:
            widget.update()

    @staticmethod
    def _nice_step(value):
        value = max(float(value), 1e-4)
        exponent = np.floor(np.log10(value))
        fraction = value / (10.0 ** exponent)
        if fraction < 1.5:
            nice = 1.0
        elif fraction < 3.5:
            nice = 2.0
        elif fraction < 7.5:
            nice = 5.0
        else:
            nice = 10.0
        return float(nice * (10.0 ** exponent))

    @staticmethod
    def _line(vertices, start, end, color):
        vertices.append((*start, *color))
        vertices.append((*end, *color))

    def _build_vertices(self):
        lo = np.asarray(self.bounds[0], dtype=np.float32)
        hi = np.asarray(self.bounds[1], dtype=np.float32)
        center = (lo + hi) * 0.5
        span = np.maximum(hi - lo, 1e-3)
        extent = max(float(np.max(span)), 1.0)
        step = self._nice_step(extent / 10.0)
        grid_extent = max(extent * 1.15, step * 4.0)
        half_grid = grid_extent * 0.5
        grid_lo_x = np.floor((float(center[0]) - half_grid) / step) * step
        grid_lo_y = np.floor((float(center[1]) - half_grid) / step) * step
        grid_hi_x = grid_lo_x + grid_extent
        grid_hi_y = grid_lo_y + grid_extent
        vertices = []

        if self.options["grid"]:
            grid_color = (0.35, 0.55, 0.65, 0.28)
            values_x = np.arange(grid_lo_x, grid_hi_x + step * 0.5, step)
            values_y = np.arange(grid_lo_y, grid_hi_y + step * 0.5, step)
            plane_z = float(lo[2])
            for value in values_x:
                self._line(
                    vertices,
                    (float(value), grid_lo_y, plane_z),
                    (float(value), grid_hi_y, plane_z),
                    grid_color,
                )
            for value in values_y:
                self._line(
                    vertices,
                    (grid_lo_x, float(value), plane_z),
                    (grid_hi_x, float(value), plane_z),
                    grid_color,
                )

        origin = np.array([center[0], center[1], lo[2]], dtype=np.float32)
        axis_length = max(extent * 0.35, step * 2.0)
        if self.options["axis"]:
            self._line(vertices, origin, origin + [axis_length, 0.0, 0.0], (1.0, 0.2, 0.2, 0.9))
            self._line(vertices, origin, origin + [0.0, axis_length, 0.0], (0.2, 1.0, 0.3, 0.9))
            self._line(vertices, origin, origin + [0.0, 0.0, axis_length], (0.2, 0.5, 1.0, 0.9))

        if self.options["bounds"]:
            corners = (
                (lo[0], lo[1], lo[2]),
                (hi[0], lo[1], lo[2]),
                (hi[0], hi[1], lo[2]),
                (lo[0], hi[1], lo[2]),
                (lo[0], lo[1], hi[2]),
                (hi[0], lo[1], hi[2]),
                (hi[0], hi[1], hi[2]),
                (lo[0], hi[1], hi[2]),
            )
            bounds_color = (1.0, 0.72, 0.2, 0.85)
            for first, second in ((0, 1), (1, 2), (2, 3), (3, 0),
                                  (4, 5), (5, 6), (6, 7), (7, 4),
                                  (0, 4), (1, 5), (2, 6), (3, 7)):
                self._line(vertices, corners[first], corners[second], bounds_color)

        if self.options["center"]:
            center_size = max(extent * 0.035, step * 0.5)
            center_color = (1.0, 0.2, 0.8, 0.95)
            self._line(vertices, center - [center_size, 0.0, 0.0], center + [center_size, 0.0, 0.0], center_color)
            self._line(vertices, center - [0.0, center_size, 0.0], center + [0.0, center_size, 0.0], center_color)
            self._line(vertices, center - [0.0, 0.0, center_size], center + [0.0, 0.0, center_size], center_color)

        if not vertices:
            return np.empty((0, 7), dtype=np.float32)
        return np.asarray(vertices, dtype=np.float32)

    def initialize_gl(self):
        shader_dir = Path(__file__).resolve().parent.parent / "shaders"
        vertex_source = (shader_dir / "scene_overlay_vert.glsl").read_text(encoding="utf-8")
        fragment_source = (shader_dir / "scene_overlay_frag.glsl").read_text(encoding="utf-8")
        self.program = shaders.compileProgram(
            shaders.compileShader(vertex_source, GL_VERTEX_SHADER),
            shaders.compileShader(fragment_source, GL_FRAGMENT_SHADER),
            validate=False,
        )
        self.vao = glGenVertexArrays(1)
        self.vbo = glGenBuffers(1)
        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 7 * 4, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, 7 * 4, ctypes.c_void_p(3 * 4))
        glEnableVertexAttribArray(1)
        glBindVertexArray(0)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

    def _upload_geometry(self):
        vertices = self._build_vertices()
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, max(vertices.nbytes, 4), vertices, GL_DYNAMIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        self._vertex_count = int(vertices.shape[0])
        self._geometry_dirty = False

    def paint(self):
        if self.program is None or not any(self.options.values()):
            return False
        if self._geometry_dirty:
            self._upload_geometry()
        if self._vertex_count <= 0:
            return False
        widget = self.glwidget()
        if widget is None:
            return False
        glUseProgram(self.program)
        set_uniform(self.program, np.asarray(widget.view_matrix, dtype=np.float32), "view_matrix")
        set_uniform(self.program, np.asarray(widget.get_projection_matrix(), dtype=np.float32), "projection_matrix")
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_FALSE)
        glBindVertexArray(self.vao)
        glLineWidth(1.0)
        glDrawArrays(GL_LINES, 0, self._vertex_count)
        glBindVertexArray(0)
        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)
        glUseProgram(0)
        return True

    def release_gl(self):
        if self.vbo:
            glDeleteBuffers(1, [int(self.vbo)])
        if self.vao:
            glDeleteVertexArrays(1, [int(self.vao)])
        if self.program:
            glDeleteProgram(int(self.program))
        self.vbo = 0
        self.vao = 0
        self.program = None
        self._vertex_count = 0
        self._geometry_dirty = True


__all__ = ["SceneOverlayItem"]
