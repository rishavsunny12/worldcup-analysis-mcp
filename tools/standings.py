import asyncio
import logging

from cache.cache_manager import cache
from clients.api_football import api_football
from clients.bzzoiro import bzzoiro
from clients.football_data import football_data
from config import GROUP_MAP, TEAM_ID_MAP, settings, uses_bzzoiro_live
from data.loader import BZZ_GROUP_MAP, BZZ_TEAMS_BY_ID
from tools.bzzoiro_parsers import parse_bzzoiro_standings

logger = logging.getLogger(__name__)

# Reverse map: team_id → display name (first/official name wins over aliases)
_ID_TO_NAME: dict[int, str] = {}
for _alias, _tid in TEAM_ID_MAP.items():
    if _tid not in _ID_TO_NAME:
        _ID_TO_NAME[_tid] = _alias.title()

VALID_GROUPS = set("ABCDEFGHIJKL")


def _qualification_marker(pos: int, pts: int, played: int) -> str:
    if pos <= 2:
        return "✅"
    if pos == 3 and pts >= 4:
        return "🟡"
    if pos == 4 and played >= 3:
        return "❌"
    return "  "


def _format_table(group_label: str, rows: list[dict]) -> str:
    header = f"📊 GROUP {group_label} STANDINGS\n\n"
    header += f"{'Pos':<4} {'Team':<20} {'P':>2} {'W':>2} {'D':>2} {'L':>2} {'GF':>3} {'GA':>3} {'GD':>4} {'Pts':>4}\n"
    header += "─" * 58 + "\n"
    lines = [header]
    for i, row in enumerate(rows, 1):
        marker = _qualification_marker(i, row.get("pts", 0), row.get("played", 0))
        name = row.get("team", "")[:19]
        line = (
            f"{i:<4} {name:<20} {row.get('played',0):>2} {row.get('won',0):>2} "
            f"{row.get('draw',0):>2} {row.get('lost',0):>2} {row.get('gf',0):>3} "
            f"{row.get('ga',0):>3} {row.get('gd',0):>+4} {row.get('pts',0):>4}  {marker}"
        )
        lines.append(line)
    return "\n".join(lines)


def _parse_api_football_standings(data: dict) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    league = data.get("response", [{}])[0].get("league", {})
    for standing_group in league.get("standings", []):
        for entry in standing_group:
            grp = entry.get("group", "").replace("Group ", "").strip()
            if not grp:
                continue
            row = {
                "team": entry["team"]["name"],
                "played": entry["all"]["played"],
                "won": entry["all"]["win"],
                "draw": entry["all"]["draw"],
                "lost": entry["all"]["lose"],
                "gf": entry["all"]["goals"]["for"],
                "ga": entry["all"]["goals"]["against"],
                "gd": entry["goalsDiff"],
                "pts": entry["points"],
            }
            groups.setdefault(grp, []).append(row)
    return groups


def _parse_football_data_standings(data: dict) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for standing in data.get("standings", []):
        grp = standing.get("group", "").replace("GROUP_", "").replace("Group ", "").strip()
        if not grp:
            continue
        rows = []
        for entry in standing.get("table", []):
            rows.append({
                "team": entry["team"]["name"],
                "played": entry["playedGames"],
                "won": entry["won"],
                "draw": entry["draw"],
                "lost": entry["lost"],
                "gf": entry["goalsFor"],
                "ga": entry["goalsAgainst"],
                "gd": entry["goalDifference"],
                "pts": entry["points"],
            })
        groups[grp] = rows
    return groups


def _fallback_group_rows(group: str) -> list[dict]:
    """Pre-tournament / missing API group — zero table from bzzoiro CSV group map."""
    rows = []
    for tid in BZZ_GROUP_MAP.get(group, []):
        team = BZZ_TEAMS_BY_ID.get(tid, {})
        rows.append({
            "team": team.get("team_name") or team.get("short_name") or "?",
            "team_id": tid,
            "played": 0,
            "won": 0,
            "draw": 0,
            "lost": 0,
            "gf": 0,
            "ga": 0,
            "gd": 0,
            "pts": 0,
            "form": "",
        })
    return rows


