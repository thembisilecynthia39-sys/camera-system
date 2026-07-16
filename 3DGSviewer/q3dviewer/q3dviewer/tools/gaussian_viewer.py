#!/usr/bin/env python3

"""
Copyright 2024 Panasonic Advanced Technology Development Co.,Ltd. (Liu Yang)
Distributed under MIT license. See LICENSE for more information.
"""

import numpy as np
import q3dviewer as q3d
import os
import time
from math import radians
from q3dviewer.utils.cloud_io import load_gs, rotate_gaussian
from q3dviewer.Qt.QtCore import Qt
from q3dviewer.Qt.QtGui import QSurfaceFormat


class GaussianGLWidget(q3d.GLWidget):
    def __init__(self):
        super().__init__()
        self.auto_orbit = False
        self.orbit_speed_deg = 20.0
        self._last_orbit_time = time.monotonic()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_O:
            self.auto_orbit = not self.auto_orbit
            self._last_orbit_time = time.monotonic()
            print(f"[GaussianViewer] Auto orbit {'ON' if self.auto_orbit else 'OFF'}")
            return
        super().keyPressEvent(ev)

    def mousePressEvent(self, ev):
        self.auto_orbit = False
        super().mousePressEvent(ev)

    def update(self):
        if self.auto_orbit:
            now = time.monotonic()
            dt = min(now - self._last_orbit_time, 0.1)
            self._last_orbit_time = now
            self.rotate(0, 0, radians(self.orbit_speed_deg * dt))
        else:
            self._last_orbit_time = time.monotonic()
        super().update()

    def rotate(self, rx=0, ry=0, rz=0):
        self.euler += np.array([rx, ry, rz])
        self.euler = (self.euler + np.pi) % (2 * np.pi) - np.pi
        self.need_recalc_view = True


class GuassianViewer(q3d.Viewer):
    def __init__(self, **kwds):
        super(GuassianViewer, self).__init__(**kwds)
        self.setAcceptDrops(True)
        self.max_gaussians = 0
        self.full_sh = True

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            self.open_gs_file(file_path)

    def open_gs_file(self, file):
        gau_item = self['gaussian']
        if gau_item is None:
            print("Can't find gaussianitem")
            return

        print("Try to load %s ..." % file)
        gs = load_gs(file)
        max_gaussians = getattr(self, 'max_gaussians', 0)
        if max_gaussians and gs.shape[0] > max_gaussians:
            idx = np.linspace(0, gs.shape[0] - 1, max_gaussians, dtype=np.int64)
            gs = gs[idx]
            print(f"[GaussianViewer] Preview decimated to {gs.shape[0]} gaussians")
        # convert camera optical frame (b) to camera frame (c).
        # Rcb = np.array([[0, -1, 0],
        #                 [0, 0, -1],
        #                 [1, 0, 0]]).T
        # gs = rotate_gaussian(Rcb, gs)
        gs_data = gs.view(np.float32).reshape(gs.shape[0], -1)
        if not self.full_sh and gs_data.shape[1] > 14:
            gs_data = gs_data[:, :14]
            print("[GaussianViewer] Fast color preview: DC color only")
        gau_item.set_data(gs_data=gs_data)
        self.fit_to_gaussians(gs)

    def fit_to_gaussians(self, gs):
        if gs.shape[0] == 0:
            return

        points = np.asarray(gs['pw'], dtype=np.float32)
        finite = np.isfinite(points).all(axis=1)
        points = points[finite]
        if points.shape[0] == 0:
            return

        lo = np.percentile(points, 1, axis=0)
        hi = np.percentile(points, 99, axis=0)
        center = (lo + hi) * 0.5
        radius = np.linalg.norm(hi - lo) * 0.5
        distance = max(float(radius) * 2.5, 1.0)
        self.glwidget.set_cam_position(center=center, distance=distance)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--path", help="3D Gaussian .ply or .npy file")
    parser.add_argument("--auto-orbit", action="store_true",
                        help="start with automatic 360-degree orbit enabled")
    parser.add_argument("--orbit-speed", type=float, default=20.0,
                        help="automatic orbit speed in degrees per second")
    parser.add_argument("--max-gaussians", type=int, default=0,
                        help="maximum gaussians to draw; default 0 keeps the full scene")
    sort_group = parser.add_mutually_exclusive_group()
    sort_group.add_argument("--sort", dest="sort", action="store_true",
                            help="enable view-depth sorting (default)")
    sort_group.add_argument("--no-sort", dest="sort", action="store_false",
                            help="disable sorting for a faster, lower-quality preview")
    parser.add_argument("--sort-backend", choices=("auto", "opengl", "torch"), default="auto",
                        help="depth sort backend; torch uses CUDA when PyTorch CUDA is available")
    sh_group = parser.add_mutually_exclusive_group()
    sh_group.add_argument("--full-sh", dest="full_sh", action="store_true",
                          help="use all spherical-harmonics colors (default)")
    sh_group.add_argument("--dc-only", dest="full_sh", action="store_false",
                          help="use only the DC color for a faster preview")
    parser.set_defaults(sort=True, full_sh=True)
    parser.add_argument("--fast-preview", action="store_true",
                        help="shortcut for --max-gaussians 120000 --no-sort --dc-only")
    parser.add_argument("--full-quality", action="store_true",
                        help="shortcut for --max-gaussians 0 --sort --full-sh")
    args = parser.parse_args()
    if args.full_quality:
        args.max_gaussians = 0
        args.sort = True
        args.full_sh = True
    elif args.fast_preview:
        args.max_gaussians = 120000
        args.sort = False
        args.full_sh = False

    os.environ.setdefault("QT_OPENGL", "desktop")
    os.environ.setdefault("QT_XCB_GL_INTEGRATION", "xcb_egl")

    fmt = QSurfaceFormat()
    fmt.setRenderableType(QSurfaceFormat.OpenGL)
    fmt.setVersion(4, 3)
    fmt.setProfile(QSurfaceFormat.CompatibilityProfile)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)
    try:
        q3d.QApplication.setAttribute(Qt.AA_UseDesktopOpenGL)
    except AttributeError:
        pass

    app = q3d.QApplication(['Guassian Viewer'])
    viewer = GuassianViewer(name='Guassian Viewer',
                            gl_widget_class=GaussianGLWidget)
    viewer.resize(960, 720)
    viewer.glwidget.set_color(np.array([0.45, 0.45, 0.45, 1.0]))
    viewer.glwidget.auto_orbit = args.auto_orbit
    viewer.glwidget.orbit_speed_deg = args.orbit_speed
    viewer.max_gaussians = args.max_gaussians
    viewer.full_sh = args.full_sh

    gau_item = q3d.GaussianItem(sort_enabled=args.sort,
                                sort_backend=args.sort_backend)

    viewer.add_items({'gaussian': gau_item})
    if args.path:
        viewer.open_gs_file(args.path)

    viewer.show()
    app.exec()


if __name__ == '__main__':
    main()
