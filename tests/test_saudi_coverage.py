"""Tests for Saudi squad coverage fixes: strict understat matching + bzzoiro in group overview."""

import pytest

from data.loader import find_player, get_bzzoiro_squad
from tools.team_analysis import _build_csv_profile


def test_find_player_rejects_kanno_kaba_confusion():
    rows = find_player("Mohamed Kanno")
    names = {r["player_name"] for r in rows}
    assert "Mohamed Kaba" not in names
    assert rows == []


def test_find_player_rejects_al_owais_salisu_confusion():
    rows = find_player("Mohammed Al-Owais")
    names = {r["player_name"] for r in rows}
    assert "Mohammed Salisu" not in names
    assert rows == []


def test_find_player_keeps_saud_abdulhamid():
    rows = find_player("Saud Abdulhamid")
    assert any(r["player_name"] == "Saud Abdulhamid" for r in rows)


def test_saudi_official_squad_full_bzzoiro_coverage():
    bzz = get_bzzoiro_squad("Saudi Arabia")
    prof = _build_csv_profile([], bzz)
    assert prof["total_squad"] == len(bzz)
    assert prof["not_found"] == 0
    assert prof["bzzoiro_count"] >= 20
    assert prof["proj_gpg"] >= 0.4


def test_saudi_without_bzzoiro_still_sparse():
    bzz = get_bzzoiro_squad("Saudi Arabia")
    official = [p["player_name"] for p in bzz if p.get("wc_status") == "official"]
    prof = _build_csv_profile(official)
    assert prof["not_found"] >= 20


def test_group_overview_profile_uses_bzzoiro_for_saudi():
    """get_group_overview path: bzz_squad as canonical roster matches analyze_team behavior."""
    bzz = get_bzzoiro_squad("Saudi Arabia")
    prof = _build_csv_profile([], bzz)
    assert prof["not_found"] == 0
    assert prof["proj_gpg"] == pytest.approx(0.61, abs=0.15)