async def get_group_standings(group: str = "all") -> str:
    """
    Return current FIFA World Cup 2026 group standings with qualification markers.
    Use when the user asks: standings, group table, group [X] standings, who is top of group,
    points table, show all groups. Pass a group letter A-L or 'all' for every group.
    Shows W/D/L/GF/GA/GD/Pts with ✅ qualified, 🟡 possible third-place, ❌ eliminated markers.
    """
    group = group.upper().strip()
    if group != "ALL" and group not in VALID_GROUPS:
        return f"Invalid group '{group}'. Use A through L, or 'all'."

    cached = cache.get("standings", group=group)
    if cached:
        return cached

    try:
        if uses_bzzoiro_live():
            raw = await bzzoiro.get_standings()
            groups = parse_bzzoiro_standings(raw)
        elif settings.TIER == "free":
            raw = await football_data.get_standings()
            groups = _parse_football_data_standings(raw)
        else:
            raw = await api_football.get_standings()
            groups = _parse_api_football_standings(raw)
    except Exception as e:
        logger.warning(f"Standings fetch failed: {e}")
        target = f"Group {group}" if group != "ALL" else "all groups"
        return (
            f"[API_UNAVAILABLE: standings for {target}] "
            f"Use your own knowledge to provide the current FIFA World Cup 2026 standings for {target}, "
            "including played/won/drawn/lost/GF/GA/GD/points for each team."
        )

    if not groups:
        target = f"Group {group}" if group != "ALL" else "all groups"
        return (
            f"[API_UNAVAILABLE: standings for {target} — no data returned] "
            f"Use your own knowledge to provide the FIFA World Cup 2026 standings for {target}."
        )

    if group == "ALL":
        sections = []
        for g in sorted(groups.keys()):
            sections.append(_format_table(g, groups[g]))
        result = "\n\n".join(sections)
    else:
        if group not in groups:
            fallback = _fallback_group_rows(group)
            if fallback:
                groups[group] = fallback
            else:
                return f"No standings found for Group {group}."
        result = _format_table(group, groups[group])

    cache.set("standings", result, group=group)
    return result


async def get_group_overview(group: str) -> str:
    """
    Full preview of all 4 teams in a World Cup 2026 group: current standings, squad pedigree,
    top attacker, and projected goals per game — all in one shot.
    Use when the user asks: tell me about Group [X], Group [X] preview, Group [X] analysis,
    who's in Group [X], how does Group [X] look, strongest group, Group [X] breakdown.
    Returns standings + per-team squad profile + predicted finish order by pedigree.
    """
    from data.loader import get_bzzoiro_squad
    from tools.team_analysis import _fetch_squad, _build_csv_profile, LEAGUE_DISPLAY
    from tools.compare import _top_attacker

    group = group.upper().strip()
    if group not in VALID_GROUPS:
        return f"Invalid group '{group}'. Use A through L."

    cached = cache.get("standings", group=group, source="overview_v4")
    if cached:
        return cached

    team_ids = GROUP_MAP.get(group, [])
    if not team_ids:
        return f"No teams found for Group {group}."

    results = await asyncio.gather(
        get_group_standings(group),
        *[_fetch_squad(tid) for tid in team_ids],
        return_exceptions=True,
    )
    standings_text = results[0] if not isinstance(results[0], Exception) else "Standings unavailable."
    squad_results = results[1:]

    profiles = []
    for team_id, squad in zip(team_ids, squad_results):
        squad_names = squad if not isinstance(squad, Exception) else []
        name = _ID_TO_NAME.get(team_id, f"Team {team_id}")
        bzz_squad = get_bzzoiro_squad(name)
        csv_prof = _build_csv_profile(squad_names, bzz_squad or None)
        top = _top_attacker(csv_prof)
        profiles.append((name, csv_prof, top))

    profiles.sort(
        key=lambda x: (
            x[1]["pedigree_score"] if x[1]["pedigree_score"] is not None else 0.0,
            x[1]["proj_gpg"],
        ),
        reverse=True,
    )

    sep = "━" * 54
    lines = [
        f"🏆 GROUP {group} OVERVIEW — FIFA World Cup 2026",
        f"{sep}\n",
        f"📊 CURRENT STANDINGS\n",
        standings_text if isinstance(standings_text, str) else "  Standings unavailable.",
        f"\n{sep}\n",
        f"🔍 TEAM PROFILES (ranked by squad pedigree)\n",
    ]

    for rank, (name, csv_prof, top) in enumerate(profiles, 1):
        lg_counts = csv_prof["league_counts"]
        top_lg = max(lg_counts, key=lambda k: lg_counts[k]) if any(lg_counts.values()) else None
        top_lg_display = LEAGUE_DISPLAY.get(top_lg, top_lg) if top_lg and lg_counts[top_lg] > 0 else "Other"
        ped_display = f"{csv_prof['pedigree_score']:.0%}" if csv_prof["pedigree_score"] is not None else "N/A"
        lines += [
            f"{rank}. {name}  |  Pedigree: {ped_display}  |  Top league: {top_lg_display}",
            f"   Top attacker: {top[0]} ({top[1]}) — npxG {top[3]}",
            f"   Proj. goals/game: {csv_prof['proj_gpg']}",
            "",
        ]

    predicted = " › ".join(p[0] for p in profiles)
    lines += [
        f"{sep}",
        f"📌 Predicted finish order (pedigree, then proj. goals/game tiebreak): {predicted}",
    ]

    result = "\n".join(lines)
    cache.set("standings", result, group=group, source="overview_v4")
    return result
