from __future__ import annotations

import os
import time

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


def _agent_url() -> str:
    return os.getenv("LOCAL_CODING_AGENT_URL", os.getenv("OPENHANDS_API_URL", "http://localhost:3000"))


class LocalCodingAgentInput(BaseModel):
    task: str = Field(description="The software or filesystem task to execute.")


class LocalCodingAgentTool(BaseTool):
    name: str = "local_coding_agent"
    description: str = (
        "Delegates software engineering and repository tasks to a locally running coding service."
    )
    args_schema: type[BaseModel] = LocalCodingAgentInput

    def _run(self, task: str) -> str:
        base_url = _agent_url().rstrip("/")
        try:
            response = requests.post(
                f"{base_url}/api/conversations",
                json={"initial_user_msg": task},
                timeout=30,
            )
        except requests.exceptions.ConnectionError:
            return "ERROR: local coding agent is not running."

        if response.status_code not in (200, 201):
            return f"ERROR: local coding agent {response.status_code}: {response.text[:200]}"

        data = response.json()
        conversation_id = data.get("conversation_id") or data.get("id")
        if not conversation_id:
            return f"ERROR: no conversation id returned: {data}"

        deadline = time.time() + 1200
        while time.time() < deadline:
            time.sleep(5)
            try:
                info = requests.get(f"{base_url}/api/conversations/{conversation_id}", timeout=10).json()
            except Exception:
                continue

            status = str(info.get("status", "")).upper()
            if status in {"STOPPED", "ERROR", "FINISHED", "COMPLETED"}:
                events = requests.get(
                    f"{base_url}/api/conversations/{conversation_id}/events",
                    timeout=10,
                ).json().get("events", [])
                final_message = next(
                    (
                        event.get("message", "")
                        for event in reversed(events)
                        if event.get("source") == "agent" and event.get("action") == "finish"
                    ),
                    None,
                )
                if final_message:
                    return final_message
                messages = [
                    event.get("message", "")
                    for event in events
                    if event.get("source") == "agent" and event.get("message")
                ]
                return messages[-1] if messages else f"Done (status={status})"

        return "ERROR: local coding agent timed out after 20 minutes."
