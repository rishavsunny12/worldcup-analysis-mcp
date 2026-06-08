"""Unit tests for bzzoiro-routed live tournament tools."""
import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from tools.fixtures import get_today_matches
from tools.players import get_top_scorers


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name: str):
    with open(os.path.join(FIXTURE_DIR, name)) as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_get_today_matches_bzzoiro_happy_path():
    today_events = [
        {
            "id": 1,
            "home_team": "Brazil",
            "away_team": "Serbia",
            "home_score": 2,
            "away_score": 0,
            "current_minute": 67,
            "event_date": "2026-06-15T18:00:00Z",
            "status": "inprogress",
        },
        {
            "id": 2,
            "home_team": "France",
            "away_team": "Germany",
            "home_score": None,
            "away_score": None,
            "event_date": "2026-06-15T21:00:00Z",
            "status": "notstarted",
        },
    ]
    with patch("tools.fixtures.uses_bzzoiro_live", return_value=True), \
         patch("tools.fixtures.bzzoiro") as mock_bzz, \
         patch("tools.fixtures.cache") as mock_cache:
        mock_bzz.get_events_today = AsyncMock(return_value=today_events)
        mock_bzz.get_live_events = AsyncMock(return_value=[today_events[0]])
        mock_cache.get.return_value = None
        mock_cache.set = lambda *a, **kw: None

        result = await get_today_matches()

    assert "LIVE" in result
    assert "UPCOMING" in result
    assert "Brazil" in result
    assert "France" in result


@pytest.mark.asyncio
async def test_get_top_scorers_bzzoiro_happy_path():
    scorers = load_fixture("bzzoiro_scorers.json")
    with patch("tools.players.uses_bzzoiro_live", return_value=True), \
         patch("tools.players.bzzoiro") as mock_bzz, \
         patch("tools.players.cache") as mock_cache:
        mock_bzz.get_top_scorers = AsyncMock(return_value=scorers)
        mock_cache.get.return_value = None
        mock_cache.set = lambda *a, **kw: None

        result = await get_top_scorers(3)

    assert "GOLDEN BOOT" in result
    assert "Richarlison" in result
    assert "4 goals" in result
