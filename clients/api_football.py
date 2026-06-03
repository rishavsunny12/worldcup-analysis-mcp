import logging
from datetime import date

import httpx

from config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://v3.football.api-sports.io"
LEAGUE = 1
SEASON = 2026


class APIFootballClient:
    def __init__(self):
        self._headers = {"x-apisports-key": settings.API_FOOTBALL_KEY}

    async def _get(self, endpoint: str, params: dict) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{BASE_URL}{endpoint}"
            resp = await client.get(url, headers=self._headers, params=params)
            remaining = resp.headers.get("x-ratelimit-requests-remaining", "?")
            logger.info(f"API-Football {endpoint} | remaining={remaining}")
            resp.raise_for_status()
            data = resp.json()
            if data.get("errors"):
                raise ValueError(f"API-Football error: {data['errors']}")
            return data

    async def get_fixtures_today(self) -> dict:
        today = date.today().isoformat()
        return await self._get("/fixtures", {"league": LEAGUE, "season": SEASON, "date": today})

    async def get_fixture(self, fixture_id: int) -> dict:
        return await self._get("/fixtures", {"id": fixture_id})

    async def get_live_fixtures(self) -> dict:
        return await self._get("/fixtures", {"league": LEAGUE, "season": SEASON, "live": "all"})

    async def get_fixture_stats(self, fixture_id: int) -> dict:
        return await self._get("/fixtures/statistics", {"fixture": fixture_id})

    async def get_fixture_events(self, fixture_id: int) -> dict:
        return await self._get("/fixtures/events", {"fixture": fixture_id})

    async def get_fixture_lineups(self, fixture_id: int) -> dict:
        return await self._get("/fixtures/lineups", {"fixture": fixture_id})

    async def get_team_stats(self, team_id: int) -> dict:
        return await self._get("/teams/statistics", {"league": LEAGUE, "season": SEASON, "team": team_id})

    async def get_h2h(self, team_a: int, team_b: int, last: int = 10) -> dict:
        return await self._get("/fixtures/headtohead", {"h2h": f"{team_a}-{team_b}", "last": last})

    async def get_standings(self) -> dict:
        return await self._get("/standings", {"league": LEAGUE, "season": SEASON})

    async def get_top_scorers(self) -> dict:
        return await self._get("/players/topscorers", {"league": LEAGUE, "season": SEASON})


api_football = APIFootballClient()
