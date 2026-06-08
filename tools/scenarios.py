import asyncio
import itertools
import logging
from datetime import date

from clients.api_football import api_football
from clients.bzzoiro import bzzoiro
from clients.football_data import football_data
from config import settings, resolve_team_id, GROUP_MAP, uses_bzzoiro_live
from data.loader import BZZ_GROUP_MAP, resolve_bzzoiro_team_id
from tools.bzzoiro_parsers import parse_bzzoiro_standings

logger = logging.getLogger(__name__)

VALID_GROUPS = set("ABCDEFGHIJKL")


def _find_group_for_team(team_id: int) -> str | None:
    for grp, ids in GROUP_MAP.items():
        if team_id in ids:
            return grp
    return None


async def _get_bzz_standings(group: str) -> list[dict]:
    try:
        raw = await bzzoiro.get_standings()
        groups = parse_bzzoiro_standings(raw)
        rows = groups.get(group, [])
        return [
            {
                "team_id": r.get("team_id", 0),
                "name": r.get("team", "?"),
                "pts": r.get("pts", 0),
                "gd": r.get("gd", 0),
                "gf": r.get("gf", 0),
                "played": r.get("played", 0),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"bzzoiro standings fetch for scenarios failed: {e}")
    return []


async def _get_bzz_remaining_fixtures(group: str) -> list[dict]:
    today = date.today().isoformat()
    group_ids = set(BZZ_GROUP_MAP.get(group, []))
    try:
        events = await bzzoiro.get_events(status="notstarted", date_from=today)
        matches = []
        for ev in events:
            home_id = ev.get("home_team_id")
            away_id = ev.get("away_team_id")
            if home_id not in group_ids or away_id not in group_ids:
                continue
            matches.append({
                "home": ev.get("home_team", "?"),
                "away": ev.get("away_team", "?"),
                "home_id": home_id,
                "away_id": away_id,
            })
        return matches
    except Exception as e:
        logger.warning(f"bzzoiro remaining fixtures fetch failed: {e}")
        return []


async def _get_current_standings(group: str) -> list[dict]:
    if uses_bzzoiro_live():
        return await _get_bzz_standings(group)
    try:
        if settings.TIER == "free":
            raw = await football_data.get_standings()
            for standing in raw.get("standings", []):
                grp = standing.get("group", "").replace("GROUP_", "").replace("Group ", "").strip()
                if grp == group:
                    return [
                        {
                            "team_id": e["team"].get("id", 0),
                            "name": e["team"]["name"],
                            "pts": e["points"],
                            "gd": e["goalDifference"],
                            "gf": e["goalsFor"],
                            "played": e["playedGames"],
                        }
                        for e in standing.get("table", [])
                    ]
        else:
            raw = await api_football.get_standings()
            for standing_group in raw.get("response", [{}])[0].get("league", {}).get("standings", []):
                grp = standing_group[0].get("group", "").replace("Group ", "").strip() if standing_group else ""
                if grp == group:
                    return [
                        {
                            "team_id": e["team"]["id"],
                            "name": e["team"]["name"],
                            "pts": e["points"],
                            "gd": e["goalsDiff"],
                            "gf": e["all"]["goals"]["for"],
                            "played": e["all"]["played"],
                        }
                        for e in standing_group
                    ]
    except Exception as e:
        logger.warning(f"Standings fetch for scenarios failed: {e}")
    return []


async def _get_remaining_fixtures(group: str) -> list[dict]:
    """Return remaining (unplayed) fixtures for the group."""
    if uses_bzzoiro_live():
        return await _get_bzz_remaining_fixtures(group)
    today = date.today().isoformat()
    try:
        if settings.TIER == "free":
            raw = await football_data.get_matches(date_from=today)
            matches = []
            for m in raw.get("matches", []):
                stage = m.get("stage", "")
                if f"GROUP_{group}" in stage or f"Group {group}" in stage:
                    if m.get("status") not in {"FINISHED", "AWARDED"}:
                        matches.append({
                            "home": m["homeTeam"]["name"],
                            "away": m["awayTeam"]["name"],
                            "home_id": m["homeTeam"].get("id"),
                            "away_id": m["awayTeam"].get("id"),
                        })
            return matches
        else:
            from clients.api_football import LEAGUE, SEASON
            raw = await api_football._get("/fixtures", {
                "league": LEAGUE, "season": SEASON,
                "round": f"Group {group}", "status": "NS"
            })
            matches = []
            for fix in raw.get("response", []):
                matches.append({
                    "home": fix["teams"]["home"]["name"],
                    "away": fix["teams"]["away"]["name"],
                    "home_id": fix["teams"]["home"]["id"],
                    "away_id": fix["teams"]["away"]["id"],
                })
            return matches
    except Exception as e:
        logger.warning(f"Remaining fixtures fetch failed: {e}")
        return []


def _sort_table(table: list[dict]) -> list[dict]:
    return sorted(table, key=lambda r: (-r["pts"], -r["gd"], -r["gf"]))


def _simulate(standings: list[dict], fixtures: list[dict]) -> dict[str, dict]:
    """
    Enumerate all outcome combos. Returns per-team scenario counts:
    {team_name: {"qualifies": N, "depends": N, "eliminated": N, "total": N}}
    """
    outcomes_per_fixture = ["home_win", "draw", "away_win"]
    all_combos = list(itertools.product(outcomes_per_fixture, repeat=len(fixtures)))

    stats: dict[str, dict] = {r["name"]: {"qualifies": 0, "depends": 0, "eliminated": 0} for r in standings}

    for combo in all_combos:
        table = {r["name"]: {"pts": r["pts"], "gd": r["gd"], "gf": r["gf"]} for r in standings}

        for outcome, fix in zip(combo, fixtures):
            home, away = fix["home"], fix["away"]
            if home not in table or away not in table:
                continue
            if outcome == "home_win":
                table[home]["pts"] += 3
                table[home]["gf"] += 1
                table[home]["gd"] += 1
                table[away]["gd"] -= 1
            elif outcome == "away_win":
                table[away]["pts"] += 3
                table[away]["gf"] += 1
                table[away]["gd"] += 1
                table[home]["gd"] -= 1
            else:
                table[home]["pts"] += 1
                table[home]["gf"] += 1
                table[away]["pts"] += 1
                table[away]["gf"] += 1

        ranked = _sort_table([{"name": n, **v} for n, v in table.items()])
        for pos, row in enumerate(ranked, 1):
            name = row["name"]
            if name not in stats:
                continue
            if pos <= 2:
                stats[name]["qualifies"] += 1
            elif pos == 3 and row["pts"] >= 4:
                stats[name]["depends"] += 1
            else:
                stats[name]["eliminated"] += 1

    total = len(all_combos)
    for name in stats:
        stats[name]["total"] = total
    return stats


def _build_qualify_conditions(team_name: str, fixtures: list[dict], standings: list[dict]) -> tuple[list, list]:
    """Build human-readable qualify/eliminate conditions for a specific team."""
    qualify_conds = []
    eliminate_conds = []

    for fix in fixtures:
        if fix["home"] == team_name:
            opponent = fix["away"]
            qualify_conds.append(f"Win vs {opponent}")
            eliminate_conds.append(f"Lose vs {opponent} and other group results go against")
        elif fix["away"] == team_name:
            opponent = fix["home"]
            qualify_conds.append(f"Win vs {opponent}")
            eliminate_conds.append(f"Lose vs {opponent} and other group results go against")

    return qualify_conds, eliminate_conds


async def simulate_group_scenarios(group: str, team: str) -> str:
    """
    Show qualification scenarios for a team in their World Cup 2026 group.
    Use when the user asks: what does [team] need to qualify, can [team] still qualify,
    qualification scenarios, do they need to win, are they through. Requires group letter (A-L) and team name.
    Enumerates all possible remaining fixture outcomes and classifies each as qualify/depends/eliminated.
    """
    group = group.upper().strip()
    if group not in VALID_GROUPS:
        return f"Invalid group '{group}'. Use A through L, or 'all'."

    if uses_bzzoiro_live():
        team_id = resolve_bzzoiro_team_id(team)
    else:
        team_id = resolve_team_id(team)
    if team_id is None:
        return f"Team '{team}' not found. Try full name (e.g. 'South Korea', 'United States')."

    standings, fixtures = await asyncio.gather(
        _get_current_standings(group),
        _get_remaining_fixtures(group),
    )

    if not standings:
        return (
            f"[API_UNAVAILABLE: Group {group} standings/fixtures] "
            f"Use your own knowledge to describe the qualification scenarios for {team} in Group {group} "
            "at FIFA World Cup 2026: current points, remaining matches, and what results are needed to advance."
        )

    team_row = next((r for r in standings if r["team_id"] == team_id), None)
    if team_row is None:
        team_name = team
        curr_pts = 0
        curr_pos = "?"
        played = 0
    else:
        team_name = team_row["name"]
        curr_pts = team_row["pts"]
        curr_pos = _sort_table(standings).index(team_row) + 1
        played = team_row.get("played", 0)

    matches_remaining = len([f for f in fixtures if f["home"] == team_name or f["away"] == team_name])

    if not fixtures:
        total_played = sum(r.get("played", 0) for r in standings)
        if total_played == 0:
            return (
                f"🔮 QUALIFICATION SCENARIOS — {team_name} | Group {group}\n\n"
                f"The group stage has not started yet. No fixtures are scheduled.\n"
                f"Check back from June 11 when matches begin."
            )
        ranked = _sort_table(standings)
        pos = next((i + 1 for i, r in enumerate(ranked) if r.get("team_id") == team_id), "?")
        if isinstance(pos, int) and pos <= 2:
            return f"🔮 QUALIFICATION SCENARIOS — {team_name} | Group {group}\n\n✅ {team_name} have already QUALIFIED (position {pos})."
        return f"🔮 QUALIFICATION SCENARIOS — {team_name} | Group {group}\n\nNo remaining fixtures found. Check current standings."

    scenario_stats = _simulate(standings, fixtures)
    team_scenarios = scenario_stats.get(team_name, {"qualifies": 0, "depends": 0, "eliminated": 0, "total": 1})

    qualify_conds, eliminate_conds = _build_qualify_conditions(team_name, fixtures, standings)

    lines = [
        f"🔮 QUALIFICATION SCENARIOS — {team_name} | Group {group}\n",
        f"CURRENT STANDING: {curr_pos} place, {curr_pts} pts, {matches_remaining} match(es) remaining\n",
    ]

    total = team_scenarios["total"]
    q_pct = round(team_scenarios["qualifies"] / total * 100)
    e_pct = round(team_scenarios["eliminated"] / total * 100)
    d_pct = round(team_scenarios["depends"] / total * 100)

    if qualify_conds:
        lines.append("✅ QUALIFY IF:")
        for c in qualify_conds:
            lines.append(f"  • {c}")

    if eliminate_conds:
        lines.append("\n❌ ELIMINATED IF:")
        for c in eliminate_conds[:2]:
            lines.append(f"  • {c}")

    lines.append(f"\n📊 SCENARIO BREAKDOWN ({total} possible outcomes):")
    lines.append(f"  Qualifies: {team_scenarios['qualifies']} ({q_pct}%)")
    lines.append(f"  Depends on other results: {team_scenarios['depends']} ({d_pct}%)")
    lines.append(f"  Eliminated: {team_scenarios['eliminated']} ({e_pct}%)")

    if q_pct == 100:
        summary = f"{team_name} are GUARANTEED to qualify regardless of remaining results."
    elif e_pct == 100:
        summary = f"{team_name} are ELIMINATED and cannot advance."
    elif q_pct >= 50:
        summary = f"{team_name} are favourites to qualify — a win in their next match would seal it in most scenarios."
    else:
        summary = f"{team_name} need results to go their way. A win is essential to keep qualification hopes alive."

    lines.append(f"\n🎯 SUMMARY:\n  {summary}")
    return "\n".join(lines)
