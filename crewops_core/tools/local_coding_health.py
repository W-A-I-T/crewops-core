from __future__ import annotations

import os
import urllib.error
import urllib.request


def _default_timeout() -> float:
    raw = os.getenv("LOCAL_CODING_AGENT_HEALTH_TIMEOUT", "5")
    try:
        return float(raw)
    except ValueError:
        return 5.0


def local_coding_agent_alive(base_url: str | None = None, timeout: float | None = None) -> bool:
    base = (base_url or os.getenv("LOCAL_CODING_AGENT_URL", os.getenv("OPENHANDS_API_URL", "http://localhost:3000"))).rstrip("/")
    request_timeout = _default_timeout() if timeout is None else timeout
    for url in (f"{base}/health", base):
        try:
            urllib.request.urlopen(url, timeout=request_timeout)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                return True
        except Exception:
            pass
    return False
