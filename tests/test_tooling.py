import json
import os
import subprocess
import time
import urllib.error

import requests

from crewops_core.config import settings
from crewops_core.tools.browser_tool import BrowserAutomationTool
from crewops_core.tools.coding_agent_tool import CodingAgentTool
from crewops_core.tools.diagnostic_tool import DiagnosticTool
from crewops_core.tools.local_coding_agent_tool import LocalCodingAgentTool
from crewops_core.tools.local_coding_health import _default_timeout, local_coding_agent_alive
from crewops_core.tools.research_agent_tool import ResearchAgentTool


class _Completed:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_coding_agent_tool_paths(monkeypatch, tmp_path):
    tool = CodingAgentTool()
    monkeypatch.delenv("CODING_AGENT_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert "not found" in tool._run("fix it")

    monkeypatch.setenv("CODING_AGENT_BIN", "coder")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/coder" if name == "coder" else None)
    calls = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        calls["cwd"] = kwargs["cwd"]
        return _Completed(stdout="", stderr="problem", returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = tool._run("fix it", working_dir=str(tmp_path / "missing"))
    assert result == "problem"
    assert calls["cmd"][0] == "/usr/bin/coder"
    assert calls["cwd"] == os.getcwd()

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("cmd", 1)))
    assert "timed out" in tool._run("fix it")

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    assert "failed to run coding agent" in tool._run("fix it")


def test_research_agent_tool_paths(monkeypatch, tmp_path):
    tool = ResearchAgentTool()
    monkeypatch.delenv("RESEARCH_AGENT_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert "not found" in tool._run("research it")

    monkeypatch.setenv("RESEARCH_AGENT_BIN", "researcher")

    def fake_which(name):
        if name == "researcher":
            return "/usr/bin/researcher"
        return None

    monkeypatch.setattr("shutil.which", fake_which)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Completed(stdout="ok", returncode=0))
    assert tool._run("research it", working_dir=str(tmp_path)) == "ok"

    monkeypatch.setenv("RESEARCH_AGENT_BIN", "")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/gemini" if name == "gemini" else None)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Completed(stdout="", stderr="oops", returncode=1))
    assert tool._run("research it") == "oops"

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("cmd", 1)))
    assert "timed out" in tool._run("research it")

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    assert "failed to run research agent" in tool._run("research it")


def test_local_coding_agent_tool_paths(monkeypatch):
    tool = LocalCodingAgentTool()

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: (_ for _ in ()).throw(requests.exceptions.ConnectionError()))
    assert "not running" in tool._run("fix it")

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: type("Resp", (), {"status_code": 500, "text": "bad", "json": lambda self: {}})())
    assert "500" in tool._run("fix it")

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: type("Resp", (), {"status_code": 201, "json": lambda self: {}})())
    assert "no conversation id returned" in tool._run("fix it")

    class JsonResp:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    responses = iter(
        [
            JsonResp({"conversation_id": "abc"}),
            JsonResp({"status": "COMPLETED"}),
            JsonResp({"events": [{"source": "agent", "action": "finish", "message": "done"}]}),
        ]
    )

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr("time.sleep", lambda *_args: None)
    assert tool._run("fix it") == "done"

    responses = iter(
        [
            JsonResp({"conversation_id": "abc"}),
            JsonResp({"status": "ERROR"}),
            JsonResp({"events": [{"source": "agent", "message": "fallback"}]}),
        ]
    )
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: next(responses))
    assert tool._run("fix it") == "fallback"

    times = iter([0, 2000])
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: JsonResp({"conversation_id": "abc"}))
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("retry")))
    monkeypatch.setattr("time.time", lambda: next(times))
    assert "timed out" in tool._run("fix it")

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: JsonResp({"conversation_id": "abc"}))
    responses = iter(
        [
            JsonResp({"status": "STOPPED"}),
            JsonResp({"events": []}),
        ]
    )
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr("time.time", lambda: 0)
    assert tool._run("fix it") == "Done (status=STOPPED)"

    responses = iter([JsonResp({"conversation_id": "abc"}), RuntimeError("retry"), JsonResp({"status": "COMPLETED"}), JsonResp({"events": []})])

    def flaky_get(*args, **kwargs):
        item = next(responses)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: JsonResp({"conversation_id": "abc"}))
    monkeypatch.setattr(requests, "get", flaky_get)
    clock = iter([0, 1, 1, 2])
    monkeypatch.setattr("time.time", lambda: next(clock))
    assert tool._run("fix it") == "Done (status=COMPLETED)"


