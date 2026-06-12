"""Unit tests for bzzoiro-routed live tournament tools."""
import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from tools.fixtures import get_today_matches
from tools.match import get_live_match
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


@pytest.mark.asyncio
async def test_get_today_matches_live_day_uses_live_cache_bucket():
    today_events = [
        {
            "id": 1,
            "home_team": "Mexico",
            "away_team": "South Africa",
            "home_score": 1,
            "away_score": 0,
            "current_minute": 34,
            "event_date": "2026-06-11T19:00:00Z",
            "status": "inprogress",
            "home_team_id": 451,
            "away_team_id": 452,
        },
    ]
    cache_sets: list[tuple] = []

    def _capture_set(*args, **kwargs):
        cache_sets.append((args, kwargs))

    with patch("tools.fixtures.uses_bzzoiro_live", return_value=True), \
         patch("tools.fixtures.bzzoiro") as mock_bzz, \
         patch("tools.fixtures.cache") as mock_cache:
        mock_bzz.get_events_today = AsyncMock(return_value=today_events)
        mock_bzz.get_live_events = AsyncMock(return_value=today_events)
        mock_cache.get.return_value = None
        mock_cache.set.side_effect = _capture_set

        await get_today_matches()

    assert cache_sets
    cache_name = cache_sets[0][0][0]
    assert cache_name == "live"
    assert cache_sets[0][1]["source"] == "today_matches"


@pytest.mark.asyncio
async def test_get_live_match_bzzoiro_happy_path():
    live_event = {
        "id": 99,
        "home_team": "Mexico",
        "away_team": "South Africa",
        "home_team_id": 451,
        "away_team_id": 452,
        "home_score": 2,
        "away_score": 1,
        "current_minute": 78,
        "group_name": "A",
        "status": "inprogress",
    }
    stats = {
        "stats": {
            "home": {
                "xg": {"actual": 1.4},
                "total_shots": 12,
                "shots_on_target": 5,
                "ball_possession": 58,
                "corners": 6,
            },
            "away": {
                "xg": {"actual": 0.9},
                "total_shots": 8,
                "shots_on_target": 3,
                "ball_possession": 42,
                "corners": 4,
            },
        }
    }
    incidents = {
        "incidents": [
            {"type": "goal", "minute": 12, "player_name": "Lozano", "team_name": "Mexico"},
            {"type": "card", "minute": 55, "player_name": "Smith", "team_name": "South Africa",
             "card_type": "Yellow"},
        ]
    }

    with patch("tools.match.uses_bzzoiro_live", return_value=True), \
         patch("tools.match.resolve_bzzoiro_team_id", return_value=451), \
         patch("tools.match.bzzoiro") as mock_bzz, \
         patch("tools.match.cache") as mock_cache:
        mock_bzz.get_live_events = AsyncMock(return_value=[live_event])
        mock_bzz.get_event = AsyncMock(return_value=live_event)
        mock_bzz.get_event_stats = AsyncMock(return_value=stats)
        mock_bzz.get_event_incidents = AsyncMock(return_value=incidents)
        mock_bzz.get_event_lineups = AsyncMock(return_value={})
        mock_cache.get.return_value = None
        mock_cache.set = lambda *a, **kw: None

        result = await get_live_match("Mexico")

    assert "LIVE" in result
    assert "Mexico" in result
    assert "South Africa" in result
    assert "2" in result
    assert "xG" in result
    assert "█" in result
    assert "GOAL TIMELINE" in result
    mock_bzz.get_live_events.assert_awaited_once_with(team_id=451)


@pytest.mark.asyncio
async def test_live_match_ascii_bars():
    from tools.match import _format_live_stats_bars

    lines = _format_live_stats_bars(
        "Mexico", "South Africa", 0.42, 0.0, 6, 0, 2, 0, 54, 46, 2, 0
    )
    text = "\n".join(lines)
    assert "█" in text
    assert "0.42" in text
    assert "Shots" in text


