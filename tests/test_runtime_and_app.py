import json
import os
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from crewops_core.app import create_app
from crewops_core.config import rate_guard
from crewops_core.runtime import get_runtime, register_delivery_adapter, register_department, register_seed_entities


def _reset_runtime() -> None:
    runtime = get_runtime()
    runtime.departments.clear()
    runtime.seed_entities.clear()
    runtime.delivery_adapters.clear()


def _patch_runtime_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir(exist_ok=True)
    (tmp_path / "store").mkdir(exist_ok=True)

    from crewops_core.lib import jarvis_bridge, task_state

    monkeypatch.setattr(task_state, "TASKS_FILE", tmp_path / "reports" / "active_tasks.json")
    monkeypatch.setattr(jarvis_bridge, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(jarvis_bridge, "TASKS_FILE", tmp_path / "reports" / "active_tasks.json")
    monkeypatch.setattr(jarvis_bridge, "TASK_REPORTS_DIR", tmp_path / "reports" / "tasks")


def test_runtime_registry_registration_and_dispatch():
    _reset_runtime()
    runtime = get_runtime()
    runtime.register_department("Support", lambda request: f"handled:{request}")
    runtime.register_seed_entities({"entity_project_support": ("project", "Support", ["support"])})
    runtime.register_delivery_adapter("webhook", lambda payload: payload)

    assert runtime.list_departments() == ["support"]
    assert runtime.seed_entities["entity_project_support"][1] == "Support"
    assert runtime.delivery_adapters["webhook"]({"ok": True}) == {"ok": True}
    assert runtime.dispatch("support", "check queue") == "handled:check queue"

    runtime.departments.clear()
    runtime.seed_entities.clear()
    runtime.delivery_adapters.clear()
    register_department("ops", lambda request: request.upper())
    register_seed_entities({"entity_project_ops": ("project", "Ops", ["ops"])})
    register_delivery_adapter("stdout", lambda payload: payload["ok"])
    assert get_runtime().dispatch("ops", "go") == "GO"
    assert get_runtime().delivery_adapters["stdout"]({"ok": True}) is True


def test_runtime_registry_unknown_department_and_async_handler():
    _reset_runtime()
    runtime = get_runtime()

    try:
        runtime.dispatch("missing", "hello")
    except KeyError as exc:
        assert "Unknown department" in str(exc)
    else:
        raise AssertionError("Expected KeyError for unknown department")

    async def async_handler(request: str):
        return request

    runtime.register_department("async", async_handler)
    try:
        runtime.dispatch("async", "hello")
    except TypeError as exc:
        assert "Async department handlers are not supported" in str(exc)
    else:
        raise AssertionError("Expected TypeError for async handler")


def test_status_and_task_flow(tmp_path, monkeypatch):
    _reset_runtime()
    _patch_runtime_paths(tmp_path, monkeypatch)
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


def test_task_endpoint_unknown_dept_and_failure(tmp_path, monkeypatch):
    _reset_runtime()
    _patch_runtime_paths(tmp_path, monkeypatch)
    runtime = get_runtime()
    runtime.register_department("boom", lambda request: (_ for _ in ()).throw(RuntimeError("bad run")))

    client = TestClient(create_app())

    missing = client.post("/api/task", json={"dept": "missing", "request": "ship it"})
    assert missing.status_code == 404

    failed = client.post("/api/task", json={"dept": "boom", "request": "explode"})
    assert failed.status_code == 500
    assert failed.json()["detail"] == "bad run"


def test_task_lookup_missing_and_memory_status_paths(tmp_path, monkeypatch):
    _reset_runtime()
    _patch_runtime_paths(tmp_path, monkeypatch)
    client = TestClient(create_app())

    missing_task = client.get("/api/task/task-missing")
    assert missing_task.status_code == 404

    bad_payload = client.post("/api/jarvis/memory/demo/status", json={})
    assert bad_payload.status_code == 400

    import crewops_core.app as app_module

    monkeypatch.setattr(app_module, "update_memory_status", lambda memory_id, status: False)
    missing_memory = client.post("/api/jarvis/memory/demo/status", json={"status": "archived"})
    assert missing_memory.status_code == 404


def test_jarvis_endpoints_and_services_health(tmp_path, monkeypatch):
    _reset_runtime()
    _patch_runtime_paths(tmp_path, monkeypatch)
    client = TestClient(create_app())

    overview = client.get("/api/jarvis/overview")
    assert overview.status_code == 200
    assert "sync" in overview.json()

    memories = client.get("/api/jarvis/memories?limit=5")
    suggestions = client.get("/api/jarvis/suggestions?limit=5")
    health = client.get("/api/services/health")

    assert memories.status_code == 200
    assert suggestions.status_code == 200
    assert health.status_code == 200
    assert "services" in health.json()


def test_app_root_and_lifespan_startup(tmp_path, monkeypatch):
    _reset_runtime()
    _patch_runtime_paths(tmp_path, monkeypatch)
    runtime = get_runtime()
    runtime.register_department("software", lambda request: request)

    client = TestClient(create_app())
    with client:
        root = client.get("/")
        status = client.get("/api/status")
    assert root.status_code == 200
    assert "crewops-core" in root.text
    assert status.status_code == 200


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


def test_rate_guard_limits_and_callbacks(monkeypatch):
    rate_guard._rpm_window.clear()
    rate_guard._rpd_window.clear()
    rate_guard._tpm_window.clear()
    monkeypatch.setenv("GEMINI_RPM_gemini_2_5_flash", "1")
    rate_guard.record_call("gemini/gemini-2.5-flash")
    assert rate_guard.is_near_limit("gemini/gemini-2.5-flash") is True

    fake_litellm = SimpleNamespace(success_callback=[], failure_callback=[])
    monkeypatch.setitem(__import__("sys").modules, "litellm", fake_litellm)
    rate_guard._callbacks_installed = False
    rate_guard.install_callbacks()
    rate_guard.install_callbacks()
    assert len(fake_litellm.success_callback) == 1


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


def test_task_state_load_update_and_append(tmp_path, monkeypatch):
    from crewops_core.lib import task_state

    task_file = tmp_path / "reports" / "active_tasks.json"
    monkeypatch.setattr(task_state, "TASKS_FILE", task_file)
    task_state.get_active_tasks().clear()

    assert task_state.load_tasks() == {}
    task_file.parent.mkdir(parents=True)
    task_file.write_text(json.dumps({"task-1": {"status": "pending"}}), encoding="utf-8")
    assert task_state.load_tasks()["task-1"]["status"] == "pending"

    updated = task_state.update_task("task-1", description="hello")
    assert updated["description"] == "hello"

    listed = task_state.append_task_list("task-1", "results", {"ok": True})
    assert listed["results"] == [{"ok": True}]
