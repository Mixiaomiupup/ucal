"""X/Twitter browser adapter.

Uses Playwright with stealth and human behavior simulation to access
Twitter content, including private data like following lists.
"""

from __future__ import annotations

import asyncio
import logging
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

X_BASE = "https://x.com"

# Centralised selectors — Twitter changes DOM frequently so keep all
# selectors here for easy updates.  Each key may list fallbacks separated
# by commas (CSS selector list syntax).
_SELECTORS: dict[str, str] = {
    # Login-state detection
    "profile_link": (
        '[data-testid="AppTabBar_Profile_Link"],'
        ' nav[aria-label="Primary"] a[href$="/profile"]'
    ),
    # Login wall / modal
    "login_wall": (
        '[data-testid="sheetDialog"],'
        ' [data-testid="bottomBar"],'
        ' div[role="dialog"][aria-modal="true"]'
    ),
    "login_wall_close": (
        '[data-testid="sheetDialog"]'
        ' [role="button"][aria-label="Close"],'
        ' div[role="dialog"] [aria-label="Close"]'
    ),
    # Tweet / post card
    "tweet": ('[data-testid="tweet"], article[role="article"]'),
    "tweet_text": '[data-testid="tweetText"]',
    "tweet_user": ('[data-testid="User-Name"], [data-testid="User-Names"]'),
    "tweet_time": "time",
    "tweet_metrics": (
        '[data-testid="reply"], [data-testid="retweet"], [data-testid="like"]'
    ),
    # User cell (following/followers lists)
    "user_cell": '[data-testid="UserCell"]',
    "user_cell_name": ('[data-testid="UserCell"] div[dir="ltr"] > span'),
    "user_cell_link": 'a[role="link"][href^="/"]',
    # Search
    "search_input": ('[data-testid="SearchBox_Search_Input"]'),
}


