"""Human behavior simulation utilities.

Ported from csfilter's captcha_solver.py — physical models for realistic
mouse movement, scrolling, and typing patterns.
"""

from __future__ import annotations

import asyncio
import random

from playwright.async_api import Page


def generate_smooth_track(distance: float) -> list[float]:
    """Generate a smooth movement track simulating human drag/swipe.

    Uses an acceleration-then-deceleration physics model with randomized
    parameters to mimic natural hand movement.

    Args:
        distance: Total distance in pixels.

    Returns:
        List of incremental move deltas.
    """
    track: list[float] = []
    current = 0.0
    mid = distance * 0.7  # Accelerate for 70%, decelerate for 30%
    t = 0.15  # Time step
    v = 0.0  # Initial velocity
    max_iterations = 1000

    for _ in range(max_iterations):
        if current >= distance:
            break

        a = random.uniform(3, 5) if current < mid else -random.uniform(4, 6)
        v0 = v
        v = max(min(v0 + a * t, 20), 0)
        move = v0 * t + 0.5 * a * t * t

        if move > 0:
            current += move
            if current > distance:
                move -= current - distance
                current = distance
            if move > 0:
                track.append(round(move, 2))
        else:
            remaining = distance - current
            if remaining > 0:
                step = min(1.0, remaining)
                track.append(round(step, 2))
                current += step
            else:
                break

    if current < distance:
        track.append(round(distance - current, 2))

    return track


async def human_type(page: Page, selector: str, text: str) -> None:
    """Type text into an element with human-like delays between keystrokes.

    Args:
        page: Playwright page.
        selector: CSS selector of the input element.
        text: Text to type.
    """
    await page.click(selector)
    for char in text:
        await page.keyboard.type(char, delay=random.randint(50, 180))
        if random.random() < 0.05:  # Occasional longer pause
            await asyncio.sleep(random.uniform(0.2, 0.6))


async def human_scroll(
    page: Page,
    direction: str = "down",
    amount: int = 500,
    steps: int = 0,
    selector: str | None = None,
) -> None:
    """Scroll the page with human-like behavior.

    When *selector* is provided, ``element.scrollBy()`` is used to scroll
    the target container directly.  This avoids two pitfalls of
    ``mouse.wheel()``: (1) the element's visual centre may be occluded by
    an overlapping panel, sending the event to the wrong container, and
    (2) some containers ignore synthetic wheel events entirely.

    Args:
        page: Playwright page.
        direction: "down" or "up".
        amount: Total pixels to scroll.
        steps: Number of discrete scroll events. 0 = auto-calculate.
        selector: Optional CSS selector of the scrollable container.
            When given, ``element.scrollBy()`` is called on that element
            instead of dispatching ``mouse.wheel()`` events.
    """
    if steps <= 0:
        steps = max(3, amount // random.randint(80, 150))

    delta_sign = 1 if direction == "down" else -1
    remaining = amount

    if selector:
        # Use element.scrollBy() for reliable container scrolling.
        # mouse.wheel() is unreliable: the mouse centre may land on an
        # overlapping panel, and some containers ignore synthetic wheel
        # events entirely.
        el = await page.query_selector(selector)
        if not el:
            msg = f"scroll selector not found: {selector}"
            raise ValueError(msg)
        for _ in range(steps):
            if remaining <= 0:
                break
            chunk = min(remaining, random.randint(60, 160))
            remaining -= chunk
            await el.evaluate("(el, dy) => el.scrollBy(0, dy)", chunk * delta_sign)
            await asyncio.sleep(random.uniform(0.02, 0.12))
    else:
        for _ in range(steps):
            if remaining <= 0:
                break
            chunk = min(remaining, random.randint(60, 160))
            remaining -= chunk
            await page.mouse.wheel(0, chunk * delta_sign)
            await asyncio.sleep(random.uniform(0.02, 0.12))

    # Small pause after scrolling
    await asyncio.sleep(random.uniform(0.1, 0.3))


async def human_move_to(page: Page, x: float, y: float) -> None:
    """Move mouse to target coordinates with a smooth, curved path.

    Args:
        page: Playwright page.
        x: Target X coordinate.
        y: Target Y coordinate.
    """
    # Get current mouse position (start from a random viewport point)
    start_x = random.randint(100, 400)
    start_y = random.randint(100, 400)

    dx = x - start_x
    dy = y - start_y
    steps = random.randint(15, 30)

    for i in range(steps):
        progress = (i + 1) / steps
        # Ease-in-out curve
        ease = progress * progress * (3 - 2 * progress)
        cx = start_x + dx * ease + random.uniform(-2, 2)
        cy = start_y + dy * ease + random.uniform(-2, 2)
        await page.mouse.move(cx, cy)
        await asyncio.sleep(random.uniform(0.005, 0.02))


async def random_delay(min_s: float = 0.5, max_s: float = 2.0) -> None:
    """Sleep for a random duration to mimic human thinking/reading time.

    Args:
        min_s: Minimum seconds.
        max_s: Maximum seconds.
    """
    await asyncio.sleep(random.uniform(min_s, max_s))
