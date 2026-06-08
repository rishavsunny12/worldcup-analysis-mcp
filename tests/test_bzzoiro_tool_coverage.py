"""Audit: all 48 WC teams have bzzoiro squad data; analytics tools use it."""

import inspect

import pytest

from data.loader import BZZ_SQUAD_INDEX, BZZ_TEAMS_BY_ID, BZZ_TEAMS_BY_NAME, get_bzzoiro_squad
from server import TOOLS
from tools.team_analysis import _build_csv_profile

BZZ_TEAM_NAMES: list[str] = [
    BZZ_TEAMS_BY_ID[tid]["team_name"] for tid in sorted(BZZ_SQUAD_INDEX.keys())
]

# Tools that must use bzzoiro for squad/player club-season analytics
BZZ_SQUAD_TOOLS = {
    "analyze_team_for_worldcup",
    "compare_teams_for_worldcup",
    "get_tournament_favorites",
    "get_group_overview",
    "get_nation_top_performers",
    "get_nation_top_defenders",
    "get_squad_league_breakdown",
    "search_players",
    "get_player_club_stats",
    "get_match_preview",
    "get_team_fixtures",
}

# Live tournament tools (bzzoiro live API when LIVE_DATA_SOURCE=bzzoiro)
LIVE_BZZOIRO_TOOLS = {
    "get_today_matches",
    "get_fixtures_range",
    "get_live_match",
    "get_team_form",
    "get_h2h",
    "get_group_standings",
    "get_top_scorers",
    "simulate_group_scenarios",
}


@pytest.mark.parametrize("team_name", BZZ_TEAM_NAMES)
def test_every_wc_team_has_bzzoiro_squad(team_name: str) -> None:
    squad = get_bzzoiro_squad(team_name)
    assert len(squad) >= 20, f"{team_name} has only {len(squad)} bzzoiro players"


def test_bzzoiro_index_covers_48_teams() -> None:
    assert len(BZZ_SQUAD_INDEX) == 48
    assert len(BZZ_TEAMS_BY_NAME) == 48


@pytest.mark.parametrize("team_name", BZZ_TEAM_NAMES)
def test_build_csv_profile_full_coverage_with_bzz(team_name: str) -> None:
    bzz = get_bzzoiro_squad(team_name)
    prof = _build_csv_profile([], bzz)
    assert prof["total_squad"] == len(bzz)
    assert prof["not_found"] == 0, f"{team_name}: {prof['not_found']} players unmatched"
    assert len(prof["performers"]) == len(bzz)
    assert prof["bzzoiro_count"] + prof["found"] >= len(bzz) - 3  # allow few understat overlaps


def test_saudi_spl_players_use_bzzoiro_not_understat_only() -> None:
    bzz = get_bzzoiro_squad("Saudi Arabia")
    official = [p for p in bzz if p.get("wc_status") == "official"]
    prof = _build_csv_profile([], official)
    assert prof["not_found"] == 0
    assert prof["bzzoiro_count"] >= 20
    assert prof["proj_gpg"] >= 0.4


def test_all_squad_tools_registered() -> None:
    registered = {t.__name__ for t in TOOLS}
    assert BZZ_SQUAD_TOOLS <= registered
    assert LIVE_BZZOIRO_TOOLS <= registered
    assert len(registered) == len(BZZ_SQUAD_TOOLS) + len(LIVE_BZZOIRO_TOOLS)


def test_squad_tools_import_bzzoiro_helpers() -> None:
    """Static check that squad tools reference bzzoiro loader paths."""
    import tools.compare as compare_mod
    import tools.favorites as favorites_mod
    import tools.match as match_mod
    import tools.squad_analysis as squad_mod
    import tools.standings as standings_mod
    import tools.team_analysis as team_mod

    import tools.fixtures as fixtures_mod

    sources = {
        "analyze_team_for_worldcup": inspect.getsource(team_mod.analyze_team_for_worldcup),
        "compare_teams_for_worldcup": inspect.getsource(compare_mod.compare_teams_for_worldcup),
        "get_tournament_favorites": inspect.getsource(favorites_mod.get_tournament_favorites),
        "get_group_overview": inspect.getsource(standings_mod.get_group_overview),
        "get_nation_top_performers": inspect.getsource(squad_mod.get_nation_top_performers),
        "get_nation_top_defenders": inspect.getsource(squad_mod.get_nation_top_defenders),
        "get_squad_league_breakdown": inspect.getsource(squad_mod.get_squad_league_breakdown),
        "search_players": inspect.getsource(squad_mod.search_players),
        "get_player_club_stats": inspect.getsource(squad_mod.get_player_club_stats),
        "get_match_preview": inspect.getsource(match_mod.get_match_preview),
        "get_team_fixtures": inspect.getsource(fixtures_mod.get_team_fixtures),
    }
    for tool_name, src in sources.items():
        assert "bzzoiro" in src.lower() or "get_bzzoiro" in src, (
            f"{tool_name} does not reference bzzoiro"
        )
