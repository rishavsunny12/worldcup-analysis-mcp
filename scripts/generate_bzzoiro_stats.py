"""
Bulk-export World Cup 2026 player and team stats from bzzoiro into two CSVs.

Usage:
    python scripts/generate_bzzoiro_stats.py

Outputs:
    data/bzzoiro_wc_players.csv  — one row per squad player (~1,459)
    data/bzzoiro_wc_teams.csv    — one row per nation (48)

Re-run safe: skips player_ids already present in the players CSV (resume).
Requires BZZOIRO_KEY in .env
"""
from __future__ import annotations

import asyncio
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
WORLD_CUP_LEAGUE_ID = 27
CONCURRENCY = 8
PLAYERS_CSV = ROOT / "data" / "bzzoiro_wc_players.csv"
TEAMS_CSV = ROOT / "data" / "bzzoiro_wc_teams.csv"

PLAYER_FIELDS = [
    "player_id",
    "player_name",
    "national_team_id",
    "national_team_name",
    "wc_group",
    "wc_jersey",
    "wc_position",
    "wc_status",
    "wc_squad_caps",
    "wc_squad_goals",
    "wc_club",
    "wc_club_country",
    "age",
    "date_of_birth",
    "nationality",
    "height_cm",
    "weight_kg",
    "preferred_foot",
    "market_value_eur",
    "contract_until",
    "wage_eur_annual",
    "availability",
    "overall_rating",
    "potential",
    "injury_risk",
    "attr_tactical",
    "attr_attacking",
    "attr_defending",
    "attr_technical",
    "attr_creativity",
    "club_team_id",
    "club_name",
    "club_league_id",
    "club_league_name",
    "club_season_id",
    "club_matches",
    "club_minutes",
    "club_goals",
    "club_assists",
    "club_xg",
    "club_xa",
    "club_shots",
    "club_shots_on_target",
    "club_key_passes",
    "club_passes",
    "club_pass_accuracy_pct",
    "club_avg_match_rating",
    "intl_caps",
    "intl_goals",
    "intl_last_appearance",
    "exported_at",
]

TEAM_FIELDS = [
    "team_id",
    "team_name",
    "short_name",
    "country",
    "wc_group",
    "venue_id",
    "squad_size",
    "avg_age",
    "total_market_value_eur",
    "avg_market_value_eur",
    "avg_overall_rating",
    "avg_club_match_rating",
    "squad_club_goals",
    "squad_club_assists",
    "squad_club_xg",
    "squad_club_xa",
    "squad_intl_caps",
    "squad_intl_goals",
    "upcoming_fixtures",
    "exported_at",
]


def _load_env() -> str:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())
    key = os.getenv("BZZOIRO_KEY", "")
    if not key:
        print("ERROR: BZZOIRO_KEY not found in .env")
        sys.exit(1)
    return key


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _round(val: float | None, n: int = 2) -> float | None:
    if val is None:
        return None
    return round(val, n)


def _aggregate_match_stats(rows: list[dict]) -> dict:
    nums = [
        "minutes_played", "goals", "goal_assist", "total_shots", "shots_on_target",
        "key_pass", "total_pass", "accurate_pass",
    ]
    agg = {k: 0 for k in nums}
    xgs: list[float] = []
    xas: list[float] = []
    ratings: list[float] = []

    for row in rows:
        for key in nums:
            val = row.get(key)
            if isinstance(val, (int, float)):
                agg[key] += val
        xg = _safe_float(row.get("expected_goals"))
        xa = _safe_float(row.get("expected_assists"))
        if xg is not None:
            xgs.append(xg)
        if xa is not None:
            xas.append(xa)
        rt = _safe_float(row.get("rating"))
        if rt is not None:
            ratings.append(rt)

    passes = agg["total_pass"]
    accurate = agg["accurate_pass"]
    pass_pct = round(accurate / passes * 100, 1) if passes else None

    return {
        "club_matches": len(rows),
        "club_minutes": agg["minutes_played"],
        "club_goals": agg["goals"],
        "club_assists": agg["goal_assist"],
        "club_xg": _round(sum(xgs)) if xgs else None,
        "club_xa": _round(sum(xas)) if xas else None,
        "club_shots": agg["total_shots"],
        "club_shots_on_target": agg["shots_on_target"],
        "club_key_passes": agg["key_pass"],
        "club_passes": passes,
        "club_pass_accuracy_pct": pass_pct,
        "club_avg_match_rating": _round(sum(ratings) / len(ratings)) if ratings else None,
        "club_league_id": None,
        "club_season_id": None,
    }


