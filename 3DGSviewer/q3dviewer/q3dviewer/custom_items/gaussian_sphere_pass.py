"""Screen-space circumscribed-sphere impostor pass for Gaussian inspection."""

from __future__ import annotations

import ctypes
from pathlib import Path

import numpy as np
from OpenGL.GL import *
from OpenGL.GL import shaders
from OpenGL.raw.GL.VERSION.GL_2_0 import glVertexAttribPointer as raw_glVertexAttribPointer
from OpenGL.raw.GL.VERSION.GL_3_1 import glDrawElementsInstanced as raw_glDrawElementsInstanced

from q3dviewer.utils import set_uniform


class GaussianSpherePass:
    """Render one ray-intersected sphere impostor per source Gaussian."""

    STYLES = {"wireframe": 0, "solid": 1, "overlay": 2}
    COLOR_MODES = {"gaussian": 0, "uniform": 1}

    def __init__(self, gpu_data):
        self.gpu_data = gpu_data
        self.program = None
        self.vao = 0
        self.vbo = 0
        self.ebo = 0
        self.width = 1
        self.height = 1
        self.settings = {
            "sigma_multiplier": 3.0,
            "opacity": 0.5,
            "line_width": 1.0,
            "color_mode": "gaussian",
            "color": (0.35, 0.78, 1.0),
            "all_instances": False,
        }

    def set_settings(self, **changes):
        values = dict(self.settings)
        values.update(changes)
        multiplier = float(values["sigma_multiplier"])
        opacity = float(values["opacity"])
        line_width = float(values["line_width"])
        color = tuple(float(component) for component in values["color"])
        if multiplier <= 0.0:
            raise ValueError("sphere sigma multiplier must be positive")
        if not 0.0 <= opacity <= 1.0:
            raise ValueError("sphere opacity must be between 0 and 1")
        if line_width <= 0.0:
            raise ValueError("sphere line width must be positive")
        if len(color) != 3 or any(component < 0.0 or component > 1.0 for component in color):
            raise ValueError("sphere color must contain three values between 0 and 1")
        color_mode = str(values["color_mode"]).lower()
        if color_mode not in self.COLOR_MODES:
            raise ValueError("unsupported sphere color mode: {}".format(color_mode))
        self.settings = {
            "sigma_multiplier": multiplier,
            "opacity": opacity,
            "line_width": line_width,
            "color_mode": color_mode,
            "color": color,
            "all_instances": bool(values["all_instances"]),
        }
        return dict(self.settings)

    def initialize_gl(self, shader_dir):
        shader_dir = Path(shader_dir)
        vertex_source = (shader_dir / "gau_sphere_vert.glsl").read_text(encoding="utf-8")
        fragment_source = (shader_dir / "gau_sphere_frag.glsl").read_text(encoding="utf-8")
        self.program = shaders.compileProgram(
            shaders.compileShader(vertex_source, GL_VERTEX_SHADER),
            shaders.compileShader(fragment_source, GL_FRAGMENT_SHADER),
            validate=False,
        )
        square_vert = np.array([-1, 1, 1, 1, 1, -1, -1, -1], dtype=np.float32)
        indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
        self.vao = glGenVertexArrays(1)
        self.vbo = glGenBuffers(1)
        self.ebo = glGenBuffers(1)
        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, square_vert.nbytes, square_vert, GL_STATIC_DRAW)
        position = glGetAttribLocation(self.program, "vert")
        raw_glVertexAttribPointer(position, 2, GL_FLOAT, False, 0, ctypes.c_void_p(0))
        glEnableVertexAttribArray(position)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)
        glBindVertexArray(0)

    def resize_gl(self, width, height):
        self.width = max(1, int(width))
        self.height = max(1, int(height))

    def paint(self, item, style="wireframe"):
        if self.program is None or self.gpu_data.count == 0:
            return False
        widget = item.glwidget()
        if widget is None:
            return False
        if item.need_updateGS:
            item.updateGS()
        all_instances = bool(self.settings["all_instances"])
        use_preview = item.interactive_preview and not all_instances
        draw_count = self.gpu_data.preview_count if use_preview else self.gpu_data.count
        if draw_count <= 0:
            return False
        view = np.asarray(widget.view_matrix, dtype=np.float32)
        projection = np.asarray(widget.get_projection_matrix(), dtype=np.float32)
        inverse_projection = np.linalg.inv(projection).astype(np.float32)
        width = max(1, int(widget.current_width()))
        height = max(1, int(widget.current_height()))
        style_id = self.STYLES.get(style, self.STYLES["wireframe"])
        values = self.settings

        glDisable(GL_CULL_FACE)
        glEnable(GL_BLEND)
        glBlendEquation(GL_FUNC_ADD)
        # gau_sphere_frag outputs premultiplied RGB (color * alpha), matching
        # the standard Gaussian pass. Avoid multiplying alpha into RGB twice.
        glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE if style_id == self.STYLES["solid"] else GL_FALSE)
        glUseProgram(self.program)
        set_uniform(self.program, view, "view_matrix")
        set_uniform(self.program, projection, "projection_matrix")
        set_uniform(self.program, inverse_projection, "inverse_projection_matrix")
        set_uniform(self.program, np.array([width, height], dtype=np.float32), "win_size")
        set_uniform(self.program, int(self.gpu_data.sh_dim), "data_sh_dim")
        set_uniform(self.program, int(self.gpu_data.count), "gs_num")
        set_uniform(self.program, int(use_preview), "preview_mode")
        set_uniform(self.program, float(values["sigma_multiplier"]), "sphere_sigma_multiplier")
        set_uniform(self.program, float(values["opacity"]), "sphere_opacity")
        set_uniform(self.program, float(values["line_width"]), "line_width")
        set_uniform(self.program, int(style_id), "render_style")
        set_uniform(self.program, int(self.COLOR_MODES[values["color_mode"]]), "color_mode")
        set_uniform(self.program, np.asarray(values["color"], dtype=np.float32), "uniform_color")
        appearance = item.render_controller.appearance_uniforms()
        set_uniform(self.program, appearance["exposure"], "appearance_exposure")
        set_uniform(self.program, appearance["tone_mapping"], "appearance_tone_mapping")
        set_uniform(self.program, appearance["contrast"], "appearance_contrast")
        set_uniform(self.program, appearance["saturation"], "appearance_saturation")
        set_uniform(self.program, appearance["vignette"], "appearance_vignette")
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 0, self.gpu_data.ssbo_gs)
        glBindBufferBase(
            GL_SHADER_STORAGE_BUFFER,
            4 if use_preview else 1,
            self.gpu_data.ssbo_preview_gi if use_preview else self.gpu_data.ssbo_gi,
        )
        glBindVertexArray(self.vao)
        raw_glDrawElementsInstanced(
            GL_TRIANGLES,
            6,
            GL_UNSIGNED_INT,
            ctypes.c_void_p(0),
            int(draw_count),
        )
        glBindVertexArray(0)
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 0, 0)
        glUseProgram(0)
        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)
        return True

    def release_gl(self):
        buffers = [int(handle) for handle in (self.vbo, self.ebo) if handle]
        if buffers:
            glDeleteBuffers(len(buffers), buffers)
        if self.vao:
            glDeleteVertexArrays(1, [int(self.vao)])
        if self.program:
            glDeleteProgram(int(self.program))
        self.vbo = 0
        self.ebo = 0
        self.vao = 0
        self.program = None


__all__ = ["GaussianSpherePass"]
