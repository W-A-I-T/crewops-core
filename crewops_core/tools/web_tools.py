"""
Shared web/search tools used across departments.

Search priority:
  1. SerperDevTool  — fast, structured results (requires SERPER_API_KEY)
  2. DuckDuckGoSearchTool — Playwright fallback, no API key needed

The fallback prevents agents from looping on failed Serper calls and burning
LLM quota when search retries keep failing.
"""

import os

from crewai.tools import BaseTool
from crewai_tools import (
    FileReadTool,
    FileWriterTool,
    ScrapeWebsiteTool,
)
from pydantic import BaseModel, Field


# ── DuckDuckGo fallback (no API key required) ─────────────────────────────────

class _DDGInput(BaseModel):
    search_query: str = Field(description="The search query to look up on the internet.")


class DuckDuckGoSearchTool(BaseTool):
    """DuckDuckGo search via ddgs library — no API key required.

    Used automatically when SERPER_API_KEY is not set, preventing the
    agent loop that burns LLM quota on repeated failed Serper calls.
    Returns top 8 results (title, URL, snippet).
    """

    name: str = "search_the_internet"
    description: str = (
        "Search the internet using DuckDuckGo. Use this to find company info, "
        "news, contact details, market research, or any web information. "
        "Input: a plain-text search query."
    )
    args_schema: type[BaseModel] = _DDGInput

    def _run(self, search_query: str) -> str:
        try:
            from ddgs import DDGS
            results = list(DDGS().text(search_query, max_results=8))
            if not results:
                return "No results found."
            lines = []
            for r in results:
                lines.append(f"Title: {r.get('title', '')}")
                lines.append(f"URL:   {r.get('href', '')}")
                lines.append(f"       {r.get('body', '')[:200]}")
                lines.append("---")
            return "\n".join(lines)
        except ImportError:
            return "Search unavailable: run 'pip install ddgs' to enable fallback search."
        except Exception as e:
            return f"Search failed: {e}"


# ── Tool exports ──────────────────────────────────────────────────────────────

def _make_web_search():
    """Return SerperDevTool if key is present, else DuckDuckGoSearchTool fallback."""
    if os.getenv("SERPER_API_KEY"):
        from crewai_tools import SerperDevTool
        return SerperDevTool()
    return DuckDuckGoSearchTool()


class LazyWebSearchTool(BaseTool):
    """Resolve the underlying search tool at call time so late env loading works."""

    name: str = "search_the_internet"
    description: str = (
        "Search the internet using the currently configured provider. "
        "Uses Serper when SERPER_API_KEY is set, otherwise DuckDuckGo."
    )
    args_schema: type[BaseModel] = _DDGInput

    def _run(self, search_query: str) -> str:
        return _make_web_search().run(search_query=search_query)


web_search  = LazyWebSearchTool()
web_scraper = ScrapeWebsiteTool()
file_writer = FileWriterTool()
file_reader = FileReadTool()
