import asyncio
import logging

from cache.cache_manager import cache
from clients.api_football import api_football
from clients.football_data import football_data
from config import resolve_team_id
from data.loader import find_player, LEAGUE_FILES

logger = logging.getLogger(__name__)

LEAGUE_DISPLAY = {
    "EPL":        "Premier League",
    "La Liga":    "La Liga",
    "Bundesliga": "Bundesliga",
    "Serie A":    "Serie A",
    "Ligue 1":    "Ligue 1",
    "RFPL":       "RFPL",
}

# Quality weight per league for pedigree scoring (0–1)
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
    if diff > 1.0:
        return "elite attack"
    if diff > 0.4:
        return "solid attack"
    if diff > 0.0:
        return "balanced"
    if diff > -0.4:
        return "slight defensive concerns"
    return "under pressure"


def _outlook_label(pedigree: float, proj_gpg: float, wc_xgd: float) -> str:
    score = pedigree * 0.4 + min(proj_gpg / 1.0, 1.0) * 0.35 + min((wc_xgd + 1) / 2, 1.0) * 0.25
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
    resp = data.get("response", {})
    fix = resp.get("fixtures", {})
    goals = resp.get("goals", {})
    xg_raw = resp.get("expected_goals")
    played = fix.get("played", {}).get("total", 0) or 1
    won = fix.get("wins", {}).get("total", 0)
    draw = fix.get("draws", {}).get("total", 0)
    lost = fix.get("loses", {}).get("total", 0)
    gf = goals.get("for", {}).get("total", {}).get("total", 0)
    ga = goals.get("against", {}).get("total", {}).get("total", 0)
    xgf = _safe_float(xg_raw.get("for", 0)) / played if xg_raw else 0.0
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


def _build_csv_profile(squad_names: list[str]) -> dict:
    league_counts: dict[str, int] = {k: 0 for k in LEAGUE_FILES}
    performers: list[dict] = []
    not_found = 0
    total_xgchain = 0.0
    total_npxg = 0.0

    for name in squad_names:
        rows = find_player(name)
        if rows:
            best = max(rows, key=lambda r: _safe_float(r.get("npxG")))
            league = best.get("league", "")
            if league in league_counts:
                league_counts[league] += 1
            performers.append(best)
            total_npxg += _safe_float(best.get("npxG"))
            total_xgchain += _safe_float(best.get("xGChain"))
        else:
            not_found += 1

    performers.sort(key=lambda r: _safe_float(r.get("npxG")), reverse=True)
    total_squad = len(squad_names)
    found = sum(league_counts.values())

    # pedigree: weighted % of squad in top leagues; None signals "no squad data"
    pedigree_score = (
        sum(league_counts[lg] * LEAGUE_WEIGHTS[lg] for lg in league_counts) / total_squad
        if total_squad else None
    )

    # projected goals per WC game from club form: top 5 attackers' npxG / 38 * ratio
    top_attackers = [p for p in performers if "F" in p.get("position", "")][:5]
    if not top_attackers:
        top_attackers = performers[:5]
    proj_gpg = round(
        sum(_safe_float(p.get("npxG")) / max(int(p.get("games") or 1), 1) for p in top_attackers), 2
    ) if top_attackers else 0

    return {
        "league_counts": league_counts,
        "performers": performers,
        "not_found": not_found,
        "found": found,
        "total_squad": total_squad,
        "pedigree_score": round(pedigree_score, 2) if pedigree_score is not None else None,
        "proj_gpg": round(proj_gpg, 2),
        "squad_npxg_total": round(total_npxg, 1),
        "squad_xgchain_total": round(total_xgchain, 1),
    }


