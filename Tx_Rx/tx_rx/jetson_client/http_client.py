"""HTTP client helpers for direct Jetson-to-WSL communication."""

from __future__ import annotations

import requests


def direct_session() -> requests.Session:
    """Create a session that does not route private WSL traffic through env proxies."""

    session = requests.Session()
    session.trust_env = False
    return session
