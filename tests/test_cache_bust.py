"""Cache invalidation: bumped source keys and CACHE_BUST startup clear."""

import asyncio

import pytest

from cache.cache_manager import cache
from config import resolve_team_id
from tools.squad_analysis import get_nation_top_performers, get_squad_league_breakdown
from tools.team_analysis import analyze_team_for_worldcup


def test_bumped_cache_keys_ignore_stale_entries():
    team_id = resolve_team_id("South Africa")
    assert team_id is not None

    cache.set("form", "STALE ANALYSIS", team_id=team_id, source="full_analysis_v2")
    cache.set("form", "STALE PERFORMERS", team_id=team_id, top_n=5, source="csv_v2")
    cache.set("standings", "STALE OVERVIEW", group="A", source="overview_v2")

    assert cache.get("form", team_id=team_id, source="full_analysis_v3") is None
    assert cache.get("form", team_id=team_id, top_n=5, source="csv_v4") is None
    assert cache.get("standings", group="A", source="overview_v4") is None


def test_cache_clear_wipes_all_buckets():
    cache.set("form", "x", team_id=1, source="test")
    cache.clear()
    assert cache.get("form", team_id=1, source="test") is None


@pytest.mark.asyncio
async def test_south_africa_tools_fresh_after_cache_bust():
    """Fresh process path: league breakdown + cached tools agree on official squad size."""
    breakdown = await get_squad_league_breakdown("South Africa")
    assert "26 official squad players" in breakdown
    assert "Africa Cup of Nations 2023" not in breakdown

    performers = await get_nation_top_performers("South Africa")
    assert "Squad: 26 players" in performers

    analysis = await analyze_team_for_worldcup("South Africa")
    assert "(of 26 total)" in analysis
    assert "Addai" not in analysis
