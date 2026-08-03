"""Sized OpenGL framebuffer targets used by stills and final video frames."""

from __future__ import annotations

import numpy as np
from OpenGL.GL import GL_RGBA, GL_UNSIGNED_BYTE, glReadPixels
from q3dviewer.Qt.QtGui import QOpenGLFramebufferObject


class RenderTargetError(ValueError):
    """Raised when a requested render target cannot be allocated safely."""


class RenderTarget:
    """Own one color/depth framebuffer while the q3dviewer context is current."""

    def __init__(self, width, height, max_dimension=8192):
        self.width, self.height = self.validate_size(width, height, max_dimension)
        self.fbo = QOpenGLFramebufferObject(
            self.width,
            self.height,
            QOpenGLFramebufferObject.CombinedDepthStencil,
        )
        if not self.fbo.isValid():
            self.fbo = None
            raise RenderTargetError("OpenGL render target allocation failed")

    @staticmethod
    def validate_size(width, height, max_dimension=8192):
        try:
            width = int(width)
            height = int(height)
            max_dimension = int(max_dimension)
        except (TypeError, ValueError):
            raise RenderTargetError("render target dimensions must be integers")
        if width <= 0 or height <= 0:
            raise RenderTargetError("render target dimensions must be positive")
        if max_dimension <= 0 or width > max_dimension or height > max_dimension:
            raise RenderTargetError("render target dimensions exceed the safety limit")
        return width, height

    def bind(self):
        if self.fbo is None or not self.fbo.bind():
            raise RenderTargetError("OpenGL render target could not be bound")

    def release(self):
        if self.fbo is not None:
            self.fbo.release()

    def read_rgba(self):
        if self.fbo is None:
            raise RenderTargetError("render target has already been released")
        pixels = glReadPixels(0, 0, self.width, self.height, GL_RGBA, GL_UNSIGNED_BYTE)
        frame = np.frombuffer(bytes(pixels), dtype=np.uint8)
        expected = self.width * self.height * 4
        if frame.size < expected:
            raise RenderTargetError("OpenGL render target readback returned incomplete pixels")
        return np.flip(frame[:expected].reshape(self.height, self.width, 4), 0).copy()


__all__ = ["RenderTarget", "RenderTargetError"]
