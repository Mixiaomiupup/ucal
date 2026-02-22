"""Anti-detection configuration for Playwright browsers.

Applies stealth settings and fingerprint tweaks to reduce bot detection.
"""

from __future__ import annotations

import logging
import random

from playwright.async_api import BrowserContext, Page
from playwright_stealth import Stealth  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Common desktop viewport sizes
VIEWPORT_SIZES = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 720},
]

# Common user agents (Chrome on macOS / Windows)
USER_AGENTS = [
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
]

LANGUAGES = ["zh-CN,zh;q=0.9,en;q=0.8", "en-US,en;q=0.9"]


def get_stealth_context_options() -> dict:
    """Return browser context options that reduce detection fingerprint.

    Returns:
        Dict of kwargs suitable for ``browser.new_context(**opts)``.
    """
    viewport = random.choice(VIEWPORT_SIZES)
    return {
        "viewport": viewport,
        "user_agent": random.choice(USER_AGENTS),
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "extra_http_headers": {
            "Accept-Language": random.choice(LANGUAGES),
        },
        "permissions": ["geolocation"],
        "geolocation": {"latitude": 31.2304, "longitude": 121.4737},
        "color_scheme": "light",
    }


_stealth = Stealth()


async def apply_stealth(page: Page) -> None:
    """Apply playwright-stealth patches to a page.

    Args:
        page: The Playwright page to patch.
    """
    await _stealth.apply_stealth_async(page)
    logger.debug("Stealth patches applied to page %s", page.url)


async def apply_anti_detect_scripts(page: Page) -> None:
    """Inject additional JS to mask automation signals.

    Args:
        page: The Playwright page.
    """
    await page.add_init_script("""
        // Override webdriver flag
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });

        // Override plugins length
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });

        // Override languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en']
        });

        // Chrome runtime mock
        window.chrome = { runtime: {} };
    """)


async def setup_context_stealth(context: BrowserContext) -> None:
    """Apply stealth to all pages opened in this context.

    Args:
        context: Playwright browser context.
    """
    context.on(
        "page",
        lambda page: page.once(
            "domcontentloaded",
            lambda: None,  # stealth_async will be called per-page in browser.py
        ),
    )
    logger.debug("Context-level stealth listeners registered")
