"""Discord API adapter.

Uses the Discord Bot REST API with a Bot Token.
"""

from __future__ import annotations

import logging
import os

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

DISCORD_API_BASE = "https://discord.com/api/v10"


class DiscordAdapter(BaseAdapter):
    """Discord adapter using Bot Token + REST API.

    Requires a Bot Token set via the ``DISCORD_BOT_TOKEN`` environment
    variable or passed in the platform config.
    """

    platform_name = "discord"
    adapter_type = AdapterType.API

    def __init__(self, bot_token: str | None = None) -> None:
        self._token = bot_token or os.environ.get("DISCORD_BOT_TOKEN", "")
        self._logged_in = False

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bot {self._token}"}

    def is_logged_in(self) -> bool:
        return self._logged_in and bool(self._token)

    async def login(self, method: LoginMethod = LoginMethod.API_KEY) -> LoginStatus:
        """Validate the bot token.

        Args:
            method: Should be ``LoginMethod.API_KEY``.

        Returns:
            Login status.
        """
        if not self._token:
            return LoginStatus(
                success=False,
                platform=self.platform_name,
                method=method.value,
                message=(
                    "No bot token. Set the DISCORD_BOT_TOKEN environment variable "
                    "or add it to config/platforms.yaml."
                ),
            )
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{DISCORD_API_BASE}/users/@me",
                    headers=self._headers(),
                )
                resp.raise_for_status()
            self._logged_in = True
            return LoginStatus(
                success=True,
                platform=self.platform_name,
                method=method.value,
                message="Bot token validated successfully.",
            )
        except httpx.HTTPStatusError as exc:
            return LoginStatus(
                success=False,
                platform=self.platform_name,
                method=method.value,
                message=f"Token validation failed: HTTP {exc.response.status_code}",
            )

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search messages in a channel.

        The ``query`` should be formatted as ``channel_id:search_text``
        (e.g. ``"123456789:hello world"``).

        Args:
            query: ``channel_id:search_text`` format.
            limit: Max messages to return.

        Returns:
            List of matching messages.
        """
        if ":" not in query:
            return [
                SearchResult(
                    title="Error",
                    url="",
                    summary=(
                        "Query format: 'channel_id:search_text'. "
                        "Example: '123456789:hello world'"
                    ),
                    platform=self.platform_name,
                )
            ]

        channel_id, search_text = query.split(":", 1)
        channel_id = channel_id.strip()
        search_text = search_text.strip().lower()

        params: dict = {"limit": min(limit, 100)}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            messages = resp.json()

        results: list[SearchResult] = []
        for msg in messages:
            if search_text and search_text not in msg.get("content", "").lower():
                continue
            author = msg.get("author", {})
            results.append(
                SearchResult(
                    title=msg["content"][:80] if msg.get("content") else "(no text)",
                    url=(
                        f"https://discord.com/channels/"
                        f"@me/{channel_id}/{msg['id']}"
                    ),
                    summary=msg.get("content", ""),
                    author=author.get("username", ""),
                    platform=self.platform_name,
                    extra={"timestamp": msg.get("timestamp", "")},
                )
            )
            if len(results) >= limit:
                break

        return results

    async def read(self, url: str) -> ContentResult:
        """Read a single message by URL.

        Expected URL format:
        ``https://discord.com/channels/{guild}/{channel}/{message}``

        Args:
            url: Discord message URL.

        Returns:
            Message content.
        """
        parts = url.rstrip("/").split("/")
        if len(parts) < 3:
            return ContentResult(
                title="Error",
                content="Invalid Discord URL format.",
                url=url,
                platform=self.platform_name,
            )

        channel_id = parts[-2]
        message_id = parts[-1]

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            msg = resp.json()

        author = msg.get("author", {})
        username = author.get("username", "unknown")

        return ContentResult(
            title=f"Message by {username}",
            content=msg.get("content", ""),
            author=username,
            url=url,
            platform=self.platform_name,
            extra={"timestamp": msg.get("timestamp", "")},
        )

    async def extract(self, url: str, fields: list[str]) -> ExtractResult:
        """Extract structured fields from a Discord message.

        Args:
            url: Discord message URL.
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
            "timestamp": content.extra.get("timestamp", ""),
        }
        selected = {k: all_fields.get(k, "") for k in fields} if fields else all_fields
        return ExtractResult(
            fields=selected,
            url=url,
            platform=self.platform_name,
        )
