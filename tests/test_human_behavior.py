"""Tests for human behavior simulation utilities."""

from ucal.utils.human_behavior import generate_smooth_track


def test_track_covers_distance():
    """Track deltas should sum to approximately the target distance."""
    distance = 200.0
    track = generate_smooth_track(distance)
    total = sum(track)
    assert abs(total - distance) < 1.0, f"Track total {total} != {distance}"


def test_track_all_positive():
    """All track steps should be positive."""
    track = generate_smooth_track(150.0)
    assert all(step > 0 for step in track)


def test_track_not_empty():
    """Track should contain at least one step."""
    track = generate_smooth_track(50.0)
    assert len(track) > 0


def test_track_small_distance():
    """Should handle very small distances."""
    track = generate_smooth_track(3.0)
    total = sum(track)
    assert abs(total - 3.0) < 1.0


def test_track_large_distance():
    """Should handle large distances without infinite loop."""
    track = generate_smooth_track(2000.0)
    total = sum(track)
    assert abs(total - 2000.0) < 1.0
