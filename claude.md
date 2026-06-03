# CLAUDE.md — worldcup-analysis-mcp

This file is read by Claude Code at startup. Follow every instruction here precisely.
Do not deviate from the patterns, naming conventions, or architectural rules defined below.

---

## Project Overview

A FastMCP server exposing 8 FIFA World Cup 2026 analysis tools to MCP-compatible LLM clients.
Provides live scores, xG stats, team form, H2H, group standings, and qualification scenarios.

**Tournament:** June 11 – July 19, 2026 | 48 teams | 104 matches | 12 groups (A–L)
**Runtime:** Python 3.11+ | FastMCP | async/await throughout | two external API sources

---

## Repository Layout

```
worldcup-analysis-mcp/
├── CLAUDE.md                   ← this file
├── .env                        ← never commit, never read directly outside config.py
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── server.py                   ← FastMCP entrypoint, tool registration only
├── config.py                   ← settings, TEAM_ID_MAP, resolve_team_id()
├── clients/
│   ├── __init__.py
│   ├── api_football.py         ← API-Football async HTTP client
│   └── football_data.py        ← football-data.org async HTTP client
├── tools/
│   ├── __init__.py
│   ├── fixtures.py             ← get_today_matches
│   ├── match.py                ← get_live_match, get_match_preview
│   ├── team.py                 ← get_team_form
│   ├── head_to_head.py         ← get_h2h
│   ├── standings.py            ← get_group_standings
│   ├── players.py              ← get_top_scorers
│   └── scenarios.py            ← simulate_group_scenarios
├── cache/
│   └── cache_manager.py        ← TTLCache singleton
└── tests/
    ├── fixtures/               ← saved raw API responses as .json (offline test data)
    └── test_*.py
```

---

## Architecture Rules — Never Violate These

**Rule 1: Clients know APIs. Tools know questions. Never mix them.**
- `clients/` files make HTTP calls, parse response envelopes, raise HTTP errors. Nothing else.
- `tools/` files call clients, apply cache, format output strings. Never make HTTP calls directly.
- If an endpoint changes, you fix `clients/` only. Tool logic stays untouched.

**Rule 2: Every tool function is async.**
- All tool functions use `async def`. All client methods use `async def`.
- Use `asyncio.gather()` any time a tool needs 2+ independent API calls. Never await them sequentially.

**Rule 3: Every tool checks cache before calling a client.**
```python
cached = cache.get("form", team_id=team_id)
if cached:
    return cached
data = await api_football.get_team_stats(team_id)
result = _format_team_form(data)
cache.set("form", result, team_id=team_id)
return result
```

**Rule 4: Tools return formatted strings, not dicts or raw data.**
- The MCP protocol sends tool output directly to the LLM as text.
- Every tool's return type is `str`. Format it to be human-readable.

**Rule 5: API tier routing via env var, never hardcoded.**
```python
import os
TIER = os.getenv("API_FOOTBALL_TIER", "free")  # "free" or "paid"
```
- `free`: route static tools (fixtures list, standings, scorers) to `FootballDataClient`
- `paid`: route all tools to `APIFootballClient`
- Live tools (`get_live_match`) always use `APIFootballClient` regardless of tier

**Rule 6: Team name resolution always goes through `resolve_team_id()`.**
- Never hardcode a team ID in a tool file. Always call `resolve_team_id(name)` from `config.py`.
- If it returns `None`, return a helpful error string: `"Team '{name}' not found. Try full name (e.g. 'South Korea', 'United States')."`

**Rule 7: Never commit secrets.**
- `.env` is in `.gitignore`. Config values come from `os.getenv()` only.
- `config.py` reads env vars at import time and exposes them as typed constants.

---

## Environment Variables

```bash
# Required
API_FOOTBALL_KEY=           # api-sports.io key
FOOTBALL_DATA_KEY=          # football-data.org token

# Tier routing
API_FOOTBALL_TIER=free      # "free" during dev, "paid" from June 11 onward

# Cache TTLs (seconds) — these are defaults, override via env
CACHE_TTL_LIVE=30
CACHE_TTL_LINEUPS=300
CACHE_TTL_FORM=3600
CACHE_TTL_FIXTURES=86400
CACHE_TTL_STANDINGS=300
CACHE_TTL_H2H=3600
CACHE_TTL_SCORERS=300
```

---

## External APIs

### API-Football (api-sports.io)

