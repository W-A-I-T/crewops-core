import json

from crewops_core.lib import jarvis_bridge
from crewops_core.lib.jarvis_spine import get_db_path, list_memories, list_suggestions, update_memory_status


def test_sync_bridge_state_promotes_events_and_suggestions(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    tasks_dir = reports_dir / "tasks"
    tasks_dir.mkdir()

    monkeypatch.setenv("JARVIS_SPINE_DB_PATH", str(tmp_path / "jarvis.db"))
    monkeypatch.setattr(jarvis_bridge, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(jarvis_bridge, "TASKS_FILE", reports_dir / "active_tasks.json")
    monkeypatch.setattr(jarvis_bridge, "TASK_REPORTS_DIR", tasks_dir)

    (reports_dir / "active_tasks.json").write_text(
        json.dumps(
            {
                "task-1": {
                    "dept": "software",
                    "request": "Check GitHub workflow failure for runtime package",
                    "result": "Waiting on fix",
                    "status": "awaiting_human",
                    "created_at": "2026-03-28T12:00:00+00:00",
                }
            }
        ),
        encoding="utf-8",
    )
    (reports_dir / "runtime-notes.md").write_text(
        "Runtime and dashboard were both updated today.",
        encoding="utf-8",
    )

    stats = jarvis_bridge.sync_bridge_state()

    assert get_db_path().exists()
    assert stats["tasks"] >= 1
    assert stats["artifacts"] >= 1
    memories = list_memories(limit=20)
    assert any(memory["memory_type"] == "episodic" for memory in memories)
    assert any(memory["memory_type"] == "semantic" for memory in memories)
    suggestions = list_suggestions(limit=20)
    assert any(suggestion["kind"] == "github_followup" for suggestion in suggestions)


def test_build_jarvis_context_includes_memory_and_actions(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    monkeypatch.setenv("JARVIS_SPINE_DB_PATH", str(tmp_path / "jarvis.db"))
    monkeypatch.setattr(jarvis_bridge, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(jarvis_bridge, "TASKS_FILE", reports_dir / "active_tasks.json")
    monkeypatch.setattr(jarvis_bridge, "TASK_REPORTS_DIR", reports_dir / "tasks")
    (reports_dir / "active_tasks.json").write_text("{}", encoding="utf-8")

    pack = jarvis_bridge.build_jarvis_context(
        "Summarize recent runtime progress",
        "software",
        [{"ref": "reports/demo.md", "kind": "md", "preview": "demo"}],
        {"enabled": False},
    )

    assert "goal_summary" in pack
    assert "recent_events" in pack
    assert "memory_refs" in pack
    assert pack["allowed_actions"] == ["suggest", "draft", "summarize"]


def test_memory_status_can_be_updated(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    tasks_dir = reports_dir / "tasks"
    tasks_dir.mkdir()
    monkeypatch.setenv("JARVIS_SPINE_DB_PATH", str(tmp_path / "jarvis.db"))
    monkeypatch.setattr(jarvis_bridge, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(jarvis_bridge, "TASKS_FILE", reports_dir / "active_tasks.json")
    monkeypatch.setattr(jarvis_bridge, "TASK_REPORTS_DIR", tasks_dir)
    (reports_dir / "active_tasks.json").write_text("{}", encoding="utf-8")
    (reports_dir / "runtime.md").write_text("Runtime moved forward today.", encoding="utf-8")

    jarvis_bridge.sync_bridge_state()
    memory = list_memories(limit=1)[0]
    assert update_memory_status(memory["memory_id"], "archived") is True
    assert list_memories(limit=5, status="archived")[0]["memory_id"] == memory["memory_id"]


def test_resolve_entity_refs_avoids_false_positive():
    refs = jarvis_bridge.resolve_entity_refs("Task is awaiting_human and waiting on review.")

    assert "entity_project_runtime" not in refs
