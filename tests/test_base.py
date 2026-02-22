"""Tests for adapter base types."""

from ucal.adapters.base import (
    ContentResult,
    ExtractResult,
    LoginStatus,
    SearchResult,
)


def test_search_result_to_dict():
    r = SearchResult(
        title="Test",
        url="https://example.com",
        summary="A test",
        author="alice",
        platform="x",
    )
    d = r.to_dict()
    assert d["title"] == "Test"
    assert d["url"] == "https://example.com"
    assert d["author"] == "alice"
    assert "extra" not in d  # empty extra is omitted


def test_search_result_with_extra():
    r = SearchResult(
        title="T",
        url="https://example.com",
        extra={"likes": 42},
    )
    d = r.to_dict()
    assert d["extra"]["likes"] == 42


def test_content_result_to_dict():
    r = ContentResult(
        title="Post",
        content="# Hello\nworld",
        author="bob",
        url="https://example.com/post/1",
        platform="xhs",
    )
    d = r.to_dict()
    assert d["title"] == "Post"
    assert "Hello" in d["content"]
    assert d["platform"] == "xhs"


def test_extract_result_to_dict():
    r = ExtractResult(
        fields={"title": "T", "likes": 10},
        url="https://example.com",
        platform="zhihu",
    )
    d = r.to_dict()
    assert d["fields"]["title"] == "T"
    assert d["fields"]["likes"] == 10


def test_login_status_to_dict():
    s = LoginStatus(
        success=True,
        platform="x",
        method="api_key",
        message="OK",
        session_file="/tmp/x.json",
    )
    d = s.to_dict()
    assert d["success"] is True
    assert d["session_file"] == "/tmp/x.json"
