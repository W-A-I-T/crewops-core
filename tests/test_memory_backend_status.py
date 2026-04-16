from crewops_core.config.settings import get_memory_backend_status


def test_memory_backend_disabled_without_keys(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    status = get_memory_backend_status()
    assert status["enabled"] is False
    assert "Neither NVIDIA_API_KEY nor GEMINI_API_KEY" in status["reason"]


def test_memory_backend_prefers_nvidia(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test")
    monkeypatch.setenv("GEMINI_API_KEY", "fallback")
    status = get_memory_backend_status()
    assert status["enabled"] is True
    assert status["provider"] == "nvidia"
    assert status["mode"] == "asymmetric"
