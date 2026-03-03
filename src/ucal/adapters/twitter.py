"""X/Twitter API adapter.

Uses the X API v2 with Bearer Token authentication.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ucal.adapters.base import (
    AdapterType,
    BaseAdapter,
    ContentResult,
    ExtractResult,
    LoginMethod,
    LoginStatus,
    SearchResult,
)

logger = logging.getLogger(__name__)

X_API_BASE = "https://api.twitter.com/2"


class TwitterAdapter(BaseAdapter):
    """X/Twitter adapter using the official v2 API.

    Requires a Bearer Token set via the ``X_BEARER_TOKEN`` environment
    variable or passed in the platform config.
    """

    platform_name = "x"
    adapter_type = AdapterType.API

    def __init__(self, bearer_token: str | None = None) -> None:
        self._token = bearer_token or os.environ.get("X_BEARER_TOKEN", "")
        self._logged_in = False

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def is_logged_in(self) -> bool:
        return self._logged_in and bool(self._token)

    async def login(self, method: LoginMethod = LoginMethod.API_KEY) -> LoginStatus:
        """Validate the API token.

        Args:
            method: Should be ``LoginMethod.API_KEY`` for this adapter.

        Returns:
            Login status.
        """
        if not self._token:
            return LoginStatus(
                success=False,
                platform=self.platform_name,
                method=method.value,
                message=(
                    "No bearer token. Set the X_BEARER_TOKEN environment variable "
                    "or add it to config/platforms.yaml."
                ),
            )
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{X_API_BASE}/users/me",
                    headers=self._headers(),
                )
                resp.raise_for_status()
            self._logged_in = True
            return LoginStatus(
                success=True,
                platform=self.platform_name,
                method=method.value,
                message="API token validated successfully.",
            )
        except httpx.HTTPStatusError as exc:
            return LoginStatus(
                success=False,
                platform=self.platform_name,
                method=method.value,
                message=f"Token validation failed: HTTP {exc.response.status_code}",
            )

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search recent tweets via the v2 search endpoint.

        Args:
            query: Search query.
            limit: Max results (10–100, default 10).

        Returns:
            List of search results.
        """
        params = {
            "query": query,
            "max_results": min(max(limit, 10), 100),
            "tweet.fields": "author_id,created_at,text",
            "expansions": "author_id",
            "user.fields": "username,name",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{X_API_BASE}/tweets/search/recent",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        # Build author lookup
        users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

        results: list[SearchResult] = []
        for tweet in data.get("data", []):
            author_id = tweet.get("author_id", "")
            user = users.get(author_id, {})
            username = user.get("username", "")
            results.append(
                SearchResult(
                    title=tweet["text"][:80],
                    url=f"https://x.com/{username}/status/{tweet['id']}",
                    summary=tweet["text"],
                    author=f"@{username}" if username else author_id,
                    platform=self.platform_name,
                    extra={"created_at": tweet.get("created_at", "")},
                )
            )
        return results

    async def read(self, url: str, **kwargs: Any) -> ContentResult:
        """Read a single tweet by URL.

        Args:
            url: Tweet URL (e.g. https://x.com/user/status/123).

        Returns:
            Tweet content.
        """
        tweet_id = url.rstrip("/").split("/")[-1]
        params = {
            "ids": tweet_id,
            "tweet.fields": "author_id,created_at,text,public_metrics",
            "expansions": "author_id",
            "user.fields": "username,name",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{X_API_BASE}/tweets",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        tweets = data.get("data", [])
        if not tweets:
            return ContentResult(
                title="Not Found",
                content="Tweet not found or not accessible.",
                url=url,
                platform=self.platform_name,
            )

        tweet = tweets[0]
        users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
        user = users.get(tweet.get("author_id", ""), {})
        username = user.get("username", "unknown")
        name = user.get("name", "")
        metrics = tweet.get("public_metrics", {})

        content_lines = [
            f"**@{username}** ({name})",
            "",
            tweet["text"],
            "",
            f"- Likes: {metrics.get('like_count', 0)}",
            f"- Retweets: {metrics.get('retweet_count', 0)}",
            f"- Replies: {metrics.get('reply_count', 0)}",
            f"- Posted: {tweet.get('created_at', '')}",
        ]

        return ContentResult(
            title=f"Tweet by @{username}",
            content="\n".join(content_lines),
            author=f"@{username}",
            url=url,
            platform=self.platform_name,
        )

    async def extract(self, url: str, fields: list[str]) -> ExtractResult:
        """Extract structured fields from a tweet.

        Args:
            url: Tweet URL.
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
