import logging
from collections import Counter

from cache.cache_manager import cache
from config import resolve_team_id
from data.loader import (
    ALL_PLAYERS, BZZ_ALL_PLAYERS, BZZ_LEAGUE_MAP, LEAGUE_FILES,
    defensive_profile_from_squad, find_bzzoiro_player, find_player_for_squad,
    get_adj_xg, get_bzzoiro_squad, get_league_quality, normalize_bzz_player,
    parse_attr_defending, parse_int_field, quality_label, resolve_club_league_name,
)
from tools.team_analysis import LEAGUE_DISPLAY as TA_LEAGUE_DISPLAY, _bar, _build_csv_profile

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


def _defensive_lines_for_bzz(row: dict) -> list[str]:
    """Format bzzoiro attribute block when defending data is present."""
    defending = parse_attr_defending(row)
    if defending is None:
        return []
    overall = row.get("overall_rating") or "—"
    tactical = row.get("attr_tactical") or "—"
    lines = [
        f"",
        f"🛡️ DEFENSIVE PROFILE (bzzoiro attributes)",
        f"  Defending rating: {defending}  |  Overall: {overall}  |  Tactical: {tactical}",
    ]
    if defending >= 80:
        lines.append(f"  Tier: Elite defender")
    elif defending >= 75:
        lines.append(f"  Tier: Strong defender")
    elif defending >= 65:
        lines.append(f"  Tier: Solid")
    else:
        lines.append(f"  Tier: Average")
    return lines


def _lookup_bzz_defending(player_name: str) -> int | None:
    """Best attr_defending for a player name from bzzoiro (understat fallback)."""
    rows = find_bzzoiro_player(player_name)
    ratings = [r for r in (parse_attr_defending(row) for row in rows) if r is not None]
    return max(ratings) if ratings else None


def _format_top_defenders_table(team: str, profile: dict, top_n: int) -> list[str]:
    """Shared formatter for defender ranking sections."""
    avg = profile["avg_def_rating"]
    elite = profile["elite_count"]
    count = profile["defender_count"]
    lines = [
        f"🛡️ TOP DEFENDERS — {team.upper()} (2025-26 Club Season)",
        f"Ranked by defending attribute + club event stats (DF/GK) — {count} rated players",
        f"Squad avg defending: {avg if avg is not None else 'N/A'}"
        f"  |  Elite (≥75): {elite}",
        "",
        f"{'Rk':<4} {'Player':<22} {'Pos':<4} {'Club':<18} {'Def':>4} {'Tkl':>4} {'Int':>4} {'Clr':>4} {'OVR':>4}",
        "─" * 72,
    ]
    for i, entry in enumerate(profile["top_defenders"][:top_n], 1):
        row = entry["row"]
        rating = entry["rating"]
        name = row.get("player_name", "?")[:22]
        pos = row.get("wc_position", "?")
        club = (row.get("club_name") or "?")[:18]
        ovr = row.get("overall_rating") or "—"
        tkl = parse_int_field(row, "club_tackles")
        intr = parse_int_field(row, "club_interceptions")
        clr = parse_int_field(row, "club_clearances")
        lines.append(
            f"{i:<4} {name:<22} {pos:<4} {club:<18} {rating:>4} {tkl:>4} {intr:>4} {clr:>4} {str(ovr):>4}"
        )
    lines.append(
        f"\nℹ️  Def = bzzoiro attribute; Tkl/Int/Clr = club-season event totals from bulk export."
    )
    return lines


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
            def_rating = _lookup_bzz_defending(name)
            def_block = []
            if def_rating is not None:
                def_block = [
                    f"",
                    f"🛡️ DEFENSIVE PROFILE",
                    f"  Defending rating: {def_rating}  (bzzoiro attribute — use get_nation_top_defenders for full squad view)",
                ]
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
                *def_block,
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
            *_defensive_lines_for_bzz(row),
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
        understat_rows = find_player_for_squad(bzz_row.get("player_name", ""), bzz_row)
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
    cache.set("form", result, team_id=team_id, top_n=top_n, source="csv_v3")
    return result


