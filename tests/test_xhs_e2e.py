"""End-to-end test for XHS adapter fixes.

Run with: uv run python tests/test_xhs_e2e.py

Requires a saved XHS browser session (login first via MCP or manually).
"""

from __future__ import annotations

import asyncio
import logging
import sys

from ucal.adapters.xhs import XHSAdapter
from ucal.core.browser import BrowserManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SEARCH_QUERY = "油碟麻酱碟"
PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"


async def main() -> None:
    """Run all three fix verifications."""
    bm = BrowserManager(headless=False)
    adapter = XHSAdapter(bm)
    failures = 0

    try:
        await bm.start()

        # ── Fix 1: search() returns token-bearing URLs ──
        logger.info("=" * 60)
        logger.info("Fix 1: search() — token-bearing URLs")
        logger.info("=" * 60)

        results = await adapter.search(SEARCH_QUERY, limit=5)
        logger.info("Got %d search results", len(results))

        if not results:
            logger.error("%s No search results returned", FAIL)
            failures += 1
        else:
            all_have_token = True
            for r in results:
                has_token = "xsec_token=" in r.url
                has_search_result = "/search_result/" in r.url
                status = PASS if (has_token and has_search_result) else FAIL
                logger.info(
                    "  %s %s  (token=%s, search_result=%s)",
                    status,
                    r.url[:80],
                    has_token,
                    has_search_result,
                )
                if not has_token or not has_search_result:
                    all_have_token = False
            if all_have_token:
                logger.info("%s All URLs have xsec_token", PASS)
            else:
                logger.error("%s Some URLs missing xsec_token", FAIL)
                failures += 1

        # ── Fix 2 & 3: read() with sub-comments and images ──
        if results:
            test_url = results[0].url
            logger.info("")
            logger.info("=" * 60)
            logger.info("Fix 2 & 3: read() — sub-comments & images")
            logger.info("=" * 60)
            logger.info("Reading: %s", test_url)

            content = await adapter.read(test_url)

            if content.title == "Error":
                logger.error("%s read() failed: %s", FAIL, content.content)
                failures += 1
            else:
                logger.info("%s Page loaded: %s", PASS, content.title)

                # Check for comments section
                has_comments = "## Top Comments" in content.content
                if has_comments:
                    logger.info("%s Comments section found", PASS)
                else:
                    logger.warning("  No comments section (page may have no comments)")

                # Check for sub-comments (indented with "  - **")
                lines = content.content.split("\n")
                sub_comments = [line for line in lines if line.startswith("  - **")]
                if sub_comments:
                    logger.info("%s Found %d sub-comments", PASS, len(sub_comments))
                    for sc in sub_comments[:3]:
                        logger.info("    %s", sc[:100])
                else:
                    logger.warning("  No sub-comments found (may not have any)")

                # Check for folded reply indicators
                folded = [
                    line
                    for line in lines
                    if line.strip().startswith("_") and "回复" in line
                ]
                if folded:
                    logger.info(
                        "%s Found %d folded-reply indicators",
                        PASS,
                        len(folded),
                    )
                    for f in folded[:3]:
                        logger.info("    %s", f.strip())
                else:
                    logger.warning("  No folded-reply indicators (may not have any)")

                # Check for comment images
                img_count = content.content.count("![comment-img]")
                if img_count:
                    logger.info("%s Found %d comment image(s)", PASS, img_count)
                else:
                    logger.warning("  No comment images found (may not have any)")

                # Print full content for manual inspection
                logger.info("")
                logger.info("=" * 60)
                logger.info("Full content (for manual inspection):")
                logger.info("=" * 60)
                print(content.content)

        # ── Test: read() extracts tags ──
        if results:
            test_url = results[0].url
            logger.info("")
            logger.info("=" * 60)
            logger.info("Test: read() — tag extraction")
            logger.info("=" * 60)

            content = await adapter.read(test_url)
            if content.extra and "tags" in content.extra:
                tag_list = content.extra["tags"]
                if isinstance(tag_list, list) and len(tag_list) > 0:
                    logger.info("%s Tags extracted: %s", PASS, tag_list[:10])
                else:
                    logger.warning("  Tags list is empty (page may have no tags)")
            else:
                logger.warning("  No tags in extra (page may have no tags)")

        # ── Test: read() extracts hot_threads ──
        if results:
            test_url = results[0].url
            logger.info("")
            logger.info("=" * 60)
            logger.info("Test: read() — hot threads detection")
            logger.info("=" * 60)

            content = await adapter.read(test_url)
            if content.extra and "hot_threads" in content.extra:
                ht = content.extra["hot_threads"]
                if isinstance(ht, list) and len(ht) > 0:
                    logger.info("%s Hot threads found: %d", PASS, len(ht))
                    for t in ht[:3]:
                        logger.info(
                            "    @%s: %s (subs=%d, more=%s)",
                            t.get("author", "?"),
                            t.get("preview", "")[:50],
                            t.get("sub_count", 0),
                            t.get("has_more", False),
                        )
                else:
                    logger.warning("  hot_threads list is empty")
            else:
                logger.warning(
                    "  No hot_threads in extra (may not have hot discussions)"
                )

        # ── Test: read() with comment_limit ──
        if results:
            test_url = results[0].url
            logger.info("")
            logger.info("=" * 60)
            logger.info("Test: read() — comment_limit=5")
            logger.info("=" * 60)

            content = await adapter.read(test_url, comment_limit=5)
            lines = content.content.split("\n")
            top_comments = [
                line
                for line in lines
                if line.startswith("- **") and not line.startswith("  - **")
            ]
            logger.info("  Top-level comments: %d", len(top_comments))
            if len(top_comments) <= 5:
                logger.info(
                    "%s comment_limit=5 respected (got %d)",
                    PASS,
                    len(top_comments),
                )
            else:
                logger.error(
                    "%s comment_limit=5 exceeded (got %d)",
                    FAIL,
                    len(top_comments),
                )
                failures += 1

        # ── Test: read() with expand_replies=2 ──
        if results:
            test_url = results[0].url
            logger.info("")
            logger.info("=" * 60)
            logger.info("Test: read() — expand_replies=2 (deep expansion)")
            logger.info("=" * 60)

            content_default = await adapter.read(test_url)
            content_deep = await adapter.read(test_url, expand_replies=2)

            default_subs = content_default.content.count("  - **")
            deep_subs = content_deep.content.count("  - **")
            logger.info("  Sub-comments: default=%d, deep=%d", default_subs, deep_subs)
            if deep_subs >= default_subs:
                logger.info(
                    "%s Deep expansion returned >= default sub-comments",
                    PASS,
                )
            else:
                logger.warning(
                    "  Deep expansion returned fewer sub-comments (may vary)"
                )

        # ── Test: default params backward compatibility ──
        if results:
            test_url = results[0].url
            logger.info("")
            logger.info("=" * 60)
            logger.info("Test: read() — default params (backward compat)")
            logger.info("=" * 60)

            content = await adapter.read(test_url)
            if content.title != "Error":
                logger.info("%s Default read() still works: %s", PASS, content.title)
            else:
                logger.error("%s Default read() broken: %s", FAIL, content.content)
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
