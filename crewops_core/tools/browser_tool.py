"""Headless browser automation for dynamic web content."""

import os
import subprocess
import sys
from typing import Optional

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class PlaywrightInput(BaseModel):
    action: str = Field(
        description=(
            "Action to perform: "
            "'navigate' — load URL and return all body text; "
            "'extract' — return text from a CSS selector; "
            "'click' — click an element then return updated page text; "
            "'fill' — fill a form field with value; "
            "'screenshot' — save page screenshot to output_path; "
            "'links' — return all links (text + href) from the page; "
            "'search_and_extract' — navigate then return lines matching value"
        )
    )
    url: Optional[str] = Field(None, description="URL to navigate to")
    selector: Optional[str] = Field(None, description="CSS selector for extract/click/fill")
    value: Optional[str] = Field(None, description="Text for fill action, or search query for search_and_extract")
    output_path: Optional[str] = Field(None, description="File path for screenshot output")
    wait_for: Optional[str] = Field(None, description="CSS selector to wait for before extracting (useful for SPAs)")
    timeout_ms: int = Field(20000, description="Page load timeout in milliseconds")


# Playwright runs in a subprocess to avoid async event loop conflicts with FastAPI
_SCRIPT = r"""
import asyncio, sys, os
from playwright.async_api import async_playwright

async def main():
    action      = {action!r}
    url         = {url!r}
    selector    = {selector!r}
    value       = {value!r}
    output_path = {output_path!r}
    wait_for    = {wait_for!r}
    timeout_ms  = {timeout_ms!r}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-CA",
            viewport={{"width": 1920, "height": 1080}},
        )
        page = await ctx.new_page()
        try:
            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                if wait_for:
                    try:
                        await page.wait_for_selector(wait_for, timeout=8000)
                    except Exception:
                        pass  # best-effort

            if action == "navigate":
                text = await page.inner_text("body")
                print(text[:6000])

            elif action == "extract":
                el = page.locator(selector or "body").first
                print(await el.inner_text())

            elif action == "click":
                await page.locator(selector).first.click()
                await page.wait_for_load_state("domcontentloaded")
                print(await page.inner_text("body"))

            elif action == "fill":
                await page.locator(selector).first.fill(value or "")
                print("Filled: " + (selector or ""))

            elif action == "screenshot":
                path = output_path or "/tmp/playwright_screenshot.png"
                await page.screenshot(path=path, full_page=True)
                print("Screenshot saved: " + path)

            elif action == "links":
                links = await page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => JSON.stringify({{text: e.innerText.trim().slice(0,80), href: e.href}}))"
                )
                for l in links[:60]:
                    print(l)

            elif action == "search_and_extract":
                body_text = await page.inner_text("body")
                query = (value or "").lower()
                if query:
                    lines = [ln for ln in body_text.splitlines() if query in ln.lower()]
                    print("\n".join(lines[:100]) if lines else body_text[:4000])
                else:
                    print(body_text[:4000])

        finally:
            await browser.close()

asyncio.run(main())
"""


class BrowserAutomationTool(BaseTool):
    name: str = "playwright_browser"
    description: str = (
        "Headless Chromium browser for JavaScript-rendered pages, portals, and dynamic sites. "
        "Actions: navigate, extract, click, fill, screenshot, links, search_and_extract."
    )
    args_schema: type[BaseModel] = PlaywrightInput

    def _run(
        self,
        action: str,
        url: Optional[str] = None,
        selector: Optional[str] = None,
        value: Optional[str] = None,
        output_path: Optional[str] = None,
        wait_for: Optional[str] = None,
        timeout_ms: int = 20000,
    ) -> str:
        script = _SCRIPT.format(
            action=action,
            url=url,
            selector=selector,
            value=value,
            output_path=output_path,
            wait_for=wait_for,
            timeout_ms=timeout_ms,
        )
        env = {**os.environ}
        try:
            proc = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                stdin=subprocess.DEVNULL,
                text=True,
                timeout=90,
                env=env,
            )
            if proc.returncode != 0:
                err = proc.stderr[:600]
                if "No module named 'playwright'" in err:
                    return (
                        "ERROR: Playwright not installed. "
                        "Run: pip install playwright && playwright install chromium"
                    )
                return f"Playwright error: {err}"
            output = proc.stdout.strip()
            return output[:6000] if output else "(page loaded but returned no text)"
        except subprocess.TimeoutExpired:
            return "ERROR: Browser timed out after 90 seconds"
        except Exception as e:
            return f"ERROR launching browser: {e}"
