import logging

from cache.cache_manager import cache
from clients.api_football import api_football
from config import resolve_team_id

logger = logging.getLogger(__name__)

WC_COMPETITIONS = {"FIFA World Cup", "World Cup"}


def _is_wc(fixture: dict) -> bool:
    league_name = fixture.get("league", {}).get("name", "")
    return any(wc in league_name for wc in WC_COMPETITIONS)


def _format_h2h(team_a: str, team_b: str, data: dict, last_n: int) -> str:
    fixtures = data.get("response", [])
    if not fixtures:
        return f"No head-to-head data found for {team_a} vs {team_b}."

    a_wins = 0
    b_wins = 0
    draws = 0
    a_goals = 0
    b_goals = 0
    result_lines = []

    for fix in fixtures[:last_n]:
        home_team = fix.get("teams", {}).get("home", {}).get("name", "?")
        away_team = fix.get("teams", {}).get("away", {}).get("name", "?")
        home_goals = fix.get("goals", {}).get("home") or 0
        away_goals = fix.get("goals", {}).get("away") or 0
        date_str = fix.get("fixture", {}).get("date", "")[:10]
        competition = fix.get("league", {}).get("name", "")
        round_name = fix.get("league", {}).get("round", "")
        wc_flag = "🏆 " if _is_wc(fix) else "   "

        # Determine who is team_a vs team_b in this fixture
        a_is_home = team_a.lower() in home_team.lower()
        if a_is_home:
            a_g, b_g = home_goals, away_goals
        else:
            a_g, b_g = away_goals, home_goals

        a_goals += a_g
        b_goals += b_g

        if a_g > b_g:
            a_wins += 1
        elif b_g > a_g:
            b_wins += 1
        else:
            draws += 1

        result_lines.append(
            f"{wc_flag}{date_str} | {home_team} {home_goals}–{away_goals} {away_team} ({competition}, {round_name})"
        )

    total = a_wins + b_wins + draws
    avg_goals = round((a_goals + b_goals) / total, 1) if total else 0

    lines = [
        f"🤝 HEAD TO HEAD: {team_a} vs {team_b}",
        f"Last {last_n} meetings\n",
        "RECORD",
        f"  {team_a}: {a_wins} wins",
        f"  Draws:    {draws}",
        f"  {team_b}: {b_wins} wins\n",
        "GOALS",
        f"  {team_a} {a_goals} — {b_goals} {team_b} ({avg_goals} per game avg)\n",
        "RESULTS",
    ] + result_lines

    return "\n".join(lines)


async def get_h2h(team_a: str, team_b: str, last_n: int = 10) -> str:
    """
    Return historical head-to-head record between two national teams (all competitions).
    Use when the user asks: H2H, head to head, record between [team] and [team], who has won more,
    history between these teams, past meetings. last_n controls number of matches (1-15, default 10).
    World Cup meetings are flagged with a trophy icon.
    """
    last_n = max(1, min(15, last_n))
    id_a = resolve_team_id(team_a)
    id_b = resolve_team_id(team_b)
    if id_a is None:
        return f"Team '{team_a}' not found. Try full name (e.g. 'South Korea', 'United States')."
    if id_b is None:
        return f"Team '{team_b}' not found. Try full name (e.g. 'South Korea', 'United States')."

    cached = cache.get("h2h", team_a_id=id_a, team_b_id=id_b, last_n=last_n)
    if cached:
        return cached

    try:
        data = await api_football.get_h2h(id_a, id_b, last=last_n)
    except Exception as e:
        logger.warning(f"H2H fetch failed {id_a} vs {id_b}: {e}")
        return (
            f"[API_UNAVAILABLE: H2H data for {team_a} vs {team_b}] "
            f"Use your own knowledge to provide head-to-head history between {team_a} and {team_b}: "
            "wins/draws/losses, aggregate goals, last meeting result, and any notable World Cup encounters."
        )

    result = _format_h2h(team_a, team_b, data, last_n)
    cache.set("h2h", result, team_a_id=id_a, team_b_id=id_b, last_n=last_n)
    return result
