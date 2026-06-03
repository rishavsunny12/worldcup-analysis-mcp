import asyncio
import logging

from cache.cache_manager import cache
from clients.api_football import api_football
from config import resolve_team_id

logger = logging.getLogger(__name__)


def _safe_float(val) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _xg_label(diff: float) -> str:
    if diff > 0.8:
        return "dominant"
    if diff < -0.3:
        return "under pressure"
    return "balanced"


def _get_stat(stats_list: list, team_idx: int, stat_type: str):
    if team_idx >= len(stats_list):
        return "-"
    for stat in stats_list[team_idx].get("statistics", []):
        if stat.get("type", "").lower() == stat_type.lower():
            return stat.get("value") if stat.get("value") is not None else "-"
    return "-"


def _format_live_match(fixture_data: dict, stats_data: dict, events_data: dict, lineups_data: dict) -> str:
    fix = fixture_data.get("response", [{}])[0]
    teams = fix.get("teams", {})
    home = teams.get("home", {}).get("name", "?")
    away = teams.get("away", {}).get("name", "?")
    score_h = fix.get("goals", {}).get("home") or 0
    score_a = fix.get("goals", {}).get("away") or 0
    minute = fix.get("fixture", {}).get("status", {}).get("elapsed", "?")
    group = fix.get("league", {}).get("round", "")

    stats = stats_data.get("response", [])
    xg_h = _safe_float(_get_stat(stats, 0, "expected_goals"))
    xg_a = _safe_float(_get_stat(stats, 1, "expected_goals"))
    shots_h = _get_stat(stats, 0, "total shots")
    shots_a = _get_stat(stats, 1, "total shots")
    on_h = _get_stat(stats, 0, "shots on goal")
    on_a = _get_stat(stats, 1, "shots on goal")
    pos_h = _get_stat(stats, 0, "ball possession")
    pos_a = _get_stat(stats, 1, "ball possession")
    corn_h = _get_stat(stats, 0, "corner kicks")
    corn_a = _get_stat(stats, 1, "corner kicks")

    events = events_data.get("response", [])
    goals_events = [e for e in events if e.get("type") == "Goal"]
    cards = [e for e in events if e.get("type") == "Card"]
    last_5 = sorted(events, key=lambda e: e.get("time", {}).get("elapsed", 0), reverse=True)[:5]

    lines = [
        f"🔴 LIVE: {home} vs {away} | {minute}' | {group}\n",
        f"SCORE: {home} {score_h} — {score_a} {away}",
    ]
    for g in goals_events:
        scorer = g.get("player", {}).get("name", "?")
        team = g.get("team", {}).get("name", "?")
        min_ = g.get("time", {}).get("elapsed", "?")
        lines.append(f"  ⚽ {min_}' {scorer} [{team}]")

    lines.append(f"\n📊 LIVE STATS          {home[:8]:<10} {away[:8]}")
    lines.append(f"  xG:              {xg_h:<10} {xg_a}")
    lines.append(f"  Shots:           {shots_h!s:<10} {shots_a}")
    lines.append(f"  On Target:       {on_h!s:<10} {on_a}")
    lines.append(f"  Possession:      {pos_h!s:<10} {pos_a}")
    lines.append(f"  Corners:         {corn_h!s:<10} {corn_a}")

    if cards:
        lines.append("\n🟨 CARDS")
        for c in cards:
            color = c.get("detail", "Yellow")
            player = c.get("player", {}).get("name", "?")
            team = c.get("team", {}).get("name", "?")
            min_ = c.get("time", {}).get("elapsed", "?")
            lines.append(f"  {player} ({team}) — {color} {min_}'")

    if last_5:
        lines.append("\n🔄 LAST 5 EVENTS")
        for e in last_5:
            min_ = e.get("time", {}).get("elapsed", "?")
            etype = e.get("type", "")
            detail = e.get("detail", "")
            player = e.get("player", {}).get("name", "?")
            lines.append(f"  {min_}' {etype} — {detail} ({player})")

    return "\n".join(lines)


