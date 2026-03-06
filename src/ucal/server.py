"""UCAL MCP Server — Universal Content Access Layer.

Provides unified tools for accessing content across multiple platforms
(X/Twitter, Discord, XHS, Zhihu, and any generic website).

Platforms with APIs use direct API calls; platforms without APIs use
Playwright browser automation with anti-detection.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, ConfigDict, Field

from ucal.adapters.base import BaseAdapter, LoginMethod
from ucal.adapters.discord_api import DiscordAdapter
from ucal.adapters.generic import GenericAdapter
from ucal.adapters.twitter import TwitterAdapter
from ucal.adapters.xhs import XHSAdapter
from ucal.adapters.zhihu import ZhihuAdapter
from ucal.core.browser import BrowserManager
from ucal.core.session import SessionManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
PLATFORMS_YAML = CONFIG_DIR / "platforms.yaml"


def _load_platform_config() -> dict[str, Any]:
    """Load platform configuration from YAML file."""
    if PLATFORMS_YAML.exists():
        with open(PLATFORMS_YAML, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


# ---------------------------------------------------------------------------
# Lifespan — initialise browser + adapters once
# ---------------------------------------------------------------------------


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    """Manage browser manager and adapter instances across the server lifetime."""
    config = _load_platform_config()

    headless = config.get("browser", {}).get("headless", True)
    session_dir = config.get("browser", {}).get("session_dir")
    session_mgr = SessionManager(session_dir) if session_dir else SessionManager()
    browser_mgr = BrowserManager(headless=headless, session_manager=session_mgr)

    # Build adapters
    adapters: dict[str, BaseAdapter] = {}

    # API adapters
    x_cfg = config.get("platforms", {}).get("x", {})
    adapters["x"] = TwitterAdapter(
        bearer_token=x_cfg.get("bearer_token") or os.environ.get("X_BEARER_TOKEN"),
    )

    discord_cfg = config.get("platforms", {}).get("discord", {})
    adapters["discord"] = DiscordAdapter(
        bot_token=discord_cfg.get("bot_token") or os.environ.get("DISCORD_BOT_TOKEN"),
    )

    # Browser adapters
    adapters["xhs"] = XHSAdapter(browser_mgr)
    adapters["zhihu"] = ZhihuAdapter(browser_mgr)
    adapters["generic"] = GenericAdapter(browser_mgr)

    yield {"browser_manager": browser_mgr, "adapters": adapters}

    # Cleanup
    await browser_mgr.close()


mcp = FastMCP("ucal_mcp", lifespan=app_lifespan)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_adapter(ctx: Context, platform: str) -> BaseAdapter:
    """Resolve an adapter by platform name.

    Args:
        ctx: MCP context with lifespan state.
        platform: Platform identifier.

    Returns:
        The adapter instance.

    Raises:
        ValueError: If the platform is unknown.
    """
    adapters: dict[str, BaseAdapter] = ctx.request_context.lifespan_context["adapters"]
    adapter = adapters.get(platform)
    if adapter is None:
        supported = ", ".join(sorted(adapters.keys()))
        raise ValueError(f"Unknown platform '{platform}'. Supported: {supported}")
    return adapter


def _get_browser_manager(ctx: Context) -> BrowserManager:
    """Get the shared browser manager from context."""
    return ctx.request_context.lifespan_context["browser_manager"]


# Domain → platform mapping for auto-detection
_DOMAIN_PLATFORM_MAP: dict[str, str] = {
    "zhihu.com": "zhihu",
    "xiaohongshu.com": "xhs",
    "xhslink.com": "xhs",
    "twitter.com": "x",
    "x.com": "x",
    "discord.com": "discord",
}


def _detect_platform_from_url(url: str) -> str | None:
    """Auto-detect platform from URL domain.

    Returns the platform identifier if the URL matches a known platform,
    otherwise None (falls back to generic context).
    """
    if not url:
        return None
    try:
        from urllib.parse import urlparse

        hostname = urlparse(url).hostname or ""
        for domain, platform in _DOMAIN_PLATFORM_MAP.items():
            if hostname == domain or hostname.endswith("." + domain):
                return platform
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------


class PlatformName(str, Enum):
    """Supported platform identifiers."""

    X = "x"
    DISCORD = "discord"
    XHS = "xhs"
    ZHIHU = "zhihu"
    GENERIC = "generic"


class LoginInput(BaseModel):
    """Input for the platform_login tool."""

    model_config = ConfigDict(str_strip_whitespace=True)

    platform: PlatformName = Field(
        ...,
        description="Platform to login to: 'x', 'discord', 'xhs', 'zhihu', 'generic'",
    )
    method: str = Field(
        default="browser",
        description=(
            "Login method: 'browser' (manual login), 'cookie' (restore saved session), "
            "'api_key' (API token)"
        ),
    )


class SearchInput(BaseModel):
    """Input for the platform_search tool."""

    model_config = ConfigDict(str_strip_whitespace=True)

    platform: PlatformName = Field(
        ...,
        description="Platform to search: 'x', 'discord', 'xhs', 'zhihu'",
    )
    query: str = Field(
        ...,
        description="Search query string",
        min_length=1,
        max_length=500,
    )
    limit: int = Field(
        default=10,
        description="Maximum number of results to return",
        ge=1,
        le=100,
    )


class ReadInput(BaseModel):
    """Input for the platform_read tool."""

    model_config = ConfigDict(str_strip_whitespace=True)

    platform: PlatformName = Field(
        ...,
        description=(
            "Platform the URL belongs to: 'x', 'discord', 'xhs', 'zhihu', 'generic'"
        ),
    )
    url: str = Field(
        ...,
        description="The URL to read content from",
        min_length=1,
    )
    comment_limit: int | None = Field(
        default=None,
        description=(
            "Max top-level comments to extract. Default platform-specific "
            "(10 for XHS). Higher for deep research."
        ),
        ge=1,
        le=50,
    )
    expand_replies: int = Field(
        default=1,
        description=(
            "Times to click 'expand replies' per thread. 1=default safe, 2=deep, 3=max."
        ),
        ge=0,
        le=3,
    )


class ExtractInput(BaseModel):
    """Input for the platform_extract tool."""

    model_config = ConfigDict(str_strip_whitespace=True)

    platform: PlatformName = Field(
        ...,
        description="Platform the URL belongs to",
    )
    url: str = Field(
        ...,
        description="The URL to extract fields from",
        min_length=1,
    )
    fields: list[str] = Field(
        default_factory=lambda: [
            "title",
            "author",
            "content",
        ],
        description=(
            "Fields to extract: 'title', 'author', 'content', 'likes', "
            "'comments', 'tags', etc."
        ),
    )


class BrowserActionInput(BaseModel):
    """Input for the browser_action tool."""

    model_config = ConfigDict(str_strip_whitespace=True)

    url: str = Field(
        default="",
        description="Starting URL to navigate to before executing actions",
    )
    actions: list[dict[str, Any]] = Field(
        ...,
        description=(
            "List of browser actions. Each action is a dict with 'type' and "
            "type-specific params. Supported types: "
            "'goto' (url), 'click' (selector), 'type' (selector, text), "
            "'scroll' (direction, amount, selector?), 'screenshot', "
            "'extract_text' (selector), 'wait' (selector, timeout)"
        ),
    )
    network_intercept_patterns: list[str] = Field(
        default_factory=list,
        description=(
            "URL substring patterns to intercept network responses. "
            "When set, matching XHR/fetch responses are captured and "
            "returned as a 'network_intercept' entry in the results. "
            "Example: ['api/market/goods', 'api/user'] "
            "will capture all responses whose URL contains those substrings."
        ),
    )


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    name="ucal_platform_login",
    annotations={
        "title": "Login to Platform",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def ucal_platform_login(params: LoginInput, ctx: Context) -> str:
    """Login to a platform and save the session for future use.

    For browser-based platforms (xhs, zhihu), this opens a browser window
    where you can login manually (e.g. scan a QR code). For API platforms
    (x, discord), this validates the configured API token.

    Args:
        params: Login parameters.
        ctx: MCP context.

    Returns:
        JSON string with login status.
    """
    try:
        # Start browser if needed for browser-based platforms
        adapter = _get_adapter(ctx, params.platform.value)
        if params.platform.value in ("xhs", "zhihu") and params.method == "browser":
            bm = _get_browser_manager(ctx)
            bm.headless = False  # Need visible browser for manual login
            await bm.start()

        method_map = {
            "browser": LoginMethod.BROWSER,
            "cookie": LoginMethod.COOKIE,
            "api_key": LoginMethod.API_KEY,
        }
        login_method = method_map.get(params.method, LoginMethod.BROWSER)

        status = await adapter.login(method=login_method)
        return json.dumps(status.to_dict(), indent=2, ensure_ascii=False)

    except Exception as exc:
        return json.dumps(
            {"success": False, "error": str(exc)},
            indent=2,
            ensure_ascii=False,
        )


@mcp.tool(
    name="ucal_platform_search",
    annotations={
        "title": "Search Platform Content",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def ucal_platform_search(params: SearchInput, ctx: Context) -> str:
    """Search for content on a specified platform.

    For API platforms (x, discord) this calls the platform's search API.
    For browser platforms (xhs, zhihu) this simulates a search in the
    browser using anti-detection measures.

    Discord query format: 'channel_id:search_text'.

    Args:
        params: Search parameters.
        ctx: MCP context.

    Returns:
        JSON array of search results with title, url, summary, author.
    """
    try:
        adapter = _get_adapter(ctx, params.platform.value)

        # Start browser if needed
        if adapter.adapter_type.value == "browser":
            bm = _get_browser_manager(ctx)
            await bm.start()

        results = await adapter.search(params.query, limit=params.limit)
        return json.dumps(
            [r.to_dict() for r in results],
            indent=2,
            ensure_ascii=False,
        )

    except Exception as exc:
        return json.dumps(
            {"error": str(exc)},
            indent=2,
            ensure_ascii=False,
        )


@mcp.tool(
    name="ucal_platform_read",
    annotations={
        "title": "Read Platform Content",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def ucal_platform_read(params: ReadInput, ctx: Context) -> str:
    """Read the full content of a URL on the specified platform.

    Returns the content in Markdown format including title, body text,
    author, and engagement metrics where available.

    Args:
        params: Read parameters.
        ctx: MCP context.

    Returns:
        JSON with title, content (Markdown), author, url, platform.
    """
    try:
        adapter = _get_adapter(ctx, params.platform.value)

        if adapter.adapter_type.value == "browser":
            bm = _get_browser_manager(ctx)
            await bm.start()

        kwargs: dict[str, Any] = {}
        if params.comment_limit is not None:
            kwargs["comment_limit"] = params.comment_limit
        if params.expand_replies != 1:
            kwargs["expand_replies"] = params.expand_replies
        result = await adapter.read(params.url, **kwargs)
        return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)

    except Exception as exc:
        return json.dumps(
            {"error": str(exc)},
            indent=2,
            ensure_ascii=False,
        )


@mcp.tool(
    name="ucal_platform_extract",
    annotations={
        "title": "Extract Structured Data",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def ucal_platform_extract(params: ExtractInput, ctx: Context) -> str:
    """Extract specific structured fields from a URL.

    Useful for getting specific data points (title, author, likes, etc.)
    in a structured JSON format rather than full Markdown content.

    Args:
        params: Extract parameters with desired field list.
        ctx: MCP context.

    Returns:
        JSON with requested fields and their values.
    """
    try:
        adapter = _get_adapter(ctx, params.platform.value)

        if adapter.adapter_type.value == "browser":
            bm = _get_browser_manager(ctx)
            await bm.start()

        result = await adapter.extract(params.url, params.fields)
        return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)

    except Exception as exc:
        return json.dumps(
            {"error": str(exc)},
            indent=2,
            ensure_ascii=False,
        )


@mcp.tool(
    name="ucal_browser_action",
    annotations={
        "title": "Execute Browser Actions",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def ucal_browser_action(params: BrowserActionInput, ctx: Context) -> str:
    """Execute a sequence of browser actions on any webpage.

    This is a low-level fallback tool for when the platform-specific tools
    don't cover your use case. You can navigate, click, type, scroll,
    take screenshots, and extract text from arbitrary pages.

    Supported action types:
    - goto: {"type": "goto", "url": "https://..."}
    - click: {"type": "click", "selector": "button.submit"}
    - type: {"type": "type", "selector": "input.search", "text": "query"}
    - scroll: {"type": "scroll", "direction": "down", "amount": 500,
              "selector": ".content-area"}
    - screenshot: {"type": "screenshot"}
    - extract_text: {"type": "extract_text", "selector": ".content"}
    - wait: {"type": "wait", "selector": ".loaded", "timeout": 10000}

    Network interception: Set ``network_intercept_patterns`` to capture
    XHR/fetch responses whose URL contains the given substrings.
    Captured responses are appended as a ``network_intercept`` entry.

    Args:
        params: URL and action sequence.
        ctx: MCP context.

    Returns:
        JSON array of results for each action.
    """
    try:
        bm = _get_browser_manager(ctx)
        await bm.start()

        adapters: dict[str, BaseAdapter] = ctx.request_context.lifespan_context[
            "adapters"
        ]
        generic: GenericAdapter = adapters["generic"]  # type: ignore[assignment]

        # Auto-detect platform from URL to reuse saved session cookies.
        # e.g. zhihu.com → use "zhihu" context (with zhihu cookies)
        detected = _detect_platform_from_url(params.url)
        if detected:
            logger.info(
                "browser_action: auto-detected platform '%s' from URL", detected
            )

        results = await generic.execute_actions(
            params.url,
            params.actions,
            platform=detected,
            network_intercept_patterns=params.network_intercept_patterns,
        )
        return json.dumps(results, indent=2, ensure_ascii=False)

    except Exception as exc:
        return json.dumps(
            {"error": str(exc)},
            indent=2,
            ensure_ascii=False,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the UCAL MCP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[logging.StreamHandler()],
    )
    mcp.run()


if __name__ == "__main__":
    main()
