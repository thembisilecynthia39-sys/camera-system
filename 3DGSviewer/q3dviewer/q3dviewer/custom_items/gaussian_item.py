"""
Copyright 2024 Panasonic Advanced Technology Development Co.,Ltd. (Liu Yang)
Distributed under MIT license. See LICENSE for more information.
"""

import numpy as np
from q3dviewer.base_item import BaseItem
from OpenGL.GL import *
import numpy as np
import os
import ctypes
import time
from q3dviewer.Qt.QtWidgets import QComboBox, QLabel
from OpenGL.GL import shaders
from OpenGL.raw.GL.VERSION.GL_2_0 import glVertexAttribPointer as raw_glVertexAttribPointer
from OpenGL.raw.GL.VERSION.GL_3_1 import glDrawElementsInstanced as raw_glDrawElementsInstanced
from OpenGL.raw.GL.VERSION.GL_4_2 import glMemoryBarrier as raw_glMemoryBarrier
from OpenGL.raw.GL.VERSION.GL_4_3 import glDispatchCompute as raw_glDispatchCompute
from q3dviewer.utils import set_uniform
from q3dviewer.custom_items.gaussian_gpu_data import GaussianGpuData


def div_round_up(x, y):
    return int((x + y - 1) / y)


class GaussianItem(BaseItem):
    def __init__(self, sort_enabled=True, sort_backend='auto',
                 sort_min_interval=0.0, sort_direction_threshold=1e-6,
                 max_bitonic_gaussians=1048576,
                 **kwds):
        super().__init__()
        self.gpu_data = GaussianGpuData(interactive_max_gaussians=120000)
        self.need_updateGS = False
        self.prev_Rz = np.array([np.inf, np.inf, np.inf], dtype=np.float32)
        self.path = os.path.dirname(__file__)
        self.sort_enabled = sort_enabled
        self.sort_suspended = False
        self.interactive_preview = False
        self.interactive_max_gaussians = 120000
        self.sort_min_interval = max(float(sort_min_interval), 0.0)
        self.sort_direction_threshold = max(float(sort_direction_threshold), 0.0)
        self.max_bitonic_gaussians = max(0, int(max_bitonic_gaussians))
        self._last_sort_time = float('-inf')
        self._defer_sort_once = False
        self.last_sort_gpu_ms = None
        self.last_sort_dispatches = 0
        self._sort_query = 0
        self._sort_query_pending = False
        self.sort_skipped_large_model = False
        self.sort_backend = 'opengl'
        self.cuda_pw = None
        try:
            if sort_backend not in ('auto', 'opengl', 'torch'):
                raise ValueError(f"Unknown sort backend: {sort_backend}")
            if sort_backend in ('auto', 'torch'):
                import torch
                if not torch.cuda.is_available():
                    raise RuntimeError("torch.cuda is not available")
                self.sort = self.torch_sort
                self.sort_backend = 'torch'
            else:
                self.sort = self.openg_sort
        except Exception as exc:
            if sort_backend == 'torch':
                print(f"[GaussianItem] CUDA sort unavailable, fallback to OpenGL sort: {exc}")
            self.sort = self.openg_sort

    @property
    def gs_data(self):
        return self.gpu_data.gs_data

    @gs_data.setter
    def gs_data(self, value):
        self.gpu_data.gs_data = np.ascontiguousarray(value, dtype=np.float32)
        if self.gpu_data.gs_data.ndim == 2 and self.gpu_data.gs_data.shape[1] >= 11:
            self.gpu_data.sh_dim = self.gpu_data.gs_data.shape[1] - 11

    @property
    def sh_dim(self):
        return self.gpu_data.sh_dim

    @sh_dim.setter
    def sh_dim(self, value):
        self.gpu_data.sh_dim = int(value)

    @property
    def need_updateGS(self):
        return self.gpu_data.need_update

    @need_updateGS.setter
    def need_updateGS(self, value):
        self.gpu_data.need_update = bool(value)

    @property
    def num_sort(self):
        return self.gpu_data.num_sort

    @num_sort.setter
    def num_sort(self, value):
        self.gpu_data.num_sort = int(value)

    def _buffer_property(name):
        def getter(self):
            return getattr(self.gpu_data, name)

        def setter(self, value):
            setattr(self.gpu_data, name, value)

        return property(getter, setter)

    ssbo_gs = _buffer_property('ssbo_gs')
    ssbo_gi = _buffer_property('ssbo_gi')
    ssbo_dp = _buffer_property('ssbo_dp')
    ssbo_pp = _buffer_property('ssbo_pp')
    ssbo_preview_gi = _buffer_property('ssbo_preview_gi')

    def add_setting(self, layout):
        label_render_mode = QLabel("Render Mode:")
        layout.addWidget(label_render_mode)
        combo = QComboBox()
        combo.addItem("render normal guassian")
        combo.addItem("render ball")
        combo.addItem("render inverse guassian")
        combo.currentIndexChanged.connect(self.onComboboxSelection)
        layout.addWidget(combo)

    def onComboboxSelection(self, index):
        glUseProgram(self.program)
        set_uniform(self.program, index, 'render_mod')
        glUseProgram(0)

    def initialize_gl(self):
        if os.environ.get('Q3D_DEBUG'):
            version = glGetString(GL_VERSION)
            shading = glGetString(GL_SHADING_LANGUAGE_VERSION)
            renderer = glGetString(GL_RENDERER)
            print(f"[GaussianItem] GL_VERSION={version.decode() if version else 'unknown'}")
            print(f"[GaussianItem] GLSL_VERSION={shading.decode() if shading else 'unknown'}")
            print(f"[GaussianItem] GL_RENDERER={renderer.decode() if renderer else 'unknown'}")
            print(f"[GaussianItem] sort_enabled={self.sort_enabled} sort_backend={self.sort_backend}")

        fragment_shader = open(
            self.path + '/../shaders/gau_frag.glsl', 'r').read()
        vertex_shader = open(
            self.path + '/../shaders/gau_vert.glsl', 'r').read()
        prep_shader = open(self.path + '/../shaders/gau_prep.glsl', 'r', encoding='utf-8').read()

        self.sort_program = None
        if self.sort_backend == 'opengl':
            sort_shader = open(
                self.path + '/../shaders/sort_by_key.glsl', 'r').read()
            self.sort_program = shaders.compileProgram(
                shaders.compileShader(sort_shader, GL_COMPUTE_SHADER),
                validate=False)

        self.prep_program = shaders.compileProgram(
            shaders.compileShader(prep_shader, GL_COMPUTE_SHADER),
            validate=False)

        self.program = shaders.compileProgram(
            shaders.compileShader(vertex_shader, GL_VERTEX_SHADER),
            shaders.compileShader(fragment_shader, GL_FRAGMENT_SHADER),
            validate=False,
        )
        self.vao = glGenVertexArrays(1)

        # trade a gaussian as a square (4 2d points)
        square_vert = np.array([-1, 1, 1, 1, 1, -1, -1, -1], dtype=np.float32)
        indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)

        # set the vertices for square
        self.vbo = glGenBuffers(1)
        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, square_vert.nbytes,
                     square_vert, GL_STATIC_DRAW)
        pos = glGetAttribLocation(self.program, 'vert')
        raw_glVertexAttribPointer(pos, 2, GL_FLOAT, False, 0, ctypes.c_void_p(0))
        glEnableVertexAttribArray(pos)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        # the vert's indices for drawing square
        self.ebo = glGenBuffers(1)
        glBindVertexArray(self.vao)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER,
                     indices.nbytes, indices, GL_STATIC_DRAW)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
        glBindVertexArray(0)

        # SSBO storage is shared by the splat and sphere render passes.
        self.gpu_data.initialize_gl()
        if self.sort_backend == 'opengl':
            try:
                self._sort_query = glGenQueries(1)
            except Exception:
                self._sort_query = 0

        self._update_viewport_uniforms(
            self.glwidget().current_width(),
            self.glwidget().current_height(),
        )

        # OpenGL settings
        glDisable(GL_CULL_FACE)
        glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)

    def _update_viewport_uniforms(self, width, height):
        """Refresh projection uniforms after widget or pixel-ratio changes."""
        width = max(int(width), 1)
        height = max(int(height), 1)
        project_matrix = self.glwidget().get_projection_matrix()
        focal_x = project_matrix[0, 0] * width / 2
        focal_y = project_matrix[1, 1] * height / 2
        glUseProgram(self.prep_program)
        set_uniform(self.prep_program,
                    project_matrix, 'projection_matrix')
        set_uniform(self.prep_program, np.array([focal_x, focal_y]), 'focal')
        glUseProgram(0)

        glUseProgram(self.program)
        set_uniform(self.program, np.array([width, height]), 'win_size')
        set_uniform(self.program, 0, 'render_mod')
        glUseProgram(0)

    def resize_gl(self, width, height):
        self._update_viewport_uniforms(width, height)

    def updateGS(self):
        if (self.need_updateGS):
            if self.gs_data.shape[0] == 0:
                self.need_updateGS = False
                return False

            self.gpu_data.interactive_max_gaussians = self.interactive_max_gaussians
            self.gpu_data.upload_gl()
            self.num_sort = self.gpu_data.num_sort
            self._preview_count = self.gpu_data.preview_count

            glUseProgram(self.prep_program)
            set_uniform(self.prep_program, self.sh_dim, 'data_sh_dim')
            set_uniform(self.prep_program, self.sh_dim, 'render_sh_dim')
            set_uniform(self.prep_program,
                        self.gs_data.shape[0], 'gs_num')
            glUseProgram(0)
            self.need_updateGS = False
            self._defer_sort_once = True
            return True
        return False

    def paint(self):
        # get current view matrix
        self.view_matrix = self.glwidget().view_matrix

        # if gaussian data is update, renew vao, ssbo, etc...
        uploaded = self.updateGS()

        if (self.gs_data.shape[0] == 0):
            return
        if uploaded:
            # Split allocation, preprocessing and sorting across event-loop
            # turns so a large PLY does not monopolize one first paint.
            self.glwidget().update()
            return

        self._poll_sort_timer()

        # disable depth test to avoid z-fighting, we will sort the gaussian and draw them in back-to-front order to get correct blending result.
        glDisable(GL_DEPTH_TEST)

        # preprocess and sort gaussian by compute shader.
        draw_count = self.preprocessGS()
        if self.interactive_preview:
            glBindBufferBase(
                GL_SHADER_STORAGE_BUFFER, 1, self.ssbo_preview_gi
            )
        else:
            glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 1, self.ssbo_gi)
            if self._defer_sort_once:
                self._defer_sort_once = False
                self.glwidget().update()
            else:
                self.try_sort()
        # BaseGLWidget restores shared GL state between items, so establish the
        # premultiplied-alpha blend state at the draw site as well as at init.
        glBlendEquation(GL_FUNC_ADD)
        glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_BLEND)
        # draw by vert shader
        glUseProgram(self.program)
        # bind vao and ebo
        glBindVertexArray(self.vao)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        # draw instances
        raw_glDrawElementsInstanced(
            GL_TRIANGLES, 6, GL_UNSIGNED_INT, ctypes.c_void_p(0), draw_count)
        # upbind vao and ebo
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
        glBindVertexArray(0)
        glUseProgram(0)
        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)

    def try_sort(self):
        if not self.sort_enabled or self.sort_suspended:
            return
        # Camera translation adds the same offset to every view depth. Direction
        # and time thresholds keep large-model sorting within a stable budget.
        Rz = self.view_matrix[2, :3]
        direction_delta = np.linalg.norm(self.prev_Rz - Rz)
        now = time.monotonic()
        if (direction_delta > self.sort_direction_threshold
                and now - self._last_sort_time >= self.sort_min_interval):
            if (
                self.sort_backend == 'opengl'
                and self.max_bitonic_gaussians > 0
                and self.gs_data.shape[0] > self.max_bitonic_gaussians
            ):
                # Bitonic work grows as O(N log²N) and can monopolize an
                # integrated Jetson GPU for multi-million-splat models.
                # Preserve responsiveness until a radix/tile sorter is used.
                self.sort_skipped_large_model = True
                self.prev_Rz = Rz.copy()
                self._last_sort_time = now
                return
            self.sort_skipped_large_model = False
            # import torch
            # torch.cuda.synchronize()
            # start = time.time()
            self.sort()
            self.prev_Rz = Rz.copy()
            self._last_sort_time = now
            # torch.cuda.synchronize()
            # end = time.time()
            # time_diff = end - start
            # print(time_diff)

    def request_sort(self):
        """Force the next rendered frame to refresh the depth order."""
        self.prev_Rz = np.array([np.inf, np.inf, np.inf], dtype=np.float32)
        self._last_sort_time = float('-inf')

    def set_interactive_preview(self, enabled, max_gaussians=120000):
        """Trade transient interaction quality for lower Jetson GPU load."""
        enabled = bool(enabled)
        self.interactive_preview = enabled
        self.interactive_max_gaussians = max(0, int(max_gaussians))
        self.gpu_data.interactive_max_gaussians = self.interactive_max_gaussians
        self.sort_suspended = enabled
        # Keep prev_Rz unchanged while sorting is suspended. On the next frame
        # try_sort() then sorts only if orbiting changed the view direction.
        # Panning and plain clicks do not alter depth order and must not launch
        # the very expensive full-model bitonic sort.

    def openg_sort(self):
        if self.sort_program is None:
            return
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 1, self.ssbo_gi)
        glUseProgram(self.sort_program)
        level_loc = glGetUniformLocation(self.sort_program, 'level')
        stage_loc = glGetUniformLocation(self.sort_program, 'stage')
        pair_count_loc = glGetUniformLocation(self.sort_program, 'pair_count')

        timer_started = False
        if self._sort_query and not self._sort_query_pending:
            try:
                glBeginQuery(GL_TIME_ELAPSED, self._sort_query)
                timer_started = True
            except Exception:
                self._sort_query = 0
        dispatches = 0
        level = 2
        while level <= self.num_sort:
            stage = level // 2
            while stage >= 1:
                glUniform1ui(level_loc, int(level))
                glUniform1ui(stage_loc, int(stage))
                glUniform1ui(pair_count_loc, int(self.num_sort // 2))
                raw_glDispatchCompute(div_round_up(self.num_sort//2, 256), 1, 1)
                raw_glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT)
                dispatches += 1
                stage //= 2
            level *= 2
        if timer_started:
            glEndQuery(GL_TIME_ELAPSED)
            self._sort_query_pending = True
        self.last_sort_dispatches = dispatches
        glUseProgram(0)

    def _poll_sort_timer(self):
        if not self._sort_query or not self._sort_query_pending:
            return
        try:
            available = glGetQueryObjectiv(
                self._sort_query, GL_QUERY_RESULT_AVAILABLE
            )
            if available:
                nanoseconds = glGetQueryObjectui64v(
                    self._sort_query, GL_QUERY_RESULT
                )
                self.last_sort_gpu_ms = float(nanoseconds) / 1_000_000.0
                self._sort_query_pending = False
        except Exception:
            self._sort_query = 0
            self._sort_query_pending = False

    def torch_sort(self):
        import torch
        if self.cuda_pw is None:
            self.cuda_pw = torch.tensor(self.gs_data[:, :3]).cuda()
        Rz = torch.tensor(self.view_matrix[2, :3].astype(np.float32)).cuda()
        depth = Rz @ self.cuda_pw.T
        index = torch.argsort(depth).type(torch.int32).cpu().numpy()
        glBindBuffer(GL_SHADER_STORAGE_BUFFER, self.ssbo_gi)
        glBufferData(GL_SHADER_STORAGE_BUFFER,
                     index.nbytes, index, GL_STATIC_DRAW)
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 1, self.ssbo_gi)
        glBindBuffer(GL_SHADER_STORAGE_BUFFER, 0)
        return index

    def preprocessGS(self):
        active_count = self.gs_data.shape[0]
        if self.interactive_preview and self.interactive_max_gaussians > 0:
            active_count = min(
                getattr(self, '_preview_count', active_count),
                self.interactive_max_gaussians,
            )
        glUseProgram(self.prep_program)
        render_sh_dim = (
            min(self.sh_dim, 3)
            if self.interactive_preview
            else self.sh_dim
        )
        # The storage stride always uses the complete row width. Preview mode
        # may reduce SH evaluation work, but it must never reinterpret the
        # packed Gaussian buffer with a shorter row stride.
        set_uniform(self.prep_program, self.sh_dim, 'data_sh_dim')
        set_uniform(self.prep_program, render_sh_dim, 'render_sh_dim')
        set_uniform(self.prep_program, self.view_matrix, 'view_matrix')
        set_uniform(self.prep_program, self.gs_data.shape[0], 'gs_num')
        set_uniform(self.prep_program, active_count, 'dispatch_num')
        set_uniform(
            self.prep_program,
            1 if self.interactive_preview else 0,
            'preview_mode',
        )
        glBindBufferBase(
            GL_SHADER_STORAGE_BUFFER, 4, self.ssbo_preview_gi
        )
        raw_glDispatchCompute(div_round_up(active_count, 256), 1, 1)
        raw_glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT)
        glUseProgram(0)
        return active_count

    def set_data(self, **kwds):
        if 'gs_data' in kwds:
            gs_data = kwds.pop('gs_data')
            validated = bool(kwds.pop('validated', False))
            dropped = self.gpu_data.set_data(gs_data, validated=validated)
            if dropped:
                print(f"[GaussianItem] Dropped {dropped} non-finite gaussians")
            self.request_sort()
            self.cuda_pw = None

    def performance_metrics(self):
        """Non-blocking renderer counters for diagnostics/telemetry."""
        return {
            'gaussians': int(self.gpu_data.count),
            'preview_gaussians': int(
                getattr(self, '_preview_count', self.gpu_data.preview_count)
            ),
            'sort_dispatches': int(self.last_sort_dispatches),
            'sort_gpu_ms': self.last_sort_gpu_ms,
            'sort_skipped_large_model': self.sort_skipped_large_model,
            'estimated_gpu_bytes': int(
                self.gs_data.nbytes
                + self.gpu_data.num_sort * 8
                + self.gpu_data.count * 4 * 12
            ),
        }

    def release_gl(self):
        """Delete all shader programs and buffers owned by this item."""
        buffers = [
            getattr(self, name, 0)
            for name in (
                "vbo", "ebo",
            )
        ]
        buffers = [int(handle) for handle in buffers if handle]
        if buffers:
            glDeleteBuffers(len(buffers), buffers)
        vao = getattr(self, "vao", 0)
        if vao:
            glDeleteVertexArrays(1, [int(vao)])
        if self._sort_query:
            glDeleteQueries(1, [int(self._sort_query)])
            self._sort_query = 0
        for name in ("program", "prep_program", "sort_program"):
            program = getattr(self, name, None)
            if program:
                glDeleteProgram(int(program))
                setattr(self, name, None)
        self.gpu_data.release_gl()
        self.cuda_pw = None
        super().release_gl()
