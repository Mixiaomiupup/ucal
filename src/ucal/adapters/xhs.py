"""XiaoHongShu (小红书) browser adapter.

Uses Playwright with stealth and human behavior simulation to access
XHS content that has no public API.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
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

XHS_BASE = "https://www.xiaohongshu.com"


class XHSAdapter(BaseAdapter):
    """Xiaohongshu adapter using Playwright browser automation.

    Requires manual QR-code login on first use; session is then persisted.
    """

    platform_name = "xhs"
    adapter_type = AdapterType.BROWSER

    def __init__(self, browser_manager: BrowserManager) -> None:
        self._bm = browser_manager
        self._logged_in = False

    def is_logged_in(self) -> bool:
        return self._logged_in

    async def login(self, method: LoginMethod = LoginMethod.BROWSER) -> LoginStatus:
        """Open XHS login page for manual QR-code scanning.

        After the user scans the QR code, the session is saved automatically.

        Args:
            method: Login method (browser or cookie).

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
                message="No saved session found. Use method='browser' to login.",
            )

        # Browser-based login: open login page for QR scan
        page = await self._bm.new_page(self.platform_name)
        try:
            await page.goto(f"{XHS_BASE}/explore", wait_until="domcontentloaded")
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

            # Wait for user to scan QR code (up to 120 seconds)
            logger.info(
                "Please scan the QR code in the browser window to login to XHS."
            )

            for _ in range(60):
                await asyncio.sleep(2)
                if await self._check_logged_in(page):
                    self._logged_in = True
                    session_file = await self._bm.save_session(self.platform_name)
                    return LoginStatus(
                        success=True,
                        platform=self.platform_name,
                        method=method.value,
                        message="Login successful via QR code scan.",
                        session_file=session_file,
                    )

            return LoginStatus(
                success=False,
                platform=self.platform_name,
                method=method.value,
                message="Login timed out. Please try again.",
            )
        finally:
            await page.close()

    async def _check_logged_in(self, page) -> bool:  # noqa: ANN001
        """Check if the user is logged in by looking for user avatar/menu."""
        try:
            avatar = await page.query_selector(
                ".user-avatar, .side-bar .user, .login-btn"
            )
            if avatar:
                class_name = await avatar.get_attribute("class") or ""
                return "login-btn" not in class_name
            return False
        except Exception:
            return False

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search XHS for posts matching the query.

        Args:
            query: Search query.
            limit: Max results to return.

        Returns:
            List of search results.
        """
        page = await self._bm.new_page(self.platform_name)
        results: list[SearchResult] = []
        try:
            search_url = (
                f"{XHS_BASE}/search_result"
                f"?keyword={query}&source=web_search_result_notes"
            )
            await page.goto(search_url, wait_until="domcontentloaded")

            # Wait for first card to appear
            try:
                await page.wait_for_selector("section.note-item", timeout=10_000)
            except Exception:
                logger.warning("No note cards appeared within timeout")
                return results

            await random_delay(0.3, 0.6)

            # Scroll to load more results.  XHS uses a 2-column waterfall
            # layout so we need enough scrolls to populate both columns.
            prev_count = 0
            for _ in range(max(limit // 3, 3)):
                await human_scroll(page, direction="down", amount=800)
                await random_delay(0.3, 0.6)
                cards = await page.query_selector_all("section.note-item")
                cur_count = len(cards)
                if cur_count >= limit or cur_count == prev_count:
                    break
                prev_count = cur_count

            # Extract note cards
            cards = await page.query_selector_all("section.note-item")
            for card in cards[:limit]:
                try:
                    # Title (some cards like videos may not have one)
                    title_el = await card.query_selector(".title")
                    title = await title_el.inner_text() if title_el else ""
                    title = title.strip()[:100]

                    # Note URL — accept any cover link with a note ID
                    link_el = await card.query_selector("a.cover")
                    link = ""
                    if link_el:
                        href = await link_el.get_attribute("href") or ""
                        if href and (
                            "/explore/" in href
                            or "/search_result/" in href
                            or "/discovery/item/" in href
                        ):
                            link = (
                                href if href.startswith("http") else f"{XHS_BASE}{href}"
                            )

                    # Skip cards without a link (e.g. "大家都在搜" blocks)
                    if not link:
                        continue

                    # Author name
                    author_el = await card.query_selector(".name")
                    author = await author_el.inner_text() if author_el else ""

                    # Like count
                    count_el = await card.query_selector(".count")
                    likes = await count_el.inner_text() if count_el else ""

                    results.append(
                        SearchResult(
                            title=title or "(untitled)",
                            url=link,
                            summary=title,
                            author=author.strip(),
                            platform=self.platform_name,
                            extra={"likes": likes.strip()} if likes else None,
                        )
                    )
                except Exception as exc:
                    logger.debug("Failed to parse XHS card: %s", exc)
                    continue

        except Exception as exc:
            logger.error("XHS search failed: %s", exc)
        finally:
            await page.close()

        return results

    async def read(self, url: str, **kwargs: Any) -> ContentResult:
        """Read full content of an XHS post including comments.

        Args:
            url: XHS note URL.
            **kwargs: Optional parameters:
                comment_limit (int): Max top-level comments (default 10).
                expand_replies (int): Times to click expand per thread
                    (default 1, max 3).

        Returns:
            Post content in Markdown format with top comments.
        """
        comment_limit: int = kwargs.get("comment_limit", 10)
        expand_depth: int = kwargs.get("expand_replies", 1)
        page = await self._bm.new_page(self.platform_name)
        try:
            await page.goto(url, wait_until="domcontentloaded")

            # Wait for comments to load (up to 10s)
            for _ in range(10):
                await asyncio.sleep(1)
                items = await page.query_selector_all(
                    ".comments-container .parent-comment,"
                    ".comments-container .comment-item"
                )
                if items:
                    break

            # Extract title
            title_el = await page.query_selector("#detail-title, .title, .note-title")
            title = await title_el.inner_text() if title_el else ""

            # Extract body — use #detail-desc first (note detail page)
            body_el = await page.query_selector("#detail-desc")
            if not body_el:
                body_el = await page.query_selector(".note-text, .content, .desc")
            body = await body_el.inner_text() if body_el else ""

            # Extract tags from body text (regex) and DOM elements
            raw_tags = re.findall(r"#([^\s#]+)", body)
            # Strip BOM / zero-width chars and dedupe
            _zw = "\ufeff\u200b"
            tags: list[str] = list(
                dict.fromkeys(t.strip(_zw) for t in raw_tags if t.strip(_zw))
            )
            try:
                tag_els = await page.query_selector_all(
                    '#detail-desc a[href*="keyword="], .tag-item'
                )
                for el in tag_els:
                    t = (await el.inner_text()).strip().lstrip("#")
                    if t and t not in tags:
                        tags.append(t)
            except Exception:
                pass

            # Extract author — use .author-wrapper .name in note detail
            author_el = await page.query_selector(
                ".author-wrapper .name, .user-nickname, .username"
            )
            author = await author_el.inner_text() if author_el else ""

            # Extract engagement metrics from bottom bar
            likes = await self._get_text(page, ".like-wrapper .count")
            comment_count = await self._get_text(page, ".comments-container .total")
            collects = await self._get_text(page, ".collect-wrapper .count")

            content_parts = [body]
            if any([likes, comment_count, collects]):
                content_parts.append("")
                content_parts.append("---")
                if likes:
                    content_parts.append(f"- Likes: {likes}")
                if comment_count:
                    content_parts.append(f"- Comments: {comment_count}")
                if collects:
                    content_parts.append(f"- Collects: {collects}")

            # Extract comments with sub-comments.
            # DOM: .parent-comment > .comment-item (main) + .reply-container
            #   reply-container has visible sub-comments and expand button.
            hot_threads: list[dict[str, Any]] = []
            parent_comments = await page.query_selector_all(
                ".comments-container .parent-comment"
            )
            if parent_comments:
                content_parts.append("")
                content_parts.append("## Top Comments")
                for parent in parent_comments[:comment_limit]:
                    # Main comment is the direct .comment-item child
                    main = await parent.query_selector(":scope > .comment-item")
                    if not main:
                        continue
                    name = await self._get_child_text(main, ".name")
                    text = await self._get_comment_content(main)
                    date = await self._get_child_text(main, ".info .date, .info")
                    if not (name and text):
                        continue
                    date_clean = date.split("\n")[0] if date else ""
                    content_parts.append(
                        f"- **{name}**: {text}"
                        + (f" ({date_clean})" if date_clean else "")
                    )

                    # Click expand button to load sub-comments
                    reply_container = await parent.query_selector(".reply-container")
                    has_expand_btn = False
                    if reply_container:
                        # Check for expand button before clicking
                        pre_expand = await reply_container.query_selector(
                            ".show-more span, .show-more"
                        )
                        has_expand_btn = pre_expand is not None
                        await self._expand_replies(
                            reply_container, max_clicks=expand_depth
                        )

                    # Extract sub-comments from reply-container
                    sub_items = await parent.query_selector_all(
                        ".reply-container .comment-item"
                    )
                    for sub in sub_items:
                        sub_name = await self._get_child_text(sub, ".name")
                        sub_text = await self._get_comment_content(sub)
                        sub_date = await self._get_child_text(sub, ".info .date, .info")
                        if sub_name and sub_text:
                            sub_date_clean = sub_date.split("\n")[0] if sub_date else ""
                            content_parts.append(
                                f"  - **{sub_name}**: {sub_text}"
                                + (f" ({sub_date_clean})" if sub_date_clean else "")
                            )

                    # Track hot discussion threads
                    if len(sub_items) >= 3 or has_expand_btn:
                        hot_threads.append(
                            {
                                "author": name,
                                "preview": text[:80],
                                "sub_count": len(sub_items),
                                "has_more": has_expand_btn,
                            }
                        )

                    # Note remaining folded replies
                    await self._note_folded_replies(
                        reply_container if reply_container else parent,
                        content_parts,
                    )

            # Build extra metadata
            extra: dict[str, Any] = {}
            if tags:
                extra["tags"] = tags
            if hot_threads:
                extra["hot_threads"] = hot_threads

            return ContentResult(
                title=title.strip(),
                content="\n".join(content_parts),
                author=author.strip(),
                url=url,
                platform=self.platform_name,
                extra=extra,
            )
        except Exception as exc:
            logger.error("XHS read failed for %s: %s", url, exc)
            return ContentResult(
                title="Error",
                content=f"Failed to read XHS post: {exc}",
                url=url,
                platform=self.platform_name,
            )
        finally:
            await page.close()

    async def _expand_replies(
        self,
        container,
        max_clicks: int = 1,  # noqa: ANN001
    ) -> None:
        """Click the expand button in a reply container to load sub-comments.

        Args:
            container: The reply container element.
            max_clicks: Number of times to click expand (1-3). Each subsequent
                click uses a progressively longer delay to mimic human behavior.
        """
        for click_num in range(max_clicks):
            try:
                expand_btn = await container.query_selector(
                    ".show-more span, .show-more"
                )
                if not expand_btn:
                    break
                btn_text = (await expand_btn.inner_text()).strip()
                if not btn_text:
                    break
                await expand_btn.click()
                delay = 1.5 + (click_num * 0.5) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
            except Exception:
                break

    async def _note_folded_replies(
        self,
        container,  # noqa: ANN001
        content_parts: list[str],
    ) -> None:
        """Append a note about remaining folded replies if expand button exists."""
        try:
            expand_btn = await container.query_selector(".show-more span, .show-more")
            if expand_btn:
                text = (await expand_btn.inner_text()).strip()
                if text:
                    content_parts.append(f"  - _{text}_")
        except Exception:
            pass

    async def _get_child_text(self, parent, selector: str) -> str:  # noqa: ANN001
        """Safely extract inner text from a child selector within a parent element."""
        try:
            el = await parent.query_selector(selector)
            return (await el.inner_text()).strip() if el else ""
        except Exception:
            return ""

    async def _get_comment_content(self, item) -> str:  # noqa: ANN001
        """Extract comment text and inline images as markdown."""
        text = await self._get_child_text(item, ".note-text")
        try:
            images = await item.query_selector_all(".note-text img, .comment-img img")
            img_parts = []
            for img in images:
                src = await img.get_attribute("src") or ""
                if src:
                    img_parts.append(f"![comment-img]({src})")
            if img_parts:
                text += " " + " ".join(img_parts)
        except Exception:
            pass
        return text

    async def _get_text(self, page, selector: str) -> str:  # noqa: ANN001
        """Safely extract inner text from a selector."""
        try:
            el = await page.query_selector(selector)
            return (await el.inner_text()).strip() if el else ""
        except Exception:
            return ""

    async def extract(self, url: str, fields: list[str]) -> ExtractResult:
        """Extract structured fields from an XHS post.

        Args:
            url: XHS note URL.
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
