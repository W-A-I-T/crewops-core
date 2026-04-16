from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class DiagnosticInput(BaseModel):
    check: str = Field(
        description=(
            "What to diagnose. Options: "
            "'local_coding_agent' — process, health, logs; "
            "'repository' — gh CLI auth and current repo access; "
            "'ollama' — running models and GPU; "
            "'all' — full stack health."
        )
    )


class DiagnosticTool(BaseTool):
    name: str = "system_diagnostic"
    description: str = "Diagnoses local service health so the runtime can understand failures before retrying."
    args_schema: type[BaseModel] = DiagnosticInput

    def _run(self, check: str) -> str:
        results = []
        normalized = check.lower()
        if normalized in ("local_coding_agent", "all"):
            results.append(self._check_local_coding_agent())
        if normalized in ("repository", "all"):
            results.append(self._check_repository())
        if normalized in ("ollama", "all"):
            results.append(self._check_ollama())
        if normalized == "all":
            results.append(self._check_memory())
        return "\n\n".join(results)

    def _check_local_coding_agent(self) -> str:
        lines = ["=== Local Coding Agent Diagnostic ==="]
        try:
            output = subprocess.check_output(["ps", "aux"], text=True, timeout=5)
            processes = [line for line in output.splitlines() if "openhands" in line.lower() and "grep" not in line]
            lines.append(f"Processes: {len(processes)} running")
        except Exception as exc:
            lines.append(f"Process check failed: {exc}")

        base_url = os.getenv("LOCAL_CODING_AGENT_URL", os.getenv("OPENHANDS_API_URL", "http://localhost:3000")).rstrip("/")
        for url in (f"{base_url}/health", base_url):
            try:
                response = urllib.request.urlopen(url, timeout=5)
                lines.append(f"HTTP {url}: {response.status} OK")
                break
            except urllib.error.HTTPError as exc:
                lines.append(f"HTTP {url}: {exc.code}")
                break
            except Exception as exc:
                lines.append(f"HTTP {url}: unreachable ({exc})")

        return "\n".join(lines)

    def _check_repository(self) -> str:
        lines = ["=== Repository Diagnostic ==="]
        try:
            output = subprocess.check_output(
                ["gh", "auth", "status"],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=10,
            )
            lines.append(output.strip())
        except subprocess.CalledProcessError as exc:
            lines.append(f"gh auth status failed:\n{exc.output.strip()}")
        except FileNotFoundError:
            lines.append("gh CLI not found in PATH.")
        except Exception as exc:
            lines.append(f"Repository check error: {exc}")

        try:
            output = subprocess.check_output(
                ["gh", "repo", "view", "--json", "name,defaultBranchRef"],
                text=True,
                timeout=10,
            )
            data = json.loads(output)
            default_branch = data.get("defaultBranchRef", {}).get("name", "?")
            lines.append(f"Repo access: OK (default branch: {default_branch})")
        except Exception as exc:
            lines.append(f"Repo access check failed: {exc}")
        return "\n".join(lines)

    def _check_ollama(self) -> str:
        lines = ["=== Ollama Diagnostic ==="]
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        try:
            response = urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=5)
            data = json.loads(response.read())
            models = [item["name"] for item in data.get("models", [])]
            lines.append(f"Ollama running. Models: {', '.join(models) if models else 'none'}")
        except Exception as exc:
            lines.append(f"Ollama unreachable: {exc}")

        try:
            output = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                    "--format=csv,noheader",
                ],
                text=True,
                timeout=5,
            )
            lines.append(f"GPU: {output.strip()}")
        except Exception:
            lines.append("No NVIDIA GPU detected (or nvidia-smi not available).")
        return "\n".join(lines)

    def _check_memory(self) -> str:
        lines = ["=== System Memory ==="]
        try:
            output = subprocess.check_output(["free", "-h"], text=True, timeout=3)
            lines.append(output.strip())
        except Exception as exc:
            lines.append(f"Memory check failed: {exc}")
        return "\n".join(lines)