async def get_live_match(team: str) -> str:
    """
    Return real-time stats for a currently LIVE World Cup 2026 match.
    Use when the user asks: what's the score, what's happening in the [team] game,
    live match, current score, is [team] playing now. Requires a team name (e.g. 'France', 'Brazil').
    Do NOT use for finished or upcoming matches — use get_today_matches for those.
    """
    team_id = resolve_team_id(team)
    if team_id is None:
        return f"Team '{team}' not found. Try full name (e.g. 'South Korea', 'United States')."

    cached = cache.get("live", team_id=team_id)
    if cached:
        return cached

    try:
        live_data = await api_football.get_live_fixtures()
    except Exception as e:
        logger.warning(f"Live fixtures fetch failed: {e}")
        return (
            f"[API_UNAVAILABLE: live match data for {team}] "
            "Use your own knowledge to describe the team's current form and likely lineup. "
            "Note that real-time scores are not available — inform the user live data activates June 11."
        )

    fixture_id = None
    for fix in live_data.get("response", []):
        home_id = fix.get("teams", {}).get("home", {}).get("id")
        away_id = fix.get("teams", {}).get("away", {}).get("id")
        if team_id in (home_id, away_id):
            fixture_id = fix.get("fixture", {}).get("id")
            break

    if fixture_id is None:
        return f"{team} is not currently playing. Use get_today_matches() to see today's schedule."

    try:
        fixture_detail, stats, events, lineups = await asyncio.gather(
            api_football.get_fixture(fixture_id),
            api_football.get_fixture_stats(fixture_id),
            api_football.get_fixture_events(fixture_id),
            api_football.get_fixture_lineups(fixture_id),
        )
    except Exception as e:
        logger.warning(f"Live match detail fetch failed: {e}")
        return "Could not reach data source. Check your connection and retry."

    result = _format_live_match(fixture_detail, stats, events, lineups)
    cache.set("live", result, team_id=team_id)
    return result


def _format_preview(team_a: str, team_b: str, stats_a: dict, stats_b: dict, h2h_data: dict) -> str:
    def extract(stats: dict) -> dict:
        resp = stats.get("response", {})
        fix = resp.get("fixtures", {})
        goals = resp.get("goals", {})
        xg_raw = resp.get("expected_goals")
        played = fix.get("played", {}).get("total", 0) or 1
        won = fix.get("wins", {}).get("total", 0)
        draw = fix.get("draws", {}).get("total", 0)
        lost = fix.get("loses", {}).get("total", 0)
        gf = goals.get("for", {}).get("average", {}).get("total", 0)
        ga = goals.get("against", {}).get("average", {}).get("total", 0)
        xgf = _safe_float(xg_raw.get("for", 0)) / played if xg_raw else 0
        xga = _safe_float(xg_raw.get("against", 0)) / played if xg_raw else 0
        diff = round(xgf - xga, 2)
        poss = resp.get("ball_possession", "?")
        shots = resp.get("shots", {}).get("total", {}).get("total", 0) or 0
        spm = round(shots / played, 1)
        clean = resp.get("clean_sheet", {}).get("total", 0) or 0
        cs_pct = round(clean / played * 100)
        team_name = resp.get("team", {}).get("name", "?")
        return {
            "name": team_name, "w": won, "d": draw, "l": lost,
            "gf": gf, "ga": ga, "xgf": round(xgf, 2), "xga": round(xga, 2),
            "diff": diff, "label": _xg_label(diff),
            "poss": poss, "spm": spm, "cs_pct": cs_pct,
        }

    a = extract(stats_a)
    b = extract(stats_b)

    h2h_fixtures = h2h_data.get("response", [])
    aw, bw, dr, ag, bg = 0, 0, 0, 0, 0
    last_result = "N/A"
    for fix in h2h_fixtures[:10]:
        home_name = fix.get("teams", {}).get("home", {}).get("name", "")
        hg = fix.get("goals", {}).get("home") or 0
        ag_ = fix.get("goals", {}).get("away") or 0
        a_is_home = team_a.lower() in home_name.lower()
        a_g, b_g = (hg, ag_) if a_is_home else (ag_, hg)
        ag += a_g
        bg += b_g
        if a_g > b_g:
            aw += 1
        elif b_g > a_g:
            bw += 1
        else:
            dr += 1
    if h2h_fixtures:
        f = h2h_fixtures[0]
        hn = f.get("teams", {}).get("home", {}).get("name", "?")
        an = f.get("teams", {}).get("away", {}).get("name", "?")
        hg = f.get("goals", {}).get("home") or 0
        ag2 = f.get("goals", {}).get("away") or 0
        last_result = f"{hn} {hg}–{ag2} {an}"

    sep = "━" * 36
    lines = [
        f"⚽ MATCH PREVIEW: {a['name']} vs {b['name']}",
        f"🏆 FIFA World Cup 2026\n",
        sep,
        f"\n📊 FORM (WC 2026)",
        f"  {a['name']}: W{a['w']} D{a['d']} L{a['l']}  ▸ {a['gf']} scored, {a['ga']} conceded",
        f"  {b['name']}: W{b['w']} D{b['d']} L{b['l']}  ▸ {b['gf']} scored, {b['ga']} conceded",
        f"\n📈 xG PROFILE (2026 WC)",
        f"  {a['name']} → xGF {a['xgf']} | xGA {a['xga']} | Diff {a['diff']:+.2f} ({a['label']})",
        f"  {b['name']} → xGF {b['xgf']} | xGA {b['xga']} | Diff {b['diff']:+.2f} ({b['label']})",
        f"\n🤝 HEAD TO HEAD (Last 10 meetings)",
        f"  {a['name']} {aw}W — {dr}D — {bw}W {b['name']}",
        f"  Goals: {a['name']} {ag} — {bg} {b['name']}",
        f"  Last match: {last_result}",
        f"\n🎯 KEY STATS",
        f"               {a['name'][:12]:<14} {b['name'][:12]}",
        f"  Possession:  {str(a['poss'])+'%':<16} {b['poss']}%",
        f"  Shots/game:  {str(a['spm']):<16} {b['spm']}",
        f"  Clean sh:    {str(a['cs_pct'])+'%':<16} {b['cs_pct']}%",
        f"\n{sep}",
    ]
    return "\n".join(lines)


