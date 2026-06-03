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
async def test_get_group_standings_happy_path_free_tier():
    raw = load_fixture("api_football_standings_wc.json")
    fd_format = {
        "standings": [
            {
                "group": "GROUP_D",
                "table": [
                    {"team": {"id": 6, "name": "Brazil"}, "playedGames": 3, "won": 3, "draw": 0,
                     "lost": 0, "goalsFor": 8, "goalsAgainst": 3, "goalDifference": 5, "points": 9},
                    {"team": {"id": 10, "name": "England"}, "playedGames": 3, "won": 2, "draw": 0,
                     "lost": 1, "goalsFor": 5, "goalsAgainst": 3, "goalDifference": 2, "points": 6},
                    {"team": {"id": 37, "name": "Colombia"}, "playedGames": 3, "won": 1, "draw": 0,
                     "lost": 2, "goalsFor": 3, "goalsAgainst": 4, "goalDifference": -1, "points": 3},
                    {"team": {"id": 7, "name": "Uruguay"}, "playedGames": 3, "won": 0, "draw": 0,
                     "lost": 3, "goalsFor": 1, "goalsAgainst": 7, "goalDifference": -6, "points": 0},
                ]
            }
        ]
    }
    with patch("tools.standings.settings") as mock_settings, \
         patch("tools.standings.football_data") as mock_fd, \
         patch("tools.standings.cache") as mock_cache:
        mock_settings.TIER = "free"
        mock_fd.get_standings = AsyncMock(return_value=fd_format)
        mock_cache.get.return_value = None
        mock_cache.set = lambda *a, **kw: None

        result = await get_group_standings("D")

    assert "Brazil" in result
    assert "England" in result
    assert "✅" in result
    assert "❌" in result


@pytest.mark.asyncio
async def test_get_group_standings_cache_hit():
    cached_value = "cached standings string"
    with patch("tools.standings.cache") as mock_cache:
        mock_cache.get.return_value = cached_value
        result = await get_group_standings("D")
    assert result == cached_value


@pytest.mark.asyncio
async def test_get_group_standings_api_error():
    with patch("tools.standings.settings") as mock_settings, \
         patch("tools.standings.football_data") as mock_fd, \
         patch("tools.standings.cache") as mock_cache:
        mock_settings.TIER = "free"
        mock_fd.get_standings = AsyncMock(side_effect=Exception("Network error"))
        mock_cache.get.return_value = None

        result = await get_group_standings("A")
    assert "No data available" in result