```
Base URL:     https://v3.football.api-sports.io
Auth header:  x-apisports-key: {API_FOOTBALL_KEY}
World Cup:    league=1, season=2026
Free tier:    100 req/day — use sparingly during dev
Paid tier:    7,500 req/day — active from June 11

Response envelope (always unwrap before returning):
{
  "response": [...],   ← the actual data
  "results": N,
  "errors": []         ← non-empty means failure
}

Rate limit header to log: x-ratelimit-requests-remaining
```

Endpoints used:

| Method | Endpoint | Params |
|---|---|---|
| get_fixtures_today | /fixtures | league=1, season=2026, date=YYYY-MM-DD |
| get_fixture | /fixtures | id={fixture_id} |
| get_live_fixtures | /fixtures | league=1, season=2026, live=all |
| get_fixture_stats | /fixtures/statistics | fixture={fixture_id} |
| get_fixture_events | /fixtures/events | fixture={fixture_id} |
| get_fixture_lineups | /fixtures/lineups | fixture={fixture_id} |
| get_team_stats | /teams/statistics | league=1, season=2026, team={team_id} |
| get_h2h | /fixtures/headtohead | h2h={a}-{b}, last={n} |
| get_standings | /standings | league=1, season=2026 |
| get_top_scorers | /players/topscorers | league=1, season=2026 |

### football-data.org

```
Base URL:     https://api.football-data.org/v4
Auth header:  X-Auth-Token: {FOOTBALL_DATA_KEY}
World Cup:    competition_code=WC
Free tier:    10 req/min, no daily cap — use freely during dev

Response structure differs from API-Football:
  fixtures → response.matches[]
  standings → response.standings[0].table[]
```

Endpoints used:

| Method | Endpoint |
|---|---|
| get_matches | /competitions/WC/matches |
| get_standings | /competitions/WC/standings |
| get_scorers | /competitions/WC/scorers |

---

## config.py — Required Contents

Must contain:

1. **Settings class** — typed constants from env vars:
```python
class Settings:
    API_FOOTBALL_KEY: str = os.getenv("API_FOOTBALL_KEY", "")
    FOOTBALL_DATA_KEY: str = os.getenv("FOOTBALL_DATA_KEY", "")
    TIER: str = os.getenv("API_FOOTBALL_TIER", "free")
    CACHE_TTL_LIVE: int = int(os.getenv("CACHE_TTL_LIVE", 30))
    CACHE_TTL_LINEUPS: int = int(os.getenv("CACHE_TTL_LINEUPS", 300))
    CACHE_TTL_FORM: int = int(os.getenv("CACHE_TTL_FORM", 3600))
    CACHE_TTL_FIXTURES: int = int(os.getenv("CACHE_TTL_FIXTURES", 86400))
    CACHE_TTL_STANDINGS: int = int(os.getenv("CACHE_TTL_STANDINGS", 300))
    CACHE_TTL_H2H: int = int(os.getenv("CACHE_TTL_H2H", 3600))
    CACHE_TTL_SCORERS: int = int(os.getenv("CACHE_TTL_SCORERS", 300))

settings = Settings()
```

2. **TEAM_ID_MAP** — all 48 qualified teams with common aliases:
```python
TEAM_ID_MAP: dict[str, int] = {
    # Generate by calling: GET /teams?league=1&season=2026
    # then hardcode here. IDs are stable across seasons.
    "argentina": 26,
    "france": 2,
    "brazil": 6,
    ...
    # Aliases
    "usa": 2036,
    "united states": 2036,
    "us": 2036,
    "south korea": 149,
    "korea": 149,
    "netherlands": 1118,
    "holland": 1118,
    ...
}
```

3. **resolve_team_id()** — fuzzy name resolver:
```python
def resolve_team_id(name: str) -> int | None:
    key = name.lower().strip()
    if key in TEAM_ID_MAP:
        return TEAM_ID_MAP[key]
    for k, v in TEAM_ID_MAP.items():
        if key in k or k in key:
            return v
    return None
```

4. **GROUP_MAP** — maps group letter to list of team IDs (populate after generating TEAM_ID_MAP):
```python
GROUP_MAP: dict[str, list[int]] = {
    "A": [...],
    "B": [...],
    ...
    "L": [...]
}
```

---

## cache_manager.py — Required Implementation

