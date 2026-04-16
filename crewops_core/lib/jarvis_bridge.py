from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crewops_core.lib.jarvis_spine import (
    get_recent_events,
    get_setting,
    list_memories,
    search_memories,
    set_setting,
    suggestion_exists,
    stable_id,
    upsert_context_pack,
    upsert_entity,
    upsert_event,
    upsert_memory,
    upsert_suggestion,
)

PACKAGE_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = PACKAGE_DIR.parent
REPORTS_DIR = ROOT_DIR / "reports"
TASKS_FILE = REPORTS_DIR / "active_tasks.json"
TASK_REPORTS_DIR = REPORTS_DIR / "tasks"

DEFAULT_SEED_ENTITIES = {
    "entity_person_operator": ("person", "Operator", ["operator", "owner", "maintainer"]),
    "entity_project_runtime": ("project", "Runtime", ["runtime", "agent runtime", "local runtime"]),
    "entity_project_dashboard": ("project", "Dashboard", ["dashboard", "control plane"]),
}

GITHUB_HINTS = ("github", "pull request", "issue #", "gh ", "workflow", "actions", "repo", "commit")


def _seed_entities() -> dict[str, tuple[str, str, list[str]]]:
    payload = os.getenv("CREWOPS_CORE_SEED_ENTITIES", "").strip()
    if not payload:
        return DEFAULT_SEED_ENTITIES
    try:
        parsed = json.loads(payload)
    except Exception:
        return DEFAULT_SEED_ENTITIES
    entities: dict[str, tuple[str, str, list[str]]] = {}
    for entity_id, fields in parsed.items():
        if not isinstance(fields, dict):
            continue
        entities[entity_id] = (
            str(fields.get("entity_type", "project")),
            str(fields.get("name", entity_id)),
            [str(alias) for alias in fields.get("aliases", [])],
        )
    return entities or DEFAULT_SEED_ENTITIES


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _compact(text: str, limit: int = 220) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_text(path: Path, limit: int = 3000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception:
        return ""


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except Exception:
        return str(path)


def seed_entities() -> None:
    now = _now_iso()
    for entity_id, (entity_type, name, aliases) in _seed_entities().items():
        upsert_entity(
            {
                "entity_id": entity_id,
                "entity_type": entity_type,
                "name": name,
                "aliases": aliases,
                "metadata": {"seeded": True},
                "updated_at": now,
            }
        )


def resolve_entity_refs(text: str) -> list[str]:
    lowered = (text or "").lower()
    refs: list[str] = []
    for entity_id, (_kind, name, aliases) in _seed_entities().items():
        candidates = [name.lower(), *aliases]
        if any(_matches_entity_candidate(lowered, candidate) for candidate in candidates):
            refs.append(entity_id)
    return sorted(set(refs))


def _matches_entity_candidate(text: str, candidate: str) -> bool:
    if not candidate:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(candidate) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def ingest_active_tasks() -> int:
    data = _load_json(TASKS_FILE)
    if not isinstance(data, dict):
        return 0
    count = 0
    for task_id, task in data.items():
        if not isinstance(task, dict):
            continue
        request = str(task.get("request") or task.get("task") or "")
        result = str(task.get("result") or "")
        status = str(task.get("status") or "unknown")
        created_at = str(task.get("created_at") or task.get("started_at") or _now_iso())
        entity_refs = resolve_entity_refs(f"{request}\n{result}")
        payload = {
            "task_id": task_id,
            "dept": task.get("dept"),
            "request": _compact(request, 400),
            "result_preview": _compact(result, 400),
            "status": status,
        }
        upsert_event(
            {
                "source": "runtime",
                "source_key": f"task:{task_id}:{hashlib.sha256(_json_text(payload).encode()).hexdigest()[:12]}",
                "event_type": "task_outcome",
                "occurred_at": created_at,
                "entity_refs": entity_refs,
                "payload": payload,
                "privacy_class": "private",
                "confidence": 0.88,
            }
        )
        count += 1

        if any(hint in request.lower() for hint in GITHUB_HINTS):
            upsert_event(
                {
                    "source": "runtime",
                    "source_key": f"github-task:{task_id}:{status}",
                    "event_type": "github_context_detected",
                    "occurred_at": created_at,
                    "entity_refs": entity_refs,
                    "payload": payload,
                    "privacy_class": "private",
                    "confidence": 0.84,
                }
            )
    return count


def ingest_report_artifacts() -> int:
    if not REPORTS_DIR.exists():
        return 0
    count = 0
    candidates = list(REPORTS_DIR.glob("*.md")) + list(REPORTS_DIR.glob("*.txt")) + list(REPORTS_DIR.glob("*.json"))
    if TASK_REPORTS_DIR.exists():
        candidates.extend(TASK_REPORTS_DIR.glob("*.json"))
    for path in sorted({candidate for candidate in candidates if candidate.is_file()}):
        if path.name in {"active_tasks.json", ".gitkeep"}:
            continue
        stat = path.stat()
        text = _read_text(path, 2000)
        if not text.strip():
            continue
        entity_refs = resolve_entity_refs(f"{path.name}\n{text}")
        event_type = "artifact_updated" if stat.st_mtime > stat.st_ctime + 1 else "artifact_created"
        upsert_event(
            {
                "source": "artifact",
                "source_key": f"artifact:{_display_path(path)}:{int(stat.st_mtime)}:{stat.st_size}",
                "event_type": event_type,
                "occurred_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                "entity_refs": entity_refs,
                "payload": {
                    "path": _display_path(path),
                    "kind": path.suffix.lstrip("."),
                    "preview": _compact(text, 300),
                },
                "privacy_class": "private",
                "confidence": 0.72,
            }
        )
        count += 1
    return count


def _task_summary(payload: dict[str, Any]) -> str:
    request = payload.get("request") or payload.get("task") or ""
    result = payload.get("result_preview") or ""
    status = payload.get("status") or "unknown"
    return _compact(f"Task {status}: {request}. {result}", 240)


def promote_memories() -> int:
    events = get_recent_events(limit=200)
    promoted = 0
    now = _now_iso()

    for event in events[:80]:
        if event["event_type"] == "task_outcome":
            summary = _task_summary(event["payload"])
        elif event["event_type"].startswith("artifact_"):
            summary = _compact(
                f"Artifact {event['payload'].get('path')} changed: {event['payload'].get('preview', '')}",
                220,
            )
        else:
            summary = _compact(_json_text(event["payload"]), 220)

        upsert_memory(
            {
                "memory_id": f"episodic:{event['event_id']}",
                "memory_type": "episodic",
                "title": event["event_type"].replace("_", " "),
                "summary": summary,
                "payload": event["payload"],
                "importance_score": min(0.95, 0.45 + event["confidence"] / 2),
                "confidence_score": event["confidence"],
                "source_event_ids": [event["event_id"]],
                "entity_refs": event["entity_refs"],
                "status": "active",
                "updated_at": now,
            }
        )
        promoted += 1

    mention_counts: Counter[str] = Counter()
    source_map: defaultdict[str, list[str]] = defaultdict(list)
    for event in events:
        for entity_ref in event["entity_refs"]:
            mention_counts[entity_ref] += 1
            source_map[entity_ref].append(event["event_id"])

    seed_entities_map = _seed_entities()
    for entity_ref, count in mention_counts.items():
        if count < 2:
            continue
        label = seed_entities_map.get(entity_ref, ("entity", entity_ref, []))[1]
        upsert_memory(
            {
                "memory_id": f"semantic:{entity_ref}",
                "memory_type": "semantic",
                "title": f"{label} is active",
                "summary": f"{label} has appeared across {count} recent events and should stay in recall context.",
                "payload": {"mention_count": count, "entity_id": entity_ref},
                "importance_score": min(0.98, 0.5 + count * 0.08),
                "confidence_score": min(0.95, 0.55 + count * 0.1),
                "source_event_ids": source_map[entity_ref][-8:],
                "entity_refs": [entity_ref],
                "status": "active",
                "updated_at": now,
            }
        )
        promoted += 1

    active_focus = [
        memory
        for memory in list_memories(limit=50, status="active")
        if memory["memory_type"] in {"semantic", "episodic"}
    ][:8]
    if active_focus:
        upsert_memory(
            {
                "memory_id": "working:active_focus",
                "memory_type": "working",
                "title": "Current operating focus",
                "summary": "Recent activity suggests a cluster of related runtime and delivery work worth keeping close at hand.",
                "payload": {"memory_refs": [memory["memory_id"] for memory in active_focus]},
                "importance_score": 0.92,
                "confidence_score": 0.8,
                "source_event_ids": [event_id for memory in active_focus for event_id in memory["source_event_ids"][:2]][:10],
                "entity_refs": sorted({entity for memory in active_focus for entity in memory["entity_refs"]}),
                "status": "active",
                "updated_at": now,
            }
        )
        promoted += 1

    return promoted


def _create_suggestion_once(source_key: str, kind: str, message: str, backing_memory_ids: list[str], created_at: str) -> int:
    suggestion_id = stable_id("sg", source_key)
    if suggestion_exists(suggestion_id):
        return 0
    upsert_suggestion(
        {
            "suggestion_id": suggestion_id,
            "source_key": source_key,
            "kind": kind,
            "message": message,
            "backing_memory_ids": backing_memory_ids,
            "status": "pending",
            "created_at": created_at,
        }
    )
    return 1


def generate_suggestions() -> int:
    settings = get_setting(
        "jarvis_settings",
        {
            "enabled": True,
            "mode": "suggest-only",
            "categories": {
                "daily_brief": True,
                "github_followups": True,
                "project_focus": True,
            },
        },
    )
    if not settings.get("enabled", True):
        return 0

    now = datetime.now(UTC)
    memories = list_memories(limit=100, status="active")
    created = 0

    entity_counts: Counter[str] = Counter()
    for memory in memories:
        for entity_ref in memory["entity_refs"]:
            entity_counts[entity_ref] += 1

    seed_map = _seed_entities()
    if settings.get("categories", {}).get("project_focus", True):
        for entity_ref, count in entity_counts.items():
            if count < 3 or entity_ref not in seed_map:
                continue
            label = seed_map[entity_ref][1]
            created += _create_suggestion_once(
                source_key=f"focus:{entity_ref}:{now.date().isoformat()}",
                kind="project_focus",
                message=f"Recent activity keeps circling back to {label}. Want a recap or next-step draft?",
                backing_memory_ids=[f"semantic:{entity_ref}"],
                created_at=now.isoformat(),
            )

    if settings.get("categories", {}).get("github_followups", True):
        for memory in memories:
            if memory["memory_type"] != "episodic":
                continue
            payload = memory["payload"]
            if payload.get("status") not in {"failed", "awaiting_human", "pending_approval"}:
                continue
            request = str(payload.get("request", ""))
            if not any(hint in request.lower() for hint in GITHUB_HINTS):
                continue
            created += _create_suggestion_once(
                source_key=f"github-followup:{payload.get('task_id')}:{payload.get('status')}",
                kind="github_followup",
                message=f"Repository work looks stalled on task `{payload.get('task_id')}`. Want a blocker summary or follow-up draft?",
                backing_memory_ids=[memory["memory_id"]],
                created_at=now.isoformat(),
            )

    if settings.get("categories", {}).get("daily_brief", True):
        created += _create_suggestion_once(
            source_key=f"daily-brief:{now.date().isoformat()}",
            kind="daily_brief",
            message="Want a compact operating brief from the latest task and artifact history?",
            backing_memory_ids=[memory["memory_id"] for memory in memories[:6]],
            created_at=now.isoformat(),
        )

    return created


def build_jarvis_context(task: str, dept: str, artifacts: list[dict[str, Any]], memory_backend: dict[str, Any]) -> dict[str, Any]:
    recent_events = get_recent_events(limit=6)
    memory_refs = search_memories(task, limit=4)
    payload = {
        "goal_summary": _compact(task, 180),
        "recent_events": [
            {"event_type": event["event_type"], "summary": _compact(_json_text(event["payload"]), 180)}
            for event in recent_events
        ],
        "memory_backend": memory_backend,
        "memory_refs": [
            {"memory_id": memory["memory_id"], "title": memory["title"], "summary": memory["summary"]}
            for memory in memory_refs
        ],
        "artifact_refs": artifacts,
        "constraints": ["Stay local-first where possible.", "Treat artifact refs as pointers, not full prompt context."],
        "allowed_actions": ["suggest", "draft", "summarize"],
    }
    upsert_context_pack(
        pack_id=stable_id("pack", dept, task),
        task_ref=stable_id("task", dept, task),
        dept=dept,
        payload=payload,
        created_at=_now_iso(),
    )
    return payload


def ensure_default_settings() -> None:
    seed_entities()
    if get_setting("jarvis_settings") is None:
        set_setting(
            "jarvis_settings",
            {
                "enabled": True,
                "mode": "suggest-only",
                "categories": {
                    "daily_brief": True,
                    "github_followups": True,
                    "project_focus": True,
                },
            },
        )


def sync_bridge_state() -> dict[str, int]:
    ensure_default_settings()
    tasks = ingest_active_tasks()
    artifacts = ingest_report_artifacts()
    promoted = promote_memories()
    suggestions = generate_suggestions()
    return {
        "tasks": tasks,
        "artifacts": artifacts,
        "promoted": promoted,
        "suggestions": suggestions,
    }