def test_local_coding_health(monkeypatch):
    monkeypatch.setenv("LOCAL_CODING_AGENT_HEALTH_TIMEOUT", "bad")
    assert _default_timeout() == 5.0

    calls = []

    def fake_urlopen(url, timeout=5):
        calls.append((url, timeout))
        if url.endswith("/health"):
            raise urllib.error.HTTPError(url, 500, "boom", None, None)
        raise urllib.error.HTTPError(url, 429, "busy", None, None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert local_coding_agent_alive("http://localhost:3000", timeout=2) is True
    assert calls == [("http://localhost:3000/health", 2), ("http://localhost:3000", 2)]

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    assert local_coding_agent_alive("http://localhost:3000", timeout=2) is False


def test_diagnostic_tool_paths(monkeypatch):
    tool = DiagnosticTool()

    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: "runner")
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: SimpleResponse(200, b'{"models":[{"name":"qwen"}]}'))
    report = tool._run("all")
    assert "Local Coding Agent Diagnostic" in report
    assert "Repository Diagnostic" in report
    assert "Ollama Diagnostic" in report
    assert "System Memory" in report

    def fail_check_output(args, **kwargs):
        if args[:2] == ["gh", "auth"]:
            raise subprocess.CalledProcessError(1, args, output="auth failed")
        if args[0] == "ps":
            raise RuntimeError("ps failed")
        if args[0] == "nvidia-smi":
            raise RuntimeError("gpu failed")
        if args[0] == "free":
            raise RuntimeError("mem failed")
        raise RuntimeError("repo failed")

    monkeypatch.setattr(subprocess, "check_output", fail_check_output)

    def fail_urlopen(url, timeout=5):
        raise urllib.error.HTTPError(url, 429, "busy", None, None)

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)
    report = tool._run("all")
    assert "Process check failed" in report
    assert "gh auth status failed" in report
    assert "Repo access check failed" in report
    assert "HTTP http://localhost:3000/health: 429" in report
    assert "No NVIDIA GPU detected" in report
    assert "Memory check failed" in report

    def file_missing(args, **kwargs):
        if args[:2] == ["gh", "auth"]:
            raise FileNotFoundError("gh missing")
        raise RuntimeError("repo failed")

    monkeypatch.setattr(subprocess, "check_output", file_missing)
    report = tool._check_repository()
    assert "gh CLI not found in PATH." in report

    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("other failure")),
    )
    report = tool._check_repository()
    assert "Repository check error: other failure" in report


def test_browser_tool_paths(monkeypatch):
    tool = BrowserAutomationTool()
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Completed(stdout="hello", returncode=0))
    assert tool._run("navigate", url="https://example.com") == "hello"

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Completed(stdout="", stderr="No module named 'playwright'", returncode=1))
    assert "Playwright not installed" in tool._run("navigate", url="https://example.com")

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Completed(stdout="", stderr="oops", returncode=1))
    assert "Playwright error: oops" == tool._run("navigate", url="https://example.com")

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("cmd", 1)))
    assert "timed out" in tool._run("navigate", url="https://example.com")

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    assert "ERROR launching browser" in tool._run("navigate", url="https://example.com")


