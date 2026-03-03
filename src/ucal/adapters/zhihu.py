"""Zhihu (知乎) browser adapter.

Uses Playwright with stealth to access Zhihu content.
"""

from __future__ import annotations

import asyncio
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

ZHIHU_BASE = "https://www.zhihu.com"


class ZhihuAdapter(BaseAdapter):
    """Zhihu adapter using Playwright browser automation.

    Supports manual login; session is persisted for future use.
    """

    platform_name = "zhihu"
    adapter_type = AdapterType.BROWSER

    def __init__(self, browser_manager: BrowserManager) -> None:
        self._bm = browser_manager
        self._logged_in = False

    def is_logged_in(self) -> bool:
        return self._logged_in

    async def login(self, method: LoginMethod = LoginMethod.BROWSER) -> LoginStatus:
        """Login to Zhihu.

        Args:
            method: Login method.

        Returns:
            Login status.
        """
        if method == LoginMethod.COOKIE:
            if self._bm.session_manager.has_session(self.platform_name):
                self._logged_in = True
                return LoginStatus(
                    success=True,
                    platform=self.platform_name,
                    method=method.value,
                    message="Session restored from saved cookies.",
                )
            return LoginStatus(
                success=False,
                platform=self.platform_name,
                method=method.value,
                message="No saved session. Use method='browser' to login.",
            )

        page = await self._bm.new_page(self.platform_name)
        try:
            await page.goto(f"{ZHIHU_BASE}/signin", wait_until="domcontentloaded")
            await random_delay(0.5, 1.0)

            # Check if already logged in
            if await self._check_logged_in(page):
                self._logged_in = True
                session_file = await self._bm.save_session(self.platform_name)
                return LoginStatus(
                    success=True,
                    platform=self.platform_name,
                    method=method.value,
                    message="Already logged in.",
                    session_file=session_file,
                )

            logger.info("Please login to Zhihu in the browser window.")

            for _ in range(60):
                await asyncio.sleep(2)
                current_url = page.url
                if "/signin" not in current_url and await self._check_logged_in(page):
                    self._logged_in = True
                    session_file = await self._bm.save_session(self.platform_name)
                    return LoginStatus(
                        success=True,
                        platform=self.platform_name,
                        method=method.value,
                        message="Login successful.",
                        session_file=session_file,
                    )

            return LoginStatus(
                success=False,
                platform=self.platform_name,
                method=method.value,
                message="Login timed out.",
            )
        finally:
            await page.close()

    async def _check_logged_in(self, page) -> bool:  # noqa: ANN001
        """Check login state by looking for user avatar."""
        try:
            avatar = await page.query_selector(
                ".AppHeader-profileAvatar, .Avatar--round"
            )
            return avatar is not None
        except Exception:
            return False

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search Zhihu for questions, answers, and articles.

        Args:
            query: Search query.
            limit: Max results.

        Returns:
            List of search results.
        """
        page = await self._bm.new_page(self.platform_name)
        results: list[SearchResult] = []
        try:
            url = f"{ZHIHU_BASE}/search?type=content&q={query}"
            await page.goto(url, wait_until="domcontentloaded")
            await random_delay(0.5, 1.0)

            for _ in range(min(limit // 5, 3)):
                await human_scroll(page, direction="down", amount=800)
                await random_delay(0.3, 0.8)

            cards = await page.query_selector_all(".SearchResult-Card, .List-item")
            for card in cards[:limit]:
                try:
                    title_el = await card.query_selector(
                        "h2, .ContentItem-title a, "
                        "a[data-za-detail-view-element_name='Title']"
                    )
                    title = await title_el.inner_text() if title_el else ""

                    link_el = await card.query_selector("h2 a, .ContentItem-title a")
                    link = ""
                    if link_el:
                        link = await link_el.get_attribute("href") or ""
                        if link and not link.startswith("http"):
                            link = f"{ZHIHU_BASE}{link}"

                    excerpt_el = await card.query_selector(
                        ".RichContent-inner, .CopyrightRichTextContainer"
                    )
                    excerpt = ""
                    if excerpt_el:
                        excerpt = await excerpt_el.inner_text()
                        excerpt = excerpt[:200]

                    author_el = await card.query_selector(
                        ".AuthorInfo-name a, .AuthorInfo .UserLink-link"
                    )
                    author = await author_el.inner_text() if author_el else ""

                    results.append(
                        SearchResult(
                            title=title.strip()[:100],
                            url=link,
                            summary=excerpt.strip(),
                            author=author.strip(),
                            platform=self.platform_name,
                        )
                    )
                except Exception as exc:
                    logger.debug("Failed to parse Zhihu card: %s", exc)
                    continue

        except Exception as exc:
            logger.error("Zhihu search failed: %s", exc)
        finally:
            await page.close()

        return results

    async def read(self, url: str, **kwargs: Any) -> ContentResult:
        """Read full content from a Zhihu question/answer/article.

        Args:
            url: Zhihu URL.

        Returns:
            Content in Markdown format.
        """
        page = await self._bm.new_page(self.platform_name)
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await random_delay(0.5, 1.0)

            # Expand collapsed content if present
            expand_btn = await page.query_selector(
                "button.ContentItem-expandButton, .RichContent-inner--collapsed"
            )
            if expand_btn:
                await expand_btn.click()
                await random_delay(0.3, 0.6)

            # Try different content structures
            title = ""
            for sel in [
                "h1.QuestionHeader-title",
                "h1",
                ".Post-Title",
                ".ContentItem-title",
            ]:
                el = await page.query_selector(sel)
                if el:
                    title = (await el.inner_text()).strip()
                    break

            body = ""
            for sel in [
                ".RichContent-inner .RichText",
                ".Post-RichTextContainer",
                ".RichText",
            ]:
                el = await page.query_selector(sel)
                if el:
                    body = (await el.inner_text()).strip()
                    break

            author = ""
            for sel in [
                ".AuthorInfo-name a",
                ".AuthorInfo .UserLink-link",
                ".Post-Author a",
            ]:
                el = await page.query_selector(sel)
                if el:
                    author = (await el.inner_text()).strip()
                    break

            # Engagement metrics
            upvotes = await self._get_text(page, "button.VoteButton--up, .VoteButton")

            content_parts = [body]
            if upvotes:
                content_parts.extend(["", "---", f"- Upvotes: {upvotes}"])

            return ContentResult(
                title=title,
                content="\n".join(content_parts),
                author=author,
                url=url,
                platform=self.platform_name,
            )
        except Exception as exc:
            logger.error("Zhihu read failed for %s: %s", url, exc)
            return ContentResult(
                title="Error",
                content=f"Failed to read Zhihu content: {exc}",
                url=url,
                platform=self.platform_name,
            )
        finally:
            await page.close()

    async def _get_text(self, page, selector: str) -> str:  # noqa: ANN001
        """Safely extract inner text."""
        try:
            el = await page.query_selector(selector)
            return (await el.inner_text()).strip() if el else ""
        except Exception:
            return ""

    async def extract(self, url: str, fields: list[str]) -> ExtractResult:
        """Extract structured fields from a Zhihu page.

        Args:
            url: Zhihu URL.
            fields: Desired field names.

        Returns:
            Extracted fields.
        """
        content = await self.read(url)
        all_fields: dict = {
            "title": content.title,
            "author": content.author,
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
