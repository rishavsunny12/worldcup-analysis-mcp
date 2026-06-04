import logging

from cache.cache_manager import cache
from config import GROUP_MAP, TEAM_ID_MAP
from data.loader import get_bzzoiro_squad, get_bzzoiro_team
from tools.compare import _top_attacker
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
    Rankings use squad pedigree (% in top-6 European leagues) and projected goals/game.
    Now covers all 48 nations with full global squad data via bzzoiro.
    """
    top_n = max(1, min(48, top_n))

    cached = cache.get("form", source="favorites_v2", top_n=top_n)
    if cached:
        return cached

    rankings = []
    for tid in _ALL_TEAM_IDS:
        team_name = _ID_TO_NAME.get(tid, f"Team {tid}")
        bzz_squad = get_bzzoiro_squad(team_name)
        bzz_team  = get_bzzoiro_team(team_name)

        # Build profile using bzzoiro squad directly (no API calls needed)
        csv_prof = _build_csv_profile([], bzz_squad)

        # Factor in bzzoiro team avg rating as a secondary signal when pedigree is low
        avg_rating = 0.0
        if bzz_team:
            try:
                avg_rating = float(bzz_team.get("avg_overall_rating") or 0)
            except (TypeError, ValueError):
                avg_rating = 0.0

        ped = csv_prof["pedigree_score"] or 0.0
        gpg = min(csv_prof["proj_gpg"] / 1.0, 1.0)
        # Normalize avg_rating (typical range 70-85) to 0-1
        rating_norm = max(0.0, min(1.0, (avg_rating - 65) / 25)) if avg_rating > 0 else 0.0

        # Composite: pedigree 50%, proj_gpg 35%, avg squad rating 15%
        composite = round(ped * 0.50 + gpg * 0.35 + rating_norm * 0.15, 3)

        top = _top_attacker(csv_prof)
        rankings.append({
            "name":         team_name,
            "pedigree":     ped,
            "proj_gpg":     csv_prof["proj_gpg"],
            "avg_rating":   round(avg_rating, 1),
            "composite":    composite,
            "top_attacker": top,
        })

    rankings.sort(key=lambda r: r["composite"], reverse=True)

    sep = "━" * 68
    lines = [
        "🏆 WORLD CUP 2026 POWER RANKINGS",
        "Based on 2025-26 club season data — all 48 nations via understat + bzzoiro",
        sep,
        "",
        f"  {'Rank':<5} {'Team':<22} {'Pedigree':>8} {'Proj GPG':>9} {'Rating':>7}  Top Attacker (xG)",
        f"  {'─'*66}",
    ]

    for i, r in enumerate(rankings[:top_n], 1):
        top = r["top_attacker"]
        attacker_str = f"{top[0]} ({top[3]})" if top[0] != "N/A" else "N/A"
        lines.append(
            f"  {i:<5} {r['name']:<22} {r['pedigree']:>7.0%}  {r['proj_gpg']:>8.2f}"
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
            lines.append(
                f"   {r['name']} — {r['proj_gpg']:.2f} proj goals/game"
                f" | {r['pedigree']:.0%} top-6 pedigree | rating {r['avg_rating']}"
            )

    lines.append(f"\n{sep}")
    result = "\n".join(lines)
    cache.set("form", result, source="favorites_v2", top_n=top_n)
    return result
