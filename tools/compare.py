import asyncio
import logging

from cache.cache_manager import cache
from clients.api_football import api_football
from clients.football_data import football_data
from config import resolve_team_id
from tools.team_analysis import _fetch_squad, _build_csv_profile, _parse_wc_stats, LEAGUE_DISPLAY

logger = logging.getLogger(__name__)


def _edge(val_a, val_b, higher_is_better: bool = True) -> str:
    if val_a == val_b:
        return "Even"
    if higher_is_better:
        return "→ A" if val_a > val_b else "→ B"
    return "→ A" if val_a < val_b else "→ B"


def _top_attacker(csv: dict) -> tuple[str, str, str, float]:
    """Return (name, club, league, npxg) of the best attacker."""
    if not csv["performers"]:
        return ("N/A", "?", "?", 0.0)
    p = csv["performers"][0]
    from tools.team_analysis import _safe_float
    return (
        p["player_name"],
        p.get("team_title", "?"),
        LEAGUE_DISPLAY.get(p.get("league", ""), "?"),
        _safe_float(p.get("npxG")),
    )


async def compare_teams_for_worldcup(team_a: str, team_b: str) -> str:
    """
    Side-by-side World Cup 2026 comparison of two teams using squad + 2025-26 club season data.
    Use when the user asks: compare [team] vs [team], who is better, [team] or [team],
    which team has the stronger squad, [team] vs [team] analysis.
    Do NOT use for head-to-head match history — use get_h2h for past results between two teams.
    """
    id_a = resolve_team_id(team_a)
    id_b = resolve_team_id(team_b)
    if id_a is None:
        return f"Team '{team_a}' not found. Try full name (e.g. 'South Korea', 'United States')."
    if id_b is None:
        return f"Team '{team_b}' not found. Try full name (e.g. 'South Korea', 'United States')."

    key = tuple(sorted([id_a, id_b]))
    cached = cache.get("form", team_a_id=key[0], team_b_id=key[1], source="compare")
    if cached:
        return cached

    results = await asyncio.gather(
        api_football.get_team_stats(id_a),
        api_football.get_team_stats(id_b),
        _fetch_squad(id_a),
        _fetch_squad(id_b),
        return_exceptions=True,
    )

    wc_raw_a = results[0] if not isinstance(results[0], Exception) else None
    wc_raw_b = results[1] if not isinstance(results[1], Exception) else None
    squad_a  = results[2] if not isinstance(results[2], Exception) else []
    squad_b  = results[3] if not isinstance(results[3], Exception) else []

    name_a = wc_raw_a.get("response", {}).get("team", {}).get("name", team_a.title()) if wc_raw_a else team_a.title()
    name_b = wc_raw_b.get("response", {}).get("team", {}).get("name", team_b.title()) if wc_raw_b else team_b.title()

    wc_a = _parse_wc_stats(wc_raw_a) if wc_raw_a else None
    wc_b = _parse_wc_stats(wc_raw_b) if wc_raw_b else None
    csv_a = _build_csv_profile(squad_a)
    csv_b = _build_csv_profile(squad_b)

    top_a = _top_attacker(csv_a)
    top_b = _top_attacker(csv_b)

    sep = "━" * 54
    col = 22  # column width for each team

    def row(label: str, va, vb) -> str:
        return f"  {label:<22} {str(va):<{col}} {vb}"

    lines = [
        f"⚔️  TEAM COMPARISON: {name_a} vs {name_b}",
        f"{sep}\n",
        f"  {'': <22} {name_a:<{col}} {name_b}",
        "",
    ]

    # WC tournament stats
    lines.append("📊 WC 2026 TOURNAMENT")
    if wc_a and wc_b:
        lines += [
            row("Record", f"W{wc_a['won']} D{wc_a['draw']} L{wc_a['lost']}", f"W{wc_b['won']} D{wc_b['draw']} L{wc_b['lost']}"),
            row("xG For/game", wc_a['xgf'], wc_b['xgf']),
            row("xG Against/game", wc_a['xga'], wc_b['xga']),
            row("xG Diff", f"{wc_a['xgd']:+.2f}", f"{wc_b['xgd']:+.2f}"),
        ]
    else:
        lines.append("  No tournament data yet — predictions based on club season stats.")

    # Squad pedigree
    top_lg_a = max(csv_a["league_counts"], key=lambda k: csv_a["league_counts"][k])
    top_lg_b = max(csv_b["league_counts"], key=lambda k: csv_b["league_counts"][k])
    lines += [
        "",
        "🏟️ SQUAD PEDIGREE (2025-26)",
        row("Top-6 coverage", f"{round(csv_a['found']/csv_a['total_squad']*100) if csv_a['total_squad'] else 0}%",
                              f"{round(csv_b['found']/csv_b['total_squad']*100) if csv_b['total_squad'] else 0}%"),
        row("Pedigree score",
            f"{csv_a['pedigree_score']:.0%}" if csv_a['pedigree_score'] is not None else "N/A",
            f"{csv_b['pedigree_score']:.0%}" if csv_b['pedigree_score'] is not None else "N/A"),
        row("Top league", LEAGUE_DISPLAY.get(top_lg_a, top_lg_a), LEAGUE_DISPLAY.get(top_lg_b, top_lg_b)),
    ]

    # Top attacker
    lines += [
        "",
        "⚽ TOP ATTACKER (npxG this season)",
        row("Name", top_a[0], top_b[0]),
        row("Club", f"{top_a[1]} ({top_a[2]})", f"{top_b[1]} ({top_b[2]})"),
        row("npxG", top_a[3], top_b[3]),
        "",
        row("🔮 Proj. goals/game", csv_a['proj_gpg'], csv_b['proj_gpg']),
    ]

    # Edge summary
    xgd_a = wc_a["xgd"] if wc_a else 0.0
    xgd_b = wc_b["xgd"] if wc_b else 0.0
    edge_xg    = _edge(xgd_a, xgd_b).replace("→ A", f"→ {name_a}").replace("→ B", f"→ {name_b}")
    ped_a = csv_a["pedigree_score"] if csv_a["pedigree_score"] is not None else 0.0
    ped_b = csv_b["pedigree_score"] if csv_b["pedigree_score"] is not None else 0.0
    edge_ped   = _edge(ped_a, ped_b).replace("→ A", f"→ {name_a}").replace("→ B", f"→ {name_b}")
    edge_att   = _edge(csv_a["proj_gpg"], csv_b["proj_gpg"]).replace("→ A", f"→ {name_a}").replace("→ B", f"→ {name_b}")

    edges = [edge_xg, edge_ped, edge_att]
    a_edges = sum(1 for e in edges if name_a in e)
    b_edges = sum(1 for e in edges if name_b in e)
    if a_edges > b_edges:
        overall = f"{name_a} have the edge"
    elif b_edges > a_edges:
        overall = f"{name_b} have the edge"
    else:
        overall = "Too close to call"

    lines += [
        "",
        "EDGE",
        f"  xG Differential  {edge_xg}",
        f"  Squad Pedigree   {edge_ped}",
        f"  Attacking Threat {edge_att}",
        "",
        f"  Overall: {overall}",
        f"\n{sep}",
    ]

    result = "\n".join(lines)
    cache.set("form", result, team_a_id=key[0], team_b_id=key[1], source="compare")
    return result
