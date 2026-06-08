"""South Africa squad tool consistency — official roster, pedigree, league labels."""

import pytest

from data.loader import (
    find_player_for_squad,
    get_bzzoiro_squad,
    resolve_club_league_name,
)
from tools.team_analysis import _build_csv_profile


def test_south_africa_official_squad_size():
    bzz = get_bzzoiro_squad("South Africa")
    assert len(bzz) == 26
    assert all((p.get("wc_status") or "").lower() == "official" for p in bzz)


def test_south_africa_pedigree_single_pl_player():
    bzz = get_bzzoiro_squad("South Africa")
    prof = _build_csv_profile([], bzz)
    assert prof["total_squad"] == 26
    assert prof["league_counts"]["EPL"] == 1
    assert prof["league_counts"]["Serie A"] == 0
    assert prof["pedigree_score"] == pytest.approx(1.0 / 26, abs=0.01)


def test_south_africa_no_false_understat_matches():
    bzz = get_bzzoiro_squad("South Africa")
    for row in bzz:
        matches = find_player_for_squad(row["player_name"], row)
        for m in matches:
            assert m["player_name"] == row["player_name"]


def test_south_africa_no_afcon_stale_league_labels():
    bzz = get_bzzoiro_squad("South Africa")
    resolved = [resolve_club_league_name(p) for p in bzz]
    assert "Africa Cup of Nations 2023" not in resolved
    psl_count = sum(1 for r in resolved if r == "South African Premiership")
    assert psl_count >= 8


def test_league_breakdown_matches_analyze_pedigree():
    from tools.squad_analysis import get_squad_league_breakdown
    import asyncio

    bzz = get_bzzoiro_squad("South Africa")
    prof = _build_csv_profile([], bzz)
    breakdown = asyncio.run(get_squad_league_breakdown("South Africa"))
    ped_str = f"{prof['pedigree_score']:.0%}"
    assert "26 official squad players" in breakdown
    assert f"Pedigree score: {ped_str}" in breakdown
    assert "Africa Cup of Nations 2023" not in breakdown


def test_group_overview_tiebreak_proj_gpg():
    """At equal pedigree, higher proj_gpg ranks ahead (Group A: SA vs South Korea)."""
    sa_bzz = get_bzzoiro_squad("South Africa")
    kr_bzz = get_bzzoiro_squad("South Korea")
    sa_prof = _build_csv_profile([], sa_bzz)
    kr_prof = _build_csv_profile([], kr_bzz)

    if sa_prof["pedigree_score"] == kr_prof["pedigree_score"]:
        assert kr_prof["proj_gpg"] > sa_prof["proj_gpg"]
        ordered = sorted(
            [("South Korea", kr_prof), ("South Africa", sa_prof)],
            key=lambda x: (x[1]["pedigree_score"], x[1]["proj_gpg"]),
            reverse=True,
        )
        assert ordered[0][0] == "South Korea"