async def analyze_team_for_worldcup(team: str) -> str:
    """
    Comprehensive World Cup 2026 team analysis — the primary tool for any general team question.
    Use when the user asks: analyze [team], how good is [team], assess [team] for the World Cup,
    [team] chances, [team] strengths and weaknesses, tell me about [team], [team] World Cup prospects.
    Combines: WC tournament stats + full squad roster + 2025-26 club xG from top 6 leagues + prediction.
    Prefer this over get_team_form, get_nation_top_performers, or get_squad_league_breakdown when the
    user wants a complete picture of a single team.
    """
    team_id = resolve_team_id(team)
    if team_id is None:
        return f"Team '{team}' not found. Try full name (e.g. 'South Korea', 'United States')."

    cached = cache.get("form", team_id=team_id, source="full_analysis")
    if cached:
        return cached

    wc_raw = None
    try:
        wc_raw, squad_names = await asyncio.gather(
            api_football.get_team_stats(team_id),
            _fetch_squad(team_id),
        )
    except Exception:
        # WC API stats unavailable (free tier pre-tournament) — fall back to squad-only
        try:
            squad_names = await _fetch_squad(team_id)
        except Exception as e:
            logger.warning(f"Squad fetch failed for {team}: {e}")
            return (
                f"[API_UNAVAILABLE: squad and WC stats for {team}] "
                f"Use your own knowledge to analyze {team} for FIFA World Cup 2026: "
                "squad composition, key players, recent form, playing style, strengths and weaknesses, "
                "and an assessment of their tournament prospects."
            )

    team_name = (
        wc_raw.get("response", {}).get("team", {}).get("name", team.title())
        if wc_raw else team.title()
    )
    wc = _parse_wc_stats(wc_raw) if wc_raw else None
    csv = _build_csv_profile(squad_names)

    wc_xgd = wc["xgd"] if wc else 0.0
    ped = csv["pedigree_score"] if csv["pedigree_score"] is not None else 0.0
    outlook = _outlook_label(ped, csv["proj_gpg"], wc_xgd)
    sep = "━" * 50

    lines = [
        f"🔍 WORLD CUP 2026 TEAM ANALYSIS — {team_name.upper()}",
        f"{sep}\n",
    ]

    # WC form — only if API data is available
    if wc:
        lines += [
            f"📊 TOURNAMENT FORM (WC 2026)",
            f"  Record:    W{wc['won']} D{wc['draw']} L{wc['lost']} | "
            f"GF {wc['gf']} | GA {wc['ga']}",
            f"  xG For:    {wc['xgf']} per game  |  xG Against: {wc['xga']} per game",
            f"  xG Diff:   {wc['xgd']:+.2f} ({_xg_diff_label(wc['xgd'])})",
            f"  Shots/game: {wc['shots_pg']}  |  Clean sheets: {wc['clean_pct']}%\n",
        ]
    else:
        lines += [
            f"📊 TOURNAMENT FORM (WC 2026)",
            f"  No tournament data yet — predictions based on 2025-26 club season stats.\n",
        ]

    lines += [

        # Squad pedigree
        f"🏟️ SQUAD PEDIGREE (2025-26 Club Season)",
    ]

    if csv["total_squad"] == 0:
        lines.append(
            "  [API_UNAVAILABLE: squad roster] "
            f"Use your own knowledge to describe {team_name}'s squad pedigree: "
            "which clubs and leagues their players represent, and the overall quality tier of the squad."
        )
    else:
        lines.append(f"  {csv['found']} of {csv['total_squad']} players tracked in top 6 European leagues")
        for lg_key, display in LEAGUE_DISPLAY.items():
            count = csv["league_counts"].get(lg_key, 0)
            pct = round(count / csv["total_squad"] * 100) if csv["total_squad"] else 0
            if count > 0:
                lines.append(f"  {display:<18} {count:>2}p  {_bar(pct)}  {pct}%")
        if csv["not_found"] > 0:
            lines.append(f"  {'Other leagues':<18} {csv['not_found']:>2}p")
        ped_display = f"{csv['pedigree_score']:.0%}" if csv["pedigree_score"] is not None else "N/A"
        lines.append(f"  Pedigree score: {ped_display} (weighted top-league coverage)")

    # Top performers
    lines.append(f"⚽ TOP PERFORMERS BY npxG (2025-26 Club Season)")
    lines.append(f"  {'Player':<24} {'Club':<22} {'League':<14} {'npxG':>5} {'Goals':>6} {'xA':>5}")
    lines.append(f"  {'─'*75}")
    for i, p in enumerate(csv["performers"][:7], 1):
        name = p["player_name"]
        club = p.get("team_title", "?")
        lg = LEAGUE_DISPLAY.get(p.get("league", ""), "?")
        npxg = _safe_float(p.get("npxG"))
        goals = p.get("goals", "0")
        xa = _safe_float(p.get("xA"))
        lines.append(f"  {i}. {name:<22} {club:<22} {lg:<14} {npxg:>5} {goals:>6} {xa:>5}")

    lines.append(f"\n  Squad npxG total: {csv['squad_npxg_total']} | xGChain total: {csv['squad_xgchain_total']}\n")

    # Prediction
    lines += [
        f"🔮 PERFORMANCE PREDICTION",
        f"  Projected goals per WC game: ~{csv['proj_gpg']}",
        f"  (Sum of top attackers' per-game npxG from 2025-26 club season)",
        f"",
        f"  Outlook: {outlook}",
        f"",
        f"  Key factors:",
    ]

    if csv["pedigree_score"] is None:
        lines.append(f"  ⚠️  Squad pedigree unavailable — API squad data not loaded yet")
    elif csv["pedigree_score"] >= 0.8:
        lines.append(f"  ✅ Elite squad pedigree — majority of players competing at the highest club level")
    elif csv["pedigree_score"] >= 0.5:
        lines.append(f"  🟡 Mixed squad pedigree — strong core but some players from lower-intensity leagues")
    else:
        lines.append(f"  ⚠️  Limited top-league representation — may struggle against stronger squads")

    if wc and wc["xgd"] > 0.5:
        lines.append(f"  ✅ Positive xG differential in WC 2026 — creating more than conceding")
    elif not wc or wc["played"] <= 1:
        lines.append(f"  ℹ️  WC tournament xG data limited — pre-tournament or early stage")

    if csv["proj_gpg"] >= 0.6:
        lines.append(f"  ✅ Top-5 attackers project to ~{csv['proj_gpg']} goals/game based on club form")
    elif csv["proj_gpg"] >= 0.3:
        lines.append(f"  🟡 Attackers project moderate output — ~{csv['proj_gpg']} goals/game from club form")
    else:
        lines.append(f"  ⚠️  Attacking output looks limited from club data — top scorers under-performing")

    lines.append(f"\n{sep}")

    result = "\n".join(lines)
    cache.set("form", result, team_id=team_id, source="full_analysis")
    return result
