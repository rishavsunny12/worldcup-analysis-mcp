import logging

from cache.cache_manager import cache
from clients.football_data import football_data
from config import resolve_team_id
from data.loader import ALL_PLAYERS, LEAGUE_FILES, find_player

logger = logging.getLogger(__name__)

LEAGUE_DISPLAY = {
    "EPL":        "Premier League",
    "La Liga":    "La Liga",
    "Bundesliga": "Bundesliga",
    "Serie A":    "Serie A",
    "Ligue 1":    "Ligue 1",
    "RFPL":       "RFPL",
}


def _safe_float(val) -> float:
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return 0.0


def _bar(pct: float, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


async def _fetch_squad_names(team_id: int) -> list[str]:
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


async def get_player_club_stats(player_name: str) -> str:
    """
    Return an individual player's 2025-26 club season stats (goals, xG, npxG, xA, xGChain, xGBuildup).
    Use when the user asks about a specific player: how was [player] doing this season, [player]'s club form,
    [player] stats, [player] xG. Data covers EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL.
    For a whole national team's top performers use get_nation_top_performers instead.
    """
    rows = find_player(player_name)
    if not rows:
        return f"Player '{player_name}' not found in 2025-26 club data. Try their full name."

    rows = sorted(rows, key=lambda r: int(r.get("games", 0) or 0), reverse=True)
    sections = []

    for row in rows:
        name = row["player_name"]
        club = row.get("team_title", "?")
        league = LEAGUE_DISPLAY.get(row.get("league", ""), row.get("league", "?"))
        pos = row.get("position", "?")
        games = row.get("games", "0")
        mins = row.get("time", "0")

        xg = _safe_float(row.get("xG"))
        npxg = _safe_float(row.get("npxG"))
        xa = _safe_float(row.get("xA"))
        xgchain = _safe_float(row.get("xGChain"))
        xgbuildup = _safe_float(row.get("xGBuildup"))
        goals = row.get("goals", "0")
        npg = row.get("npg", "0")
        assists = row.get("assists", "0")
        shots = row.get("shots", "0")
        key_passes = row.get("key_passes", "0")

        sections.append("\n".join([
            f"⚽ CLUB FORM 2025-26: {name}",
            f"{club} | {league} | {pos}",
            f"",
            f"GOALS & EXPECTED",
            f"  Goals:     {goals:<6} (xG: {xg})",
            f"  npGoals:   {npg:<6} (npxG: {npxg})",
            f"  Assists:   {assists:<6} (xA: {xa})",
            f"",
            f"ADVANCED xG",
            f"  xGChain:   {xgchain:<8} (build-up involvement)",
            f"  xGBuildup: {xgbuildup:<8} (non-shot/key-pass involvement)",
            f"  Shots:     {shots} | Key passes: {key_passes}",
            f"",
            f"📅 {games} games | {mins} mins played",
        ]))

    return "\n\n─────────────────────────────\n\n".join(sections)


async def get_nation_top_performers(team: str, top_n: int = 5) -> str:
    """
    Return a World Cup team's top performers ranked by npxG from their 2025-26 club season.
    Use when the user asks: who are [team]'s best players, top performers, dangerous attackers,
    best forwards, who scores most for [team] at club level. top_n controls list length (default 5).
    For a full combined analysis with pedigree and prediction use analyze_team_for_worldcup instead.
    """
    top_n = max(1, min(20, top_n))
    team_id = resolve_team_id(team)
    if team_id is None:
        return f"Team '{team}' not found. Try full name (e.g. 'South Korea', 'United States')."

    cached = cache.get("form", team_id=team_id, top_n=top_n, source="csv")
    if cached:
        return cached

    squad_names = await _fetch_squad_names(team_id)
    if not squad_names:
        return (
            f"[API_UNAVAILABLE: squad roster for {team}] "
            f"Use your own knowledge to list {team}'s top {top_n} performers heading into "
            "FIFA World Cup 2026, ranked by attacking threat: goals, xG, assists, and key stats "
            "from their 2025-26 club season."
        )

    matched = []
    not_found = 0
    for name in squad_names:
        rows = find_player(name)
        if rows:
            best = max(rows, key=lambda r: _safe_float(r.get("npxG")))
            matched.append(best)
        else:
            not_found += 1

    if not matched:
        return f"No players from {team}'s squad found in top 6 European league data."

    matched.sort(key=lambda r: _safe_float(r.get("npxG")), reverse=True)
    top = matched[:top_n]

    team_display = top[0].get("team_title", team) if top else team
    lines = [
        f"🌍 TOP PERFORMERS IN EUROPE — {team.upper()} (2025-26 Club Season)",
        f"Based on {len(matched)} squad players found across top 6 European leagues\n",
        f"{'Rank':<5} {'Player':<25} {'Club (League)':<28} {'npxG':>5} {'xG':>6} {'Goals':>6} {'xA':>6}",
        "─" * 80,
    ]

    for i, row in enumerate(top, 1):
        name = row["player_name"]
        club = row.get("team_title", "?")
        league = LEAGUE_DISPLAY.get(row.get("league", ""), "?")
        npxg = _safe_float(row.get("npxG"))
        xg = _safe_float(row.get("xG"))
        goals = row.get("goals", "0")
        xa = _safe_float(row.get("xA"))
        lines.append(
            f"{i:<5} {name:<25} {club+' ('+league+')':<28} {npxg:>5} {xg:>6} {goals:>6} {xa:>6}"
        )

    if not_found:
        lines.append(f"\n⚠️  {not_found} squad players not found in top 6 European league data")

    result = "\n".join(lines)
    cache.set("form", result, team_id=team_id, top_n=top_n, source="csv")
    return result


async def get_squad_league_breakdown(team: str) -> str:
    """
    Show which European leagues a World Cup team's squad plays in — a squad pedigree signal.
    Use when the user asks: which leagues do [team]'s players play in, squad pedigree, where do they play
    their club football, league breakdown, how many play in the Premier League / top leagues.
    For a full combined analysis use analyze_team_for_worldcup instead.
    """
    team_id = resolve_team_id(team)
    if team_id is None:
        return f"Team '{team}' not found. Try full name (e.g. 'South Korea', 'United States')."

    squad_names = await _fetch_squad_names(team_id)
    if not squad_names:
        return (
            f"[API_UNAVAILABLE: squad roster for {team}] "
            f"Use your own knowledge to describe which European leagues {team}'s players "
            "compete in for the 2025-26 club season, and what that says about the squad's pedigree."
        )

    league_counts: dict[str, int] = {k: 0 for k in LEAGUE_FILES}
    not_found = 0

    for name in squad_names:
        rows = find_player(name)
        if rows:
            league = rows[0].get("league", "")
            if league in league_counts:
                league_counts[league] += 1
        else:
            not_found += 1

    total_found = sum(league_counts.values())
    total_squad = len(squad_names)
    coverage_pct = round(total_found / total_squad * 100) if total_squad else 0
    top_league = max(league_counts, key=lambda k: league_counts[k]) if total_found else "N/A"

    lines = [
        f"🏟️ SQUAD LEAGUE BREAKDOWN — {team.upper()}",
        f"2025-26 season | {total_found} of {total_squad} players in top 6 European leagues\n",
    ]

    for league_key, display in LEAGUE_DISPLAY.items():
        count = league_counts.get(league_key, 0)
        pct = round(count / total_squad * 100) if total_squad else 0
        lines.append(f"  {display:<18} {count:>2} players  {_bar(pct)}  {pct}%")

    lines.append(f"  {'Other/Unknown':<18} {not_found:>2} players")
    lines.append(f"\n🏆 Top league: {LEAGUE_DISPLAY.get(top_league, top_league)} | Top-6 coverage: {coverage_pct}%")

    return "\n".join(lines)


async def search_players(
    query: str = "",
    position: str = "",
    league: str = "",
    min_xg: float = 0.0,
    top_n: int = 10,
) -> str:
    """
    Search 2025-26 club season stats across top 6 European leagues by player name,
    position, league, or minimum xG threshold. Pure in-memory — no API call needed.
    Use when the user asks: find strikers with xG > 10, top midfielders in La Liga,
    search for [player], players with most assists, show me EPL forwards, who has highest xG.
    position: F (forward), M (midfielder), D (defender), GK (goalkeeper) — partial match.
    league: EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL — exact match.
    min_xg: minimum season xG value to filter by.
    """
    top_n = max(1, min(50, top_n))
    q = query.lower().strip()

    filtered = []
    for row in ALL_PLAYERS:
        if q and q not in row.get("player_name", "").lower() and q not in row.get("team_title", "").lower():
            continue
        if position and position.upper() not in row.get("position", "").upper():
            continue
        if league and league.lower() != row.get("league", "").lower():
            continue
        if min_xg > 0 and _safe_float(row.get("xG")) < min_xg:
            continue
        filtered.append(row)

    if not filtered:
        parts = []
        if q:        parts.append(f"name/club containing '{query}'")
        if position: parts.append(f"position '{position}'")
        if league:   parts.append(f"league '{league}'")
        if min_xg > 0: parts.append(f"xG ≥ {min_xg}")
        return f"No players found matching: {', '.join(parts) or 'no filters specified'}."

    filtered.sort(key=lambda r: _safe_float(r.get("xG")), reverse=True)
    top = filtered[:top_n]

    filter_parts = []
    if q:          filter_parts.append(f"'{query}'")
    if position:   filter_parts.append(f"pos={position.upper()}")
    if league:     filter_parts.append(league)
    if min_xg > 0: filter_parts.append(f"xG≥{min_xg}")
    filters_str = " | ".join(filter_parts) if filter_parts else "all players"

    lines = [
        f"🔍 PLAYER SEARCH — {filters_str}",
        f"Found {len(filtered)} players | Showing top {len(top)} by xG",
        "",
        f"  {'Player':<25} {'Club':<22} {'League':<14} {'xG':>6} {'Goals':>6} {'npxG':>6} {'xA':>5}",
        f"  {'─'*82}",
    ]

    for row in top:
        name = row.get("player_name", "?")
        club = row.get("team_title", "?")
        lg   = LEAGUE_DISPLAY.get(row.get("league", ""), "?")
        xg   = _safe_float(row.get("xG"))
        goals = row.get("goals", "0")
        npxg = _safe_float(row.get("npxG"))
        xa   = _safe_float(row.get("xA"))
        lines.append(f"  {name:<25} {club:<22} {lg:<14} {xg:>6} {goals:>6} {npxg:>6} {xa:>5}")

    return "\n".join(lines)
