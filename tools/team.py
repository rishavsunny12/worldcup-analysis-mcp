import logging

from cache.cache_manager import cache
from clients.api_football import api_football
from config import resolve_team_id

logger = logging.getLogger(__name__)


def _xg_label(diff: float) -> str:
    if diff > 0.8:
        return "dominant"
    if diff < -0.3:
        return "under pressure"
    return "balanced"


def _safe_float(val) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _format_form_string(fixtures: list[dict], team_id: int, last_n: int) -> str:
    results = []
    for fix in fixtures[-last_n:]:
        home_id = fix.get("teams", {}).get("home", {}).get("id")
        home_winner = fix.get("teams", {}).get("home", {}).get("winner")
        away_winner = fix.get("teams", {}).get("away", {}).get("winner")
        if home_id == team_id:
            winner = home_winner
        else:
            winner = away_winner
        if winner is True:
            results.append("W")
        elif winner is False:
            results.append("L")
        else:
            results.append("D")
    return " ".join(results) if results else "N/A"


def _format_team_form(data: dict, team_id: int, last_n: int) -> str:
    resp = data.get("response", {})
    team_name = resp.get("team", {}).get("name", "Unknown")
    fixtures_stats = resp.get("fixtures", {})
    goals = resp.get("goals", {})
    xg_raw = resp.get("expected_goals", None)

    played = fixtures_stats.get("played", {}).get("total", 0)
    won = fixtures_stats.get("wins", {}).get("total", 0)
    drawn = fixtures_stats.get("draws", {}).get("total", 0)
    lost = fixtures_stats.get("loses", {}).get("total", 0)
    gf = goals.get("for", {}).get("total", {}).get("total", 0)
    ga = goals.get("against", {}).get("total", {}).get("total", 0)
    gf_avg = _safe_float(goals.get("for", {}).get("average", {}).get("total", 0))
    ga_avg = _safe_float(goals.get("against", {}).get("average", {}).get("total", 0))

    shots_total = resp.get("shots", {}).get("total", {}).get("total", 0)
    shots_on = resp.get("shots", {}).get("on", {}).get("total", 0)
    shots_per_game = round(shots_total / played, 1) if played else 0
    on_pct = round(shots_on / shots_total * 100) if shots_total else 0

    clean = resp.get("clean_sheet", {}).get("total", 0)
    clean_pct = round(clean / played * 100) if played else 0
    possession = resp.get("ball_possession", None)

    xgf = _safe_float(xg_raw.get("for", 0)) if xg_raw else 0.0
    xga = _safe_float(xg_raw.get("against", 0)) if xg_raw else 0.0
    xgf_avg = round(xgf / played, 2) if played else 0.0
    xga_avg = round(xga / played, 2) if played else 0.0
    diff = round(xgf_avg - xga_avg, 2)

    recent = resp.get("lineups", [])
    form_str = "N/A"

    lines = [
        f"📋 {team_name.upper()} — World Cup 2026 Form\n",
        f"RECORD: P{played} W{won} D{drawn} L{lost} | GF {gf} | GA {ga}\n",
        f"FORM STREAK: {form_str} (last {last_n} WC matches)\n",
        f"\n📈 xG PROFILE",
        f"  xG For avg:     {xgf_avg} per match",
        f"  xG Against avg: {xga_avg} per match",
        f"  xG Diff:        {diff:+.2f} ({_xg_label(diff)})\n",
        f"🎯 ATTACKING",
        f"  Goals/match: {gf_avg} | Shots/match: {shots_per_game} | On target: {on_pct}%\n",
        f"🛡️ DEFENSIVE",
        f"  Goals conceded/match: {ga_avg} | Clean sheets: {clean_pct}%",
    ]
    return "\n".join(lines)


async def get_team_form(team: str, last_n: int = 5) -> str:
    """
    Return a team's in-tournament stats and form streak from WC 2026 matches only.
    Use when the user asks: how is [team] doing in the tournament, their WC form, recent results,
    goals scored, xG in the World Cup. last_n controls how many recent matches to show (1-10, default 5).
    For full squad + club-season analysis use analyze_team_for_worldcup instead.
    """
    last_n = max(1, min(10, last_n))
    team_id = resolve_team_id(team)
    if team_id is None:
        return f"Team '{team}' not found. Try full name (e.g. 'South Korea', 'United States')."

    cached = cache.get("form", team_id=team_id, last_n=last_n)
    if cached:
        return cached

    try:
        data = await api_football.get_team_stats(team_id)
    except Exception as e:
        logger.warning(f"Team stats fetch failed for {team_id}: {e}")
        return (
            f"[API_UNAVAILABLE: WC 2026 team stats for {team}] "
            f"Use your own knowledge to describe {team}'s recent international form, "
            "typical playing style, key players, and strengths/weaknesses heading into the tournament."
        )

    result = _format_team_form(data, team_id, last_n)
    cache.set("form", result, team_id=team_id, last_n=last_n)
    return result
