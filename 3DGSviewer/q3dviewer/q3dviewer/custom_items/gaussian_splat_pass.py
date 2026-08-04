"""Standard Gaussian splat pass kept behind the render-mode controller."""


class GaussianSplatPass:
    """Delegate the existing high-quality sorted splat path to GaussianItem."""

    def __init__(self, item):
        self.item = item

    def paint(self):
        return self.item.paint_standard()


__all__ = ["GaussianSplatPass"]
