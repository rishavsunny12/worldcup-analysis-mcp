import asyncio
import logging

from cache.cache_manager import cache
from config import GROUP_MAP, TEAM_ID_MAP
from tools.team_analysis import _fetch_squad, _build_csv_profile
from tools.compare import _top_attacker

logger = logging.getLogger(__name__)

_ID_TO_NAME: dict[int, str] = {}
for _alias, _tid in TEAM_ID_MAP.items():
    if _tid not in _ID_TO_NAME:
        _ID_TO_NAME[_tid] = _alias.title()

_ALL_TEAM_IDS: list[int] = [tid for tids in GROUP_MAP.values() for tid in tids]

_BATCH_SIZE = 4


async def get_tournament_favorites(top_n: int = 10) -> str:
    """
    Rank all 48 World Cup 2026 teams by squad strength using 2025-26 club season data.
    Use when the user asks: who are the favorites, strongest teams, best squads,
    who will win the World Cup, top teams, power rankings, dark horses, best chances.
    top_n controls how many teams to show (default 10, max 48).
    Rankings are based on squad pedigree (% in top-6 European leagues) and projected goals/game.
    """
    top_n = max(1, min(48, top_n))

    cached = cache.get("form", source="favorites", top_n=top_n)
    if cached:
        return cached

    # Fetch all 48 squads in batches of 8 to stay within API rate limits
    all_squads: dict[int, list[str]] = {}
    for i in range(0, len(_ALL_TEAM_IDS), _BATCH_SIZE):
        batch = _ALL_TEAM_IDS[i:i + _BATCH_SIZE]
        results = await asyncio.gather(*[_fetch_squad(tid) for tid in batch], return_exceptions=True)
        for tid, squad in zip(batch, results):
            all_squads[tid] = squad if not isinstance(squad, Exception) else []

    rankings = []
    for tid in _ALL_TEAM_IDS:
        squad = all_squads.get(tid, [])
        csv_prof = _build_csv_profile(squad)
        composite = csv_prof["pedigree_score"] * 0.6 + min(csv_prof["proj_gpg"] / 1.0, 1.0) * 0.4
        top = _top_attacker(csv_prof)
        rankings.append({
            "name": _ID_TO_NAME.get(tid, f"Team {tid}"),
            "pedigree": csv_prof["pedigree_score"],
            "proj_gpg": csv_prof["proj_gpg"],
            "composite": round(composite, 3),
            "top_attacker": top,
        })

    rankings.sort(key=lambda r: r["composite"], reverse=True)

    sep = "━" * 62
    lines = [
        "🏆 WORLD CUP 2026 POWER RANKINGS",
        "Based on 2025-26 club season data across top 6 European leagues",
        sep,
        "",
        f"  {'Rank':<5} {'Team':<22} {'Pedigree':>8} {'Proj GPG':>9}  Top Attacker (npxG)",
        f"  {'─'*60}",
    ]

    for i, r in enumerate(rankings[:top_n], 1):
        top = r["top_attacker"]
        attacker_str = f"{top[0]} ({top[3]})" if top[0] != "N/A" else "N/A"
        lines.append(
            f"  {i:<5} {r['name']:<22} {r['pedigree']:>7.0%}  {r['proj_gpg']:>8.2f}  {attacker_str}"
        )

    dark_horses = sorted(
        [r for r in rankings if r["pedigree"] < 0.5 and r["proj_gpg"] >= 0.4],
        key=lambda r: r["proj_gpg"],
        reverse=True,
    )[:3]

    if dark_horses:
        lines += ["", "⭐ Dark horses (strong projected output, lower squad pedigree):"]
        for r in dark_horses:
            lines.append(
                f"   {r['name']} — {r['proj_gpg']:.2f} proj goals/game | {r['pedigree']:.0%} pedigree"
            )

    scored = sum(1 for r in rankings if r["pedigree"] > 0 or r["proj_gpg"] > 0)
    if scored < len(rankings):
        lines.append(
            f"\n⚠️  {len(rankings) - scored} teams unscored (rate limit on first run). "
            f"Ask again to fill in remaining teams from cache."
        )

    lines.append(f"\n{sep}")
    result = "\n".join(lines)
    cache.set("form", result, source="favorites", top_n=top_n)
    return result