async def get_match_preview(team_a: str, team_b: str) -> str:
    """
    Return a full pre-match breakdown for two World Cup 2026 teams: form, xG profile, H2H history, key stats.
    Use when the user asks: preview [team] vs [team], who will win, preview the match, matchup analysis.
    Requires two team names. Do NOT use for live matches — use get_live_match for those.
    """
    id_a = resolve_team_id(team_a)
    id_b = resolve_team_id(team_b)
    if id_a is None:
        return f"Team '{team_a}' not found. Try full name (e.g. 'South Korea', 'United States')."
    if id_b is None:
        return f"Team '{team_b}' not found. Try full name (e.g. 'South Korea', 'United States')."

    key = tuple(sorted([id_a, id_b]))
    cached = cache.get("form", team_a_id=key[0], team_b_id=key[1], preview=True)
    if cached:
        return cached

    gathered = await asyncio.gather(
        api_football.get_team_stats(id_a),
        api_football.get_team_stats(id_b),
        api_football.get_h2h(id_a, id_b, last=10),
        return_exceptions=True,
    )
    stats_a = gathered[0] if not isinstance(gathered[0], Exception) else None
    stats_b = gathered[1] if not isinstance(gathered[1], Exception) else None
    h2h_data = gathered[2] if not isinstance(gathered[2], Exception) else {"response": []}

    if gathered[0] is None and gathered[1] is None:
        logger.warning(f"Match preview: all API calls failed for {team_a} vs {team_b}")

    if stats_a is None and stats_b is None and not h2h_data.get("response"):
        return (
            f"[API_UNAVAILABLE: match preview for {team_a.title()} vs {team_b.title()}] "
            f"Use your own knowledge to provide a full pre-match analysis: "
            f"recent international form for both teams, head-to-head history, "
            f"key players to watch, tactical styles, and an outlook for the match."
        )

    result = _format_preview(team_a, team_b, stats_a or {"response": {}}, stats_b or {"response": {}}, h2h_data)
    cache.set("form", result, team_a_id=key[0], team_b_id=key[1], preview=True)
    return result
