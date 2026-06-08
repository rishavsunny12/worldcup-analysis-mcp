import logging

from cache.cache_manager import cache
from config import GROUP_MAP, TEAM_ID_MAP
from data.loader import defensive_profile_from_squad, get_bzzoiro_squad, get_bzzoiro_team
from tools.compare import _top_attacker, _top_defender
from tools.team_analysis import _build_csv_profile

logger = logging.getLogger(__name__)

_ID_TO_NAME: dict[int, str] = {}
for _alias, _tid in TEAM_ID_MAP.items():
    if _tid not in _ID_TO_NAME:
        _ID_TO_NAME[_tid] = _alias.title()

_ALL_TEAM_IDS: list[int] = [tid for tids in GROUP_MAP.values() for tid in tids]


async def get_tournament_favorites(top_n: int = 10) -> str:
    """
    Rank all 48 World Cup 2026 teams by squad strength using 2025-26 club season data.
    Use when the user asks: who are the favorites, strongest teams, best squads, who will win
    the World Cup, top teams, power rankings, dark horses, best chances.
    top_n controls how many teams to show (default 10, max 48).
    Rankings blend attack (proj goals/game), defense (DF/GK defending attribute), and pedigree.
    """
    top_n = max(1, min(48, top_n))

    cached = cache.get("form", source="favorites_v3", top_n=top_n)
    if cached:
        return cached

    rankings = []
    for tid in _ALL_TEAM_IDS:
        team_name = _ID_TO_NAME.get(tid, f"Team {tid}")
        bzz_squad = get_bzzoiro_squad(team_name)
        bzz_team  = get_bzzoiro_team(team_name)

        csv_prof = _build_csv_profile([], bzz_squad)
        def_prof = defensive_profile_from_squad(bzz_squad)

        avg_rating = 0.0
        if bzz_team:
            try:
                avg_rating = float(bzz_team.get("avg_overall_rating") or 0)
            except (TypeError, ValueError):
                avg_rating = 0.0

        ped = csv_prof["pedigree_score"] or 0.0
        gpg = min(csv_prof["proj_gpg"] / 1.0, 1.0)
        def_score = def_prof["defense_score"]
        rating_norm = max(0.0, min(1.0, (avg_rating - 65) / 25)) if avg_rating > 0 else 0.0

        # Attack 35%, defense 25%, pedigree 25%, avg rating 15%
        composite = round(
            gpg * 0.35 + def_score * 0.25 + ped * 0.25 + rating_norm * 0.15,
            3,
        )

        top = _top_attacker(csv_prof)
        top_def = _top_defender(def_prof)
        rankings.append({
            "name":          team_name,
            "pedigree":      ped,
            "proj_gpg":      csv_prof["proj_gpg"],
            "avg_def":       def_prof["avg_def_rating"],
            "def_score":     def_score,
            "avg_rating":    round(avg_rating, 1),
            "composite":     composite,
            "top_attacker":  top,
            "top_defender":  top_def,
        })

    rankings.sort(key=lambda r: r["composite"], reverse=True)

    sep = "━" * 72
    lines = [
        "🏆 WORLD CUP 2026 POWER RANKINGS",
        "Attack (proj GPG) + defense (DF/GK attr) + pedigree — all 48 nations",
        sep,
        "",
        f"  {'Rank':<5} {'Team':<20} {'Atk GPG':>8} {'Def Avg':>8} {'Ped':>6} {'Rating':>7}  Top Attacker",
        f"  {'─'*70}",
    ]

    for i, r in enumerate(rankings[:top_n], 1):
        top = r["top_attacker"]
        attacker_str = f"{top[0]} ({top[3]})" if top[0] != "N/A" else "N/A"
        def_avg = f"{r['avg_def']:.0f}" if r["avg_def"] is not None else "—"
        lines.append(
            f"  {i:<5} {r['name']:<20} {r['proj_gpg']:>8.2f} {def_avg:>8} {r['pedigree']:>5.0%}"
            f"  {r['avg_rating']:>6.1f}  {attacker_str}"
        )

    dark_horses = sorted(
        [r for r in rankings if r["pedigree"] < 0.4 and r["proj_gpg"] >= 0.3],
        key=lambda r: r["composite"],
        reverse=True,
    )[:3]

    if dark_horses:
        lines += ["", "⭐ Dark horses (strong output, lower top-league pedigree):"]
        for r in dark_horses:
            def_str = f"def avg {r['avg_def']:.0f}" if r["avg_def"] else "def N/A"
            lines.append(
                f"   {r['name']} — {r['proj_gpg']:.2f} proj GPG"
                f" | {def_str} | {r['pedigree']:.0%} pedigree"
            )

    lines.append(f"\n{sep}")
    result = "\n".join(lines)
    cache.set("form", result, source="favorites_v3", top_n=top_n)
    return result
