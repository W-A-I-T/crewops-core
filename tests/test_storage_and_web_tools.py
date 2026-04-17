import builtins
import json
import os
import sys
import types

from crewops_core.lib import jarvis_spine
from crewops_core.tools import web_tools


def test_jarvis_spine_crud_and_queries(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_SPINE_DB_PATH", str(tmp_path / "jarvis.db"))
    jarvis_spine._thread_local = types.SimpleNamespace()

    event_id = jarvis_spine.upsert_event(
        {
            "source": "runtime",
            "event_type": "task_outcome",
            "occurred_at": "2026-04-16T00:00:00+00:00",
            "payload": {"request": "Ship runtime", "status": "done"},
            "entity_refs": ["entity_project_runtime"],
        }
    )
    jarvis_spine.upsert_entity(
        {
            "entity_type": "project",
            "name": "Runtime",
            "aliases": ["runtime"],
            "metadata": {"seeded": True},
            "updated_at": "2026-04-16T00:00:00+00:00",
        }
    )
    memory_id = jarvis_spine.upsert_memory(
        {
            "memory_type": "semantic",
            "title": "Runtime focus",
            "summary": "Runtime needs attention",
            "payload": {"request": "Ship runtime"},
            "source_event_ids": [event_id],
            "entity_refs": ["entity_project_runtime"],
            "updated_at": "2026-04-16T00:00:00+00:00",
        }
    )
    jarvis_spine.upsert_context_pack("pack-1", "task-1", "software", {"ok": True}, "2026-04-16T00:00:00+00:00")
    suggestion_id = jarvis_spine.upsert_suggestion(
        {
            "kind": "project_focus",
            "message": "Review runtime",
            "backing_memory_ids": [memory_id],
            "created_at": "2026-04-16T00:00:00+00:00",
        }
    )
    jarvis_spine.mark_suggestion_sent(suggestion_id, "2026-04-16T01:00:00+00:00")
    jarvis_spine.set_setting("jarvis_settings", {"enabled": True})

    assert jarvis_spine.get_recent_events(limit=1)[0]["event_id"] == event_id
    assert jarvis_spine.list_memories(limit=5, status="active")[0]["memory_id"] == memory_id
    assert jarvis_spine.search_memories("runtime")[0]["memory_id"] == memory_id
    assert jarvis_spine.search_memories("")  # empty term path
    assert jarvis_spine.suggestion_exists(suggestion_id) is True
    assert jarvis_spine.list_suggestions(limit=5, status="sent")[0]["suggestion_id"] == suggestion_id
    assert jarvis_spine.get_setting("jarvis_settings") == {"enabled": True}
    assert jarvis_spine.get_setting("missing", {"default": True}) == {"default": True}
    assert jarvis_spine.get_entities()[0]["name"] == "Runtime"
    assert jarvis_spine._loads("not-json", {"fallback": True}) == {"fallback": True}
    assert jarvis_spine.update_memory_status(memory_id, "dismissed") is True


def test_jarvis_spine_connection_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_SPINE_DB_PATH", str(tmp_path / "jarvis.db"))
    conn = jarvis_spine._connect()
    conn.close()
    assert jarvis_spine._connect() is not None


def test_duckduckgo_search_and_lazy_tool(monkeypatch):
    class FakeDDGS:
        def text(self, query, max_results=8):
            assert query == "crewops"
            assert max_results == 8
            return [{"title": "One", "href": "https://example.com", "body": "summary"}]

    fake_module = types.SimpleNamespace(DDGS=FakeDDGS)
    monkeypatch.setitem(sys.modules, "ddgs", fake_module)
    result = web_tools.DuckDuckGoSearchTool()._run("crewops")
    assert "Title: One" in result

    class EmptyDDGS:
        def text(self, query, max_results=8):
            return []

    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=EmptyDDGS))
    assert web_tools.DuckDuckGoSearchTool()._run("crewops") == "No results found."

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "ddgs":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert "Search unavailable" in web_tools.DuckDuckGoSearchTool()._run("crewops")
    monkeypatch.setattr(builtins, "__import__", original_import)

    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=lambda: (_ for _ in ()).throw(RuntimeError("boom"))))
    assert "Search failed" in web_tools.DuckDuckGoSearchTool()._run("crewops")

    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    assert isinstance(web_tools._make_web_search(), web_tools.DuckDuckGoSearchTool)

    class FakeSerperTool:
        def run(self, search_query):
            return f"serper:{search_query}"

    monkeypatch.setenv("SERPER_API_KEY", "test")
    import crewai_tools

    monkeypatch.setattr(crewai_tools, "SerperDevTool", lambda: FakeSerperTool())
    assert web_tools.LazyWebSearchTool()._run("crewops") == "serper:crewops"