def test_settings_helpers(monkeypatch, tmp_path):
    original_pick_model = settings._pick_model
    original_default_storage_path = settings._default_memory_storage_path
    original_ollama_has = settings._ollama_has
    monkeypatch.setattr(settings, "_model_cache", None)
    monkeypatch.setattr(settings, "_RATE_LIMIT_TTL", 0.0)
    monkeypatch.setattr(settings, "_ollama_has", lambda model: model == "qwen2.5:14b")
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)
    assert settings._pick_model() == "ollama/qwen2.5:14b"
    assert settings.is_rate_limit_error("status 429 reached")

    settings.mark_rate_limited("gemini/gemini-2.5-flash")
    monkeypatch.setattr(settings.rate_guard, "is_near_limit", lambda model: False)
    assert settings._is_available("gemini/gemini-2.5-flash") is True

    storage = tmp_path / "memory"
    storage.mkdir()
    (storage / "one.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(settings, "_default_memory_storage_path", lambda: str(storage))
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    status = settings.get_memory_backend_status()
    assert status["has_data"] is True
    assert status["provider"] == "google"

    class FakeLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    import sys

    fake_crewai = type("CrewAIModule", (), {"LLM": FakeLLM})
    monkeypatch.setitem(sys.modules, "crewai", fake_crewai)
    monkeypatch.setattr(settings, "_pick_model", lambda: "ollama/qwen2.5:14b")
    llm = settings.get_llm()
    assert llm.kwargs["base_url"] == settings.OLLAMA_BASE_URL

    monkeypatch.setattr(settings, "_pick_model", lambda: "gemini/gemini-2.5-flash")
    llm = settings.get_llm()
    assert llm.kwargs["model"] == "gemini/gemini-2.5-flash"

    monkeypatch.setattr(settings, "_pick_model", original_pick_model)
    monkeypatch.setenv("DEFAULT_MODEL", "custom/model")
    assert settings._pick_model() == "custom/model"
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)

    monkeypatch.setattr(settings, "_model_cache", ("gemini/gemini-2.5-flash", 0.0))
    monkeypatch.setattr(settings, "_time", SimpleNamespace(monotonic=lambda: 1.0))
    monkeypatch.setattr(settings, "_is_available", lambda model: True)
    assert settings._pick_model() == "gemini/gemini-2.5-flash"

    monkeypatch.setattr(settings, "_model_cache", None)
    monkeypatch.setattr(settings, "_ollama_has", lambda model: model == "llama3.1:8b")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert settings._pick_model() == "ollama/llama3.1:8b"

    monkeypatch.setattr(settings, "_model_cache", None)
    monkeypatch.setattr(settings, "_ollama_has", lambda model: False)
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(settings, "_is_available", lambda model: model == "gemini/gemini-2.5-flash")
    assert settings._pick_model() == "gemini/gemini-2.5-flash"

    monkeypatch.setattr(settings, "_ollama_has", original_ollama_has)
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    assert settings._ollama_has("qwen2.5:14b") is False

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: SimpleResponse(200, b'{"models":[{"name":"qwen2.5:14b"}]}'))
    assert settings._ollama_has("qwen2.5:14b") is True

    monkeypatch.setattr(settings, "_default_memory_storage_path", original_default_storage_path)
    fake_paths = type("PathsModule", (), {"db_storage_path": staticmethod(lambda: str(tmp_path / "db"))})
    sys_modules = __import__("sys").modules
    monkeypatch.setitem(sys_modules, "crewai.utilities.paths", fake_paths)
    monkeypatch.delenv("CREWAI_STORAGE_DIR", raising=False)
    assert settings._default_memory_storage_path().endswith("/db/memory")

    class BadStorage:
        def exists(self):
            return True

        def rglob(self, pattern):
            raise RuntimeError("bad storage")

        def __str__(self):
            return "/tmp/bad"

    monkeypatch.setattr(settings, "_default_memory_storage_path", lambda: str(tmp_path / "broken"))
    monkeypatch.setattr(settings, "Path", lambda *args, **kwargs: BadStorage())
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    bad_status = settings.get_memory_backend_status()
    assert bad_status["file_count"] == 0

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: SimpleResponse(200, b"{}"))
    monkeypatch.setattr(settings, "local_coding_agent_alive", lambda: False)
    snapshot = settings.get_service_health_snapshot()
    assert snapshot["services"]["ollama"] is True
    assert snapshot["services"]["local_coding_agent"] is False

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    snapshot = settings.get_service_health_snapshot()
    assert snapshot["services"]["ollama"] is False


def test_rate_guard_helpers(monkeypatch, tmp_path):
    from crewops_core.config import rate_guard

    state_file = tmp_path / "store" / "state.json"
    monkeypatch.setattr(rate_guard, "_STATE_FILE", state_file)
    monkeypatch.setenv("GEMINI_RPM_gemini_2_5_flash", "2")
    monkeypatch.setenv("GEMINI_RPD_gemini_2_5_flash", "3")
    monkeypatch.setenv("GEMINI_TPM_gemini_2_5_flash", "4")

    limits = rate_guard._get_limits("gemini/gemini-2.5-flash")
    assert limits.rpm == 2
    assert rate_guard._get_limits("custom/model") is None

    dq = __import__("collections").deque([time.monotonic() - 100, time.monotonic()])
    rate_guard._evict(dq, 60)
    assert len(dq) == 1

    dq = __import__("collections").deque([time.time() - 90_000, time.time()])
    rate_guard._evict_rpd(dq)
    assert len(dq) == 1

    dq = __import__("collections").deque([(time.monotonic() - 61, 1), (time.monotonic(), 2)])
    rate_guard._evict_tpm(dq)
    assert len(dq) == 1

    state_file.parent.mkdir(parents=True)
    state_file.write_text("{", encoding="utf-8")
    rate_guard._load_state()
    rate_guard._rpd_window.clear()
    rate_guard._save_state()
    assert state_file.exists()

    assert rate_guard.record_call("ollama/qwen2.5:14b") is None
    assert rate_guard.is_near_limit("custom/model") is False

    monkeypatch.setitem(__import__("sys").modules, "litellm", None)
    rate_guard._callbacks_installed = False
    rate_guard.install_callbacks()

    class FakeLiteLLM:
        success_callback = []
        failure_callback = []

    monkeypatch.setitem(__import__("sys").modules, "litellm", FakeLiteLLM)
    rate_guard._callbacks_installed = False
    rate_guard.install_callbacks()
    callback = FakeLiteLLM.success_callback[0]
    callback({"model": "gemini/gemini-2.5-flash"}, SimpleNamespace(usage=SimpleNamespace(total_tokens=7)), None, None)
    usage = rate_guard.get_usage()
    assert usage["gemini/gemini-2.5-flash"]["tpm"]["used"] >= 7


class SimpleNamespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class SimpleResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False