```python
from cachetools import TTLCache
from config import settings
import hashlib, json

class CacheManager:
    def __init__(self):
        self._caches = {
            "live":      TTLCache(maxsize=50,  ttl=settings.CACHE_TTL_LIVE),
            "lineups":   TTLCache(maxsize=100, ttl=settings.CACHE_TTL_LINEUPS),
            "form":      TTLCache(maxsize=100, ttl=settings.CACHE_TTL_FORM),
            "fixtures":  TTLCache(maxsize=10,  ttl=settings.CACHE_TTL_FIXTURES),
            "standings": TTLCache(maxsize=20,  ttl=settings.CACHE_TTL_STANDINGS),
            "h2h":       TTLCache(maxsize=200, ttl=settings.CACHE_TTL_H2H),
            "scorers":   TTLCache(maxsize=5,   ttl=settings.CACHE_TTL_SCORERS),
        }
        self._hits = {k: 0 for k in self._caches}
        self._misses = {k: 0 for k in self._caches}

    def _key(self, **kwargs) -> str:
        return hashlib.md5(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()

    def get(self, cache_name: str, **kwargs):
        key = self._key(**kwargs)
        val = self._caches[cache_name].get(key)
        if val is not None:
            self._hits[cache_name] += 1
        else:
            self._misses[cache_name] += 1
        return val

    def set(self, cache_name: str, value, **kwargs):
        key = self._key(**kwargs)
        self._caches[cache_name][key] = value

    def stats(self) -> dict:
        return {k: {"hits": self._hits[k], "misses": self._misses[k]}
                for k in self._caches}

cache = CacheManager()  # module-level singleton — import this everywhere
```

---

## Tool Specifications

### `get_today_matches() -> str`
**File:** `tools/fixtures.py`
**Cache:** `fixtures`, TTL 30s if any live match, 300s otherwise
**Tier routing:** `free` → `FootballDataClient.get_matches(date=today)` | `paid` → `APIFootballClient.get_fixtures_today()`
**Logic:**
- Fetch all matches for today (UTC date)
- Bucket into LIVE (status: 1H/2H/HT/ET/P), UPCOMING (NS), FINISHED (FT/AET/PEN)
- If no matches today, return `"No World Cup matches scheduled today."`

**Output format:**
```
📅 TODAY'S WORLD CUP MATCHES — {date}

🔴 LIVE
  {Team A} vs {Team B} | {minute}' | {score} | {venue}

⏰ UPCOMING
  {Team A} vs {Team B} | {time} UTC | {venue}

✅ FINISHED
  {Team A} vs {Team B} | FT {score}
```

---

### `get_live_match(team: str) -> str`
**File:** `tools/match.py`
**Cache:** `live`, TTL 30s
**Tier routing:** Always `APIFootballClient` (football-data.org has no live scores)
**Logic:**
1. Call `get_live_fixtures()`, find fixture where either team name matches
2. If not found: return `"{team} is not currently playing. Use get_today_matches() to see today's schedule."`
3. Use `asyncio.gather()` to fetch stats + events + lineups in parallel
4. Parse xG from stats where `type == "expected_goals"`
5. Sort events by minute desc, show last 5

**Output format:**
```
🔴 LIVE: {Team A} vs {Team B} | {minute}' | Group {X}

SCORE: {Team A} {score_a} — {score_b} {Team B}
  ⚽ {minute}' {scorer} [{team}]

📊 LIVE STATS          {A}    {B}
  xG:                {xg_a}  {xg_b}
  Shots:             {s_a}   {s_b}
  On Target:         {ot_a}  {ot_b}
  Possession:        {p_a}%  {p_b}%
  Corners:           {c_a}   {c_b}

🟨 CARDS
  {player} ({team}) — {color} {minute}'

🔄 LAST 5 EVENTS
  {minute}' {event_description}
```

---

### `get_match_preview(team_a: str, team_b: str) -> str`
**File:** `tools/match.py`
**Cache:** `form`, TTL 3600s, key includes both team IDs
**Logic:**
1. Resolve both team names — return error if either is `None`
2. `asyncio.gather(api_football.get_team_stats(id_a), api_football.get_team_stats(id_b), api_football.get_h2h(id_a, id_b, last=10))`
3. Extract from team stats: fixtures W/D/L, goals for/against, xG for/against, possession avg, clean sheets
4. Build form string from last 5 fixtures results: `"W W D W L"`
5. From H2H: count wins each side, draws, total goals, flag WC meetings with 🏆
6. xG differential label: `>+0.8` → "dominant", `±0.3` → "balanced", `<-0.3` → "under pressure"

