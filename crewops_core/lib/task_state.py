from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crewops_core.lib.atomic_io import atomic_write_json

PACKAGE_DIR = Path(__file__).resolve().parents[1]
TASKS_FILE = PACKAGE_DIR.parent / "reports" / "active_tasks.json"

_active_tasks: dict[str, dict[str, Any]] = {}


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def get_active_tasks() -> dict[str, dict[str, Any]]:
    return _active_tasks


def load_tasks() -> dict[str, dict[str, Any]]:
    if not TASKS_FILE.exists():
        _active_tasks.clear()
        return _active_tasks
    data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    _active_tasks.clear()
    _active_tasks.update(data)
    return _active_tasks


def save_tasks() -> None:
    atomic_write_json(TASKS_FILE, _active_tasks, ensure_ascii=False, default=str)


def ensure_task(task_id: str, **fields: Any) -> dict[str, Any]:
    task = _active_tasks.setdefault(task_id, {})
    if "created_at" not in task:
        task["created_at"] = fields.pop("created_at", utc_now_iso())
    task.update(fields)
    task["updated_at"] = utc_now_iso()
    return task


def update_task(task_id: str, persist: bool = False, **fields: Any) -> dict[str, Any]:
    task = ensure_task(task_id, **fields)
    if persist:
        save_tasks()
    return task


def append_task_list(task_id: str, key: str, item: Any, persist: bool = False) -> dict[str, Any]:
    task = ensure_task(task_id)
    task.setdefault(key, []).append(item)
    task["updated_at"] = utc_now_iso()
    if persist:
        save_tasks()
    return task
