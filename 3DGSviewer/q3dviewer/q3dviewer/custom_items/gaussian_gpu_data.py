"""Shared CPU/GPU ownership for Gaussian data used by multiple render passes."""

from __future__ import annotations

import math

import numpy as np

from q3dviewer.utils.gaussian_sphere import deterministic_preview_indices


class GaussianGpuData:
    """Own one packed Gaussian array and its reusable OpenGL storage buffers."""

    VALID_SH_DIMS = (3, 12, 27, 48)

    def __init__(self, interactive_max_gaussians=120000):
        self.gs_data = np.empty((0, 0), dtype=np.float32)
        self.sh_dim = 0
        self.interactive_max_gaussians = max(0, int(interactive_max_gaussians))
        self.need_update = False
        self.dropped_count = 0
        self.preview_indices = np.empty(0, dtype=np.uint32)
        self._preview_count = 0
        self.num_sort = 0
        self.ssbo_gs = 0
        self.ssbo_gi = 0
        self.ssbo_dp = 0
        self.ssbo_pp = 0
        self.ssbo_preview_gi = 0

    @property
    def count(self):
        return int(self.gs_data.shape[0])

    @property
    def row_width(self):
        return int(self.gs_data.shape[1]) if self.gs_data.ndim == 2 else 0

    @property
    def preview_count(self):
        return int(self._preview_count)

    def set_data(self, gs_data, validated=False):
        values = np.asarray(gs_data, dtype=np.float32)
        if values.ndim != 2:
            raise ValueError("Gaussian data must be a two-dimensional array")
        if values.shape[1] < 14:
            raise ValueError("Gaussian data is missing the required payload fields")
        if not validated:
            finite = np.isfinite(values).all(axis=1)
            self.dropped_count = int(values.shape[0] - np.count_nonzero(finite))
            if self.dropped_count:
                values = values[finite]
        else:
            self.dropped_count = 0
        sh_dim = int(values.shape[1] - (3 + 4 + 3 + 1))
        if sh_dim not in self.VALID_SH_DIMS:
            raise ValueError(
                "Unsupported spherical-harmonics payload: {} floats; expected one of {}".format(
                    sh_dim, self.VALID_SH_DIMS
                )
            )
        self.gs_data = np.ascontiguousarray(values, dtype=np.float32)
        self.sh_dim = sh_dim
        self.preview_indices = np.empty(0, dtype=np.uint32)
        self._preview_count = 0
        self.need_update = True
        return self.dropped_count

    def build_preview_indices(self, max_gaussians=None):
        limit = (
            self.interactive_max_gaussians
            if max_gaussians is None
            else max(0, int(max_gaussians))
        )
        self.preview_indices = deterministic_preview_indices(self.count, limit)
        self._preview_count = int(self.preview_indices.shape[0])
        return self.preview_indices

    def initialize_gl(self):
        """Allocate reusable buffers; must be called with the GL context current."""

        if self.ssbo_gs:
            return
        from OpenGL.GL import glGenBuffers

        self.ssbo_gs = glGenBuffers(1)
        self.ssbo_gi = glGenBuffers(1)
        self.ssbo_dp = glGenBuffers(1)
        self.ssbo_pp = glGenBuffers(1)
        self.ssbo_preview_gi = glGenBuffers(1)

    def upload_gl(self):
        """Upload source, preview, sorting, and preprocess storage once."""

        if not self.need_update:
            return False
        if not self.ssbo_gs:
            raise RuntimeError("GaussianGpuData GL buffers are not initialized")
        if self.count == 0:
            self.need_update = False
            self.num_sort = 0
            self.build_preview_indices()
            return False

        from OpenGL.GL import (
            GL_DYNAMIC_DRAW,
            GL_SHADER_STORAGE_BUFFER,
            GL_STATIC_DRAW,
            glBindBuffer,
            glBindBufferBase,
            glBufferData,
        )

        self.num_sort = max(1, 1 << int(math.ceil(math.log2(self.count))))
        glBindBuffer(GL_SHADER_STORAGE_BUFFER, self.ssbo_gs)
        glBufferData(
            GL_SHADER_STORAGE_BUFFER,
            self.gs_data.nbytes,
            self.gs_data.reshape(-1),
            GL_STATIC_DRAW,
        )
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 0, self.ssbo_gs)
        self.build_preview_indices()
        glBindBuffer(GL_SHADER_STORAGE_BUFFER, self.ssbo_preview_gi)
        glBufferData(
            GL_SHADER_STORAGE_BUFFER,
            max(self.preview_indices.nbytes, 4),
            self.preview_indices,
            GL_STATIC_DRAW,
        )
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 4, self.ssbo_preview_gi)

        depth = np.full(self.num_sort, np.inf, dtype=np.float32)
        glBindBuffer(GL_SHADER_STORAGE_BUFFER, self.ssbo_dp)
        glBufferData(GL_SHADER_STORAGE_BUFFER, depth.nbytes, depth, GL_DYNAMIC_DRAW)
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 2, self.ssbo_dp)

        indices = np.arange(self.num_sort, dtype=np.uint32)
        glBindBuffer(GL_SHADER_STORAGE_BUFFER, self.ssbo_gi)
        glBufferData(GL_SHADER_STORAGE_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 1, self.ssbo_gi)

        glBindBuffer(GL_SHADER_STORAGE_BUFFER, self.ssbo_pp)
        glBufferData(
            GL_SHADER_STORAGE_BUFFER,
            self.count * 4 * 12,
            None,
            GL_STATIC_DRAW,
        )
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER, 3, self.ssbo_pp)
        glBindBuffer(GL_SHADER_STORAGE_BUFFER, 0)
        self.need_update = False
        return True

    def release_gl(self):
        """Release only buffers owned by this data owner."""

        from OpenGL.GL import glDeleteBuffers

        buffers = [
            int(handle)
            for handle in (
                self.ssbo_gs,
                self.ssbo_gi,
                self.ssbo_dp,
                self.ssbo_pp,
                self.ssbo_preview_gi,
            )
            if handle
        ]
        if buffers:
            glDeleteBuffers(len(buffers), buffers)
        self.ssbo_gs = 0
        self.ssbo_gi = 0
        self.ssbo_dp = 0
        self.ssbo_pp = 0
        self.ssbo_preview_gi = 0

    def performance_metrics(self):
        return {
            "gaussians": self.count,
            "preview_gaussians": self.preview_count,
            "estimated_data_bytes": int(self.gs_data.nbytes),
            "estimated_preprocess_bytes": int(self.count * 4 * 12),
            "estimated_sort_bytes": int(self.num_sort * 8),
        }


__all__ = ["GaussianGpuData"]
