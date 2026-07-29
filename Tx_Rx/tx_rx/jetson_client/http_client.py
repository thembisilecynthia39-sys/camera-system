"""HTTP client helpers for direct Jetson-to-WSL communication."""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def direct_session(max_retries: int = 3) -> requests.Session:
    """Create a session that does not route private WSL traffic through env proxies."""

    session = requests.Session()
    session.trust_env = False
    retry_options = dict(
        total=max(0, int(max_retries)),
        connect=max(0, int(max_retries)),
        read=max(0, int(max_retries)),
        status=max(0, int(max_retries)),
        backoff_factor=0.3,
        status_forcelist=(429, 502, 503, 504),
        raise_on_status=False,
    )
    try:
        retry = Retry(
            allowed_methods=frozenset({"GET", "HEAD"}),
            **retry_options,
        )
    except TypeError:  # urllib3 < 1.26 on JetPack 5
        retry = Retry(
            method_whitelist=frozenset({"GET", "HEAD"}),
            **retry_options,
        )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def network_timeout(seconds: float, read_cap: float = None):
    """Return a short connect timeout plus the configured read budget."""

    configured = max(0.1, float(seconds))
    read_timeout = (
        configured
        if read_cap is None
        else min(configured, max(0.1, float(read_cap)))
    )
    return min(2.0, configured), read_timeout