class TwitterBrowserAdapter(BaseAdapter):
    """X/Twitter adapter using Playwright browser automation.

    Replaces the API-only adapter to support authenticated access
    (following lists, private accounts, etc.) via browser session.
    """

    platform_name = "x"
    adapter_type = AdapterType.BROWSER

    def __init__(self, browser_manager: BrowserManager) -> None:
        self._bm = browser_manager
        self._logged_in = False

    def is_logged_in(self) -> bool:
        return self._logged_in

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self, method: LoginMethod = LoginMethod.BROWSER) -> LoginStatus:
        """Open X login page for manual login or restore saved session.

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

        page = await self._bm.new_page(self.platform_name)
        try:
            await page.goto(f"{X_BASE}/login", wait_until="domcontentloaded")
            await random_delay(1.0, 2.0)

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

            logger.info("Please login to X/Twitter in the browser window.")

            for _ in range(60):
                await asyncio.sleep(2)
                if await self._check_logged_in(page):
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
                message="Login timed out. Please try again.",
            )
        finally:
            await page.close()

    async def _check_logged_in(self, page) -> bool:  # noqa: ANN001
        """Detect whether the user is logged in by checking for profile link."""
        try:
            el = await page.query_selector(_SELECTORS["profile_link"])
            return el is not None
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Login wall handling
    # ------------------------------------------------------------------

    async def _dismiss_login_wall(self, page) -> bool:  # noqa: ANN001
        """Try to close Twitter's login wall modal.

        Returns True if a wall was detected (whether or not it was closed).
        """
        try:
            wall = await page.query_selector(_SELECTORS["login_wall"])
            if not wall:
                return False

            # Try clicking close button
            close_btn = await page.query_selector(_SELECTORS["login_wall_close"])
            if close_btn:
                await close_btn.click()
                await random_delay(0.3, 0.6)
                return True

            # Fallback: press Escape
            await page.keyboard.press("Escape")
            await random_delay(0.3, 0.6)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Read — URL-based routing
    # ------------------------------------------------------------------

    async def read(self, url: str, **kwargs: Any) -> ContentResult:
        """Read content from a Twitter URL.

        Routes to the appropriate handler based on URL pattern:
        - ``/following`` → following list
        - ``/status/`` → single tweet
        - Otherwise → user timeline

        Args:
            url: Twitter URL.
            **kwargs: Optional parameters:
                limit (int): Max items to fetch (default varies by type).

        Returns:
            Content in Markdown format.
        """
        if "/following" in url:
            return await self._read_following(url, **kwargs)
        elif "/status/" in url:
            return await self._read_tweet(url, **kwargs)
        else:
            return await self._read_user_tweets(url, **kwargs)

    # ------------------------------------------------------------------
    # Read: following list
    # ------------------------------------------------------------------

    async def _read_following(self, url: str, **kwargs: Any) -> ContentResult:
        """Scrape a user's following list.

        Args:
            url: URL like https://x.com/{username}/following
            **kwargs: limit (int) — max users to collect (default 50).
        """
        limit: int = kwargs.get("limit", 50)
        page = await self._bm.new_page(self.platform_name)
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await random_delay(1.5, 2.5)

            # Wait for first user cell
            try:
                await page.wait_for_selector(_SELECTORS["user_cell"], timeout=10_000)
            except Exception:
                # Might be behind login wall
                await self._dismiss_login_wall(page)
                try:
                    await page.wait_for_selector(_SELECTORS["user_cell"], timeout=5_000)
                except Exception:
                    return ContentResult(
                        title="Following list",
                        content=(
                            "Could not load following list."
                            " You may need to login first."
                        ),
                        url=url,
                        platform=self.platform_name,
                    )

            seen_handles: set[str] = set()
            users: list[dict[str, str]] = []
            stale_rounds = 0

            while len(users) < limit and stale_rounds < 5:
                cells = await page.query_selector_all(_SELECTORS["user_cell"])
                new_found = False
                for cell in cells:
                    if len(users) >= limit:
                        break
                    info = await self._extract_user_cell(cell)
                    if info and info["handle"] not in seen_handles:
                        seen_handles.add(info["handle"])
                        users.append(info)
                        new_found = True

                if not new_found:
                    stale_rounds += 1
                else:
                    stale_rounds = 0

                if len(users) >= limit:
                    break

                await self._dismiss_login_wall(page)
                await human_scroll(page, direction="down", amount=800)
                await random_delay(1.5, 3.0)

            # Extract username from URL
            username = self._username_from_url(url)

            # Build markdown
            lines = [f"Following list for @{username} ({len(users)} users)\n"]
            for u in users:
                lines.append(f"- **{u['name']}** (@{u['handle']})")

            return ContentResult(
                title=f"@{username}'s following list",
                content="\n".join(lines),
                author=f"@{username}",
                url=url,
                platform=self.platform_name,
                extra={"count": len(users)},
            )
        except Exception as exc:
            logger.error("Failed to read following list %s: %s", url, exc)
            return ContentResult(
                title="Error",
                content=f"Failed to read following list: {exc}",
                url=url,
                platform=self.platform_name,
            )
        finally:
            await page.close()

    async def _extract_user_cell(self, cell) -> dict[str, str] | None:  # noqa: ANN001
        """Extract display name and handle from a UserCell element."""
        try:
            # Find the profile link to get the handle
            links = await cell.query_selector_all('a[role="link"]')
            handle = ""
            for link in links:
                href = await link.get_attribute("href") or ""
                # Profile links are like /username (no further segments)
                if href and re.match(r"^/[A-Za-z0-9_]+$", href):
                    handle = href.lstrip("/")
                    break

            if not handle:
                return None

            # Display name — first dir="ltr" span in the cell
            name_el = await cell.query_selector('div[dir="ltr"] > span')
            name = ""
            if name_el:
                name = (await name_el.inner_text()).strip()

            return {"handle": handle, "name": name or handle}
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Read: user tweets
    # ------------------------------------------------------------------

    async def _read_user_tweets(self, url: str, **kwargs: Any) -> ContentResult:
        """Scrape recent tweets from a user's profile.

        Args:
            url: URL like https://x.com/{username}
            **kwargs: limit (int) — max tweets (default 10).
        """
        limit: int = kwargs.get("limit", 10)
        page = await self._bm.new_page(self.platform_name)
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await random_delay(1.5, 2.5)

            try:
                await page.wait_for_selector(_SELECTORS["tweet"], timeout=10_000)
            except Exception:
                await self._dismiss_login_wall(page)
                try:
                    await page.wait_for_selector(_SELECTORS["tweet"], timeout=5_000)
                except Exception:
                    return ContentResult(
                        title="User tweets",
                        content="Could not load tweets. You may need to login first.",
                        url=url,
                        platform=self.platform_name,
                    )

            seen_texts: set[str] = set()
            tweets: list[dict[str, str]] = []
            stale_rounds = 0

            while len(tweets) < limit and stale_rounds < 5:
                articles = await page.query_selector_all(_SELECTORS["tweet"])
                new_found = False
                for article in articles:
                    if len(tweets) >= limit:
                        break
                    info = await self._extract_tweet(article)
                    if info and info["text"] not in seen_texts:
                        seen_texts.add(info["text"])
                        tweets.append(info)
                        new_found = True

                if not new_found:
                    stale_rounds += 1
                else:
                    stale_rounds = 0

                if len(tweets) >= limit:
                    break

                await self._dismiss_login_wall(page)
                await human_scroll(page, direction="down", amount=800)
                await random_delay(1.5, 3.0)

            username = self._username_from_url(url)
            lines = [f"Recent tweets from @{username} ({len(tweets)} tweets)\n"]
            for t in tweets:
                lines.append(f"### {t.get('author', username)} · {t.get('time', '')}")
                lines.append(t["text"])
                if t.get("metrics"):
                    lines.append(f"_{t['metrics']}_")
                if t.get("url"):
                    lines.append(f"[View tweet]({t['url']})")
                lines.append("")

            return ContentResult(
                title=f"@{username}'s tweets",
                content="\n".join(lines),
                author=f"@{username}",
                url=url,
                platform=self.platform_name,
                extra={"count": len(tweets)},
            )
        except Exception as exc:
            logger.error("Failed to read user tweets %s: %s", url, exc)
            return ContentResult(
                title="Error",
                content=f"Failed to read user tweets: {exc}",
                url=url,
                platform=self.platform_name,
            )
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # Read: single tweet
    # ------------------------------------------------------------------

    async def _read_tweet(self, url: str, **kwargs: Any) -> ContentResult:
        """Read a single tweet and its replies.

        Args:
            url: Tweet URL like https://x.com/user/status/123
        """
        page = await self._bm.new_page(self.platform_name)
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await random_delay(1.5, 2.5)

            try:
                await page.wait_for_selector(_SELECTORS["tweet"], timeout=10_000)
            except Exception:
                await self._dismiss_login_wall(page)
                try:
                    await page.wait_for_selector(_SELECTORS["tweet"], timeout=5_000)
                except Exception:
                    return ContentResult(
                        title="Tweet",
                        content="Could not load tweet. You may need to login first.",
                        url=url,
                        platform=self.platform_name,
                    )

            articles = await page.query_selector_all(_SELECTORS["tweet"])
            if not articles:
                return ContentResult(
                    title="Tweet not found",
                    content="No tweet content found at this URL.",
                    url=url,
                    platform=self.platform_name,
                )

            # First article is the main tweet
            main_tweet = await self._extract_tweet(articles[0])
            if not main_tweet:
                return ContentResult(
                    title="Tweet",
                    content="Could not extract tweet content.",
                    url=url,
                    platform=self.platform_name,
                )

            lines = [
                f"**{main_tweet.get('author', '')}**",
                "",
                main_tweet["text"],
                "",
            ]
            if main_tweet.get("time"):
                lines.append(f"Posted: {main_tweet['time']}")
            if main_tweet.get("metrics"):
                lines.append(main_tweet["metrics"])

            # Scroll to load some replies
            reply_limit: int = kwargs.get("limit", 5)
            await human_scroll(page, direction="down", amount=600)
            await random_delay(1.0, 2.0)

            reply_articles = await page.query_selector_all(_SELECTORS["tweet"])
            replies: list[dict[str, str]] = []
            seen_texts: set[str] = set()
            seen_texts.add(main_tweet["text"])

            for article in reply_articles:
                if len(replies) >= reply_limit:
                    break
                info = await self._extract_tweet(article)
                if info and info["text"] not in seen_texts:
                    seen_texts.add(info["text"])
                    replies.append(info)

            if replies:
                lines.append("")
                lines.append("## Replies")
                for r in replies:
                    reply_line = (
                        f"- **{r.get('author', '')}**: {r['text']}"
                        + (f" ({r['time']})" if r.get("time") else "")
                    )
                    if r.get("url"):
                        reply_line += f" [↗]({r['url']})"
                    lines.append(reply_line)

            return ContentResult(
                title=f"Tweet by {main_tweet.get('author', '')}",
                content="\n".join(lines),
                author=main_tweet.get("author", ""),
                url=url,
                platform=self.platform_name,
            )
        except Exception as exc:
            logger.error("Failed to read tweet %s: %s", url, exc)
            return ContentResult(
                title="Error",
                content=f"Failed to read tweet: {exc}",
                url=url,
                platform=self.platform_name,
            )
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search Twitter for tweets matching the query.

        Args:
            query: Search query.
            limit: Max results to return.

        Returns:
            List of search results.
        """
        page = await self._bm.new_page(self.platform_name)
        results: list[SearchResult] = []
        try:
            from urllib.parse import quote

            search_url = f"{X_BASE}/search?q={quote(query)}&src=typed_query"
            await page.goto(search_url, wait_until="domcontentloaded")
            await random_delay(1.5, 2.5)

            try:
                await page.wait_for_selector(_SELECTORS["tweet"], timeout=10_000)
            except Exception:
                await self._dismiss_login_wall(page)
                try:
                    await page.wait_for_selector(_SELECTORS["tweet"], timeout=5_000)
                except Exception:
                    logger.warning("No search results appeared")
                    return results

            seen_texts: set[str] = set()
            stale_rounds = 0

            while len(results) < limit and stale_rounds < 5:
                articles = await page.query_selector_all(_SELECTORS["tweet"])
                new_found = False
                for article in articles:
                    if len(results) >= limit:
                        break
                    info = await self._extract_tweet(article)
                    if not info or info["text"] in seen_texts:
                        continue
                    seen_texts.add(info["text"])
                    new_found = True

                    results.append(
                        SearchResult(
                            title=info["text"][:80],
                            url=info.get("url") or X_BASE,
                            summary=info["text"],
                            author=info.get("author", ""),
                            platform=self.platform_name,
                            extra={
                                "time": info.get("time", ""),
                                "metrics": info.get("metrics", ""),
                            },
                        )
                    )

                if not new_found:
                    stale_rounds += 1
                else:
                    stale_rounds = 0

                if len(results) >= limit:
                    break

                await self._dismiss_login_wall(page)
                await human_scroll(page, direction="down", amount=800)
                await random_delay(1.5, 3.0)

        except Exception as exc:
            logger.error("Twitter search failed: %s", exc)
        finally:
            await page.close()

        return results

    # ------------------------------------------------------------------
    # Extract
    # ------------------------------------------------------------------

    async def extract(self, url: str, fields: list[str]) -> ExtractResult:
        """Extract structured fields from a tweet.

        Args:
            url: Tweet URL.
            fields: Desired field names.

        Returns:
            Extracted fields.
        """
        content = await self.read(url)
        all_fields: dict[str, Any] = {
            "title": content.title,
            "author": content.author,
            "content": content.content,
            "url": url,
            "platform": self.platform_name,
        }
        if content.extra:
            all_fields.update(content.extra)
        selected = {k: all_fields.get(k, "") for k in fields} if fields else all_fields
        return ExtractResult(
            fields=selected,
            url=url,
            platform=self.platform_name,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _extract_tweet(self, article) -> dict[str, str] | None:  # noqa: ANN001
        """Extract text, author, time, and metrics from a tweet article."""
        try:
            # Tweet text
            text_el = await article.query_selector(_SELECTORS["tweet_text"])
            text = ""
            if text_el:
                text = (await text_el.inner_text()).strip()
            if not text:
                return None

            # Author
            user_el = await article.query_selector(_SELECTORS["tweet_user"])
            author = ""
            if user_el:
                author = (await user_el.inner_text()).strip()
                # Clean up — often contains newlines between name and @handle
                parts = [p.strip() for p in author.split("\n") if p.strip()]
                # Keep display name and @handle
                if len(parts) >= 2:
                    author = " ".join(parts[:2])
                elif parts:
                    author = parts[0]
                else:
                    author = ""

            # Time
            time_el = await article.query_selector(_SELECTORS["tweet_time"])
            time_str = ""
            if time_el:
                time_str = await time_el.get_attribute("datetime") or ""
                if not time_str:
                    time_str = (await time_el.inner_text()).strip()

            # Metrics (replies, retweets, likes)
            metrics_parts: list[str] = []
            for testid in ("reply", "retweet", "like"):
                try:
                    el = await article.query_selector(f'[data-testid="{testid}"]')
                    if el:
                        val = (await el.get_attribute("aria-label")) or ""
                        if val:
                            metrics_parts.append(val)
                except Exception:
                    pass
            metrics = " · ".join(metrics_parts)

            # Tweet permalink URL
            tweet_url = ""
            try:
                time_link = await article.query_selector("time")
                if time_link:
                    parent = await time_link.evaluate_handle(
                        "el => el.closest('a')"
                    )
                    if parent:
                        href = await parent.get_property("href")
                        href_str = await href.json_value()
                        if href_str and "/status/" in str(href_str):
                            tweet_url = str(href_str)
            except Exception:
                pass

            return {
                "text": text,
                "author": author,
                "time": time_str,
                "metrics": metrics,
                "url": tweet_url,
            }
        except Exception:
            return None

    @staticmethod
    def _username_from_url(url: str) -> str:
        """Extract username from a Twitter URL path."""
        from urllib.parse import urlparse

        path = urlparse(url).path.strip("/")
        # Path: username or username/following etc.
        return path.split("/")[0] if path else "unknown"
