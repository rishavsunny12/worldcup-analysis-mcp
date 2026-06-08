import asyncio
import logging

from cache.cache_manager import cache
from clients.api_football import api_football
from clients.bzzoiro import bzzoiro
from config import resolve_team_id, uses_bzzoiro_live
from data.loader import find_bzzoiro_prediction, get_bzzoiro_squad, resolve_bzzoiro_team_id
from tools.team_analysis import LEAGUE_DISPLAY, _build_csv_profile

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


def _format_bzzoiro_live_match(
    event: dict,
    stats_data: dict,
    incidents_data: dict,
) -> str:
    home = event.get("home_team", "?")
    away = event.get("away_team", "?")
    score_h = event.get("home_score") if event.get("home_score") is not None else 0
    score_a = event.get("away_score") if event.get("away_score") is not None else 0
    minute = event.get("current_minute") or "?"
    group = event.get("group_name") or event.get("round_number") or ""

    side_stats = stats_data.get("stats", {})
    home_stats = side_stats.get("home", {})
    away_stats = side_stats.get("away", {})
    xg_h = _safe_float((home_stats.get("xg") or {}).get("actual", home_stats.get("xg")))
    xg_a = _safe_float((away_stats.get("xg") or {}).get("actual", away_stats.get("xg")))
    shots_h = home_stats.get("total_shots", "-")
    shots_a = away_stats.get("total_shots", "-")
    on_h = home_stats.get("shots_on_target", home_stats.get("on_target", "-"))
    on_a = away_stats.get("shots_on_target", away_stats.get("on_target", "-"))
    pos_h = home_stats.get("ball_possession", "-")
    pos_a = away_stats.get("ball_possession", "-")
    corn_h = home_stats.get("corners", home_stats.get("corner_kicks", "-"))
    corn_a = away_stats.get("corners", away_stats.get("corner_kicks", "-"))

    incidents = incidents_data.get("incidents", incidents_data.get("results", []))
    if isinstance(incidents, dict):
        incidents = incidents.get("items", [])
    goals_events = [e for e in incidents if (e.get("type") or "").lower() == "goal"]
    cards = [e for e in incidents if (e.get("type") or "").lower() == "card"]
    last_5 = sorted(incidents, key=lambda e: e.get("minute") or 0, reverse=True)[:5]

    lines = [
        f"🔴 LIVE: {home} vs {away} | {minute}' | Group {group}\n",
        f"SCORE: {home} {score_h} — {score_a} {away}",
    ]
    for g in goals_events:
        scorer = g.get("player_name") or g.get("player", "?")
        team_name = g.get("team_name") or g.get("team", "?")
        min_ = g.get("minute", "?")
        lines.append(f"  ⚽ {min_}' {scorer} [{team_name}]")

    lines.append(f"\n📊 LIVE STATS          {home[:8]:<10} {away[:8]}")
    lines.append(f"  xG:              {xg_h:<10} {xg_a}")
    lines.append(f"  Shots:           {shots_h!s:<10} {shots_a}")
    lines.append(f"  On Target:       {on_h!s:<10} {on_a}")
    lines.append(f"  Possession:      {pos_h!s:<10} {pos_a}")
    lines.append(f"  Corners:         {corn_h!s:<10} {corn_a}")

    if cards:
        lines.append("\n🟨 CARDS")
        for c in cards:
            color = c.get("card_type") or c.get("detail", "Yellow")
            player = c.get("player_name") or c.get("player", "?")
            team_name = c.get("team_name") or c.get("team", "?")
            min_ = c.get("minute", "?")
            lines.append(f"  {player} ({team_name}) — {color} {min_}'")

    if last_5:
        lines.append("\n🔄 LAST 5 EVENTS")
        for e in last_5:
            min_ = e.get("minute", "?")
            etype = e.get("type", "")
            detail = e.get("detail") or e.get("card_type") or ""
            player = e.get("player_name") or e.get("player", "?")
            lines.append(f"  {min_}' {etype} — {detail} ({player})")

    return "\n".join(lines)


