"""
Bulk-export World Cup 2026 player and team stats from bzzoiro into CSVs.

Usage:
    python scripts/generate_bzzoiro_stats.py           # resume new players only
    python scripts/generate_bzzoiro_stats.py --full    # re-fetch all players (schema refresh)
    python scripts/generate_bzzoiro_stats.py --meta-only  # teams/predictions/fixtures only

Outputs:
    data/bzzoiro_wc_players.csv
    data/bzzoiro_wc_teams.csv
    data/bzzoiro_wc_predictions.csv
    data/bzzoiro_wc_fixtures.csv

Requires BZZOIRO_KEY in .env
"""
from __future__ import annotations

import argparse
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
PREDICTIONS_CSV = ROOT / "data" / "bzzoiro_wc_predictions.csv"
FIXTURES_CSV = ROOT / "data" / "bzzoiro_wc_fixtures.csv"

PLAYER_FIELDS = [
    "player_id", "player_name", "national_team_id", "national_team_name",
    "wc_group", "wc_jersey", "wc_position", "wc_status", "wc_squad_caps", "wc_squad_goals",
    "wc_club", "wc_club_country", "age", "date_of_birth", "nationality",
    "height_cm", "weight_kg", "preferred_foot", "market_value_eur", "contract_until",
    "wage_eur_annual", "availability", "overall_rating", "potential", "injury_risk",
    "attr_tactical", "attr_attacking", "attr_defending", "attr_technical", "attr_creativity",
    "club_team_id", "club_name", "club_league_id", "club_league_name", "club_season_id",
    "club_matches", "club_minutes", "club_goals", "club_assists",
    "club_xg", "club_xa", "club_shots", "club_shots_on_target", "club_key_passes",
    "club_passes", "club_pass_accuracy_pct", "club_avg_match_rating",
    "club_tackles", "club_tackles_won", "club_interceptions", "club_clearances",
    "club_ball_recovery", "club_blocks", "club_duels_won", "club_duels_lost",
    "club_aerial_won", "club_aerial_lost", "club_saves", "club_goals_conceded",
    "club_yellow_cards", "club_red_cards", "club_dribbles_won", "club_dribbles_attempted",
    "club_crosses", "club_long_balls", "club_touches", "club_fouls",
    "intl_caps", "intl_goals", "intl_last_appearance", "exported_at",
]

TEAM_FIELDS = [
    "team_id", "team_name", "short_name", "country", "wc_group", "venue_id",
    "squad_size", "avg_age", "total_market_value_eur", "avg_market_value_eur",
    "avg_overall_rating", "avg_club_match_rating",
    "avg_attr_defending", "elite_defender_count",
    "squad_club_goals", "squad_club_assists", "squad_club_xg", "squad_club_xa",
    "squad_club_tackles", "squad_club_interceptions", "squad_club_clearances", "squad_club_saves",
    "squad_intl_caps", "squad_intl_goals", "upcoming_fixtures",
    "manager_name", "manager_formation", "manager_tactical_profile",
    "manager_win_pct", "manager_avg_goals_scored", "manager_avg_goals_conceded",
    "manager_clean_sheet_pct", "manager_avg_possession",
    "exported_at",
]

PREDICTION_FIELDS = [
    "event_id", "event_date", "status", "home_team_id", "home_team",
    "away_team_id", "away_team", "prob_home", "prob_draw", "prob_away",
    "predicted_result", "xg_home", "xg_away", "prob_btts_yes", "prob_over_25",
    "most_likely_score", "model_confidence", "exported_at",
]

FIXTURE_FIELDS = [
    "event_id", "event_date", "status", "home_team_id", "home_team",
    "away_team_id", "away_team", "home_score", "away_score",
    "round_number", "venue_id", "exported_at",
]

# Integer counters summed from per-match stat rows
STAT_COUNT_FIELDS = [
    "minutes_played", "goals", "goal_assist", "total_shots", "shots_on_target",
    "key_pass", "total_pass", "accurate_pass",
    "total_tackle", "won_tackle", "interception", "total_clearance", "ball_recovery",
    "blocked_scoring_attempt", "duel_won", "duel_lost", "aerial_won", "aerial_lost",
    "saves", "goals_conceded", "yellow_card", "red_card",
    "won_contest", "total_contest", "total_cross", "total_long_balls", "touches", "fouls",
]

