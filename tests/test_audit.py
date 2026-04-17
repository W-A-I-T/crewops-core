from pathlib import Path

from scripts.audit_forbidden_strings import CANONICAL_REPO_URLS, find_forbidden_strings


def test_audit_ignores_repo_url_and_wait_like_substrings(tmp_path):
    good = tmp_path / "good.md"
    good.write_text(
        "Clone with git clone <repo-url>. The task is awaiting review and uses wait_for in tests.\n"
        + "\n".join(CANONICAL_REPO_URLS),
        encoding="utf-8",
    )
    assert find_forbidden_strings(tmp_path) == []


def test_audit_flags_real_forbidden_terms(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("This file mentions NanoClaw and Claude.", encoding="utf-8")
    failures = find_forbidden_strings(tmp_path)
    assert len(failures) == 1
    assert "forbidden term" in failures[0]
