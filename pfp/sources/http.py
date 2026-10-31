from __future__ import annotations

import threading
import time
from collections import defaultdict
from urllib.parse import urlsplit

import requests

USER_AGENT = "PlanetFrontPage/1.0 (+https://github.com/your-org/planet-front-page)"

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_last_call: dict[str, float] = defaultdict(float)
_lock = threading.Lock()

# Minimum seconds between requests to the same host. GDELT asks for one request every 5 s.
HOST_INTERVAL = {"api.gdeltproject.org": 5.5, "news.google.com": 1.0}
DEFAULT_INTERVAL = 0.5


def get(url: str, *, params: dict | None = None, timeout: float = 20) -> requests.Response:
    host = urlsplit(url).netloc
    wait = HOST_INTERVAL.get(host, DEFAULT_INTERVAL)
    with _lock:
        delay = _last_call[host] + wait - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        _last_call[host] = time.monotonic()
    for attempt in range(3):
        resp = _session.get(url, params=params, timeout=timeout)
        if resp.status_code in (429, 502, 503):
            time.sleep(wait * (attempt + 2))
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp
