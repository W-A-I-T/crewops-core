"""Shared local-first memory spine for the runtime."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

CREW_DIR = Path(__file__).resolve().parents[1]
STORE_DIR = CREW_DIR / "store"
DEFAULT_DB_PATH = STORE_DIR / "jarvis_spine.db"
_thread_local = threading.local()


def get_db_path() -> Path:
    raw = os.getenv("JARVIS_SPINE_DB_PATH", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_DB_PATH


def _connect() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    cached = getattr(_thread_local, "conn", None)
    cached_path = getattr(_thread_local, "db_path", None)
    if cached is not None and cached_path == str(db_path):
        try:
            cached.execute("SELECT 1")
            return cached
        except sqlite3.Error:
            try:
                cached.close()
            except Exception:
                pass
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(conn)
    _thread_local.conn = conn
    _thread_local.db_path = str(db_path)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS jarvis_events (
          event_id TEXT PRIMARY KEY,
          source TEXT NOT NULL,
          source_key TEXT NOT NULL UNIQUE,
          event_type TEXT NOT NULL,
          occurred_at TEXT NOT NULL,
          entity_refs TEXT NOT NULL,
          payload TEXT NOT NULL,
          privacy_class TEXT NOT NULL DEFAULT 'private',
          confidence REAL NOT NULL DEFAULT 0.5,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS jarvis_entities (
          entity_id TEXT PRIMARY KEY,
          entity_type TEXT NOT NULL,
          name TEXT NOT NULL,
          aliases TEXT NOT NULL,
          metadata TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jarvis_memories (
          memory_id TEXT PRIMARY KEY,
          memory_type TEXT NOT NULL,
          title TEXT NOT NULL,
          summary TEXT NOT NULL,
          payload TEXT NOT NULL,
          importance_score REAL NOT NULL DEFAULT 0.5,
          confidence_score REAL NOT NULL DEFAULT 0.5,
          source_event_ids TEXT NOT NULL,
          entity_refs TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jarvis_context_packs (
          pack_id TEXT PRIMARY KEY,
          task_ref TEXT NOT NULL,
          dept TEXT NOT NULL,
          payload TEXT NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jarvis_suggestions (
          suggestion_id TEXT PRIMARY KEY,
          source_key TEXT NOT NULL UNIQUE,
          kind TEXT NOT NULL,
          message TEXT NOT NULL,
          backing_memory_ids TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          created_at TEXT NOT NULL,
          sent_at TEXT
        );

        CREATE TABLE IF NOT EXISTS jarvis_settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256(
        "|".join(json.dumps(part, sort_keys=True, default=str) for part in parts).encode("utf-8")
    ).hexdigest()[:16]
    return f"{prefix}_{digest}"


def upsert_event(event: dict[str, Any]) -> str:
    source_key = event.get("source_key") or stable_id(
        "event_key",
        event.get("source"),
        event.get("event_type"),
        event.get("occurred_at"),
        event.get("payload"),
    )
    event_id = event.get("event_id") or stable_id("evt", source_key)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jarvis_events (
              event_id, source, source_key, event_type, occurred_at,
              entity_refs, payload, privacy_class, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
              source = excluded.source,
              source_key = excluded.source_key,
              event_type = excluded.event_type,
              occurred_at = excluded.occurred_at,
              entity_refs = excluded.entity_refs,
              payload = excluded.payload,
              privacy_class = excluded.privacy_class,
              confidence = excluded.confidence
            """,
            (
                event_id,
                event["source"],
                source_key,
                event["event_type"],
                event["occurred_at"],
                _json(event.get("entity_refs", [])),
                _json(event.get("payload", {})),
                event.get("privacy_class", "private"),
                float(event.get("confidence", 0.5)),
            ),
        )
        conn.commit()
    return event_id


def upsert_entity(entity: dict[str, Any]) -> str:
    entity_id = entity.get("entity_id") or stable_id(
        "entity", entity.get("entity_type"), entity.get("name")
    )
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jarvis_entities (entity_id, entity_type, name, aliases, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
              entity_type = excluded.entity_type,
              name = excluded.name,
              aliases = excluded.aliases,
              metadata = excluded.metadata,
              updated_at = excluded.updated_at
            """,
            (
                entity_id,
                entity["entity_type"],
                entity["name"],
                _json(entity.get("aliases", [])),
                _json(entity.get("metadata", {})),
                entity["updated_at"],
            ),
        )
        conn.commit()
    return entity_id


def upsert_memory(memory: dict[str, Any]) -> str:
    memory_id = memory.get("memory_id") or stable_id(
        "mem",
        memory.get("memory_type"),
        memory.get("title"),
        memory.get("entity_refs"),
    )
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jarvis_memories (
              memory_id, memory_type, title, summary, payload, importance_score,
              confidence_score, source_event_ids, entity_refs, status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(memory_id) DO UPDATE SET
              memory_type = excluded.memory_type,
              title = excluded.title,
              summary = excluded.summary,
              payload = excluded.payload,
              importance_score = excluded.importance_score,
              confidence_score = excluded.confidence_score,
              source_event_ids = excluded.source_event_ids,
              entity_refs = excluded.entity_refs,
              status = CASE
                WHEN jarvis_memories.status IN ('archived', 'dismissed')
                THEN jarvis_memories.status
                ELSE excluded.status
              END,
              updated_at = excluded.updated_at
            """,
            (
                memory_id,
                memory["memory_type"],
                memory["title"],
                memory["summary"],
                _json(memory.get("payload", {})),
                float(memory.get("importance_score", 0.5)),
                float(memory.get("confidence_score", 0.5)),
                _json(memory.get("source_event_ids", [])),
                _json(memory.get("entity_refs", [])),
                memory.get("status", "active"),
                memory["updated_at"],
            ),
        )
        conn.commit()
    return memory_id


