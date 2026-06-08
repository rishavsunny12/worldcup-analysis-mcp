import asyncio
import logging

from cache.cache_manager import cache
from clients.api_football import api_football
from clients.football_data import football_data
from config import resolve_team_id
from data.loader import (
    LEAGUE_FILES, find_player, get_adj_xg,
    get_bzzoiro_squad, get_bzzoiro_team, normalize_bzz_player,
    defensive_profile_from_squad,
)

logger = logging.getLogger(__name__)

LEAGUE_DISPLAY = {
    "EPL":        "Premier League",
    "La Liga":    "La Liga",
    "Bundesliga": "Bundesliga",
    "Serie A":    "Serie A",
    "Ligue 1":    "Ligue 1",
    "RFPL":       "RFPL",
}

LEAGUE_WEIGHTS = {
    "EPL": 1.0, "La Liga": 1.0, "Bundesliga": 0.9,
    "Serie A": 0.9, "Ligue 1": 0.85, "RFPL": 0.6,
}


def _safe_float(val) -> float:
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return 0.0


def _bar(pct: float, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _xg_diff_label(diff: float) -> str:
    if diff > 1.0:   return "elite attack"
    if diff > 0.4:   return "solid attack"
    if diff > 0.0:   return "balanced"
    if diff > -0.4:  return "slight defensive concerns"
    return "under pressure"


def _outlook_label(pedigree: float, proj_gpg: float, wc_xgd: float, defense_score: float = 0.0) -> str:
    attack = min(proj_gpg / 1.0, 1.0) * 0.35 + min((wc_xgd + 1) / 2, 1.0) * 0.15
    score = (
        pedigree * 0.25
        + attack
        + defense_score * 0.25
    )
    if score >= 0.75:
        return "🏆 Strong contender"
    if score >= 0.55:
        return "⭐ Dark horse / solid group-stage team"
    if score >= 0.35:
        return "⚠️  Group stage uncertain — needs results"
    return "❌ Group stage exit risk"


async def _fetch_squad(team_id: int) -> list[str]:
    cached = cache.get("squad", team_id=team_id)
    if cached:
        return cached
    try:
        data = await football_data.get_team_squad(team_id)
        names = [p["name"] for p in data.get("squad", [])]
        cache.set("squad", names, team_id=team_id)
        return names
    except Exception as e:
        logger.warning(f"Squad fetch failed for {team_id}: {e}")
        return []


def _parse_wc_stats(data: dict) -> dict:
    resp  = data.get("response", {})
    fix   = resp.get("fixtures", {})
    goals = resp.get("goals", {})
    xg_raw = resp.get("expected_goals")
    played = fix.get("played", {}).get("total", 0) or 1
    won    = fix.get("wins",  {}).get("total", 0)
    draw   = fix.get("draws", {}).get("total", 0)
    lost   = fix.get("loses", {}).get("total", 0)
    gf     = goals.get("for",     {}).get("total", {}).get("total", 0)
    ga     = goals.get("against", {}).get("total", {}).get("total", 0)
    xgf = _safe_float(xg_raw.get("for",     0)) / played if xg_raw else 0.0
    xga = _safe_float(xg_raw.get("against", 0)) / played if xg_raw else 0.0
    shots = resp.get("shots", {}).get("total", {}).get("total", 0) or 0
    clean = resp.get("clean_sheet", {}).get("total", 0) or 0
    return {
        "played": played, "won": won, "draw": draw, "lost": lost,
        "gf": gf, "ga": ga,
        "xgf": round(xgf, 2), "xga": round(xga, 2),
        "xgd": round(xgf - xga, 2),
        "shots_pg": round(shots / played, 1),
        "clean_pct": round(clean / played * 100) if played else 0,
    }


def _build_csv_profile(squad_names: list[str], bzz_squad: list[dict] | None = None) -> dict:
    """Build squad profile from understat data, filling gaps with bzzoiro rows.

    Priority: understat (npxG, xGChain) > bzzoiro (club_xg as proxy).
    If squad_names is empty and bzz_squad is provided, uses bzzoiro squad directly.
    """
    # Build a fast name lookup for bzzoiro squad
    bzz_by_name: dict[str, dict] = {}
    if bzz_squad:
        for p in bzz_squad:
            key = (p.get("player_name") or "").lower().strip()
            bzz_by_name[key] = p

    league_counts: dict[str, int] = {k: 0 for k in LEAGUE_FILES}
    performers:    list[dict] = []
    not_found = 0
    total_xgchain = 0.0
    total_npxg    = 0.0
    bzzoiro_count = 0

    # Decide which names to iterate: API names or bzzoiro squad names
    if squad_names:
        names_to_check = squad_names
    elif bzz_squad:
        names_to_check = [p.get("player_name", "") for p in bzz_squad]
    else:
        names_to_check = []

    for name in names_to_check:
        rows = find_player(name)
        if rows:
            best = max(rows, key=lambda r: _safe_float(r.get("npxG")))
            league = best.get("league", "")
            if league in league_counts:
                league_counts[league] += 1
            performers.append(best)
            total_npxg    += _safe_float(best.get("npxG"))
            total_xgchain += _safe_float(best.get("xGChain"))
        else:
            # Understat miss — fall back to bzzoiro
            key = name.lower().strip()
            bzz_row = bzz_by_name.get(key)
            if not bzz_row and bzz_squad:
                # loose name match
                bzz_row = next(
                    (p for p in bzz_squad
                     if key in (p.get("player_name") or "").lower()
                     or (p.get("player_name") or "").lower() in key),
                    None,
                )
            if bzz_row:
                norm = normalize_bzz_player(bzz_row)
                league = norm.get("league", "")
                if league in league_counts:
                    league_counts[league] += 1
                performers.append(norm)
                total_npxg += _safe_float(norm.get("npxG"))
                bzzoiro_count += 1
            else:
                not_found += 1

    performers.sort(key=lambda r: _safe_float(r.get("npxG")), reverse=True)
    total_squad = len(names_to_check)
    found = sum(league_counts.values())

    pedigree_score = (
        sum(league_counts[lg] * LEAGUE_WEIGHTS[lg] for lg in league_counts) / total_squad
        if total_squad else None
    )

    top_attackers = [p for p in performers if "F" in p.get("position", "")][:5]
    if not top_attackers:
        top_attackers = performers[:5]

    # Use quality-adjusted xG per game so players in weaker leagues aren't over-weighted
    proj_gpg = round(
        sum(
            get_adj_xg(p) / max(int(p.get("games") or 1), 1)
            for p in top_attackers
        ),
        2,
    ) if top_attackers else 0

    return {
        "league_counts":      league_counts,
        "performers":         performers,
        "not_found":          not_found,
        "found":              found,
        "bzzoiro_count":      bzzoiro_count,
        "total_squad":        total_squad,
        "pedigree_score":     round(pedigree_score, 2) if pedigree_score is not None else None,
        "proj_gpg":           round(proj_gpg, 2),
        "squad_npxg_total":   round(total_npxg, 1),
        "squad_xgchain_total": round(total_xgchain, 1),
    }


async def analyze_team_for_worldcup(team: str) -> str:
    """
    Comprehensive World Cup 2026 team analysis — the primary tool for any general team question.
    Use when the user asks: analyze [team], how good is [team], assess [team] for the World Cup,
    [team] chances, [team] strengths and weaknesses, tell me about [team], [team] World Cup prospects.
    Combines: WC tournament stats + squad roster + 2025-26 club xG from all leagues + prediction.
    Covers all 48 nations. Prefer this over get_team_form or get_nation_top_performers for a full picture.
    """
    team_id = resolve_team_id(team)
    if team_id is None:
        return f"Team '{team}' not found. Try full name (e.g. 'South Korea', 'United States')."

    cached = cache.get("form", team_id=team_id, source="full_analysis_v2")
    if cached:
        return cached

    # Always load bzzoiro data (no API cost, covers all nations)
    bzz_squad = get_bzzoiro_squad(team)
    bzz_team  = get_bzzoiro_team(team)

    wc_raw = None
    squad_names: list[str] = []
    try:
        wc_raw, squad_names = await asyncio.gather(
            api_football.get_team_stats(team_id),
            _fetch_squad(team_id),
        )
    except Exception:
        try:
            squad_names = await _fetch_squad(team_id)
        except Exception as e:
            logger.warning(f"Squad fetch failed for {team}: {e}")

    team_name = (
        wc_raw.get("response", {}).get("team", {}).get("name", team.title())
        if wc_raw else team.title()
    )
    wc  = _parse_wc_stats(wc_raw) if wc_raw else None
    csv = _build_csv_profile(squad_names, bzz_squad)
    def_prof = defensive_profile_from_squad(bzz_squad, top_n=5)

    wc_xgd  = wc["xgd"] if wc else 0.0
    ped     = csv["pedigree_score"] if csv["pedigree_score"] is not None else 0.0
    outlook = _outlook_label(ped, csv["proj_gpg"], wc_xgd, def_prof["defense_score"])
    sep = "━" * 50

    lines = [
        f"🔍 WORLD CUP 2026 TEAM ANALYSIS — {team_name.upper()}",
        f"{sep}\n",
    ]

    # WC tournament form
    if wc:
        lines += [
            f"📊 TOURNAMENT FORM (WC 2026)",
            f"  Record:    W{wc['won']} D{wc['draw']} L{wc['lost']} | GF {wc['gf']} | GA {wc['ga']}",
            f"  xG For:    {wc['xgf']} per game  |  xG Against: {wc['xga']} per game",
            f"  xG Diff:   {wc['xgd']:+.2f} ({_xg_diff_label(wc['xgd'])})",
            f"  Shots/game: {wc['shots_pg']}  |  Clean sheets: {wc['clean_pct']}%\n",
        ]
    else:
        lines += [
            f"📊 TOURNAMENT FORM (WC 2026)",
            f"  No tournament data yet — predictions based on 2025-26 club season.\n",
        ]

    # Bzzoiro squad-level stats
    if bzz_team:
        mv  = int(bzz_team.get("total_market_value_eur") or 0)
        avg = _safe_float(bzz_team.get("avg_overall_rating"))
        sqg = int(bzz_team.get("squad_club_goals") or 0)
        sqx = _safe_float(bzz_team.get("squad_club_xg"))
        sqxv = _safe_float(bzz_team.get("squad_club_xa"))
        age = bzz_team.get("avg_age", "—")
        lines += [
            f"💰 SQUAD OVERVIEW",
            f"  Market value: €{mv:,}  |  Avg squad rating: {avg}  |  Avg age: {age}",
            f"  Combined 2025-26 club: {sqg} goals | xG {sqx} | xA {sqxv}\n",
        ]
        mgr = bzz_team.get("manager_name")
        if mgr:
            formation = bzz_team.get("manager_formation") or "—"
            tactical = bzz_team.get("manager_tactical_profile") or "—"
            win_pct = bzz_team.get("manager_win_pct") or "—"
            avg_ga = bzz_team.get("manager_avg_goals_conceded") or "—"
            cs_pct = bzz_team.get("manager_clean_sheet_pct") or "—"
            lines += [
                f"👔 MANAGER (bzzoiro NT profile)",
                f"  {mgr}  |  Formation: {formation}  |  Style: {tactical}",
                f"  Win %: {win_pct}  |  Avg goals conceded: {avg_ga}  |  Clean sheets: {cs_pct}%\n",
            ]

    # Squad pedigree
    lines.append(f"🏟️ SQUAD PEDIGREE (2025-26 Club Season)")
    if csv["total_squad"] == 0:
        lines.append(
            f"  [DATA_UNAVAILABLE] Use your own knowledge to describe {team_name}'s squad pedigree."
        )
    else:
        top6 = csv["found"]
        bzz  = csv["bzzoiro_count"]
        other = csv["not_found"]
        lines.append(
            f"  {top6} in top-6 European leagues · {bzz} in other leagues · {other} unmatched"
            f" (of {csv['total_squad']} total)"
        )
        for lg_key, display in LEAGUE_DISPLAY.items():
            count = csv["league_counts"].get(lg_key, 0)
            pct   = round(count / csv["total_squad"] * 100) if csv["total_squad"] else 0
            if count > 0:
                lines.append(f"  {display:<18} {count:>2}p  {_bar(pct)}  {pct}%")
        ped_display = f"{csv['pedigree_score']:.0%}" if csv["pedigree_score"] is not None else "N/A"
        lines.append(f"  Pedigree score: {ped_display} (weighted top-league coverage)\n")

    # Top performers
    lines.append(f"⚽ TOP PERFORMERS BY xG (2025-26 Club Season)")
    lines.append(f"  {'Player':<24} {'Club':<22} {'League':<18} {'xG':>5} {'Goals':>6} {'xA':>5}")
    lines.append(f"  {'─'*80}")
    for i, p in enumerate(csv["performers"][:7], 1):
        name  = p.get("player_name", "?")
        club  = p.get("team_title", "?")
        if p.get("_source") == "bzzoiro":
            bzz = p.get("_bzz", {})
            club   = bzz.get("club_name", club)
            lg     = bzz.get("club_league_name", "—")
        else:
            lg = LEAGUE_DISPLAY.get(p.get("league", ""), "—")
        xg    = _safe_float(p.get("npxG"))
        goals = p.get("goals", "0")
        xa    = _safe_float(p.get("xA"))
        lines.append(f"  {i}. {name:<22} {club:<22} {lg:<18} {xg:>5} {goals:>6} {xa:>5}")

    lines.append(f"\n  Squad xG total: {csv['squad_npxg_total']} | xGChain total: {csv['squad_xgchain_total']}\n")

    # Defensive depth (bzzoiro attributes)
    if def_prof["top_defenders"]:
        avg_def = def_prof["avg_def_rating"]
        lines += [
            f"🛡️ DEFENSIVE DEPTH (bzzoiro defending attribute)",
            f"  Avg DF/GK defending: {avg_def}  |  Elite (≥75): {def_prof['elite_count']}"
            f"  |  Rated players: {def_prof['defender_count']}",
            f"  {'Player':<24} {'Pos':<4} {'Club':<22} {'Def':>4} {'OVR':>4}",
            f"  {'─'*62}",
        ]
        for entry in def_prof["top_defenders"]:
            row = entry["row"]
            tkl = row.get("club_tackles") or "—"
            intr = row.get("club_interceptions") or "—"
            lines.append(
                f"  {row.get('player_name', '?'):<22} {row.get('wc_position', '?'):<4}"
                f" {row.get('club_name', '?'):<22} {entry['rating']:>4}"
                f" {str(row.get('overall_rating') or '—'):>4}  Tkl {tkl} Int {intr}"
            )
        lines.append("")

    # Prediction
    lines += [
        f"🔮 PERFORMANCE PREDICTION",
        f"  Projected goals per WC game: ~{csv['proj_gpg']}",
        f"  (Top attackers' per-game xG from 2025-26 club season)",
        f"",
        f"  Outlook: {outlook}",
        f"",
        f"  Key factors:",
    ]

    if csv["pedigree_score"] is None:
        lines.append(f"  ⚠️  Pedigree unavailable")
    elif csv["pedigree_score"] >= 0.8:
        lines.append(f"  ✅ Elite squad pedigree — majority in top European leagues")
    elif csv["pedigree_score"] >= 0.5:
        lines.append(f"  🟡 Mixed pedigree — strong core, some players from lower-intensity leagues")
    else:
        lines.append(f"  ⚠️  Limited top-league representation — squad quality may be a factor")

    if wc and wc["xgd"] > 0.5:
        lines.append(f"  ✅ Positive xG differential in WC 2026")
    elif not wc or wc["played"] <= 1:
        lines.append(f"  ℹ️  WC tournament xG data limited — pre-tournament or early stage")

    if csv["proj_gpg"] >= 0.6:
        lines.append(f"  ✅ Top attackers project ~{csv['proj_gpg']} goals/game from club form")
    elif csv["proj_gpg"] >= 0.3:
        lines.append(f"  🟡 Moderate attacking output — ~{csv['proj_gpg']} goals/game from club form")
    else:
        lines.append(f"  ⚠️  Attacking output looks limited from club data")

    if def_prof["avg_def_rating"] is not None:
        if def_prof["avg_def_rating"] >= 75:
            lines.append(f"  ✅ Strong defensive depth — avg defending {def_prof['avg_def_rating']}")
        elif def_prof["avg_def_rating"] >= 68:
            lines.append(f"  🟡 Solid back line — avg defending {def_prof['avg_def_rating']}")
        else:
            lines.append(f"  ⚠️  Defensive depth a concern — avg defending {def_prof['avg_def_rating']}")

    lines.append(f"\n{sep}")
    result = "\n".join(lines)
    cache.set("form", result, team_id=team_id, source="full_analysis_v2")
    return result
