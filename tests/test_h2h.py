import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from tools.head_to_head import get_h2h


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name: str):
    with open(os.path.join(FIXTURE_DIR, name)) as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_get_h2h_invalid_team_a():
    result = await get_h2h("Atlantis FC", "brazil")
    assert "not found" in result


@pytest.mark.asyncio
async def test_get_h2h_invalid_team_b():
    result = await get_h2h("brazil", "Atlantis FC")
    assert "not found" in result


@pytest.mark.asyncio
async def test_get_h2h_happy_path():
    raw = load_fixture("bzzoiro_h2h_brazil_england.json")
    with patch("tools.head_to_head.uses_bzzoiro_live", return_value=True), \
         patch("tools.head_to_head.bzzoiro") as mock_bzz, \
         patch("tools.head_to_head.cache") as mock_cache:
        mock_bzz.get_head_to_head_events = AsyncMock(return_value=raw)
        mock_cache.get.return_value = None
        mock_cache.set = lambda *a, **kw: None

        result = await get_h2h("brazil", "england")

    assert "Brazil" in result
    assert "England" in result
    assert "HEAD TO HEAD" in result
    assert "🏆" in result


@pytest.mark.asyncio
async def test_get_h2h_cache_hit():
    cached_value = "cached h2h string"
    with patch("tools.head_to_head.cache") as mock_cache:
        mock_cache.get.return_value = cached_value
        result = await get_h2h("brazil", "england")
    assert result == cached_value