def upsert_context_pack(pack_id: str, task_ref: str, dept: str, payload: dict[str, Any], created_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jarvis_context_packs (pack_id, task_ref, dept, payload, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(pack_id) DO UPDATE SET
              task_ref = excluded.task_ref,
              dept = excluded.dept,
              payload = excluded.payload,
              created_at = excluded.created_at
            """,
            (pack_id, task_ref, dept, _json(payload), created_at),
        )
        conn.commit()


def upsert_suggestion(suggestion: dict[str, Any]) -> str:
    source_key = suggestion.get("source_key") or stable_id(
        "suggestion_key",
        suggestion.get("kind"),
        suggestion.get("message"),
    )
    suggestion_id = suggestion.get("suggestion_id") or stable_id("sg", source_key)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jarvis_suggestions (
              suggestion_id, source_key, kind, message, backing_memory_ids, status, created_at, sent_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(suggestion_id) DO UPDATE SET
              source_key = excluded.source_key,
              kind = excluded.kind,
              message = excluded.message,
              backing_memory_ids = excluded.backing_memory_ids,
              status = excluded.status,
              created_at = excluded.created_at,
              sent_at = excluded.sent_at
            """,
            (
                suggestion_id,
                source_key,
                suggestion["kind"],
                suggestion["message"],
                _json(suggestion.get("backing_memory_ids", [])),
                suggestion.get("status", "pending"),
                suggestion["created_at"],
                suggestion.get("sent_at"),
            ),
        )
        conn.commit()
    return suggestion_id


def mark_suggestion_sent(suggestion_id: str, sent_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jarvis_suggestions SET status = 'sent', sent_at = ? WHERE suggestion_id = ?",
            (sent_at, suggestion_id),
        )
        conn.commit()


def update_memory_status(memory_id: str, status: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE jarvis_memories SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE memory_id = ?",
            (status, memory_id),
        )
        conn.commit()
        return cur.rowcount > 0


def get_recent_events(limit: int = 10) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jarvis_events
            ORDER BY occurred_at DESC, created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_event(row) for row in rows]


def list_memories(limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM jarvis_memories"
    params: list[Any] = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY importance_score DESC, updated_at DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_memory(row) for row in rows]


def search_memories(query: str, limit: int = 6) -> list[dict[str, Any]]:
    import re

    terms = {token for token in re.findall(r"[a-z0-9]{3,}", query.lower())}
    scored: list[tuple[float, dict[str, Any]]] = []
    for memory in list_memories(limit=200, status="active"):
        haystack = f"{memory['title']} {memory['summary']} {_json(memory['payload'])}".lower()
        overlap = sum(1 for token in terms if token in haystack)
        if overlap == 0 and terms:
            continue
        score = overlap * 2 + memory["importance_score"] + memory["confidence_score"]
        scored.append((score, memory))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [memory for _score, memory in scored[:limit]]


def suggestion_exists(suggestion_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM jarvis_suggestions WHERE suggestion_id = ? LIMIT 1",
            (suggestion_id,),
        ).fetchone()
    return row is not None


def list_suggestions(limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM jarvis_suggestions"
    params: list[Any] = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_suggestion(row) for row in rows]


def get_setting(key: str, default: Any = None) -> Any:
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM jarvis_settings WHERE key = ?",
            (key,),
        ).fetchone()
    if not row:
        return default
    return _loads(row["value"], default)


def set_setting(key: str, value: Any) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jarvis_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
              value = excluded.value,
              updated_at = CURRENT_TIMESTAMP
            """,
            (key, _json(value)),
        )
        conn.commit()


def get_entities() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jarvis_entities ORDER BY name ASC"
        ).fetchall()
    return [
        {
            "entity_id": row["entity_id"],
            "entity_type": row["entity_type"],
            "name": row["name"],
            "aliases": _loads(row["aliases"], []),
            "metadata": _loads(row["metadata"], {}),
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "source": row["source"],
        "source_key": row["source_key"],
        "event_type": row["event_type"],
        "occurred_at": row["occurred_at"],
        "entity_refs": _loads(row["entity_refs"], []),
        "payload": _loads(row["payload"], {}),
        "privacy_class": row["privacy_class"],
        "confidence": row["confidence"],
        "created_at": row["created_at"],
    }


def _row_to_memory(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "memory_id": row["memory_id"],
        "memory_type": row["memory_type"],
        "title": row["title"],
        "summary": row["summary"],
        "payload": _loads(row["payload"], {}),
        "importance_score": row["importance_score"],
        "confidence_score": row["confidence_score"],
        "source_event_ids": _loads(row["source_event_ids"], []),
        "entity_refs": _loads(row["entity_refs"], []),
        "status": row["status"],
        "updated_at": row["updated_at"],
    }


def _row_to_suggestion(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "suggestion_id": row["suggestion_id"],
        "source_key": row["source_key"],
        "kind": row["kind"],
        "message": row["message"],
        "backing_memory_ids": _loads(row["backing_memory_ids"], []),
        "status": row["status"],
        "created_at": row["created_at"],
        "sent_at": row["sent_at"],
    }
