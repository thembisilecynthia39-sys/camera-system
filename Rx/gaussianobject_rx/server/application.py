"""Receiver lifecycle: HTTP listener plus reconstruction worker."""

from __future__ import annotations

import threading
from typing import Optional

from gaussianobject_rx.server.config import ReceiverConfig
from gaussianobject_rx.server.http_server import ReceiverHTTPServer
from gaussianobject_rx.server.service import ReceiverService


class ReceiverApplication:
    def __init__(self, config: ReceiverConfig) -> None:
        self.config = config
        self.service = ReceiverService(config)
        try:
            self.http_server = ReceiverHTTPServer((config.listen_host, config.listen_port), self.service)
        except Exception:
            self.service.stop()
            raise
        self._thread: Optional[threading.Thread] = None
        self._stopped = False

    @property
    def address(self):
        return self.http_server.server_address

    @property
    def server_url(self) -> str:
        host, port = self.address[:2]
        if host in {"", "0.0.0.0", "::"}:
            host = "127.0.0.1"
        return f"http://{host}:{port}"

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self.http_server.serve_forever, name="rx-http-server", daemon=False)
        self._thread.start()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._thread is not None:
            self.http_server.shutdown()
            self.http_server.server_close()
            self._thread.join(timeout=self.config.process_stop_timeout_seconds + 2)
            if self._thread.is_alive():
                raise RuntimeError("receiver HTTP server did not stop")
        else:
            self.http_server.server_close()
        self.service.stop()

    def __enter__(self) -> "ReceiverApplication":
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()
