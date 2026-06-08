import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from tools.team import get_team_form


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name: str) -> dict:
    with open(os.path.join(FIXTURE_DIR, name)) as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_get_team_form_invalid_team():
    result = await get_team_form("Atlantis FC")
    assert "not found" in result


@pytest.mark.asyncio
async def test_get_team_form_happy_path():
    bundle = load_fixture("bzzoiro_team_stats_brazil.json")
    with patch("tools.team.uses_bzzoiro_live", return_value=True), \
         patch("tools.team.bzzoiro") as mock_bzz, \
         patch("tools.team.cache") as mock_cache:
        mock_bzz.get_standings = AsyncMock(return_value=bundle)
        mock_bzz.get_events = AsyncMock(return_value=bundle["events"])
        mock_cache.get.return_value = None
        mock_cache.set = lambda *a, **kw: None

        result = await get_team_form("brazil")

    assert "BRAZIL" in result.upper() or "Brazil" in result
    assert "RECORD" in result
    assert "xG" in result


@pytest.mark.asyncio
async def test_get_team_form_cache_hit():
    cached_value = "cached form string"
    with patch("tools.team.cache") as mock_cache:
        mock_cache.get.return_value = cached_value
        result = await get_team_form("brazil")
    assert result == cached_value


@pytest.mark.asyncio
async def test_get_team_form_last_n_clamped():
    bundle = load_fixture("bzzoiro_team_stats_brazil.json")
    with patch("tools.team.uses_bzzoiro_live", return_value=True), \
         patch("tools.team.bzzoiro") as mock_bzz, \
         patch("tools.team.cache") as mock_cache:
        mock_bzz.get_standings = AsyncMock(return_value=bundle)
        mock_bzz.get_events = AsyncMock(return_value=bundle["events"])
        mock_cache.get.return_value = None
        mock_cache.set = lambda *a, **kw: None
        result = await get_team_form("brazil", last_n=99)
    assert "BRAZIL" in result.upper()
