"""Central logging setup and log-tail access."""

from __future__ import annotations

import logging
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOGGER_NAME = "camera_system_app"
MANAGED_LOGGERS = ("camera_system_app", "multiwebcam", "tx_rx", "q3dviewer")


class LogService:
    """Read-only application log access for the diagnostics page."""

    def __init__(self, log_file: Path) -> None:
        self.log_file = log_file

    def tail(self, max_lines: int = 300) -> str:
        if not self.log_file.exists():
            return "日志文件尚未生成。"
        with self.log_file.open("r", encoding="utf-8", errors="replace") as handle:
            lines = deque(handle, maxlen=max(1, max_lines))
        return "".join(lines)


def configure_logging(log_file: Path, level_name: str) -> LogService:
    """Configure the application logger once and return its reader."""

    level = getattr(logging, level_name.upper(), logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    for name in MANAGED_LOGGERS:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return LogService(log_file)
