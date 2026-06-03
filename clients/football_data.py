import logging
from datetime import date

import httpx

from config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.football-data.org/v4"
COMPETITION = "WC"


class FootballDataClient:
    def __init__(self):
        self._headers = {"X-Auth-Token": settings.FOOTBALL_DATA_KEY}

    async def _get(self, endpoint: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{BASE_URL}{endpoint}"
            resp = await client.get(url, headers=self._headers, params=params or {})
            logger.info(f"FootballData {endpoint} | status={resp.status_code}")
            resp.raise_for_status()
            return resp.json()

    async def get_matches(self, date_from: str | None = None, date_to: str | None = None) -> dict:
        params: dict = {}
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        if not date_from and not date_to:
            today = date.today().isoformat()
            params["dateFrom"] = today
            params["dateTo"] = today
        return await self._get(f"/competitions/{COMPETITION}/matches", params)

    async def get_standings(self) -> dict:
        return await self._get(f"/competitions/{COMPETITION}/standings")

    async def get_scorers(self, limit: int = 20) -> dict:
        return await self._get(f"/competitions/{COMPETITION}/scorers", {"limit": limit})

    async def get_team_squad(self, team_id: int) -> dict:
        return await self._get(f"/teams/{team_id}")


football_data = FootballDataClient()