STAT_CSV_MAP = {
    "minutes_played": "club_minutes",
    "goals": "club_goals",
    "goal_assist": "club_assists",
    "total_shots": "club_shots",
    "shots_on_target": "club_shots_on_target",
    "key_pass": "club_key_passes",
    "total_pass": "club_passes",
    "total_tackle": "club_tackles",
    "won_tackle": "club_tackles_won",
    "interception": "club_interceptions",
    "total_clearance": "club_clearances",
    "ball_recovery": "club_ball_recovery",
    "blocked_scoring_attempt": "club_blocks",
    "duel_won": "club_duels_won",
    "duel_lost": "club_duels_lost",
    "aerial_won": "club_aerial_won",
    "aerial_lost": "club_aerial_lost",
    "saves": "club_saves",
    "goals_conceded": "club_goals_conceded",
    "yellow_card": "club_yellow_cards",
    "red_card": "club_red_cards",
    "won_contest": "club_dribbles_won",
    "total_contest": "club_dribbles_attempted",
    "total_cross": "club_crosses",
    "total_long_balls": "club_long_balls",
    "touches": "club_touches",
    "fouls": "club_fouls",
}


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


def _sum_int(rows: list[dict], field: str) -> int:
    total = 0
    for row in rows:
        val = row.get(field)
        if isinstance(val, (int, float)):
            total += int(val)
    return total


def _aggregate_match_stats(rows: list[dict]) -> dict:
    agg = {k: 0 for k in STAT_COUNT_FIELDS}
    xgs: list[float] = []
    xas: list[float] = []
    ratings: list[float] = []

    for row in rows:
        for key in STAT_COUNT_FIELDS:
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

    out = {
        "club_matches": len(rows),
        "club_xg": _round(sum(xgs)) if xgs else None,
        "club_xa": _round(sum(xas)) if xas else None,
        "club_pass_accuracy_pct": pass_pct,
        "club_avg_match_rating": _round(sum(ratings) / len(ratings)) if ratings else None,
        "club_league_id": None,
        "club_season_id": None,
    }
    for src, dst in STAT_CSV_MAP.items():
        out[dst] = agg[src]
    return out


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


async def _fetch_manager(client: httpx.AsyncClient, team_id: int) -> dict:
    resp = await client.get("managers/", params={"team_id": team_id, "limit": 1})
    if resp.status_code != 200:
        return {}
    results = resp.json().get("results") or []
    return results[0] if results else {}


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

    club_name = await names.team_name(club_team_id) or squad_row.get("club")
    league_name = await names.league_name(club_stats.get("club_league_id"))

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


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load_existing_player_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {r["player_id"] for r in csv.DictReader(f) if r.get("player_id")}


def _defender_attr_vals(players: list[dict]) -> list[float]:
    vals = []
    for p in players:
        pos = (p.get("wc_position") or "").upper()
        if pos not in {"DF", "GK"}:
            continue
        v = _safe_float(p.get("attr_defending"))
        if v is not None:
            vals.append(v)
    return vals


