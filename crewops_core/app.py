from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from crewops_core.config.settings import get_service_health_snapshot
from crewops_core.lib.jarvis_bridge import ensure_default_settings, sync_bridge_state
from crewops_core.lib.jarvis_spine import (
    list_memories,
    list_suggestions,
    update_memory_status,
)
from crewops_core.lib.task_state import (
    ensure_task,
    get_active_tasks,
    load_tasks,
    save_tasks,
)
from crewops_core.runtime import get_runtime


STATIC_DIR = Path(__file__).resolve().parent / "static"


class TaskRequest(BaseModel):
    dept: str = Field(description="Registered department name.")
    request: str = Field(description="Request text to send to the department handler.")


def _load_static_index() -> str:
    index_path = STATIC_DIR / "index.html"
    return index_path.read_text(encoding="utf-8")


def create_app() -> FastAPI:
    app = FastAPI(title="crewops-core", version="0.1.0")

    @app.on_event("startup")
    async def _startup() -> None:
        load_tasks()
        ensure_default_settings()

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def ui() -> str:
        return _load_static_index()

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        runtime = get_runtime()
        return {
            "status": "ok",
            "registered_departments": runtime.list_departments(),
            "active_tasks": len(get_active_tasks()),
        }

    @app.get("/api/services/health")
    async def services_health() -> dict[str, Any]:
        return get_service_health_snapshot()

    @app.post("/api/task")
    async def run_task(body: TaskRequest) -> dict[str, Any]:
        runtime = get_runtime()
        if body.dept.strip().lower() not in runtime.departments:
            raise HTTPException(status_code=404, detail=f"Unknown department: {body.dept}")

        task_id = f"task-{uuid.uuid4().hex[:10]}"
        ensure_task(task_id, dept=body.dept, request=body.request, status="running")
        save_tasks()

        try:
            result = runtime.dispatch(body.dept, body.request)
            result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
            ensure_task(task_id, status="completed", result=result_text)
            save_tasks()
            return {"task_id": task_id, "status": "completed", "result": result_text}
        except Exception as exc:
            ensure_task(task_id, status="failed", result=str(exc))
            save_tasks()
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/task/{task_id}")
    async def get_task(task_id: str) -> dict[str, Any]:
        task = get_active_tasks().get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @app.get("/api/jarvis/overview")
    async def get_jarvis_overview() -> dict[str, Any]:
        stats = sync_bridge_state()
        return {
            "sync": stats,
            "memory_count": len(list_memories(limit=50)),
            "suggestion_count": len(list_suggestions(limit=50)),
        }

    @app.get("/api/jarvis/memories")
    async def get_jarvis_memories(status: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        return list_memories(limit=limit, status=status)

    @app.post("/api/jarvis/memory/{memory_id}/status")
    async def set_jarvis_memory_status(memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = payload.get("status")
        if not isinstance(state, str):
            raise HTTPException(status_code=400, detail="Missing status")
        if not update_memory_status(memory_id, state):
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"ok": True}

    @app.get("/api/jarvis/suggestions")
    async def get_jarvis_suggestions(status: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        return list_suggestions(limit=limit, status=status)

    return app
