"""Session (cookie / storage_state) persistence manager.

Saves and loads Playwright storage states so users don't have to re-login
every time the MCP server restarts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from playwright.async_api import BrowserContext

logger = logging.getLogger(__name__)

DEFAULT_SESSION_DIR = Path(__file__).resolve().parents[3] / "config" / "sessions"


class SessionManager:
    """Manages platform session persistence via Playwright storage_state.

    Args:
        session_dir: Directory to store session JSON files.
    """

    def __init__(self, session_dir: Path | str | None = None) -> None:
        self.session_dir = Path(session_dir) if session_dir else DEFAULT_SESSION_DIR
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, platform: str) -> Path:
        """Return the file path for a platform's session.

        Args:
            platform: Platform identifier (e.g. "xhs", "zhihu").

        Returns:
            Path to the session JSON file.
        """
        return self.session_dir / f"{platform}_session.json"

    def has_session(self, platform: str) -> bool:
        """Check if a saved session exists for the platform.

        Args:
            platform: Platform identifier.

        Returns:
            True if a session file exists and is non-empty.
        """
        path = self._session_path(platform)
        return path.exists() and path.stat().st_size > 0

    async def save_session(self, platform: str, context: BrowserContext) -> str:
        """Save the browser context's storage state to disk.

        Args:
            platform: Platform identifier.
            context: Playwright browser context whose state to persist.

        Returns:
            Path to the saved session file.
        """
        path = self._session_path(platform)
        await context.storage_state(path=str(path))
        logger.info("Session saved for %s at %s", platform, path)
        return str(path)

    def load_session_state(self, platform: str) -> dict | None:
        """Load a previously saved storage state.

        Args:
            platform: Platform identifier.

        Returns:
            The storage state dict, or None if not found.
        """
        path = self._session_path(platform)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            logger.info("Session loaded for %s from %s", platform, path)
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load session for %s: %s", platform, exc)
            return None

    def delete_session(self, platform: str) -> bool:
        """Delete the saved session for a platform.

        Args:
            platform: Platform identifier.

        Returns:
            True if a session was deleted.
        """
        path = self._session_path(platform)
        if path.exists():
            path.unlink()
            logger.info("Session deleted for %s", platform)
            return True
        return False
