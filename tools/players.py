import logging

from cache.cache_manager import cache
from clients.api_football import api_football
from clients.football_data import football_data
from config import settings

logger = logging.getLogger(__name__)

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _parse_api_football_scorers(data: dict, top_n: int) -> list[dict]:
    scorers = []
    for entry in data.get("response", [])[:top_n]:
        player = entry.get("player", {})
        stats = entry.get("statistics", [{}])[0]
        scorers.append({
            "name": player.get("name", "Unknown"),
            "team": stats.get("team", {}).get("name", "?"),
            "goals": stats.get("goals", {}).get("total", 0) or 0,
            "assists": stats.get("goals", {}).get("assists", 0) or 0,
        })
    return scorers


def _parse_football_data_scorers(data: dict, top_n: int) -> list[dict]:
    scorers = []
    for entry in data.get("scorers", [])[:top_n]:
        player = entry.get("player", {})
        team = entry.get("team", {})
        scorers.append({
            "name": player.get("name", "Unknown"),
            "team": team.get("name", "?"),
            "goals": entry.get("goals", 0) or 0,
            "assists": entry.get("assists", 0) or 0,
        })
    return scorers


def _format_scorers(scorers: list[dict]) -> str:
    lines = ["⚽ GOLDEN BOOT — FIFA World Cup 2026\n"]
    for i, s in enumerate(scorers, 1):
        medal = MEDALS.get(i, "  ")
        assist_str = f"  {s['assists']} assists" if s["assists"] else ""
        lines.append(f"{medal} {i:<3} {s['name']:<25} ({s['team']})  —  {s['goals']} goals{assist_str}")
    return "\n".join(lines)


async def get_top_scorers(top_n: int = 10) -> str:
    """
    Return the FIFA World Cup 2026 Golden Boot (top scorers) leaderboard.
    Use when the user asks: top scorers, Golden Boot, who has scored most goals,
    leading scorer, goals leaderboard. top_n controls how many players to show (1-20, default 10).
    """
    top_n = max(1, min(20, top_n))

    cached = cache.get("scorers", top_n=top_n)
    if cached:
        return cached

    try:
        if settings.TIER == "free":
            raw = await football_data.get_scorers(limit=top_n)
            scorers = _parse_football_data_scorers(raw, top_n)
        else:
            raw = await api_football.get_top_scorers()
            scorers = _parse_api_football_scorers(raw, top_n)
    except Exception as e:
        logger.warning(f"Scorers fetch failed: {e}")
        return (
            "[API_UNAVAILABLE: Golden Boot leaderboard] "
            f"Use your own knowledge to list the top {top_n} likely Golden Boot contenders "
            "for FIFA World Cup 2026, including goals scored if the tournament has started, "
            "or pre-tournament predictions based on current club form."
        )

    if not scorers:
        return (
            "[API_UNAVAILABLE: Golden Boot leaderboard — no scorer data yet] "
            f"Use your own knowledge to name the top {top_n} expected scorers "
            "at FIFA World Cup 2026 based on recent club and international form."
        )

    result = _format_scorers(scorers)
    cache.set("scorers", result, top_n=top_n)
    return result