def _build_team_rows(
    teams: list[dict],
    squad_meta: dict[int, dict],
    player_rows: list[dict],
    managers: dict[int, dict],
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
        mgr = managers.get(tid, {})

        ages = [a for a in (_safe_float(p.get("age")) for p in players) if a is not None]
        market_vals = [m for m in (_safe_float(p.get("market_value_eur")) for p in players) if m]
        ovr_ratings = [r for r in (_safe_float(p.get("overall_rating")) for p in players) if r]
        match_ratings = [
            r for r in (_safe_float(p.get("club_avg_match_rating")) for p in players) if r
        ]
        def_attrs = _defender_attr_vals(players)
        avg_def = _round(sum(def_attrs) / len(def_attrs), 1) if def_attrs else None
        elite = sum(1 for v in def_attrs if v >= 75)

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
                "avg_attr_defending": avg_def,
                "elite_defender_count": elite,
                "squad_club_goals": sum(int(p.get("club_goals") or 0) for p in players),
                "squad_club_assists": sum(int(p.get("club_assists") or 0) for p in players),
                "squad_club_xg": _round(sum(_safe_float(p.get("club_xg")) or 0 for p in players)),
                "squad_club_xa": _round(sum(_safe_float(p.get("club_xa")) or 0 for p in players)),
                "squad_club_tackles": sum(int(p.get("club_tackles") or 0) for p in players),
                "squad_club_interceptions": sum(int(p.get("club_interceptions") or 0) for p in players),
                "squad_club_clearances": sum(int(p.get("club_clearances") or 0) for p in players),
                "squad_club_saves": sum(int(p.get("club_saves") or 0) for p in players),
                "squad_intl_caps": sum(int(p.get("intl_caps") or 0) for p in players),
                "squad_intl_goals": sum(int(p.get("intl_goals") or 0) for p in players),
                "upcoming_fixtures": meta.get("upcoming_fixtures"),
                "manager_name": mgr.get("name"),
                "manager_formation": mgr.get("preferred_formation"),
                "manager_tactical_profile": mgr.get("tactical_profile"),
                "manager_win_pct": mgr.get("win_pct"),
                "manager_avg_goals_scored": mgr.get("avg_goals_scored"),
                "manager_avg_goals_conceded": mgr.get("avg_goals_conceded"),
                "manager_clean_sheet_pct": mgr.get("clean_sheet_pct"),
                "manager_avg_possession": mgr.get("avg_possession"),
                "exported_at": exported_at,
            }
        )
    return team_rows


def _flatten_prediction(item: dict, exported_at: str) -> dict:
    event = item.get("event") or {}
    markets = item.get("markets") or {}
    mr = markets.get("match_result") or {}
    xg = markets.get("expected_goals") or {}
    ou = markets.get("over_under") or {}
    btts = markets.get("btts") or {}
    score = markets.get("score") or {}
    model = item.get("model") or {}
    return {
        "event_id": event.get("id"),
        "event_date": event.get("event_date"),
        "status": event.get("status"),
        "home_team_id": event.get("home_team_id"),
        "home_team": event.get("home_team"),
        "away_team_id": event.get("away_team_id"),
        "away_team": event.get("away_team"),
        "prob_home": mr.get("prob_home"),
        "prob_draw": mr.get("prob_draw"),
        "prob_away": mr.get("prob_away"),
        "predicted_result": mr.get("predicted"),
        "xg_home": xg.get("home"),
        "xg_away": xg.get("away"),
        "prob_btts_yes": btts.get("prob_yes"),
        "prob_over_25": ou.get("prob_over_25"),
        "most_likely_score": score.get("most_likely"),
        "model_confidence": model.get("confidence"),
        "exported_at": exported_at,
    }


def _flatten_fixture(item: dict, exported_at: str) -> dict:
    return {
        "event_id": item.get("id"),
        "event_date": item.get("event_date"),
        "status": item.get("status"),
        "home_team_id": item.get("home_team_id"),
        "home_team": item.get("home_team"),
        "away_team_id": item.get("away_team_id"),
        "away_team": item.get("away_team"),
        "home_score": item.get("home_score"),
        "away_score": item.get("away_score"),
        "round_number": item.get("round_number"),
        "venue_id": item.get("venue_id"),
        "exported_at": exported_at,
    }


async def _fetch_upcoming_fixtures(client: httpx.AsyncClient, team_id: int) -> int:
    resp = await client.get(f"teams/{team_id}/fixtures/")
    if resp.status_code != 200:
        return 0
    data = resp.json()
    results = data if isinstance(data, list) else data.get("results", [])
    return sum(1 for fx in results if fx.get("status") == "notstarted")


