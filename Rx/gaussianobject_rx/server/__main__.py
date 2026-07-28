"""Command-line entry point for the WSL/server receiver."""

from __future__ import annotations

import argparse
import logging
import signal
import threading
from pathlib import Path

from gaussianobject_rx.server.application import ReceiverApplication
from gaussianobject_rx.server.config import load_receiver_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Receive Tx tasks, run baseline, and return 3DGS.ply")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_receiver_config(args.config)
    stopped = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    application = ReceiverApplication(config)
    try:
        application.start()
        logging.getLogger(__name__).info("receiver listening on %s", application.server_url)
        stopped.wait()
    finally:
        application.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