async def _fetch_all_pages(client: httpx.AsyncClient, path: str) -> list[dict]:
    path = path.lstrip("/")
    items: list[dict] = []
    resp = await client.get(path)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    items.extend(data.get("results", data.get("data", [])))
    next_url = data.get("next")
    while next_url:
        resp = await client.get(next_url)
        resp.raise_for_status()
        data = resp.json()
        items.extend(data.get("results", data.get("data", [])))
        next_url = data.get("next")
    return items


class NameCache:
    """Cache club and league names to avoid repeat lookups."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._teams: dict[int, str] = {}
        self._leagues: dict[int, str] = {}

    async def team_name(self, team_id: int | None) -> str | None:
        if not team_id:
            return None
        if team_id in self._teams:
            return self._teams[team_id]
        resp = await self._client.get(f"teams/{team_id}/")
        if resp.status_code != 200:
            return None
        name = resp.json().get("name") or resp.json().get("short_name")
        if name:
            self._teams[team_id] = name
        return name

    async def league_name(self, league_id: int | None) -> str | None:
        if not league_id:
            return None
        if league_id in self._leagues:
            return self._leagues[league_id]
        resp = await self._client.get(f"leagues/{league_id}/")
        if resp.status_code != 200:
            return None
        name = resp.json().get("name")
        if name:
            self._leagues[league_id] = name
        return name


async def _fetch_player_bundle(
    client: httpx.AsyncClient,
    names: NameCache,
    squad_row: dict,
    team_name: str,
    wc_group: str,
    exported_at: str,
) -> dict | None:
    player_id = squad_row.get("player_id")
    if not player_id:
        return None

    profile_resp, nat_resp, career_resp = await asyncio.gather(
        client.get(f"players/{player_id}/"),
        client.get(f"players/{player_id}/national-team/"),
        client.get(f"players/{player_id}/career/"),
    )
    profile_resp.raise_for_status()
    profile = profile_resp.json()
    national = nat_resp.json() if nat_resp.status_code == 200 else {}
    career_seasons = career_resp.json().get("seasons") or [] if career_resp.status_code == 200 else []

    club_team_id = profile.get("current_team_id")
    stats_rows: list[dict] = []
    career_meta: dict = {}

    career_row = next((s for s in career_seasons if s.get("team_id") == club_team_id), None)
    if not career_row and career_seasons:
        career_row = career_seasons[0]

    if club_team_id:
        stats_rows = await _fetch_all_pages(
            client, f"players/{player_id}/stats/?team_id={club_team_id}"
        )
        if not stats_rows and career_row:
            career_meta = {
                "club_matches": career_row.get("matches"),
                "club_minutes": career_row.get("minutes"),
                "club_goals": career_row.get("goals"),
                "club_assists": career_row.get("assists"),
                "club_avg_match_rating": career_row.get("avg_rating"),
                "club_league_id": career_row.get("league_id"),
                "club_season_id": career_row.get("season_id"),
            }

    club_stats = _aggregate_match_stats(stats_rows) if stats_rows else career_meta
    if career_row and not club_stats.get("club_league_id"):
        club_stats["club_league_id"] = career_row.get("league_id")
        club_stats["club_season_id"] = career_row.get("season_id")
    attrs = profile.get("attributes") or {}

    league_id = club_stats.get("club_league_id")

    club_name = await names.team_name(club_team_id) or squad_row.get("club")
    league_name = await names.league_name(league_id)

    row = {
        "player_id": player_id,
        "player_name": squad_row.get("name") or profile.get("name") or "",
        "national_team_id": squad_row.get("team_id"),
        "national_team_name": team_name,
        "wc_group": wc_group,
        "wc_jersey": squad_row.get("jersey_number"),
        "wc_position": squad_row.get("position"),
        "wc_status": squad_row.get("status"),
        "wc_squad_caps": squad_row.get("caps"),
        "wc_squad_goals": squad_row.get("goals"),
        "wc_club": squad_row.get("club"),
        "wc_club_country": squad_row.get("club_country"),
        "age": squad_row.get("age"),
        "date_of_birth": squad_row.get("date_of_birth") or profile.get("date_of_birth"),
        "nationality": profile.get("nationality"),
        "height_cm": profile.get("height_cm"),
        "weight_kg": profile.get("weight_kg"),
        "preferred_foot": profile.get("preferred_foot"),
        "market_value_eur": profile.get("market_value_eur"),
        "contract_until": profile.get("contract_until"),
        "wage_eur_annual": profile.get("wage_eur_annual"),
        "availability": profile.get("availability"),
        "overall_rating": profile.get("rating"),
        "potential": profile.get("potential"),
        "injury_risk": profile.get("injury_risk"),
        "attr_tactical": attrs.get("tactical"),
        "attr_attacking": attrs.get("attacking"),
        "attr_defending": attrs.get("defending"),
        "attr_technical": attrs.get("technical"),
        "attr_creativity": attrs.get("creativity"),
        "club_team_id": club_team_id,
        "club_name": club_name,
        "club_league_name": league_name,
        "intl_caps": national.get("caps"),
        "intl_goals": national.get("goals"),
        "intl_last_appearance": national.get("last_appearance"),
        "exported_at": exported_at,
    }
    row.update(club_stats)
    return row


def _load_existing_player_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {r["player_id"] for r in csv.DictReader(f) if r.get("player_id")}


def _append_players(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PLAYER_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def _build_team_rows(
    teams: list[dict],
    squad_meta: dict[int, dict],
    player_rows: list[dict],
    exported_at: str,
) -> list[dict]:
    by_team: dict[int, list[dict]] = {}
    for row in player_rows:
        tid = row.get("national_team_id")
        if tid:
            by_team.setdefault(int(tid), []).append(row)

    team_rows: list[dict] = []
    for team in teams:
        tid = team["id"]
        players = by_team.get(tid, [])
        meta = squad_meta.get(tid, {})
        ages = [a for a in (_safe_float(p.get("age")) for p in players) if a is not None]
        market_vals = [m for m in (_safe_float(p.get("market_value_eur")) for p in players) if m]
        ovr_ratings = [r for r in (_safe_float(p.get("overall_rating")) for p in players) if r]
        match_ratings = [
            r for r in (_safe_float(p.get("club_avg_match_rating")) for p in players) if r
        ]

        team_rows.append(
            {
                "team_id": tid,
                "team_name": team.get("name"),
                "short_name": team.get("short_name"),
                "country": team.get("country"),
                "wc_group": meta.get("group"),
                "venue_id": team.get("venue_id"),
                "squad_size": len(players),
                "avg_age": _round(sum(ages) / len(ages), 1) if ages else None,
                "total_market_value_eur": int(sum(market_vals)) if market_vals else None,
                "avg_market_value_eur": int(sum(market_vals) / len(market_vals)) if market_vals else None,
                "avg_overall_rating": _round(sum(ovr_ratings) / len(ovr_ratings)) if ovr_ratings else None,
                "avg_club_match_rating": _round(sum(match_ratings) / len(match_ratings))
                if match_ratings
                else None,
                "squad_club_goals": sum(int(p.get("club_goals") or 0) for p in players),
                "squad_club_assists": sum(int(p.get("club_assists") or 0) for p in players),
                "squad_club_xg": _round(sum(_safe_float(p.get("club_xg")) or 0 for p in players)),
                "squad_club_xa": _round(sum(_safe_float(p.get("club_xa")) or 0 for p in players)),
                "squad_intl_caps": sum(int(p.get("intl_caps") or 0) for p in players),
                "squad_intl_goals": sum(int(p.get("intl_goals") or 0) for p in players),
                "upcoming_fixtures": meta.get("upcoming_fixtures"),
                "exported_at": exported_at,
            }
        )
    return team_rows


async def _fetch_upcoming_fixtures(client: httpx.AsyncClient, team_id: int) -> int:
    resp = await client.get(f"teams/{team_id}/fixtures/")
    if resp.status_code != 200:
        return 0
    data = resp.json()
    results = data if isinstance(data, list) else data.get("results", [])
    return sum(1 for fx in results if fx.get("status") == "notstarted")


async def export_all() -> None:
    api_key = _load_env()
    exported_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing_ids = _load_existing_player_ids(PLAYERS_CSV)

    headers = {"Authorization": f"Token {api_key}"}
    async with httpx.AsyncClient(
        base_url="https://sports.bzzoiro.com/api/v2",
        headers=headers,
        timeout=30.0,
    ) as client:
        teams = await _fetch_all_pages(
            client, f"teams/?in_competition=true&league_id={WORLD_CUP_LEAGUE_ID}"
        )
        teams.sort(key=lambda t: (t.get("name") or "").lower())
        print(f"World Cup teams: {len(teams)}")

        squad_meta: dict[int, dict] = {}
        all_squad_rows: list[tuple[dict, str, str]] = []

        for i, team in enumerate(teams, 1):
            tid = team["id"]
            name = team.get("name") or ""
            resp = await client.get(f"worldcup/squads/{tid}/")
            resp.raise_for_status()
            squad_data = resp.json()
            group = squad_data.get("group") or ""
            squad = squad_data.get("results") or []
            upcoming = await _fetch_upcoming_fixtures(client, tid)
            squad_meta[tid] = {"group": group, "upcoming_fixtures": upcoming}
            print(f"  squad {i:2}/{len(teams)} {name} — {len(squad)} players, group {group}")
            for member in squad:
                all_squad_rows.append((member, name, group))

        pending = [
            row
            for row in all_squad_rows
            if str(row[0].get("player_id")) not in existing_ids and row[0].get("player_id")
        ]
        skipped = len(all_squad_rows) - len(pending)
        print(f"\nPlayers to fetch: {len(pending)} (skipping {skipped} already exported)")

        sem = asyncio.Semaphore(CONCURRENCY)
        new_rows: list[dict] = []
        names = NameCache(client)

        async def _worker(squad_row: dict, team_name: str, group: str) -> dict | None:
            async with sem:
                try:
                    return await _fetch_player_bundle(
                        client, names, squad_row, team_name, group, exported_at
                    )
                except httpx.HTTPError as exc:
                    pid = squad_row.get("player_id")
                    print(f"  WARN player {pid}: {exc}")
                    return None

        batch_size = CONCURRENCY * 5
        for batch_start in range(0, len(pending), batch_size):
            batch = pending[batch_start : batch_start + batch_size]
            results = await asyncio.gather(
                *[_worker(row, team_name, group) for row, team_name, group in batch]
            )
            batch_rows = [r for r in results if r]
            if batch_rows:
                _append_players(PLAYERS_CSV, batch_rows)
                new_rows.extend(batch_rows)
            done = min(batch_start + len(batch), len(pending))
            print(f"  progress {done}/{len(pending)}")

        all_player_rows: list[dict] = []
        if PLAYERS_CSV.exists():
            with PLAYERS_CSV.open(encoding="utf-8") as f:
                all_player_rows = list(csv.DictReader(f))

        team_rows = _build_team_rows(teams, squad_meta, all_player_rows, exported_at)
        TEAMS_CSV.parent.mkdir(parents=True, exist_ok=True)
        with TEAMS_CSV.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=TEAM_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(team_rows)

    print(f"\nWrote {len(all_player_rows)} players -> {PLAYERS_CSV}")
    print(f"Wrote {len(team_rows)} teams   -> {TEAMS_CSV}")
    print(f"New players this run: {len(new_rows)}")


def main() -> None:
    asyncio.run(export_all())


if __name__ == "__main__":
    main()
