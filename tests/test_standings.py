import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from tools.standings import get_group_standings, _format_table


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name: str) -> dict:
    with open(os.path.join(FIXTURE_DIR, name)) as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_get_group_standings_invalid_group():
    result = await get_group_standings("Z")
    assert "Invalid group" in result


@pytest.mark.asyncio
async def test_get_group_standings_happy_path_bzzoiro():
    raw = load_fixture("bzzoiro_standings_wc.json")
    with patch("tools.standings.uses_bzzoiro_live", return_value=True), \
         patch("tools.standings.bzzoiro") as mock_bzz, \
         patch("tools.standings.cache") as mock_cache:
        mock_bzz.get_standings = AsyncMock(return_value=raw)
        mock_cache.get.return_value = None
        mock_cache.set = lambda *a, **kw: None

        result = await get_group_standings("D")

    assert "Brazil" in result
    assert "England" in result
    assert "✅" in result
    assert "❌" in result


@pytest.mark.asyncio
async def test_get_group_standings_group_a_normalizes_group_key():
    raw = load_fixture("bzzoiro_standings_group_a.json")
    with patch("tools.standings.uses_bzzoiro_live", return_value=True), \
         patch("tools.standings.bzzoiro") as mock_bzz, \
         patch("tools.standings.cache") as mock_cache:
        mock_bzz.get_standings = AsyncMock(return_value=raw)
        mock_cache.get.return_value = None
        mock_cache.set = lambda *a, **kw: None

        result = await get_group_standings("A")

    assert "No standings found" not in result
    assert "Mexico" in result
    assert "South Africa" in result
    assert "South Korea" in result


@pytest.mark.asyncio
async def test_get_group_overview_embeds_group_a_standings():
    from tools.standings import get_group_overview

    raw = load_fixture("bzzoiro_standings_group_a.json")
    with patch("tools.standings.uses_bzzoiro_live", return_value=True), \
         patch("tools.standings.bzzoiro") as mock_bzz, \
         patch("tools.standings.cache") as mock_cache, \
         patch("tools.team_analysis._fetch_squad", new_callable=AsyncMock) as mock_squad:
        mock_bzz.get_standings = AsyncMock(return_value=raw)
        mock_cache.get.return_value = None
        mock_cache.set = lambda *a, **kw: None
        mock_squad.return_value = []

        result = await get_group_overview("A")

    assert "No standings found" not in result
    assert "Mexico" in result
    assert "GROUP A OVERVIEW" in result


def test_normalize_group_letter_variants():
    from tools.bzzoiro_parsers import normalize_group_letter

    assert normalize_group_letter("Group A") == "A"
    assert normalize_group_letter("GROUP_A") == "A"
    assert normalize_group_letter("a") == "A"


@pytest.mark.asyncio
async def test_get_group_standings_cache_hit():
    cached_value = "cached standings string"
    with patch("tools.standings.cache") as mock_cache:
        mock_cache.get.return_value = cached_value
        result = await get_group_standings("D")
    assert result == cached_value


@pytest.mark.asyncio
async def test_get_group_standings_api_error():
    with patch("tools.standings.uses_bzzoiro_live", return_value=True), \
         patch("tools.standings.bzzoiro") as mock_bzz, \
         patch("tools.standings.cache") as mock_cache:
        mock_bzz.get_standings = AsyncMock(side_effect=Exception("Network error"))
        mock_cache.get.return_value = None

        result = await get_group_standings("A")
    assert "API_UNAVAILABLE" in result