**Output format:**
```
⚽ MATCH PREVIEW: {Team A} vs {Team B}
🏆 FIFA World Cup 2026 — {stage} | {date} {time} UTC

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 FORM (Last 5 WC matches)
  {Team A}:  {form}  ▸ {gf} scored, {ga} conceded
  {Team B}:  {form}  ▸ {gf} scored, {ga} conceded

📈 xG PROFILE (2026 WC)
  {Team A} → xGF {xgf} | xGA {xga} | Diff {diff} ({label})
  {Team B} → xGF {xgf} | xGA {xga} | Diff {diff} ({label})

🤝 HEAD TO HEAD (Last 10 meetings)
  {Team A} {aW}W — {d}D — {bW}W {Team B}
  Goals: {A} {ag} — {bg} {B}
  Last match: {result}

🎯 KEY STATS
               {Team A}    {Team B}
  Possession:   {p_a}%      {p_b}%
  Shots/game:   {s_a}       {s_b}
  Clean sheets: {cs_a}%     {cs_b}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📍 Venue: {venue}, {city}
```

---

### `get_team_form(team: str, last_n: int = 5) -> str`
**File:** `tools/team.py`
**Cache:** `form`, TTL 3600s
**Constraints:** Clamp `last_n` to range 1–10
**Logic:** Fetch `api_football.get_team_stats(team_id)`. Extract aggregate stats + last N fixture results.

**Output format:**
```
📋 {TEAM} — World Cup 2026 Form

RECORD: P{p} W{w} D{d} L{l} | GF {gf} | GA {ga}

FORM STREAK: {form_string} (last {n} WC matches)

📈 xG PROFILE
  xG For avg:     {xgf} per match
  xG Against avg: {xga} per match
  xG Diff:        {diff} ({label})

🎯 ATTACKING
  Goals/match: {gpm} | Shots/match: {spm} | On target: {ot}%

🛡️ DEFENSIVE
  Goals conceded/match: {gcpm} | Clean sheets: {cs}%

LAST {n} MATCHES
  {result} {score} vs {opponent} | xG {xgf_match} vs {xga_match}
  ...
```

---

### `get_h2h(team_a: str, team_b: str, last_n: int = 10) -> str`
**File:** `tools/head_to_head.py`
**Cache:** `h2h`, TTL 3600s
**Constraints:** Clamp `last_n` to range 1–15
**Logic:** Fetch `api_football.get_h2h(id_a, id_b, last=last_n)`. Compute: wins per side, draws, goals per side, avg goals/game. Flag WC meetings with 🏆.

**Output format:**
```
🤝 HEAD TO HEAD: {Team A} vs {Team B}
Last {n} meetings

RECORD
  {Team A}: {aW} wins
  Draws:    {d}
  {Team B}: {bW} wins

GOALS
  {Team A} {ag} — {bg} {Team B} ({avg} per game avg)

RESULTS
  🏆 Jun 2022 | {Team A} 1–0 {Team B} (World Cup, Group Stage)
     Mar 2023 | {Team B} 2–1 {Team A} (Friendly)
  ...
```

---

### `get_group_standings(group: str = "all") -> str`
**File:** `tools/standings.py`
**Cache:** `standings`, TTL 300s
**Tier routing:** `free` → `FootballDataClient.get_standings()` | `paid` → `APIFootballClient.get_standings()`
**Constraints:** Accept group as A–L (case-insensitive) or "all"

**Qualification markers:**
- Top 2 in group → ✅ Qualified
- 3rd place → 🟡 (potential best third-place — 8+ pts generally safe)
- 4th place → ❌ Eliminated (if mathematically impossible)

**Output format (single group):**
```
📊 GROUP {X} STANDINGS

Pos  Team          P  W  D  L  GF  GA  GD  Pts
1.   {Team}  ✅   {p} {w} {d} {l} {gf} {ga} {gd} {pts}
2.   {Team}  ✅   ...
3.   {Team}  🟡   ...
4.   {Team}  ❌   ...
```

---

### `get_top_scorers(top_n: int = 10) -> str`
**File:** `tools/players.py`
**Cache:** `scorers`, TTL 300s
**Constraints:** Clamp `top_n` to range 1–20
**Tier routing:** `free` → `FootballDataClient.get_scorers()` | `paid` → `APIFootballClient.get_top_scorers()`

