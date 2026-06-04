import logging
from collections import Counter

from cache.cache_manager import cache
from config import resolve_team_id
from data.loader import (
    ALL_PLAYERS, BZZ_ALL_PLAYERS, BZZ_LEAGUE_MAP, LEAGUE_FILES,
    find_bzzoiro_player, find_player, get_adj_xg, get_bzzoiro_squad,
    get_league_quality, normalize_bzz_player, quality_label,
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

TOP6_BZZ_LEAGUES = set(BZZ_LEAGUE_MAP.keys())


def _safe_float(val) -> float:
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return 0.0


def _bar(pct: float, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


async def get_player_club_stats(player_name: str) -> str:
    """
    Return an individual player's 2025-26 club season stats (goals, xG, npxG, xA, xGChain, xGBuildup).
    Use when the user asks about a specific player: how was [player] doing this season, [player]'s club form,
    [player] stats, [player] xG. Data covers EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL (understat)
    plus all other World Cup squad players via bzzoiro. For a whole national team use get_nation_top_performers.
    """
    rows = find_player(player_name)
    if rows:
        rows = sorted(rows, key=lambda r: int(r.get("games", 0) or 0), reverse=True)
        sections = []
        for row in rows:
            name   = row["player_name"]
            club   = row.get("team_title", "?")
            league = LEAGUE_DISPLAY.get(row.get("league", ""), row.get("league", "?"))
            pos    = row.get("position", "?")
            games  = row.get("games", "0")
            mins   = row.get("time", "0")
            xg     = _safe_float(row.get("xG"))
            npxg   = _safe_float(row.get("npxG"))
            xa     = _safe_float(row.get("xA"))
            xgchain   = _safe_float(row.get("xGChain"))
            xgbuildup = _safe_float(row.get("xGBuildup"))
            goals  = row.get("goals", "0")
            npg    = row.get("npg", "0")
            assists = row.get("assists", "0")
            shots  = row.get("shots", "0")
            kp     = row.get("key_passes", "0")
            lq  = get_league_quality(row.get("league", ""))
            adj = round(npxg * lq, 2)
            sections.append("\n".join([
                f"⚽ CLUB FORM 2025-26: {name}",
                f"{club} | {league} {quality_label(lq)} | {pos}",
                f"",
                f"GOALS & EXPECTED",
                f"  Goals:     {goals:<6} | xG: {xg:<7} | Adj. xG: {adj}  (× {lq:.2f} quality)",
                f"  npGoals:   {npg:<6} | npxG: {npxg:<5} | Adj. npxG: {adj}",
                f"  Assists:   {assists:<6} (xA: {xa})",
                f"",
                f"ADVANCED xG",
                f"  xGChain:   {xgchain:<8} (build-up involvement)",
                f"  xGBuildup: {xgbuildup:<8} (non-shot/key-pass involvement)",
                f"  Shots:     {shots} | Key passes: {kp}",
                f"",
                f"📅 {games} games | {mins} mins played",
            ]))
        return "\n\n─────────────────────────────\n\n".join(sections)

    # Understat miss → try bzzoiro (covers non-top-6 league players)
    bzz_rows = find_bzzoiro_player(player_name)
    if not bzz_rows:
        return f"Player '{player_name}' not found in 2025-26 club data. Try their full name."

    bzz_rows = sorted(bzz_rows, key=lambda r: int(r.get("club_matches") or 0), reverse=True)
    sections = []
    for row in bzz_rows:
        name    = row.get("player_name", "?")
        club    = row.get("club_name", "?")
        league  = row.get("club_league_name", "?")
        pos     = row.get("wc_position", "?")
        matches = row.get("club_matches") or "0"
        mins    = row.get("club_minutes") or "0"
        goals   = row.get("club_goals") or "0"
        assists = row.get("club_assists") or "0"
        xg      = _safe_float(row.get("club_xg"))
        xa      = _safe_float(row.get("club_xa"))
        shots   = row.get("club_shots") or "0"
        kp      = row.get("club_key_passes") or "0"
        rating  = row.get("club_avg_match_rating") or "—"
        team    = row.get("national_team_name", "?")
        lq  = get_league_quality(league)
        adj = round(xg * lq, 2)
        sections.append("\n".join([
            f"⚽ CLUB FORM 2025-26: {name}  ({team})",
            f"{club} | {league} {quality_label(lq)} | {pos}",
            f"",
            f"GOALS & STATS",
            f"  Goals:     {goals:<6} | xG: {xg:<7} | Adj. xG: {adj}  (× {lq:.2f} quality)",
            f"  Assists:   {assists:<6} (xA: {xa})",
            f"  Shots:     {shots} | Key passes: {kp}",
            f"  Avg match rating: {rating}",
            f"",
            f"📅 {matches} games | {mins} mins played",
            f"ℹ️  Adj. xG discounts raw xG by league quality — not all leagues are equal",
        ]))
    return "\n\n─────────────────────────────\n\n".join(sections)


async def get_nation_top_performers(team: str, top_n: int = 5) -> str:
    """
    Return a World Cup team's top performers ranked by xG from their 2025-26 club season.
    Covers ALL 48 nations — uses understat for top-6 European league players (advanced xG stats)
    and bzzoiro for players in other leagues worldwide. Use when the user asks: who are [team]'s
    best players, top performers, dangerous attackers, who scores most for [team] at club level.
    top_n controls list length (default 5). For full analysis use analyze_team_for_worldcup.
    """
    top_n = max(1, min(20, top_n))
    team_id = resolve_team_id(team)
    if team_id is None:
        return f"Team '{team}' not found. Try full name (e.g. 'South Korea', 'United States')."

    cached = cache.get("form", team_id=team_id, top_n=top_n, source="csv_v2")
    if cached:
        return cached

    bzz_squad = get_bzzoiro_squad(team)
    if not bzz_squad:
        return f"No squad data found for '{team}'. Check the team name."

    matched: list[dict] = []
    understat_count = 0
    bzzoiro_count = 0

    for bzz_row in bzz_squad:
        understat_rows = find_player(bzz_row.get("player_name", ""))
        if understat_rows:
            best = max(understat_rows, key=lambda r: _safe_float(r.get("npxG")))
            matched.append(best)
            understat_count += 1
        else:
            matched.append(normalize_bzz_player(bzz_row))
            bzzoiro_count += 1

    if not matched:
        return f"No club stats found for {team}'s squad."

    # Rank by quality-adjusted xG so 20 xG in Saudi League ≠ 20 xG in Premier League
    matched.sort(key=get_adj_xg, reverse=True)
    top = matched[:top_n]

    lines = [
        f"🌍 TOP PERFORMERS — {team.upper()} (2025-26 Club Season)",
        f"Squad: {len(matched)} players | {understat_count} understat (top-6) · {bzzoiro_count} bzzoiro (other leagues)",
        f"Ranked by Adj. xG = raw xG × league quality factor (see ★ rating)",
        "",
        f"{'Rk':<4} {'Player':<24} {'Club / League':<28} {'Qual':>6} {'Raw xG':>7} {'Adj xG':>7} {'Goals':>6} {'xA':>5}",
        "─" * 86,
    ]

    for i, row in enumerate(top, 1):
        name = row.get("player_name", "?")
        if row.get("_source") == "bzzoiro":
            bzz    = row.get("_bzz", {})
            club   = bzz.get("club_name", "?")
            league = bzz.get("club_league_name", "?")
            lq     = row.get("_league_quality", 0.55)
        else:
            club   = row.get("team_title", "?")
            league = LEAGUE_DISPLAY.get(row.get("league", ""), row.get("league", "") or "—")
            lq     = get_league_quality(row.get("league", ""))

        raw_xg = _safe_float(row.get("npxG"))
        adj    = get_adj_xg(row)
        goals  = row.get("goals", "0")
        xa     = _safe_float(row.get("xA"))
        stars  = ("★★★★★" if lq >= 0.98 else "★★★★" if lq >= 0.88
                  else "★★★" if lq >= 0.75 else "★★" if lq >= 0.63 else "★")
        club_lg = f"{club} ({league})"
        lines.append(
            f"{i:<4} {name:<24} {club_lg:<28} {stars:>6} {raw_xg:>7} {adj:>7} {goals:>6} {xa:>5}"
        )

    if bzzoiro_count:
        lines.append(f"\nℹ️  Adj. xG = raw xG × quality factor. 20 xG in ★ leagues ≠ 20 xG in ★★★★★.")

    result = "\n".join(lines)
    cache.set("form", result, team_id=team_id, top_n=top_n, source="csv_v2")
    return result


async def get_squad_league_breakdown(team: str) -> str:
    """
    Show which leagues a World Cup team's squad plays in — a full global squad pedigree signal.
    Now covers all 48 nations with complete league coverage via bzzoiro. Use when the user asks:
    which leagues do [team]'s players play in, squad pedigree, where do they play club football,
    league breakdown, how many play in the Premier League / top leagues.
    For a full combined analysis use analyze_team_for_worldcup instead.
    """
    team_id = resolve_team_id(team)
    if team_id is None:
        return f"Team '{team}' not found. Try full name (e.g. 'South Korea', 'United States')."

    bzz_squad = get_bzzoiro_squad(team)
    if not bzz_squad:
        return f"No squad data found for '{team}'."

    top6_counts: dict[str, int] = {k: 0 for k in LEAGUE_FILES}
    other_leagues: Counter = Counter()
    total = len(bzz_squad)

    for p in bzz_squad:
        raw_league = p.get("club_league_name", "") or ""
        understat_key = BZZ_LEAGUE_MAP.get(raw_league, "")
        if understat_key:
            top6_counts[understat_key] += 1
        else:
            other_leagues[raw_league or "Unknown"] += 1

    top6_total = sum(top6_counts.values())
    top6_pct   = round(top6_total / total * 100) if total else 0

    lines = [
        f"🏟️ SQUAD LEAGUE BREAKDOWN — {team.upper()}",
        f"2025-26 season | {total} players total\n",
        f"  TOP-6 EUROPEAN LEAGUES  ({top6_total} players, {top6_pct}%)",
    ]

    for league_key, display in LEAGUE_DISPLAY.items():
        count = top6_counts.get(league_key, 0)
        if count == 0:
            continue
        pct = round(count / total * 100)
        lines.append(f"    {display:<18} {count:>2} players  {_bar(pct)}  {pct}%")

    if other_leagues:
        lines.append(f"\n  OTHER LEAGUES  ({sum(other_leagues.values())} players)")
        for league_name, count in other_leagues.most_common(10):
            pct = round(count / total * 100)
            lines.append(f"    {league_name:<28} {count:>2} players  {pct}%")

    top_league_name = (
        LEAGUE_DISPLAY.get(max(top6_counts, key=lambda k: top6_counts[k]), "")
        if top6_total else (other_leagues.most_common(1)[0][0] if other_leagues else "—")
    )
    lines.append(f"\n🏆 Top league: {top_league_name} | Top-6 coverage: {top6_pct}%")

    return "\n".join(lines)


async def search_players(
    query: str = "",
    position: str = "",
    league: str = "",
    min_xg: float = 0.0,
    top_n: int = 10,
) -> str:
    """
    Search 2025-26 club season stats across all World Cup players by name, position, league,
    or minimum xG threshold. Covers top-6 European leagues (understat, with npxG/xGChain) and
    all other leagues worldwide (bzzoiro). Use when the user asks: find strikers with xG > 10,
    top midfielders in La Liga, search for [player], players with most assists, show EPL forwards,
    who has highest xG, best Saudi League players.
    position: F (forward), M (midfielder), D (defender), GK — partial match.
    league: EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL, or any bzzoiro league name.
    min_xg: minimum season xG to filter by.
    """
    top_n = max(1, min(50, top_n))
    q = query.lower().strip()
    league_lower = league.lower().strip()

    # --- understat pool (top-6 leagues) ---
    filtered: list[dict] = []
    for row in ALL_PLAYERS:
        if q and q not in row.get("player_name", "").lower() and q not in row.get("team_title", "").lower():
            continue
        if position and position.upper() not in row.get("position", "").upper():
            continue
        if league_lower:
            row_league = LEAGUE_DISPLAY.get(row.get("league", ""), row.get("league", "")).lower()
            if league_lower not in row_league and league_lower not in row.get("league", "").lower():
                continue
        if min_xg > 0 and _safe_float(row.get("xG")) < min_xg:
            continue
        filtered.append(row)

    # --- bzzoiro pool (non-top-6 leagues only, avoid duplicating understat) ---
    understat_names = {row.get("player_name", "").lower() for row in filtered}
    for row in BZZ_ALL_PLAYERS:
        raw_league = row.get("club_league_name", "") or ""
        if raw_league in TOP6_BZZ_LEAGUES:
            continue  # already covered by understat
        if q and q not in row.get("player_name", "").lower() and q not in row.get("club_name", "").lower():
            continue
        pos_mapped = {"FW": "F", "MF": "M", "DF": "D", "GK": "GK"}.get(row.get("wc_position", ""), "")
        if position and position.upper() not in pos_mapped.upper():
            continue
        if league_lower and league_lower not in raw_league.lower():
            continue
        xg = _safe_float(row.get("club_xg"))
        if min_xg > 0 and xg < min_xg:
            continue
        if row.get("player_name", "").lower() in understat_names:
            continue  # understat row already included
        norm = normalize_bzz_player(row)
        norm["_bzz_raw_league"] = raw_league
        filtered.append(norm)

    if not filtered:
        parts = []
        if q:          parts.append(f"name/club containing '{query}'")
        if position:   parts.append(f"position '{position}'")
        if league:     parts.append(f"league '{league}'")
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
        f"  {'Player':<25} {'Club':<22} {'League':<20} {'xG':>6} {'Goals':>6} {'npxG':>6} {'xA':>5}",
        f"  {'─'*88}",
    ]

    for row in top:
        name   = row.get("player_name", "?")
        club   = row.get("team_title", "?")
        lg     = (LEAGUE_DISPLAY.get(row.get("league", ""), row.get("league", "?"))
                  if row.get("_source") != "bzzoiro"
                  else row.get("_bzz_raw_league") or "—")
        xg     = _safe_float(row.get("xG"))
        goals  = row.get("goals", "0")
        npxg   = _safe_float(row.get("npxG"))
        xa     = _safe_float(row.get("xA"))
        lines.append(f"  {name:<25} {club:<22} {lg:<20} {xg:>6} {goals:>6} {npxg:>6} {xa:>5}")

    return "\n".join(lines)
