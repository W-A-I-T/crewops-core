from __future__ import annotations

import re
import sys
from pathlib import Path


CANONICAL_REPO_URLS = {
    "https://github.com/W-A-I-T/crewops-core",
    "https://github.com/W-A-I-T/crewops-core.git",
}

_PATTERNS = (
    re.compile(r"\bnano(?:claw|crew)\b", re.IGNORECASE),
    re.compile(r"\bwait[- ]?tech\b", re.IGNORECASE),
    re.compile(r"\bwaitinc\b", re.IGNORECASE),
    re.compile(r"\bcodex\b", re.IGNORECASE),
    re.compile(r"\bclaude\b", re.IGNORECASE),
)

_SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", ".venv", "node_modules"}
_SKIP_TOP_LEVEL_DIRS = {"tests"}
_TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".yml",
    ".yaml",
    ".html",
    ".json",
    ".sh",
}
_TEXT_FILENAMES = {".env.example", "Dockerfile", "LICENSE"}


def _is_audited_file(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    if any(part in _SKIP_DIRS for part in relative_parts):
        return False
    if relative_parts and relative_parts[0] in _SKIP_TOP_LEVEL_DIRS:
        return False
    return path.suffix in _TEXT_EXTENSIONS or path.name in _TEXT_FILENAMES


def find_forbidden_strings(root: Path) -> list[str]:
    failures: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or not _is_audited_file(path, root):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        masked = text
        for url in CANONICAL_REPO_URLS:
            masked = masked.replace(url, "")
        for pattern in _PATTERNS:
            match = pattern.search(masked)
            if match:
                failures.append(f"{path.relative_to(root)}: forbidden term `{match.group(0)}`")
                break
    return failures


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    root = Path(args[0]).resolve() if args else Path.cwd()
    failures = find_forbidden_strings(root)
    if failures:
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