**Output format:**
```
⚽ GOLDEN BOOT — FIFA World Cup 2026

🥇 1.  {Player}  ({Team})  —  {goals} goals  {assists} assists
🥈 2.  {Player}  ({Team})  —  {goals} goals
🥉 3.  {Player}  ({Team})  —  {goals} goals
   4.  {Player}  ({Team})  —  {goals} goals
   ...
```

---

### `simulate_group_scenarios(group: str, team: str) -> str`
**File:** `tools/scenarios.py`
**Cache:** None — always recompute (standings change after every match)
**Logic:**

```python
# 1. Fetch current standings for the group (call get_group_standings internally)
# 2. Fetch remaining fixtures for that group from today onwards
# 3. Enumerate all outcome combinations for remaining fixtures
#    Each fixture has 3 outcomes: home_win, draw, away_win
#    Points delta: win=3, draw=1, loss=0
# 4. For each combination, compute final points table
# 5. Apply tiebreakers in order: points → goal difference → goals scored
# 6. Team qualifies if: position <= 2, OR position == 3 with pts >= 4
#    (Note: exact best-third rules TBD by FIFA — use 4pts as conservative threshold)
# 7. Classify each combination as: QUALIFIES / ELIMINATED / DEPENDS
# 8. Return plain English summary of what the team needs
```

**Output format:**
```
🔮 QUALIFICATION SCENARIOS — {Team} | Group {X}

CURRENT STANDING: {pos} place, {pts} pts, {matches_remaining} match(es) remaining

✅ QUALIFY IF:
  • Win vs {Opponent} (regardless of other results)
  • Draw vs {Opponent} AND {Other Team} beats {Other Team}

❌ ELIMINATED IF:
  • Lose vs {Opponent} AND {Other Match} ends in draw

🎯 SUMMARY:
  {Plain English: "Mexico need a win to guarantee qualification. A draw keeps
  them alive only if Poland fail to beat Argentina."}
```

---

## server.py — Exact Structure

```python
import logging
from fastmcp import FastMCP
from config import settings
from tools.fixtures import get_today_matches
from tools.match import get_live_match, get_match_preview
from tools.team import get_team_form
from tools.head_to_head import get_h2h
from tools.standings import get_group_standings
from tools.players import get_top_scorers
from tools.scenarios import simulate_group_scenarios

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOOLS = [
    get_today_matches,
    get_live_match,
    get_match_preview,
    get_team_form,
    get_h2h,
    get_group_standings,
    get_top_scorers,
    simulate_group_scenarios,
]

mcp = FastMCP(
    name="worldcup-analysis-mcp",
    instructions="""
You are a FIFA World Cup 2026 analysis assistant backed by live tournament data.
The tournament runs June 11 – July 19, 2026 across USA, Canada, and Mexico.
Format: 48 teams, 12 groups (A–L), top 2 per group + best 8 third-place teams advance (32 total).

Available tools:
- get_today_matches       → today's schedule and live scores
- get_live_match          → real-time stats for an ongoing match
- get_match_preview       → full pre-match analysis (form, xG, H2H)
- get_team_form           → a team's stats and form streak this tournament
- get_h2h                 → head-to-head history between two national teams
- get_group_standings     → current group tables with qualification status
- get_top_scorers         → Golden Boot leaderboard
- simulate_group_scenarios → what a team needs to qualify from their group

ALWAYS call a tool before answering any question about:
- current standings, points, or group positions
- live or recent match scores
- team form, xG, or stats this tournament
- qualification status or scenarios
Never answer these from training data — the tournament is live.
    """
)

for tool in TOOLS:
    mcp.tool()(tool)

logger.info(f"worldcup-analysis-mcp started | {len(TOOLS)} tools | tier={settings.TIER}")

if __name__ == "__main__":
    mcp.run()
```

---

## requirements.txt

