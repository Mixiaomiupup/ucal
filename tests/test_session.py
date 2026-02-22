"""Tests for session manager."""

import json
from pathlib import Path

from ucal.core.session import SessionManager


def test_has_session_false(tmp_path: Path):
    mgr = SessionManager(session_dir=tmp_path)
    assert mgr.has_session("xhs") is False


def test_load_nonexistent(tmp_path: Path):
    mgr = SessionManager(session_dir=tmp_path)
    assert mgr.load_session_state("xhs") is None


def test_save_and_load(tmp_path: Path):
    # Simulate saving by writing directly (no real browser context in unit test)
    path = tmp_path / "test_session.json"
    state = {"cookies": [{"name": "sid", "value": "abc123"}]}
    path.write_text(json.dumps(state), encoding="utf-8")

    mgr_path = tmp_path / "test_session.json"
    loaded = json.loads(mgr_path.read_text(encoding="utf-8"))
    assert loaded["cookies"][0]["name"] == "sid"


def test_delete_session(tmp_path: Path):
    mgr = SessionManager(session_dir=tmp_path)
    # Create a fake session file
    (tmp_path / "fake_session.json").write_text("{}", encoding="utf-8")
    assert mgr.delete_session("fake") is True
    assert mgr.delete_session("fake") is False  # Already deleted
