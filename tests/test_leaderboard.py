from datetime import datetime, timezone

from pipeline.leaderboard import tracked_delta, velocity


def test_velocity_stars_per_day():
    now = datetime(2026, 8, 12, tzinfo=timezone.utc)
    assert velocity("2026-08-02T00:00:00Z", 500, now) == 50


def test_velocity_brand_new_repo_no_zero_division():
    now = datetime(2026, 8, 12, 6, 0, tzinfo=timezone.utc)
    assert velocity("2026-08-12T00:00:00Z", 120, now) == 120


def test_tracked_delta_uses_oldest_sample():
    history = {"org/repo": {"2026-08-09": 1000, "2026-08-11": 1400}}
    assert tracked_delta(history, "org/repo", 1600, "2026-08-12") == 200  # (1600-1000)/3


def test_tracked_delta_ignores_today_sample():
    # today's own sample must not collapse the span to zero on re-runs
    history = {"org/repo": {"2026-08-12": 1600}}
    assert tracked_delta(history, "org/repo", 1600, "2026-08-12") is None


def test_tracked_delta_unknown_repo():
    assert tracked_delta({}, "org/new", 100, "2026-08-12") is None