```
fastmcp>=0.9.0
httpx>=0.27.0
python-dotenv>=1.0.0
cachetools>=5.3.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

---

## Testing Rules

1. **No live API calls in unit tests.** All unit tests load from `tests/fixtures/*.json`.
2. **Integration tests** are marked `@pytest.mark.integration` and run manually only.
3. **Every tool has at least 3 unit tests:**
   - Happy path with valid input
   - Invalid team name → correct error string returned
   - Cache hit → client method not called twice
4. **Fixture JSON files** are named: `{client}_{endpoint}_{context}.json`
   e.g. `api_football_team_stats_brazil.json`, `football_data_standings_wc.json`

---

## Error Handling Contracts

Every tool must handle these cases explicitly — never let an exception propagate to the MCP caller:

| Error Case | Expected Return |
|---|---|
| Team name not found | `"Team '{name}' not found. Try full name (e.g. 'South Korea', 'United States')."` |
| No live match for team | `"{team} is not currently playing. Use get_today_matches() to see today's schedule."` |
| API returns empty response | `"No data available for {context}. The tournament may not have started yet."` |
| API quota exceeded (429) | `"API rate limit reached. Data will refresh shortly — please retry in 60 seconds."` |
| Network timeout | `"Could not reach data source. Check your connection and retry."` |
| Invalid group letter | `"Invalid group '{group}'. Use A through L, or 'all'."` |

---

## Claude Desktop Connection

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "worldcup-analysis-mcp": {
      "command": "python",
      "args": ["/absolute/path/to/worldcup-analysis-mcp/server.py"],
      "env": {
        "API_FOOTBALL_KEY": "your_key_here",
        "FOOTBALL_DATA_KEY": "your_key_here",
        "API_FOOTBALL_TIER": "free"
      }
    }
  }
}
```

Change `API_FOOTBALL_TIER` to `"paid"` on June 11 and restart Claude Desktop.

---

## Build Order (Follow Exactly)

### Phase 1A — Foundation
```
1. Create full directory structure with empty __init__.py files
2. requirements.txt
3. .env.example with all variables listed
4. .gitignore (include .env, __pycache__, .pytest_cache, *.pyc)
5. config.py — Settings class + TEAM_ID_MAP stub (10 teams) + resolve_team_id()
6. cache/cache_manager.py — full implementation
7. clients/api_football.py — base get() + 3 endpoints (get_fixtures_today, get_standings, get_team_stats)
8. clients/football_data.py — get_standings() + get_matches()
```

### Phase 1B — Static Tools
```
9.  tools/standings.py → get_group_standings
10. tools/team.py → get_team_form
11. tools/fixtures.py → get_today_matches
12. tools/head_to_head.py → get_h2h
13. tools/players.py → get_top_scorers
14. server.py — register all 5 static tools
15. Smoke test in Claude Desktop: "Show Group A standings"
```

### Phase 1C — Live Tools + Scenarios
```
16. Add remaining client methods to api_football.py
    (get_fixture, get_live_fixtures, get_fixture_stats, get_fixture_events,
     get_fixture_lineups, get_h2h, get_top_scorers)
17. tools/match.py → get_live_match (with asyncio.gather)
18. tools/match.py → get_match_preview (with asyncio.gather)
19. tools/scenarios.py → simulate_group_scenarios
20. Complete TEAM_ID_MAP for all 48 teams
21. Add all tools to server.py
22. Write unit tests for all tools
23. README.md
24. git push
```

---

## Coding Standards

- **Imports:** stdlib → third-party → local, separated by blank lines
- **Type hints:** required on all function signatures
- **Docstrings:** every tool function needs a docstring — it becomes the MCP tool description
- **Logging:** use `logging` module, not `print`. Log at INFO for cache hits/misses, WARNING for API errors.
- **Line length:** 100 chars max
- **String formatting:** f-strings only, no `.format()` or `%`
- **No global mutable state** outside of the `cache` singleton and `settings` singleton

---

## Debugging Commands

```bash
# Test a single tool without Claude Desktop
python -c "
import asyncio
from tools.standings import get_group_standings
result = asyncio.run(get_group_standings('A'))
print(result)
"

# Check remaining API quota
python -c "
import asyncio, httpx, os
from dotenv import load_dotenv
load_dotenv()
async def check():
    async with httpx.AsyncClient() as c:
        r = await c.get('https://v3.football.api-sports.io/status',
                        headers={'x-apisports-key': os.getenv('API_FOOTBALL_KEY')})
        print(r.json())
asyncio.run(check())
"

# Run only unit tests (no API calls)
pytest tests/ -m "not integration" -v

# Run integration tests manually (costs API quota)
pytest tests/test_integration.py -m integration -v
```

---

## Phase 2 Additions (Do Not Build in Phase 1)

- `tools/odds.py` — The-Odds-API integration, EV calculation, Kelly sizing
- `tools/compare.py` — `compare_teams(team_a, team_b)` side-by-side analytical table
- `tools/bracket.py` — knockout bracket tracker, path-to-final simulator
- `tools/players_detail.py` — player-level xG, key passes, heatmaps (requires API-Football Ultra)
