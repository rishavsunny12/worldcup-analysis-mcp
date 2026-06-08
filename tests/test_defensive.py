"""Unit tests for defensive profile helpers and get_nation_top_defenders tool."""

import pytest

from data.loader import (
    BZZ_PREDICTIONS,
    defense_score_from_avg,
    defender_event_score,
    defensive_profile_from_squad,
    find_bzzoiro_prediction,
    is_defensive_player,
    parse_attr_defending,
)
from tools.squad_analysis import get_nation_top_defenders


SAMPLE_SQUAD = [
    {
        "player_name": "Alpha CB",
        "wc_position": "DF",
        "club_name": "Big Club",
        "attr_defending": "82",
        "overall_rating": "84",
    },
    {
        "player_name": "Beta GK",
        "wc_position": "GK",
        "club_name": "Big Club",
        "attr_defending": "78",
        "overall_rating": "80",
    },
    {
        "player_name": "Gamma Striker",
        "wc_position": "FW",
        "club_name": "Big Club",
        "attr_defending": "40",
        "overall_rating": "85",
    },
    {
        "player_name": "Delta CB",
        "wc_position": "DF",
        "club_name": "Small Club",
        "attr_defending": "",
        "overall_rating": "70",
    },
]


def test_parse_attr_defending_valid():
    assert parse_attr_defending({"attr_defending": "72"}) == 72
    assert parse_attr_defending({"attr_defending": 75.0}) == 75


def test_parse_attr_defending_missing():
    assert parse_attr_defending({}) is None
    assert parse_attr_defending({"attr_defending": ""}) is None


def test_is_defensive_player():
    assert is_defensive_player({"wc_position": "DF"})
    assert is_defensive_player({"wc_position": "GK"})
    assert is_defensive_player({"position": "D M"})
    assert not is_defensive_player({"wc_position": "FW"})


def test_defensive_profile_from_squad():
    profile = defensive_profile_from_squad(SAMPLE_SQUAD, top_n=3)
    assert profile["defender_count"] == 2
    assert profile["elite_count"] == 2
    assert profile["avg_def_rating"] == 80.0
    assert len(profile["top_defenders"]) == 2
    assert profile["top_defenders"][0]["rating"] == 82
    assert profile["top_defenders"][0]["row"]["player_name"] == "Alpha CB"


def test_defense_score_from_avg():
    assert defense_score_from_avg(80) == pytest.approx(0.833, abs=0.01)
    assert defense_score_from_avg(None) == 0.0


def test_defender_event_score():
    row = {"wc_position": "DF", "club_tackles": "40", "club_interceptions": "20", "club_clearances": "30"}
    assert defender_event_score(row) > 0


def test_defender_event_score_gk():
    row = {"wc_position": "GK", "club_saves": "50", "club_tackles": "0"}
    assert defender_event_score(row) == pytest.approx(100.0)


def test_find_bzzoiro_prediction_when_csv_loaded():
    if not BZZ_PREDICTIONS:
        pytest.skip("predictions CSV not exported yet")
    row = BZZ_PREDICTIONS[0]
    home, away = row["home_team"], row["away_team"]
    found = find_bzzoiro_prediction(home, away)
    assert found is not None
    assert found["home_team"] == home


def test_defensive_profile_event_boost():
    squad = [
        {"player_name": "A", "wc_position": "DF", "attr_defending": "70", "club_tackles": "60",
         "club_interceptions": "30", "club_clearances": "20"},
        {"player_name": "B", "wc_position": "DF", "attr_defending": "72", "club_tackles": "5",
         "club_interceptions": "2", "club_clearances": "1"},
    ]
    profile = defensive_profile_from_squad(squad, top_n=2)
    assert profile["top_defenders"][0]["row"]["player_name"] == "A"


@pytest.mark.asyncio
async def test_get_nation_top_defenders_invalid_team():
    result = await get_nation_top_defenders("Not A Real Nation FC")
    assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_get_nation_top_defenders_happy_path():
    result = await get_nation_top_defenders("France", top_n=3)
    assert "TOP DEFENDERS" in result
    assert "FRANCE" in result
    assert "Def" in result


@pytest.mark.asyncio
async def test_get_nation_top_defenders_cache_hit():
    from cache.cache_manager import cache
    from config import resolve_team_id

    team_id = resolve_team_id("France")
    cache.set("form", "cached defenders", team_id=team_id, top_n=5, source="defenders_v2")
    result = await get_nation_top_defenders("France", top_n=5)
    assert result == "cached defenders"