@pytest.mark.asyncio
async def test_live_match_goal_timeline_is_home():
    from tools.match import _format_bzzoiro_live_match

    event = {
        "home_team": "Mexico",
        "away_team": "South Africa",
        "home_score": 1,
        "away_score": 0,
        "current_minute": 26,
        "group_name": "A",
    }
    stats = {"stats": {"home": {"expected_goals": "0.42"}, "away": {"expected_goals": "0"}}}
    incidents = {
        "incidents": [
            {
                "type": "goal",
                "minute": 9,
                "player": "Julián Quiñones",
                "is_home": True,
                "assist": "assist by Érik Lira",
            },
        ]
    }
    result = _format_bzzoiro_live_match(event, stats, incidents)

    assert "GOAL TIMELINE" in result
    assert "Mexico" in result
    assert "Julián Quiñones" in result
    assert "Érik Lira" in result
    assert "[?]" not in result


@pytest.mark.asyncio
async def test_live_match_no_xg_timeline_when_empty():
    from tools.match import _format_bzzoiro_live_match

    event = {"home_team": "A", "away_team": "B", "home_score": 0, "away_score": 0}
    stats = {"stats": {"home": {}, "away": {}}, "xg_per_minute": []}
    result = _format_bzzoiro_live_match(event, stats, {"incidents": []})

    assert "xG TIMELINE" not in result


@pytest.mark.asyncio
async def test_live_match_xg_timeline_when_present():
    from tools.match import _format_bzzoiro_live_match

    event = {"home_team": "Home FC", "away_team": "Away FC", "home_score": 1, "away_score": 1}
    stats = {
        "stats": {"home": {"xg": {"actual": 1.2}}, "away": {"xg": {"actual": 2.1}}},
        "xg_per_minute": [
            {"m": 15, "cum_home": 0.38, "cum_away": 0.11},
            {"m": 45, "cum_home": 0.50, "cum_away": 1.20},
            {"m": 90, "cum_home": 0.50, "cum_away": 2.16},
        ],
    }
    result = _format_bzzoiro_live_match(event, stats, {"incidents": []})

    assert "xG TIMELINE" in result
    assert "0.38" in result
    assert "2.16" in result


@pytest.mark.asyncio
async def test_get_live_match_bzzoiro_expected_goals_field():
    """Live API returns xG in expected_goals when xg.actual is null."""
    from tools.match import _format_bzzoiro_live_match

    event = {
        "home_team": "Mexico",
        "away_team": "South Africa",
        "home_score": 1,
        "away_score": 0,
        "current_minute": 26,
        "group_name": "A",
    }
    stats = {
        "stats": {
            "home": {
                "xg": {"actual": None},
                "expected_goals": "0.39",
                "total_shots": 5,
                "ShotsOnTarget": 2,
                "BallPossesion": 54,
                "corners": 2,
            },
            "away": {
                "xg": {"actual": None},
                "expected_goals": "0.00",
                "total_shots": 0,
                "ShotsOnTarget": 0,
                "BallPossesion": 46,
                "corners": 0,
            },
        }
    }
    result = _format_bzzoiro_live_match(event, stats, {"incidents": []})

    assert "0.39" in result
    assert "0.0" in result  # away xG
    assert "ShotsOnTarget" not in result
    assert "54" in result
    assert "2" in result
    assert "█" in result
    assert "LIVE STATS (bars)" in result


@pytest.mark.asyncio
async def test_get_live_match_not_playing():
    with patch("tools.match.uses_bzzoiro_live", return_value=True), \
         patch("tools.match.resolve_bzzoiro_team_id", return_value=451), \
         patch("tools.match.bzzoiro") as mock_bzz, \
         patch("tools.match.cache") as mock_cache:
        mock_bzz.get_live_events = AsyncMock(return_value=[])
        mock_cache.get.return_value = None

        result = await get_live_match("Mexico")

    assert "not currently playing" in result
