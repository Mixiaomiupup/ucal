"""End-to-end test for Twitter browser adapter.

Run with: uv run python tests/test_twitter_browser.py

Requires a saved X/Twitter browser session (login first via MCP or manually).
"""

from __future__ import annotations

import asyncio
import logging
import sys

from ucal.adapters.twitter import TwitterBrowserAdapter
from ucal.core.browser import BrowserManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"

# Public account for testing (high-profile, unlikely to go private)
TEST_USERNAME = "elonmusk"


async def main() -> None:
    """Run Twitter browser adapter E2E tests."""
    bm = BrowserManager(headless=False)
    adapter = TwitterBrowserAdapter(bm)
    failures = 0

    try:
        await bm.start()

        # ── Test 1: Login / cookie restore ──
        logger.info("=" * 60)
        logger.info("Test 1: Login (cookie restore)")
        logger.info("=" * 60)

        from ucal.adapters.base import LoginMethod

        status = await adapter.login(method=LoginMethod.COOKIE)
        if status.success:
            logger.info("%s Session restored from cookies", PASS)
        else:
            logger.warning("  No saved session — attempting browser login")
            status = await adapter.login(method=LoginMethod.BROWSER)
            if status.success:
                logger.info("%s Browser login successful", PASS)
            else:
                logger.error("%s Login failed: %s", FAIL, status.message)
                failures += 1

        # ── Test 2: Read user tweets ──
        logger.info("")
        logger.info("=" * 60)
        logger.info("Test 2: Read user tweets")
        logger.info("=" * 60)

        content = await adapter.read(f"https://x.com/{TEST_USERNAME}", limit=5)
        if content.title == "Error":
            logger.error("%s Failed to read tweets: %s", FAIL, content.content)
            failures += 1
        else:
            logger.info("%s Got tweets: %s", PASS, content.title)
            count = content.extra.get("count", 0)
            logger.info("  Tweet count: %d", count)
            if count > 0:
                logger.info("%s Tweets extracted successfully", PASS)
                # Show first 200 chars
                logger.info("  Preview: %s", content.content[:200])
            else:
                logger.error("%s No tweets extracted", FAIL)
                failures += 1

        # ── Test 3: Read single tweet ──
        logger.info("")
        logger.info("=" * 60)
        logger.info("Test 3: Read single tweet")
        logger.info("=" * 60)

        # Use a well-known tweet (Elon's "the bird is freed")
        tweet_url = f"https://x.com/{TEST_USERNAME}/status/1585841080431321088"
        content = await adapter.read(tweet_url)
        if content.title == "Error" or content.title == "Tweet not found":
            logger.error("%s Failed to read tweet: %s", FAIL, content.content)
            failures += 1
        else:
            logger.info("%s Tweet loaded: %s", PASS, content.title)
            logger.info("  Preview: %s", content.content[:200])

        # ── Test 4: Read following list ──
        logger.info("")
        logger.info("=" * 60)
        logger.info("Test 4: Read following list")
        logger.info("=" * 60)

        content = await adapter.read(
            f"https://x.com/{TEST_USERNAME}/following", limit=10
        )
        if "Could not load" in content.content or content.title == "Error":
            logger.error("%s Failed to read following: %s", FAIL, content.content)
            failures += 1
        else:
            logger.info("%s Following list loaded: %s", PASS, content.title)
            count = content.extra.get("count", 0)
            logger.info("  Users found: %d", count)
            if count > 0:
                logger.info("%s Following list extracted", PASS)
                # Show first few entries
                for line in content.content.split("\n")[:12]:
                    if line.startswith("- "):
                        logger.info("  %s", line)
            else:
                logger.error("%s No users extracted", FAIL)
                failures += 1

        # ── Test 5: Search ──
        logger.info("")
        logger.info("=" * 60)
        logger.info("Test 5: Search")
        logger.info("=" * 60)

        results = await adapter.search("python programming", limit=5)
        logger.info("  Got %d search results", len(results))
        if results:
            logger.info("%s Search returned results", PASS)
            for r in results[:3]:
                logger.info("  - @%s: %s", r.author[:20], r.title[:60])
        else:
            logger.error("%s No search results", FAIL)
            failures += 1

    finally:
        await bm.close()

    # Summary
    print()
    if failures:
        logger.error("=" * 60)
        logger.error("%d check(s) FAILED", failures)
        logger.error("=" * 60)
        sys.exit(1)
    else:
        logger.info("=" * 60)
        logger.info("%s All checks passed", PASS)
        logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
