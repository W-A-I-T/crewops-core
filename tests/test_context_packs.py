import json

from crewops_core.lib import context_packs
from crewops_core.lib.context_packs import build_context_pack, prepend_context_pack


def test_build_context_pack_has_expected_shape():
    pack = build_context_pack("Fix the summary output", "software")
    assert pack["task_ref"].startswith("software-")
    assert pack["task_type"] in {"implementation", "research", "content", "general"}
    assert pack["active_goal_summary"]
    assert "memory_backend" in pack
    assert "memory_refs" in pack


def test_prepend_context_pack_wraps_request():
    packed = prepend_context_pack("Write a follow-up note", "operations")
    assert "[CONTEXT_PACK]" in packed
    assert "User request:" in packed
    assert "Write a follow-up note" in packed


def test_context_pack_helpers_cover_artifact_paths(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    task_dir = reports_dir / "tasks"
    task_dir.mkdir(parents=True)
    (reports_dir / "notes.md").write_text("alpha beta gamma", encoding="utf-8")
    (reports_dir / "data.json").write_text(json.dumps({"summary": "beta summary"}), encoding="utf-8")
    (task_dir / "software-1.json").write_text(json.dumps({"result": "gamma result"}), encoding="utf-8")
    (reports_dir / "broken.json").write_text("{", encoding="utf-8")

    monkeypatch.setattr(context_packs, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(context_packs, "TASK_REPORTS_DIR", task_dir)
    monkeypatch.setattr(context_packs, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(
        context_packs,
        "build_jarvis_context",
        lambda task, dept, artifacts, memory_backend: {
            "goal_summary": task,
            "recent_events": [],
            "memory_backend": memory_backend,
            "memory_refs": [],
            "artifact_refs": artifacts,
            "constraints": [],
            "allowed_actions": ["suggest"],
        },
    )
    monkeypatch.setattr(context_packs, "get_memory_backend_status", lambda: {"enabled": False})

    assert context_packs._compact("x" * 300).endswith("...")
    assert context_packs._task_type("draft outreach email") == "content"
    assert context_packs._task_type("hello world") == "general"
    assert "beta" in context_packs._query_terms("Please write beta summary")

    candidates = context_packs._artifact_candidates("software")
    assert any(path.name == "software-1.json" for path in candidates)

    assert context_packs._artifact_preview(reports_dir / "broken.json") == ""
    refs = context_packs._relevant_artifacts("find beta gamma", "software", limit=2)
    assert refs

    pack = build_context_pack("find beta gamma", "software")
    assert pack["recent_artifact_ref"] is not None
