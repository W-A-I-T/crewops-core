from __future__ import annotations

import logging
import os
import threading
import time as _time
import urllib.request
from pathlib import Path
from typing import Any

from crewops_core.config import rate_guard
from crewops_core.tools.local_coding_health import local_coding_agent_alive

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in {"true", "1", "yes"}
SMART_ROUTER = "crewai" if DEMO_MODE else os.getenv("SMART_ROUTER", "enabled")

_settings_lock = threading.RLock()
_model_cache: tuple[str, float] | None = None
_MODEL_CACHE_TTL = 60.0
_rate_limited: dict[str, float] = {}
_RATE_LIMIT_TTL = 3600.0
_RATE_LIMIT_PHRASES = {
    "rate limit",
    "ratelimit",
    "rate_limit",
    "quota exceeded",
    "quota_exceeded",
    "resource_exhausted",
    "too many requests",
    "daily limit",
    "daily quota",
    "status 429",
    "code 429",
}


def _ollama_has(model: str) -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=2) as response:
            import json

            data = json.loads(response.read())
            names = [item["name"] for item in data.get("models", [])]
            return model.removeprefix("ollama/") in names
    except Exception:
        return False


def is_rate_limit_error(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _RATE_LIMIT_PHRASES)


def mark_rate_limited(model: str) -> None:
    global _model_cache
    with _settings_lock:
        _rate_limited[model] = _time.monotonic()
        _model_cache = None


def _is_available(model: str) -> bool:
    with _settings_lock:
        ts = _rate_limited.get(model)
    if ts is not None:
        if _time.monotonic() - ts > _RATE_LIMIT_TTL:
            with _settings_lock:
                _rate_limited.pop(model, None)
        else:
            return False
    return not rate_guard.is_near_limit(model)


def _pick_model() -> str:
    override = os.getenv("DEFAULT_MODEL")
    if override:
        return override

    global _model_cache
    now = _time.monotonic()
    with _settings_lock:
        cached = _model_cache
    if cached and now - cached[1] < _MODEL_CACHE_TTL:
        if cached[0].startswith("ollama/") or _is_available(cached[0]):
            return cached[0]

    if _ollama_has("qwen2.5:14b"):
        model = "ollama/qwen2.5:14b"
    elif _ollama_has("llama3.1:8b"):
        model = "ollama/llama3.1:8b"
    elif os.getenv("GEMINI_API_KEY") and _is_available("gemini/gemini-2.5-flash"):
        model = "gemini/gemini-2.5-flash"
    else:
        model = "gemini/gemini-2.5-flash"

    with _settings_lock:
        _model_cache = (model, now)
    return model


def get_llm():
    from crewai import LLM

    model = _pick_model()
    if model.startswith("ollama/"):
        return LLM(model=model, base_url=OLLAMA_BASE_URL, timeout=1800)
    return LLM(model=model)


def _default_memory_storage_path() -> str:
    storage_dir = os.getenv("CREWAI_STORAGE_DIR")
    if storage_dir:
        return str(Path(storage_dir) / "memory")
    from crewai.utilities.paths import db_storage_path

    return str(Path(db_storage_path()) / "memory")


def get_memory_backend_status() -> dict[str, Any]:
    storage_path = Path(_default_memory_storage_path())
    file_count = 0
    if storage_path.exists():
        try:
            file_count = sum(1 for path in storage_path.rglob("*") if path.is_file())
        except Exception:
            file_count = 0

    if os.getenv("NVIDIA_API_KEY", ""):
        return {
            "enabled": True,
            "provider": "nvidia",
            "model": "nvidia/nv-embedqa-e5-v5",
            "mode": "asymmetric",
            "storage_path": str(storage_path),
            "has_data": file_count > 0,
            "file_count": file_count,
            "reason": "NVIDIA_API_KEY present",
        }

    if os.getenv("GEMINI_API_KEY", ""):
        return {
            "enabled": True,
            "provider": "google",
            "model": "gemini-embedding-001",
            "mode": "symmetric",
            "storage_path": str(storage_path),
            "has_data": file_count > 0,
            "file_count": file_count,
            "reason": "Falling back to Gemini embeddings",
        }

    return {
        "enabled": False,
        "provider": None,
        "model": None,
        "mode": None,
        "storage_path": str(storage_path),
        "has_data": file_count > 0,
        "file_count": file_count,
        "reason": "Neither NVIDIA_API_KEY nor GEMINI_API_KEY is set",
    }


def get_service_health_snapshot() -> dict[str, Any]:
    ollama_ok = False
    try:
        urllib.request.urlopen(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=2)
        ollama_ok = True
    except Exception:
        ollama_ok = False

    return {
        "status": "ok",
        "services": {
            "ollama": ollama_ok,
            "local_coding_agent": local_coding_agent_alive(),
        },
    }
