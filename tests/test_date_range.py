from __future__ import annotations

import pytest

from ai_fluency_collector.cli import _dates_to_iso_weeks, _parse_date

# ── _parse_date ──────────────────────────────────────────────────────────────


def test_parse_date_valid():
    from datetime import date

    assert _parse_date("2026-01-05") == date(2026, 1, 5)


def test_parse_date_invalid_format():
    import click

    with pytest.raises(click.BadParameter, match="YYYY-MM-DD"):
        _parse_date("01/05/2026")


def test_parse_date_invalid_date():
    import click

    with pytest.raises(click.BadParameter):
        _parse_date("2026-13-01")


# ── _dates_to_iso_weeks ──────────────────────────────────────────────────────


def test_single_day_returns_one_week():
    weeks = _dates_to_iso_weeks("2026-03-16", "2026-03-16")
    assert weeks == ["2026-W12"]


def test_full_week_returns_one_week():
    """Monday to Sunday of the same ISO week → one entry."""
    weeks = _dates_to_iso_weeks("2026-03-16", "2026-03-22")
    assert weeks == ["2026-W12"]


def test_range_spanning_two_weeks():
    weeks = _dates_to_iso_weeks("2026-03-19", "2026-03-23")
    assert weeks == ["2026-W12", "2026-W13"]


def test_range_spanning_full_month():
    """March 2026: Mar 1 (Sun of W09) through Mar 31 (Tue of W14) → W09–W14."""
    weeks = _dates_to_iso_weeks("2026-03-01", "2026-03-31")
    assert weeks == ["2026-W09", "2026-W10", "2026-W11", "2026-W12", "2026-W13", "2026-W14"]


def test_from_date_snaps_to_monday():
    """Mid-week from_date includes the whole week from Monday."""
    weeks = _dates_to_iso_weeks("2026-03-18", "2026-03-22")  # Wed to Sun
    assert "2026-W12" in weeks
    assert weeks[0] == "2026-W12"


def test_year_boundary_week():
    """Range crossing a year boundary produces correct week strings."""
    weeks = _dates_to_iso_weeks("2025-12-29", "2026-01-04")
    # 2025-12-29 is Monday of 2026-W01 (ISO weeks can belong to next year)
    assert "2026-W01" in weeks


def test_from_after_to_raises():
    import click

    with pytest.raises(click.BadParameter, match="--from must be earlier"):
        _dates_to_iso_weeks("2026-03-22", "2026-03-16")


def test_eleven_week_range():
    """2026-01-05 (Mon W02) through 2026-03-22 (Sun W12) → W02–W12 = 11 weeks."""
    weeks = _dates_to_iso_weeks("2026-01-05", "2026-03-22")
    assert len(weeks) == 11
    assert weeks[0] == "2026-W02"
    assert weeks[-1] == "2026-W12"
