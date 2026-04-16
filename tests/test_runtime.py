import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from crewops_core.app import create_app
from crewops_core.config import rate_guard
from crewops_core.runtime import get_runtime


def _reset_runtime() -> None:
    runtime = get_runtime()
    runtime.departments.clear()
    runtime.seed_entities.clear()
    runtime.delivery_adapters.clear()


def test_status_and_task_flow(tmp_path, monkeypatch):
    _reset_runtime()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "store").mkdir()

    from crewops_core.lib import task_state
    from crewops_core.lib import jarvis_bridge

    monkeypatch.setattr(task_state, "TASKS_FILE", tmp_path / "reports" / "active_tasks.json")
    monkeypatch.setattr(jarvis_bridge, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(jarvis_bridge, "TASKS_FILE", tmp_path / "reports" / "active_tasks.json")
    monkeypatch.setattr(jarvis_bridge, "TASK_REPORTS_DIR", tmp_path / "reports" / "tasks")

    runtime = get_runtime()
    runtime.register_department("software", lambda request: f"handled:{request}")

    client = TestClient(create_app())
    status = client.get("/api/status")
    assert status.status_code == 200
    assert "software" in status.json()["registered_departments"]

    response = client.post("/api/task", json={"dept": "software", "request": "ship it"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["result"] == "handled:ship it"

    task_response = client.get(f"/api/task/{body['task_id']}")
    assert task_response.status_code == 200
    assert task_response.json()["status"] == "completed"


def test_rate_guard_rpd_state_survives_restart(tmp_path, monkeypatch):
    state_file = tmp_path / "store" / "rate_guard_state.json"
    monkeypatch.setattr(rate_guard, "_STATE_FILE", state_file)
    rate_guard._rpm_window.clear()
    rate_guard._rpd_window.clear()
    rate_guard._tpm_window.clear()

    rate_guard.record_call("gemini/gemini-2.5-flash")
    assert state_file.exists()

    rate_guard._rpd_window.clear()
    rate_guard._load_state()
    usage = rate_guard.get_usage()
    assert usage["gemini/gemini-2.5-flash"]["rpd"]["used"] == 1


def test_task_state_save_is_atomic(tmp_path, monkeypatch):
    from crewops_core.lib import task_state

    task_file = tmp_path / "reports" / "active_tasks.json"
    monkeypatch.setattr(task_state, "TASKS_FILE", task_file)
    task_state.get_active_tasks().clear()
    task_state.ensure_task("task-atomic", status="pending")

    seen = {}
    original_replace = os.replace

    def fake_replace(src, dst):
        seen["src"] = Path(src)
        seen["dst"] = Path(dst)
        return original_replace(src, dst)

    monkeypatch.setattr("crewops_core.lib.atomic_io.os.replace", fake_replace)
    task_state.save_tasks()

    assert seen["dst"] == task_file
    assert seen["src"].name.startswith(f".{task_file.name}.")
    assert json.loads(task_file.read_text(encoding="utf-8"))["task-atomic"]["status"] == "pending"
