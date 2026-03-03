"""Generic website adapter.

Fallback adapter that works with any website via Playwright.
Extracts text content from arbitrary URLs.
"""

from __future__ import annotations

import logging
from typing import Any

from ucal.adapters.base import (
    AdapterType,
    BaseAdapter,
    ContentResult,
    ExtractResult,
    LoginMethod,
    LoginStatus,
    SearchResult,
)
from ucal.core.browser import BrowserManager
from ucal.utils.human_behavior import human_scroll, random_delay

logger = logging.getLogger(__name__)


class GenericAdapter(BaseAdapter):
    """Generic adapter for any website using Playwright.

    No login support — just direct page access and content extraction.
    """

    platform_name = "generic"
    adapter_type = AdapterType.BROWSER

    def __init__(self, browser_manager: BrowserManager) -> None:
        self._bm = browser_manager

    def is_logged_in(self) -> bool:
        return True  # No login needed

    async def login(self, method: LoginMethod = LoginMethod.BROWSER) -> LoginStatus:
        """No-op login — generic adapter doesn't require authentication.

        Args:
            method: Ignored.

        Returns:
            Always-success status.
        """
        return LoginStatus(
            success=True,
            platform=self.platform_name,
            method=method.value,
            message="Generic adapter requires no login.",
        )

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Not supported for the generic adapter.

        Args:
            query: Ignored.
            limit: Ignored.

        Returns:
            Empty list with a hint.
        """
        return [
            SearchResult(
                title="Search not supported",
                url="",
                summary=(
                    "The generic adapter doesn't support search. "
                    "Use platform_read with a specific URL instead."
                ),
                platform=self.platform_name,
            )
        ]

    async def read(self, url: str, **kwargs: Any) -> ContentResult:
        """Read content from any URL.

        Args:
            url: The URL to fetch.

        Returns:
            Page content as Markdown.
        """
        page = await self._bm.new_page(self.platform_name)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await random_delay(1.0, 3.0)

            # Scroll to trigger lazy loading
            await human_scroll(page, direction="down", amount=600)
            await random_delay(0.5, 1.0)

            title = await page.title()

            # Try to find main content area
            body = ""
            for sel in [
                "article",
                "main",
                "[role='main']",
                ".content",
                ".post-content",
                "#content",
            ]:
                el = await page.query_selector(sel)
                if el:
                    body = (await el.inner_text()).strip()
                    break

            # Fallback: entire body text
            if not body:
                body_el = await page.query_selector("body")
                if body_el:
                    body = (await body_el.inner_text()).strip()
                    # Truncate very long pages
                    if len(body) > 10000:
                        body = body[:10000] + "\n\n... (truncated)"

            return ContentResult(
                title=title,
                content=body,
                url=url,
                platform=self.platform_name,
            )
        except Exception as exc:
            logger.error("Generic read failed for %s: %s", url, exc)
            return ContentResult(
                title="Error",
                content=f"Failed to read page: {exc}",
                url=url,
                platform=self.platform_name,
            )
        finally:
            await page.close()

    async def extract(self, url: str, fields: list[str]) -> ExtractResult:
        """Extract content from any URL.

        Only supports 'title' and 'content' fields for generic pages.

        Args:
            url: The URL to extract from.
            fields: Desired field names.

        Returns:
            Extracted fields.
        """
        content = await self.read(url)
        all_fields: dict[str, Any] = {
            "title": content.title,
            "content": content.content,
            "url": url,
            "platform": self.platform_name,
        }
        selected = {k: all_fields.get(k, "") for k in fields} if fields else all_fields
        return ExtractResult(
            fields=selected,
            url=url,
            platform=self.platform_name,
        )

    async def execute_actions(
        self, url: str, actions: list[dict], *, platform: str | None = None
    ) -> list[dict[str, Any]]:
        """Execute a sequence of browser actions on a page.

        This is the implementation behind the ``browser_action`` MCP tool.

        Args:
            url: Starting URL.
            actions: List of action dicts. Supported types:
                - goto: Navigate to a URL.
                - click: Click a CSS selector.
                - type: Type text into a selector.
                - scroll: Scroll the page.
                - screenshot: Take a screenshot.
                - extract_text: Get text from a selector.
                - wait: Wait for a selector.
            platform: Optional platform identifier to use for session cookies.
                If provided, the browser context for that platform (with its
                saved cookies) will be used instead of the generic context.

        Returns:
            List of result dicts for each action.
        """
        context_platform = platform or self.platform_name
        page = await self._bm.new_page(context_platform)
        results: list[dict[str, Any]] = []

        try:
            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await random_delay(0.5, 1.5)

            for action in actions:
                action_type = action.get("type", "")
                result: dict[str, Any] = {"type": action_type, "success": True}

                try:
                    if action_type == "goto":
                        await page.goto(
                            action["url"],
                            wait_until="domcontentloaded",
                            timeout=30000,
                        )
                        result["url"] = page.url

                    elif action_type == "click":
                        await page.click(action["selector"], timeout=10000)
                        result["selector"] = action["selector"]

                    elif action_type == "type":
                        await page.fill(action["selector"], action.get("text", ""))
                        result["selector"] = action["selector"]

                    elif action_type == "scroll":
                        direction = action.get("direction", "down")
                        amount = action.get("amount", 500)
                        await human_scroll(page, direction=direction, amount=amount)

                    elif action_type == "screenshot":
                        save_path = action.get("path", "")
                        if save_path:
                            await page.screenshot(
                                path=save_path, full_page=action.get("full_page", False)
                            )
                            result["path"] = save_path
                            result["message"] = f"Screenshot saved to {save_path}"
                        else:
                            buf = await page.screenshot()
                            result["size"] = len(buf)
                            result["message"] = "Screenshot captured (binary data)."

                    elif action_type == "eval_js":
                        js_result = await page.evaluate(action["expression"])
                        result["value"] = js_result

                    elif action_type == "extract_text":
                        el = await page.query_selector(action["selector"])
                        result["text"] = (await el.inner_text()).strip() if el else ""

                    elif action_type == "wait":
                        await page.wait_for_selector(
                            action["selector"], timeout=action.get("timeout", 10000)
                        )

                    else:
                        result["success"] = False
                        result["error"] = f"Unknown action type: {action_type}"

                except Exception as exc:
                    result["success"] = False
                    result["error"] = str(exc)

                results.append(result)

        finally:
            await page.close()

        return results