async def export_all(full: bool = False, meta_only: bool = False) -> None:
    api_key = _load_env()
    exported_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing_ids: set[str] = set() if full else _load_existing_player_ids(PLAYERS_CSV)

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

        if not meta_only:
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
            fetched_rows: list[dict] = []
            for batch_start in range(0, len(pending), batch_size):
                batch = pending[batch_start : batch_start + batch_size]
                results = await asyncio.gather(
                    *[_worker(row, team_name, group) for row, team_name, group in batch]
                )
                batch_rows = [r for r in results if r]
                fetched_rows.extend(batch_rows)
                done = min(batch_start + len(batch), len(pending))
                print(f"  progress {done}/{len(pending)}")

            if full:
                _write_csv(PLAYERS_CSV, PLAYER_FIELDS, fetched_rows)
                all_player_rows = fetched_rows
                new_rows = fetched_rows
            else:
                if fetched_rows:
                    if not PLAYERS_CSV.exists():
                        _write_csv(PLAYERS_CSV, PLAYER_FIELDS, fetched_rows)
                    else:
                        with PLAYERS_CSV.open("a", newline="", encoding="utf-8") as f:
                            writer = csv.DictWriter(f, fieldnames=PLAYER_FIELDS, extrasaction="ignore")
                            writer.writerows(fetched_rows)
                new_rows = fetched_rows
                with PLAYERS_CSV.open(encoding="utf-8") as f:
                    all_player_rows = list(csv.DictReader(f))
        else:
            print("Skipping player fetch (--meta-only)")
            if not PLAYERS_CSV.exists():
                print("ERROR: players CSV missing — run full export first")
                sys.exit(1)
            with PLAYERS_CSV.open(encoding="utf-8") as f:
                all_player_rows = list(csv.DictReader(f))
            for team in teams:
                tid = team["id"]
                resp = await client.get(f"worldcup/squads/{tid}/")
                group = resp.json().get("group") or "" if resp.status_code == 200 else ""
                upcoming = await _fetch_upcoming_fixtures(client, tid)
                squad_meta[tid] = {"group": group, "upcoming_fixtures": upcoming}

        print("\nFetching managers...")
        managers: dict[int, dict] = {}
        for team in teams:
            tid = team["id"]
            managers[tid] = await _fetch_manager(client, tid)

        team_rows = _build_team_rows(teams, squad_meta, all_player_rows, managers, exported_at)
        _write_csv(TEAMS_CSV, TEAM_FIELDS, team_rows)

        print("Fetching WC predictions...")
        predictions_raw = await _fetch_all_pages(
            client, f"predictions/?league_id={WORLD_CUP_LEAGUE_ID}"
        )
        prediction_rows = [_flatten_prediction(p, exported_at) for p in predictions_raw]
        _write_csv(PREDICTIONS_CSV, PREDICTION_FIELDS, prediction_rows)

        print("Fetching WC fixtures...")
        fixtures_raw = await _fetch_all_pages(client, f"events/?league_id={WORLD_CUP_LEAGUE_ID}")
        fixture_rows = [_flatten_fixture(f, exported_at) for f in fixtures_raw]
        _write_csv(FIXTURES_CSV, FIXTURE_FIELDS, fixture_rows)

    print(f"\nWrote {len(all_player_rows)} players -> {PLAYERS_CSV}")
    print(f"Wrote {len(team_rows)} teams    -> {TEAMS_CSV}")
    print(f"Wrote {len(prediction_rows)} predictions -> {PREDICTIONS_CSV}")
    print(f"Wrote {len(fixture_rows)} fixtures    -> {FIXTURES_CSV}")
    if not meta_only:
        print(f"New/updated players this run: {len(new_rows)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export bzzoiro World Cup 2026 bulk CSVs")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Re-fetch all squad players (use after schema changes)",
    )
    parser.add_argument(
        "--meta-only",
        action="store_true",
        help="Rebuild teams/predictions/fixtures from existing player CSV",
    )
    args = parser.parse_args()
    if args.full and args.meta_only:
        print("ERROR: use --full or --meta-only, not both")
        sys.exit(1)
    asyncio.run(export_all(full=args.full, meta_only=args.meta_only))


if __name__ == "__main__":
    main()
