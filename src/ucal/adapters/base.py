"""Base adapter interface for all platform adapters."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AdapterType(str, Enum):
    """How the adapter accesses the platform."""

    API = "api"
    BROWSER = "browser"


class LoginMethod(str, Enum):
    """Supported login methods."""

    BROWSER = "browser"  # Manual login via browser window
    COOKIE = "cookie"  # Import cookies from file
    API_KEY = "api_key"  # API key / token


@dataclass
class SearchResult:
    """A single search result from any platform."""

    title: str
    url: str
    summary: str = ""
    author: str = ""
    platform: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d: dict[str, Any] = {
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "author": self.author,
            "platform": self.platform,
        }
        if self.extra:
            d["extra"] = self.extra
        return d


@dataclass
class ContentResult:
    """Full content read from a URL."""

    title: str
    content: str  # Markdown formatted
    author: str = ""
    url: str = ""
    platform: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d: dict[str, Any] = {
            "title": self.title,
            "content": self.content,
            "author": self.author,
            "url": self.url,
            "platform": self.platform,
        }
        if self.extra:
            d["extra"] = self.extra
        return d


@dataclass
class ExtractResult:
    """Structured field extraction result."""

    fields: dict[str, Any]
    url: str = ""
    platform: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "url": self.url,
            "platform": self.platform,
            "fields": self.fields,
        }


@dataclass
class LoginStatus:
    """Login status information."""

    success: bool
    platform: str
    method: str
    message: str = ""
    session_file: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "success": self.success,
            "platform": self.platform,
            "method": self.method,
            "message": self.message,
            "session_file": self.session_file,
        }


class BaseAdapter(abc.ABC):
    """Abstract base class for all platform adapters.

    Each platform (X, XHS, Zhihu, Discord, etc.) implements this interface.
    API-based adapters talk directly to APIs; browser-based adapters use
    Playwright for page automation.
    """

    platform_name: str = ""
    adapter_type: AdapterType = AdapterType.BROWSER

    @abc.abstractmethod
    async def login(self, method: LoginMethod = LoginMethod.BROWSER) -> LoginStatus:
        """Login to the platform and persist the session.

        Args:
            method: How to authenticate.

        Returns:
            Login status with session info.
        """

    @abc.abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search content on the platform.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of search results.
        """

    @abc.abstractmethod
    async def read(self, url: str, **kwargs: Any) -> ContentResult:
        """Read full content from a URL.

        Args:
            url: The URL to read.
            **kwargs: Platform-specific parameters (e.g. comment_limit,
                expand_replies for XHS).

        Returns:
            Full content in Markdown format.
        """

    @abc.abstractmethod
    async def extract(self, url: str, fields: list[str]) -> ExtractResult:
        """Extract structured fields from a URL.

        Args:
            url: The URL to extract from.
            fields: List of field names to extract.

        Returns:
            Structured extraction result.
        """

    async def close(self) -> None:
        """Cleanup resources. Override if needed."""

    def is_logged_in(self) -> bool:
        """Check if the adapter has an active session.

        Override in subclasses that track login state.
        """
        return False
