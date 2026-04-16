"""Small context packs for crews and router dispatches."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from crewops_core.config.settings import get_memory_backend_status
from crewops_core.lib.jarvis_bridge import build_jarvis_context

PACKAGE_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = PACKAGE_DIR.parent
REPORTS_DIR = ROOT_DIR / "reports"
TASK_REPORTS_DIR = REPORTS_DIR / "tasks"
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "build",
    "create",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "please",
    "the",
    "this",
    "to",
    "what",
    "with",
    "write",
}


def _compact(text: str, limit: int = 220) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _task_type(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("fix", "bug", "debug", "implement", "build", "api", "code")):
        return "implementation"
    if any(word in lowered for word in ("research", "find", "scan", "analyze", "review")):
        return "research"
    if any(word in lowered for word in ("proposal", "draft", "write", "marketing", "sales", "outreach")):
        return "content"
    return "general"


def _query_terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", text.lower())
        if token not in _STOPWORDS
    }


def _artifact_candidates(dept: str) -> list[Path]:
    candidates: list[Path] = []
    if TASK_REPORTS_DIR.exists():
        candidates.extend(sorted(TASK_REPORTS_DIR.glob(f"{dept}-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:12])
        candidates.extend(sorted(TASK_REPORTS_DIR.glob("auto-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:6])

    for pattern in ("*.md", "*.txt", "*.json"):
        candidates.extend(
            sorted(
                [
                    path
                    for path in REPORTS_DIR.glob(pattern)
                    if path.is_file() and path.parent == REPORTS_DIR and path.name not in {"active_tasks.json", ".gitkeep"}
                ],
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )[:10]
        )

    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in candidates:
        if path in seen:
            continue
        deduped.append(path)
        seen.add(path)
    return deduped[:24]


def _artifact_preview(path: Path) -> str:
    try:
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in ("request", "result", "summary", "description", "status"):
                    value = data.get(key)
                    if isinstance(value, str) and value.strip():
                        return _compact(value)
                return _compact(json.dumps(data, ensure_ascii=False))
            return _compact(json.dumps(data, ensure_ascii=False))
        return _compact(path.read_text(encoding="utf-8"))
    except Exception:
        return ""


def _relevant_artifacts(task: str, dept: str, limit: int = 3) -> list[dict[str, Any]]:
    terms = _query_terms(task)
    scored: list[tuple[int, float, Path, str]] = []
    for path in _artifact_candidates(dept):
        preview = _artifact_preview(path)
        if not preview:
            continue
        haystack = f"{path.name} {preview}".lower()
        overlap = len(terms & _query_terms(haystack))
        recency = path.stat().st_mtime
        if overlap == 0 and len(scored) >= 6:
            continue
        scored.append((overlap, recency, path, preview))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    refs: list[dict[str, Any]] = []
    for overlap, _mtime, path, preview in scored[:limit]:
        refs.append(
            {
                "ref": str(path.relative_to(ROOT_DIR)),
                "kind": path.suffix.lstrip("."),
                "score": overlap,
                "preview": preview,
            }
        )
    return refs


def build_context_pack(task: str, dept: str) -> dict[str, Any]:
    digest = hashlib.sha256(f"{dept}:{task}".encode()).hexdigest()[:10]
    artifacts = _relevant_artifacts(task, dept)
    latest_artifact = artifacts[0]["ref"] if artifacts else None
    jarvis_context = build_jarvis_context(task, dept, artifacts, get_memory_backend_status())
    return {
        "task_ref": f"{dept}-{digest}",
        "task_type": _task_type(task),
        "active_goal_summary": _compact(task, limit=180),
        "goal_summary": jarvis_context["goal_summary"],
        "recent_events": jarvis_context["recent_events"],
        "memory_backend": jarvis_context["memory_backend"],
        "memory_refs": jarvis_context["memory_refs"],
        "artifact_refs": jarvis_context["artifact_refs"],
        "legacy_artifact_refs": artifacts,
        "constraints": jarvis_context["constraints"],
        "allowed_actions": jarvis_context["allowed_actions"],
        "recent_artifact_ref": latest_artifact,
    }


def serialize_context_pack(pack: dict[str, Any]) -> str:
    return json.dumps(pack, ensure_ascii=False, indent=2)


def prepend_context_pack(task: str, dept: str, pack: dict[str, Any] | None = None) -> str:
    active_pack = pack or build_context_pack(task, dept)
    return (
        "Use this compact operating context before you start. "
        "Treat referenced artifacts as pointers, not raw prompt content.\n\n"
        "[CONTEXT_PACK]\n"
        f"{serialize_context_pack(active_pack)}\n"
        "[/CONTEXT_PACK]\n\n"
        "User request:\n"
        f"{task}"
    )
