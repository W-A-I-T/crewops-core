from __future__ import annotations

import os
import shutil
import subprocess

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class ResearchAgentInput(BaseModel):
    task: str = Field(description="The research or drafting task to execute.")
    working_dir: str = Field(default="", description="Optional absolute working directory.")


class ResearchAgentTool(BaseTool):
    name: str = "research_agent"
    description: str = (
        "Delegates research, drafting, summarization, and analysis tasks to a locally installed research agent CLI."
    )
    args_schema: type[BaseModel] = ResearchAgentInput

    def _run(self, task: str, working_dir: str = "") -> str:
        binary = shutil.which(os.getenv("RESEARCH_AGENT_BIN", ""))
        if not binary:
            binary = shutil.which("gemini")
        if not binary:
            return "ERROR: research agent CLI not found."

        cwd = working_dir.strip() or os.getcwd()
        if not os.path.isdir(cwd):
            cwd = os.getcwd()

        try:
            result = subprocess.run(
                [binary, "-p", task],
                capture_output=True,
                stdin=subprocess.DEVNULL,
                text=True,
                timeout=300,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            return "ERROR: research agent timed out after 5 minutes."
        except Exception as exc:
            return f"ERROR: failed to run research agent: {exc}"

        output = result.stdout.strip()
        if result.returncode != 0 and result.stderr:
            stderr = result.stderr.strip()
            output = f"{output}\n{stderr}".strip() if output else stderr
        return output or f"Done (exit code {result.returncode})"
