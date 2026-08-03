"""Display-mode orchestration for the shared Gaussian render passes."""

from __future__ import annotations

from q3dviewer.custom_items.gaussian_sphere_pass import GaussianSpherePass
from q3dviewer.custom_items.gaussian_splat_pass import GaussianSplatPass


class GaussianRenderController:
    """Switch standard/sphere/overlay drawing without reloading Gaussian data."""

    MODES = ("standard", "sphere_wireframe", "sphere_solid", "overlay")
    QUALITY_PRESETS = ("preview", "high", "final")

    def __init__(self, item):
        self.item = item
        self.splat_pass = GaussianSplatPass(item)
        self.sphere_pass = GaussianSpherePass(item.gpu_data)
        self.mode = "standard"
        self.quality = "high"

    def initialize_gl(self, shader_dir):
        self.sphere_pass.initialize_gl(shader_dir)

    def resize_gl(self, width, height):
        self.sphere_pass.resize_gl(width, height)

    def set_mode(self, mode):
        mode = str(mode).lower()
        if mode not in self.MODES:
            raise ValueError("unsupported Gaussian display mode: {}".format(mode))
        self.mode = mode
        if self.item.glwidget() is not None:
            self.item.glwidget().update()
        return self.mode

    def set_quality(self, quality):
        quality = str(quality).lower()
        if quality not in self.QUALITY_PRESETS:
            raise ValueError("unsupported Gaussian quality preset: {}".format(quality))
        self.quality = quality
        if quality == "preview":
            self.item.set_interactive_preview(True, max_gaussians=120000)
        else:
            self.item.set_interactive_preview(False)
        return self.quality

    def set_sphere_settings(self, **changes):
        settings = self.sphere_pass.set_settings(**changes)
        if self.item.glwidget() is not None:
            self.item.glwidget().update()
        return settings

    def paint(self):
        if self.mode == "standard":
            return self.splat_pass.paint()
        if self.item.need_updateGS:
            self.item.updateGS()
        if self.mode == "sphere_solid":
            return self.sphere_pass.paint(self.item, style="solid")
        if self.mode == "overlay":
            self.splat_pass.paint()
            return self.sphere_pass.paint(self.item, style="overlay")
        return self.sphere_pass.paint(self.item, style="wireframe")

    def performance_metrics(self):
        metrics = dict(self.item.gpu_data.performance_metrics())
        metrics.update(
            {
                "display_mode": self.mode,
                "quality": self.quality,
                "sphere_sigma_multiplier": self.sphere_pass.settings["sigma_multiplier"],
            }
        )
        return metrics

    def release_gl(self):
        if self.sphere_pass.program is not None:
            self.sphere_pass.release_gl()


__all__ = ["GaussianRenderController"]