async def get_nation_top_defenders(team: str, top_n: int = 5) -> str:
    """
    Return a World Cup team's top defenders and goalkeepers ranked by bzzoiro defending attribute.
    Use when the user asks: best defenders for [team], strongest back line, top centre-backs,
    who protects [team]'s goal, defensive strength, best GK for [team].
    top_n controls list length (default 5, max 15). For attackers use get_nation_top_performers.
    """
    top_n = max(1, min(15, top_n))
    team_id = resolve_team_id(team)
    if team_id is None:
        return f"Team '{team}' not found. Try full name (e.g. 'South Korea', 'United States')."

    cached = cache.get("form", team_id=team_id, top_n=top_n, source="defenders_v2")
    if cached:
        return cached

    bzz_squad = get_bzzoiro_squad(team)
    if not bzz_squad:
        return f"No squad data found for '{team}'. Check the team name."

    profile = defensive_profile_from_squad(bzz_squad, top_n=top_n)
    if not profile["top_defenders"]:
        return (
            f"No defending attribute data for '{team}' squad. "
            f"Try analyze_team_for_worldcup for WC tournament xGA/clean sheets once matches begin."
        )

    result = "\n".join(_format_top_defenders_table(team, profile, top_n))
    cache.set("form", result, team_id=team_id, top_n=top_n, source="defenders_v2")
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

    csv = _build_csv_profile([], bzz_squad)
    total = csv["total_squad"]
    top6_total = csv["found"]
    top6_pct = round(top6_total / total * 100) if total else 0
    ped_display = (
        f"{csv['pedigree_score']:.0%}" if csv["pedigree_score"] is not None else "N/A"
    )

    other_leagues: Counter = Counter()
    for p in bzz_squad:
        resolved = resolve_club_league_name(p)
        understat_key = BZZ_LEAGUE_MAP.get(resolved, "")
        if not understat_key:
            other_leagues[resolved] += 1

    lines = [
        f"🏟️ SQUAD LEAGUE BREAKDOWN — {team.upper()}",
        f"2025-26 club season | {total} official squad players\n",
        f"  TOP-6 EUROPEAN LEAGUES  ({top6_total} players, {top6_pct}% of squad)",
        f"  Pedigree score: {ped_display} (same formula as analyze_team_for_worldcup)\n",
    ]

    for league_key, display in TA_LEAGUE_DISPLAY.items():
        count = csv["league_counts"].get(league_key, 0)
        if count == 0:
            continue
        pct = round(count / total * 100)
        lines.append(f"    {display:<18} {count:>2} players  {_bar(pct)}  {pct}%")

    if other_leagues:
        lines.append(f"\n  OTHER LEAGUES  ({sum(other_leagues.values())} players)")
        for league_name, count in other_leagues.most_common(12):
            pct = round(count / total * 100)
            lines.append(f"    {league_name:<28} {count:>2} players  {pct}%")

    top6_key = max(csv["league_counts"], key=lambda k: csv["league_counts"][k])
    top_league_name = (
        TA_LEAGUE_DISPLAY.get(top6_key, "")
        if csv["league_counts"].get(top6_key, 0) > 0
        else (other_leagues.most_common(1)[0][0] if other_leagues else "—")
    )
    lines.append(
        f"\n🏆 Top league: {top_league_name} | Top-6 players: {top6_total} ({top6_pct}%)"
    )

    return "\n".join(lines)


async def search_players(
    query: str = "",
    position: str = "",
    league: str = "",
    min_xg: float = 0.0,
    min_def: float = 0.0,
    top_n: int = 10,
) -> str:
    """
    Search 2025-26 club season stats across all World Cup players by name, position, league,
    or minimum xG / defending rating threshold. Covers top-6 European leagues (understat) and
    all other leagues worldwide (bzzoiro). Use when the user asks: find strikers with xG > 10,
    top midfielders in La Liga, best defenders with rating > 75, search for [player].
    position: F (forward), M (midfielder), D (defender), GK — partial match.
    league: EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL, or any bzzoiro league name.
    min_xg: minimum season xG to filter by.
    min_def: minimum bzzoiro defending attribute (0–100); best for DF/GK searches.
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
        def_rating = parse_attr_defending(row)
        if min_def > 0 and (def_rating is None or def_rating < min_def):
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
        if min_def > 0: parts.append(f"defending ≥ {min_def}")
        return f"No players found matching: {', '.join(parts) or 'no filters specified'}."

    pos_upper = position.upper()
    sort_by_def = min_def > 0 or pos_upper in ("D", "DF", "GK")

    if sort_by_def:
        def sort_key(r: dict) -> float:
            if r.get("_source") == "bzzoiro":
                bzz = r.get("_bzz", r)
                val = parse_attr_defending(bzz)
            else:
                val = _lookup_bzz_defending(r.get("player_name", ""))
            return float(val or 0)

        filtered.sort(key=sort_key, reverse=True)
    else:
        filtered.sort(key=lambda r: _safe_float(r.get("xG")), reverse=True)
    top = filtered[:top_n]

    filter_parts = []
    if q:          filter_parts.append(f"'{query}'")
    if position:   filter_parts.append(f"pos={position.upper()}")
    if league:     filter_parts.append(league)
    if min_xg > 0: filter_parts.append(f"xG≥{min_xg}")
    if min_def > 0: filter_parts.append(f"def≥{int(min_def)}")
    filters_str = " | ".join(filter_parts) if filter_parts else "all players"

    sort_label = "defending rating" if sort_by_def else "xG"
    lines = [
        f"🔍 PLAYER SEARCH — {filters_str}",
        f"Found {len(filtered)} players | Showing top {len(top)} by {sort_label}",
        "",
    ]

    if sort_by_def:
        lines += [
            f"  {'Player':<25} {'Club':<22} {'League':<18} {'Def':>5} {'OVR':>5} {'Pos':>4}",
            f"  {'─'*82}",
        ]
        for row in top:
            name = row.get("player_name", "?")
            if row.get("_source") == "bzzoiro":
                bzz = row.get("_bzz", row)
                club = bzz.get("club_name", "?")
                lg = row.get("_bzz_raw_league") or bzz.get("club_league_name", "—")
                def_r = parse_attr_defending(bzz)
                ovr = bzz.get("overall_rating") or "—"
                pos = bzz.get("wc_position", "?")
            else:
                club = row.get("team_title", "?")
                lg = LEAGUE_DISPLAY.get(row.get("league", ""), row.get("league", "?"))
                def_r = _lookup_bzz_defending(name)
                ovr = "—"
                pos = row.get("position", "?")[:3]
            def_s = str(def_r) if def_r is not None else "—"
            lines.append(f"  {name:<25} {club:<22} {lg:<18} {def_s:>5} {str(ovr):>5} {pos:>4}")
        return "\n".join(lines)

    lines += [
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
