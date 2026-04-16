from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import NamedTuple

from crewops_core.lib.atomic_io import atomic_write_json

log = logging.getLogger(__name__)

_SOFT_LIMIT = 0.85


class _Quota(NamedTuple):
    rpm: int
    rpd: int
    tpm: int


_DEFAULT_LIMITS: dict[str, _Quota] = {
    "gemini/gemini-2.5-flash": _Quota(rpm=5, rpd=20, tpm=250_000),
    "gemini/gemini-2.0-flash": _Quota(rpm=15, rpd=200, tpm=1_000_000),
    "gemini/gemini-2.5-flash-lite": _Quota(rpm=10, rpd=20, tpm=250_000),
    "gemini/gemini-1.5-flash": _Quota(rpm=15, rpd=200, tpm=1_000_000),
}

_lock = threading.Lock()
_rpm_window: dict[str, deque[float]] = {}
_rpd_window: dict[str, deque[float]] = {}
_tpm_window: dict[str, deque[tuple[float, int]]] = {}
_STATE_FILE = Path(__file__).resolve().parents[2] / "store" / "rate_guard_state.json"
_callbacks_installed = False


def _env_override(model: str, kind: str, default: int) -> int:
    slug = model.split("/")[-1].replace("-", "_").replace(".", "_")
    value = os.getenv(f"GEMINI_{kind.upper()}_{slug}")
    return int(value) if value else default


def _get_limits(model: str) -> _Quota | None:
    default = _DEFAULT_LIMITS.get(model)
    if default is None:
        return None
    return _Quota(
        rpm=_env_override(model, "rpm", default.rpm),
        rpd=_env_override(model, "rpd", default.rpd),
        tpm=_env_override(model, "tpm", default.tpm),
    )


def _evict(dq: deque[float], window_secs: float) -> None:
    cutoff = time.monotonic() - window_secs
    while dq and dq[0] < cutoff:
        dq.popleft()


def _evict_rpd(dq: deque[float]) -> None:
    cutoff = time.time() - 86_400.0
    while dq and dq[0] < cutoff:
        dq.popleft()


def _evict_tpm(dq: deque[tuple[float, int]]) -> None:
    cutoff = time.monotonic() - 60.0
    while dq and dq[0][0] < cutoff:
        dq.popleft()


def _load_state() -> None:
    if not _STATE_FILE.exists():
        return
    try:
        payload = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    for model, timestamps in payload.get("rpd_window", {}).items():
        dq = deque(float(ts) for ts in timestamps)
        _evict_rpd(dq)
        if dq:
            _rpd_window[model] = dq


def _save_state() -> None:
    serializable: dict[str, list[float]] = {}
    for model, dq in _rpd_window.items():
        _evict_rpd(dq)
        if dq:
            serializable[model] = list(dq)
    atomic_write_json(_STATE_FILE, {"rpd_window": serializable}, indent=2)


def record_call(model: str, tokens: int = 0) -> None:
    if not model.startswith("gemini/"):
        return
    now = time.monotonic()
    now_wall = time.time()
    with _lock:
        _rpm_window.setdefault(model, deque()).append(now)
        _rpd_window.setdefault(model, deque()).append(now_wall)
        _tpm_window.setdefault(model, deque()).append((now, tokens))
        _save_state()


def is_near_limit(model: str) -> bool:
    limits = _get_limits(model)
    if limits is None:
        return False

    with _lock:
        rpm_dq = _rpm_window.get(model, deque())
        rpd_dq = _rpd_window.get(model, deque())
        tpm_dq = _tpm_window.get(model, deque())
        _evict(rpm_dq, 60.0)
        _evict_rpd(rpd_dq)
        _evict_tpm(tpm_dq)
        rpm_used = len(rpm_dq)
        rpd_used = len(rpd_dq)
        tpm_used = sum(tokens for _, tokens in tpm_dq)

    for kind, used, limit in (
        ("RPM", rpm_used, limits.rpm),
        ("RPD", rpd_used, limits.rpd),
        ("TPM", tpm_used, limits.tpm),
    ):
        if used >= limit * _SOFT_LIMIT:
            log.warning("rate_guard: %s %s %d/%d", model, kind, used, limit)
            return True
    return False


def get_usage() -> dict[str, dict[str, dict]]:
    result: dict[str, dict[str, dict]] = {}
    with _lock:
        all_models = set(_rpm_window) | set(_rpd_window) | set(_tpm_window)
        for model in all_models:
            rpm_dq = _rpm_window.get(model, deque())
            rpd_dq = _rpd_window.get(model, deque())
            tpm_dq = _tpm_window.get(model, deque())
            _evict(rpm_dq, 60.0)
            _evict_rpd(rpd_dq)
            _evict_tpm(tpm_dq)
            limits = _get_limits(model)
            result[model] = {
                "rpm": {"used": len(rpm_dq), "limit": limits.rpm if limits else None},
                "rpd": {"used": len(rpd_dq), "limit": limits.rpd if limits else None},
                "tpm": {"used": sum(tokens for _, tokens in tpm_dq), "limit": limits.tpm if limits else None},
            }
    return result


def install_callbacks() -> None:
    global _callbacks_installed
    if _callbacks_installed:
        return
    try:
        import litellm
    except ImportError:
        return

    def _on_success(kwargs: dict, response, start_time, end_time) -> None:  # noqa: ARG001
        model = kwargs.get("model", "")
        usage = getattr(response, "usage", None)
        tokens = getattr(usage, "total_tokens", 0) if usage else 0
        record_call(model, tokens)

    if _on_success not in litellm.success_callback:
        litellm.success_callback.append(_on_success)
    _callbacks_installed = True


with _lock:
    _load_state()
