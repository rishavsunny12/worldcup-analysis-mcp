"""Fixtures date range and 2026-only filtering (no historical WC pollution)."""

import pytest

from data.loader import BZZ_FIXTURES, get_bzzoiro_fixtures, get_bzzoiro_fixtures_in_range
from tools.fixtures import get_fixtures_range, get_team_fixtures


def test_bzz_fixtures_exclude_historical_world_cups():
    years = {row.get("event_date", "")[:4] for row in BZZ_FIXTURES}
    assert years == {"2026"}
    assert not any(
        "Croatia" in row.get("home_team", "")
        and row.get("event_date", "").startswith("2014")
        for row in BZZ_FIXTURES
    )


def test_opening_three_days_six_matches():
    rows = get_bzzoiro_fixtures_in_range("2026-06-11", "2026-06-13")
    assert len(rows) == 6
    matchups = {f"{r['home_team']} vs {r['away_team']}" for r in rows}
    assert "Mexico vs South Africa" in matchups
    assert "Brazil vs Morocco" in matchups
    assert not any("Croatia" in m for m in matchups)
    assert not any("Netherlands" in m for m in matchups)


@pytest.mark.asyncio
async def test_get_fixtures_range_jun_11_13():
    result = await get_fixtures_range("2026-06-11", "2026-06-13")
    assert "Mexico vs South Africa" in result
    assert "South Korea vs Czechia" in result
    assert "Brazil vs Morocco" in result
    assert "Croatia" not in result
    assert "6 match" in result
    assert "xG" in result


@pytest.mark.asyncio
async def test_get_team_fixtures_brazil_no_2014():
    from unittest.mock import patch

    with patch("tools.fixtures.cache") as mock_cache:
        mock_cache.get.return_value = None
        mock_cache.set = lambda *a, **kw: None
        result = await get_team_fixtures("Brazil")
    assert "2014" not in result
    assert "2022" not in result
    assert "Morocco" in result


def test_get_bzzoiro_fixtures_team_only_2026():
    rows = get_bzzoiro_fixtures("Brazil")
    assert rows
    assert all(r.get("event_date", "").startswith("2026-") for r in rows)


@pytest.mark.asyncio
async def test_get_fixtures_range_invalid_dates():
    bad = await get_fixtures_range("not-a-date", "2026-06-13")
    assert "Invalid date" in bad
