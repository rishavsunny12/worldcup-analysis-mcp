"""Quick script to explore bzzoiro API endpoints and see raw response shapes."""
import csv
import os
from pathlib import Path

import httpx

# Load .env manually without needing python-dotenv
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    for _line in open(_env_path):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

KEY = os.getenv("BZZOIRO_KEY", "")
BASE = "https://sports.bzzoiro.com/api/v2"
HEADERS = {"Authorization": f"Token {KEY}"}

def fetch_all_pages(path: str) -> list[dict]:
    """Fetch every page from a paginated bzzoiro list endpoint."""
    url = f"{BASE}{path}"
    items: list[dict] = []
    while url:
        r = httpx.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            items.extend(data)
            break
        items.extend(data.get("results", data.get("data", [])))
        url = data.get("next")
    return items


def print_all_leagues():
    print(f"\n{'='*60}")
    print(f"GET {BASE}/leagues/  (all pages)")
    print("="*60)
    try:
        leagues = fetch_all_pages("/leagues/")
        print(f"Total leagues: {len(leagues)}\n")
        for i, league in enumerate(leagues, 1):
            season = league.get("current_season") or {}
            season_name = (season.get("name") or "—")
            active = "active" if league.get("is_active") else "inactive"
            women = " (women)" if league.get("is_women") else ""
            print(
                f"{i:3}. [{league.get('id')}] {league.get('name')}{women}"
                f"  |  {league.get('country', '—')}  |  {active}"
                f"  |  season: {season_name}"
            )
    except Exception as e:
        print(f"Error: {e}")


WORLD_CUP_LEAGUE_ID = 27


def print_world_cup_teams():
    path = f"/teams/?in_competition=true&league_id={WORLD_CUP_LEAGUE_ID}"
    print(f"\n{'='*60}")
    print(f"GET {BASE}{path}")
    print("="*60)
    try:
        teams = fetch_all_pages(path)
        teams.sort(key=lambda t: (t.get("name") or "").lower())
        print(f"Total teams: {len(teams)}\n")
        for i, team in enumerate(teams, 1):
            short = team.get("short_name") or team.get("name", "—")
            country = team.get("country") or "—"
            print(
                f"{i:3}. [{team.get('id')}] {team.get('name')}"
                f"  ({short})  |  {country}"
            )
    except Exception as e:
        print(f"Error: {e}")


def fetch_team_squad(team_id: int) -> tuple[list[dict], str]:
    """Return squad players and which endpoint supplied them."""
    r = httpx.get(f"{BASE}/worldcup/squads/{team_id}/", headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    players = data.get("results") or data.get("players") or []
    if players:
        return players, "worldcup_squads"

    r = httpx.get(f"{BASE}/teams/{team_id}/squad/", headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    players = data.get("players") or []
    if players:
        return players, "squad"
    return fetch_all_pages(f"/players/?national_team_id={team_id}"), "national_team_id"


def export_world_cup_squads_csv(output_path: str | Path = "worldcup_squad_players.csv") -> Path:
    """Fetch every WC team squad and write player/team ids to CSV."""
    output = Path(output_path)
    teams_path = f"/teams/?in_competition=true&league_id={WORLD_CUP_LEAGUE_ID}"
    teams = fetch_all_pages(teams_path)
    teams.sort(key=lambda t: (t.get("name") or "").lower())

    rows: list[dict[str, str | int]] = []
    source_counts = {"worldcup_squads": 0, "squad": 0, "national_team_id": 0}

    print(f"\n{'='*60}")
    print(f"Exporting World Cup squads -> {output.resolve()}")
    print("="*60)

    for i, team in enumerate(teams, 1):
        team_id = team["id"]
        team_name = team.get("name") or ""
        players, source = fetch_team_squad(team_id)
        source_counts[source] += 1
        print(f"{i:2}/{len(teams)} {team_name} [{team_id}] -> {len(players)} players ({source})")

        for player in players:
            rows.append(
                {
                    "player_id": player.get("player_id") or player["id"],
                    "player_name": player.get("name") or "",
                    "team_id": player.get("team_id") or team_id,
                    "team_name": team_name,
                }
            )

    rows.sort(key=lambda r: (str(r["team_name"]).lower(), str(r["player_name"]).lower()))

    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["player_id", "player_name", "team_id", "team_name"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"\nWrote {len(rows)} players from {len(teams)} teams "
        f"(worldcup_squads: {source_counts['worldcup_squads']}, "
        f"squad fallback: {source_counts['squad']}, "
        f"national_team_id fallback: {source_counts['national_team_id']})"
    )
    return output


if __name__ == "__main__":
    if not KEY:
        print("ERROR: BZZOIRO_KEY not found in .env")
        raise SystemExit(1)
    export_world_cup_squads_csv()
