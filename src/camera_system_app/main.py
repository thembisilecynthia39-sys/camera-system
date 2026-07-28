"""Command-line interface for the unified desktop application."""

from __future__ import annotations

import argparse
import logging
from typing import List, Optional

from camera_system_app import __version__
from camera_system_app.application.controller import ApplicationController
from camera_system_app.application.diagnostics import render_report
from camera_system_app.bootstrap import build_context, run_gui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="camera_system_app",
        description="Jetson 采集、重建与结果查看统一 Qt 应用",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="Camera System {}".format(__version__),
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="输出本机环境诊断并退出，不启动 Qt 图形界面",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="配合 --diagnose 输出 JSON",
    )
    parser.add_argument(
        "--project-root",
        help="显式指定三个子项目所在根目录；相对路径不按当前目录解析",
    )
    parser.add_argument(
        "--config",
        help="显式指定统一 JSON 或 YAML 配置文件",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="以窗口模式启动，不自动最大化",
    )
    parser.add_argument(
        "--smoke-test-ms",
        type=int,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        context = build_context(args.project_root, args.config)
        logger = logging.getLogger("camera_system_app.main")
        if args.diagnose:
            controller = ApplicationController(
                context.paths,
                context.settings_manager,
                context.settings,
                context.logs,
            )
            report = controller.diagnose()
            print(render_report(report, as_json=args.json))
            return 0 if report.is_usable else 1

        logger.info("Starting unified Qt shell")
        return run_gui(
            context,
            smoke_test_ms=args.smoke_test_ms,
            force_windowed=args.windowed,
        )
    except Exception as exc:
        logging.getLogger("camera_system_app.main").exception(
            "Application startup failed"
        )
        print("无法启动 Qt 界面：{}".format(exc))
        print("可运行 python -m camera_system_app --diagnose 查看环境。")
        return 2
