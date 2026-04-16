from __future__ import annotations

import os
import shutil
import subprocess

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class CodingAgentInput(BaseModel):
    task: str = Field(description="The software or repository task to execute.")
    working_dir: str = Field(default="", description="Optional absolute working directory.")


class CodingAgentTool(BaseTool):
    name: str = "coding_agent"
    description: str = (
        "Delegates software engineering, shell, and repository tasks to a locally installed coding agent CLI."
    )
    args_schema: type[BaseModel] = CodingAgentInput

    def _run(self, task: str, working_dir: str = "") -> str:
        configured = os.getenv("CODING_AGENT_BIN", "").strip()
        binary = shutil.which(configured) if configured else None
        if not binary:
            return "ERROR: coding agent CLI not found."

        cwd = working_dir.strip() or os.getcwd()
        if not os.path.isdir(cwd):
            cwd = os.getcwd()

        try:
            result = subprocess.run(
                [binary, "--print", "--dangerously-skip-permissions", task],
                capture_output=True,
                stdin=subprocess.DEVNULL,
                text=True,
                timeout=1200,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            return "ERROR: coding agent timed out after 20 minutes."
        except Exception as exc:
            return f"ERROR: failed to run coding agent: {exc}"

        output = result.stdout.strip()
        if result.returncode != 0 and result.stderr:
            stderr = result.stderr.strip()
            output = f"{output}\n{stderr}".strip() if output else stderr
        return output or f"Done (exit code {result.returncode})"
