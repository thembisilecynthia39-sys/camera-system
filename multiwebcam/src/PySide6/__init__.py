"""Compatibility shim for running the app with PyQt5 on JetPack 5.

The project is written against PySide6. Ubuntu 20.04 based Jetson images
provide PyQt5 through apt, while PySide6 wheels are not always practical on
the device. These modules expose the small PySide6 surface used by the app.
"""