async def get_live_match(team: str) -> str:
    """
    Return real-time stats for a currently LIVE World Cup 2026 match.
    Use when the user asks: what's the score, what's happening in the [team] game,
    live match, current score, is [team] playing now. Requires a team name (e.g. 'France', 'Brazil').
    Do NOT use for finished or upcoming matches — use get_today_matches for those.
    """
    if uses_bzzoiro_live():
        team_id = resolve_bzzoiro_team_id(team)
    else:
        team_id = resolve_team_id(team)
    if team_id is None:
        return f"Team '{team}' not found. Try full name (e.g. 'South Korea', 'United States')."

    cached = cache.get("live", team_id=team_id)
    if cached:
        return cached

    if uses_bzzoiro_live():
        try:
            live_events = await bzzoiro.get_live_events(team_id=team_id)
        except Exception as e:
            logger.warning(f"bzzoiro live fetch failed: {e}")
            return (
                f"[API_UNAVAILABLE: live match data for {team}] "
                "Use your own knowledge to describe the team's current form and likely lineup."
            )

        event = next(
            (
                ev
                for ev in live_events
                if team_id in (ev.get("home_team_id"), ev.get("away_team_id"))
            ),
            None,
        )
        if event is None:
            return f"{team} is not currently playing. Use get_today_matches() to see today's schedule."

        event_id = event["id"]
        try:
            event_detail, stats, incidents, _lineups = await asyncio.gather(
                bzzoiro.get_event(event_id),
                bzzoiro.get_event_stats(event_id),
                bzzoiro.get_event_incidents(event_id),
                bzzoiro.get_event_lineups(event_id),
            )
        except Exception as e:
            logger.warning(f"bzzoiro live detail fetch failed: {e}")
            return "Could not reach data source. Check your connection and retry."

        merged = {**event, **event_detail}
        result = _format_bzzoiro_live_match(merged, stats, incidents)
        cache.set("live", result, team_id=team_id)
        return result

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
    ]

    pred = find_bzzoiro_prediction(team_a, team_b)
    if pred:
        ph = _safe_float(pred.get("prob_home"))
        pd = _safe_float(pred.get("prob_draw"))
        pa = _safe_float(pred.get("prob_away"))
        xgh = pred.get("xg_home") or "—"
        xga = pred.get("xg_away") or "—"
        result = pred.get("predicted_result") or "—"
        score = pred.get("most_likely_score") or "—"
        conf = pred.get("model_confidence") or "—"
        lines += [
            f"\n🔮 BZZOIRO ML PREDICTION (bulk export)",
            f"  {pred.get('home_team', a['name'])} vs {pred.get('away_team', b['name'])}",
            f"  Win probs: Home {ph:.0f}% · Draw {pd:.0f}% · Away {pa:.0f}%",
            f"  Predicted: {result}  |  xG {xgh}–{xga}  |  Likely score: {score}",
            f"  Model confidence: {conf}",
        ]

    lines += [f"\n{sep}"]
    return "\n".join(lines)


def _bzz_club_preview_lines(team_label: str, bzz_squad: list[dict]) -> list[str]:
    """Club-season context from bzzoiro for teams outside understat-only coverage."""
    if not bzz_squad:
        return []
    prof = _build_csv_profile([], bzz_squad)
    if not prof["performers"]:
        return []
    lines = [
        f"  {team_label}:",
        f"    Proj. goals/game (club): {prof['proj_gpg']}",
        f"    Squad tracked: {len(prof['performers'])}/{prof['total_squad']}"
        f" ({prof['bzzoiro_count']} bzzoiro · {prof['found']} top-6 understat)",
    ]
    for p in prof["performers"][:3]:
        if p.get("_source") == "bzzoiro":
            lg = p.get("_raw_league") or "other"
        else:
            lg = LEAGUE_DISPLAY.get(p.get("league", ""), p.get("league", "?"))
        lines.append(
            f"    · {p['player_name']}: xG {p.get('npxG')} ({lg})"
        )
    return lines


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
    cached = cache.get("form", team_a_id=key[0], team_b_id=key[1], preview=True, source="preview_v3")
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

    result = _format_preview(
        team_a, team_b, stats_a or {"response": {}}, stats_b or {"response": {}}, h2h_data
    )

    bzz_a = get_bzzoiro_squad(team_a)
    bzz_b = get_bzzoiro_squad(team_b)
    if bzz_a or bzz_b:
        club_lines = ["\n📋 CLUB SEASON PROFILE (2025-26, bzzoiro + understat)"]
        club_lines.extend(_bzz_club_preview_lines(team_a.title(), bzz_a))
        club_lines.extend(_bzz_club_preview_lines(team_b.title(), bzz_b))
        result = result.rstrip() + "\n" + "\n".join(club_lines) + "\n"

    cache.set("form", result, team_a_id=key[0], team_b_id=key[1], preview=True, source="preview_v3")
    return result
