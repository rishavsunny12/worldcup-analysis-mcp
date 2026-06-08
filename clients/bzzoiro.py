import asyncio
import logging
from datetime import date

import httpx

from config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://sports.bzzoiro.com/api/v2"
WORLD_CUP_LEAGUE_ID = 27


class BzzoiroClient:
    def __init__(self):
        self._headers = {"Authorization": f"Token {settings.BZZOIRO_KEY}"}

    async def _get(self, path: str, params: dict | None = None) -> dict | list:
        async with httpx.AsyncClient(timeout=15.0) as client:
            url = f"{BASE_URL}/{path.lstrip('/')}"
            resp = await client.get(url, headers=self._headers, params=params or {})
            logger.info(f"bzzoiro {path} | status={resp.status_code}")
            if resp.status_code == 429:
                raise ValueError("API rate limit reached")
            resp.raise_for_status()
            return resp.json()

    async def _fetch_all_pages(self, path: str, params: dict | None = None) -> list[dict]:
        """Collect every page from a paginated list endpoint."""
        base_params = dict(params or {})
        items: list[dict] = []
        offset = 0
        limit = base_params.pop("limit", 200)

        while True:
            page_params = {**base_params, "limit": limit, "offset": offset}
            data = await self._get(path, page_params)
            if isinstance(data, list):
                return data

            batch = data.get("results", data.get("events", data.get("data", [])))
            if not isinstance(batch, list):
                break
            items.extend(batch)

            count = data.get("count")
            if data.get("next"):
                offset += limit
                if count is not None and offset >= count:
                    break
                continue
            if len(batch) < limit:
                break
            offset += limit
            if count is not None and offset >= count:
                break

        return items

    async def get_events_today(self, league_id: int = WORLD_CUP_LEAGUE_ID) -> list[dict]:
        today = date.today().isoformat()
        return await self._fetch_all_pages(
            "events/",
            {"league_id": league_id, "date_from": today, "date_to": today},
        )

    async def get_live_events(
        self,
        league_id: int = WORLD_CUP_LEAGUE_ID,
        team_id: int | None = None,
    ) -> list[dict]:
        params: dict = {"league_id": league_id}
        if team_id is not None:
            params["team_id"] = team_id
        data = await self._get("events/live/", params)
        if isinstance(data, list):
            return data
        return data.get("events", data.get("results", []))

    async def get_event(self, event_id: int) -> dict:
        data = await self._get(f"events/{event_id}/")
        return data if isinstance(data, dict) else {}

    async def get_event_stats(self, event_id: int) -> dict:
        data = await self._get(f"events/{event_id}/stats/")
        return data if isinstance(data, dict) else {}

    async def get_event_incidents(self, event_id: int) -> dict:
        data = await self._get(f"events/{event_id}/incidents/")
        return data if isinstance(data, dict) else {}

    async def get_event_lineups(self, event_id: int) -> dict:
        data = await self._get(f"events/{event_id}/lineups/")
        return data if isinstance(data, dict) else {}

    async def get_event_player_stats(self, event_id: int) -> list[dict]:
        data = await self._get(f"events/{event_id}/player-stats/")
        if isinstance(data, list):
            return data
        return data.get("results", data.get("players", []))

    async def get_events(
        self,
        league_id: int = WORLD_CUP_LEAGUE_ID,
        status: str | None = None,
        team_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        params: dict = {"league_id": league_id}
        if status:
            params["status"] = status
        if team_id is not None:
            params["team_id"] = team_id
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        return await self._fetch_all_pages("events/", params)

    async def get_standings(self, league_id: int = WORLD_CUP_LEAGUE_ID) -> dict:
        data = await self._get(f"leagues/{league_id}/standings/")
        return data if isinstance(data, dict) else {}

    async def get_head_to_head_events(
        self,
        team_a_id: int,
        team_b_id: int,
        last: int = 10,
        league_id: int | None = None,
    ) -> list[dict]:
        """Return finished meetings between two teams, newest first."""
        params: dict = {"team_id": team_a_id, "status": "finished"}
        if league_id is not None:
            params["league_id"] = league_id
        events = await self._fetch_all_pages("events/", params)
        pair = {team_a_id, team_b_id}
        meetings = [
            e
            for e in events
            if {e.get("home_team_id"), e.get("away_team_id")} == pair
        ]
        meetings.sort(key=lambda e: e.get("event_date", ""), reverse=True)
        return meetings[:last]

    async def get_top_scorers(
        self,
        top_n: int = 10,
        league_id: int = WORLD_CUP_LEAGUE_ID,
    ) -> list[dict]:
        """Aggregate goals from finished tournament matches."""
        events = await self.get_events(league_id=league_id, status="finished")
        if not events:
            return []

        totals: dict[int, dict] = {}
        sem = asyncio.Semaphore(5)

        async def _accumulate(event_id: int) -> None:
            async with sem:
                try:
                    rows = await self.get_event_player_stats(event_id)
                except Exception as exc:
                    logger.warning(f"player-stats for event {event_id} failed: {exc}")
                    return
                for row in rows:
                    pid = row.get("player_id") or row.get("id")
                    if pid is None:
                        continue
                    goals = int(row.get("goals") or 0)
                    assists = int(row.get("goal_assist") or row.get("assists") or 0)
                    if goals == 0 and assists == 0:
                        continue
                    bucket = totals.setdefault(
                        int(pid),
                        {
                            "name": row.get("player_name") or row.get("name") or "Unknown",
                            "team": row.get("team_name") or row.get("team") or "?",
                            "goals": 0,
                            "assists": 0,
                        },
                    )
                    bucket["goals"] += goals
                    bucket["assists"] += assists
                    if row.get("player_name"):
                        bucket["name"] = row["player_name"]
                    if row.get("team_name"):
                        bucket["team"] = row["team_name"]

        await asyncio.gather(*[_accumulate(e["id"]) for e in events if e.get("id")])

        ranked = sorted(totals.values(), key=lambda r: (-r["goals"], -r["assists"]))
        return ranked[:top_n]


bzzoiro = BzzoiroClient()
