"""Playwright browser lifecycle manager.

Handles launching, context creation (with anti-detection), page management,
and graceful shutdown.  Provides a retry wrapper for flaky browser operations.
"""

from __future__ import annotations

import atexit
import asyncio
import logging
import os
import signal
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from ucal.core.anti_detect import (
    apply_anti_detect_scripts,
    apply_stealth,
    get_stealth_context_options,
)
from ucal.core.session import SessionManager

logger = logging.getLogger(__name__)

# Track all browser PIDs globally so atexit/signal handlers can kill them
# even when the async event loop is gone.
_browser_pids: set[int] = set()


def _kill_browser_pids() -> None:
    """Kill any tracked browser processes on interpreter exit."""
    for pid in list(_browser_pids):
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info("atexit: sent SIGTERM to browser PID %d", pid)
        except OSError:
            pass
    _browser_pids.clear()


atexit.register(_kill_browser_pids)


class BrowserManager:
    """Manages a single Playwright browser instance shared across adapters.

    Args:
        headless: Whether to run the browser headless.
        session_manager: Optional session manager for cookie persistence.
    """

    def __init__(
        self,
        headless: bool = True,
        session_manager: SessionManager | None = None,
    ) -> None:
        self.headless = headless
        self.session_manager = session_manager or SessionManager()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._contexts: dict[str, BrowserContext] = {}

    async def start(self) -> None:
        """Launch the Playwright browser."""
        if self._browser:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
            ],
        )
        # Track the browser process PID for atexit cleanup
        try:
            pid = self._browser.process.pid  # type: ignore[union-attr]
            _browser_pids.add(pid)
            logger.info(
                "Browser launched (headless=%s, pid=%d)", self.headless, pid
            )
        except Exception:
            logger.info("Browser launched (headless=%s)", self.headless)

    async def get_context(
        self,
        platform: str,
        *,
        load_session: bool = True,
    ) -> BrowserContext:
        """Get or create a browser context for a platform.

        If a saved session exists it will be loaded automatically.

        Args:
            platform: Platform identifier (used as context key).
            load_session: Whether to restore a saved session.

        Returns:
            A Playwright BrowserContext.
        """
        if platform in self._contexts:
            return self._contexts[platform]

        if not self._browser:
            await self.start()
        assert self._browser is not None

        opts = get_stealth_context_options()

        # Restore cookies / storage state if available
        if load_session:
            state = self.session_manager.load_session_state(platform)
            if state is not None:
                opts["storage_state"] = state
                logger.info("Restored session for %s", platform)

        context = await self._browser.new_context(**opts)
        self._contexts[platform] = context
        return context

    async def new_page(self, platform: str) -> Page:
        """Open a new stealth page inside the platform's context.

        Args:
            platform: Platform identifier.

        Returns:
            A stealth-patched Playwright Page.
        """
        context = await self.get_context(platform)
        page = await context.new_page()
        await apply_stealth(page)
        await apply_anti_detect_scripts(page)
        return page

    async def save_session(self, platform: str) -> str:
        """Persist the current context's cookies / storage state.

        Args:
            platform: Platform identifier.

        Returns:
            Path to the saved session file.
        """
        context = self._contexts.get(platform)
        if context is None:
            raise RuntimeError(f"No active context for platform '{platform}'")
        return await self.session_manager.save_session(platform, context)

    async def close_context(self, platform: str) -> None:
        """Close and remove a platform's browser context.

        Args:
            platform: Platform identifier.
        """
        context = self._contexts.pop(platform, None)
        if context:
            await context.close()
            logger.info("Context closed for %s", platform)

    async def close(self) -> None:
        """Shutdown the browser and all contexts."""
        for name in list(self._contexts):
            await self.close_context(name)
        if self._browser:
            try:
                pid = self._browser.process.pid  # type: ignore[union-attr]
                _browser_pids.discard(pid)
            except Exception:
                pass
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Browser manager shut down")


async def with_retry(
    coro_factory: Any,
    *,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    description: str = "operation",
) -> Any:
    """Retry an async operation with exponential-ish back-off.

    Args:
        coro_factory: A callable that returns an awaitable.
        max_retries: Maximum attempts.
        retry_delay: Base delay in seconds between retries.
        description: Label for log messages.

    Returns:
        The result of the successful call.

    Raises:
        The last exception if all retries fail.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "%s failed (attempt %d/%d): %s",
                description,
                attempt,
                max_retries,
                exc,
            )
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * attempt)

    raise last_exc  # type: ignore[misc]
