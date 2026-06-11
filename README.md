# worldcup-analysis-mcp

A [FastMCP](https://github.com/jlowin/fastmcp) server that gives LLM clients live, data-backed tools for FIFA World Cup 2026 analysis — fixtures, live scores, standings, xG, squad depth, qualification scenarios, and more.

**Tournament:** June 11 – July 19, 2026 · 48 teams · 12 groups (A–L) · USA, Canada, Mexico

Connect from **Claude Desktop**, **Cursor**, or any MCP-compatible client. Deploy to **Railway** with OAuth for a shared remote endpoint.

---

## What it does

Instead of guessing from training data, the assistant calls tools that fetch real tournament and squad data, then returns human-readable formatted text.

| Category | Tools |
|----------|-------|
| **Live & fixtures** | `get_today_matches`, `get_live_match`, `get_fixtures_range`, `get_team_fixtures` |
| **Match analysis** | `get_match_preview`, `get_h2h` |
| **Tournament state** | `get_group_standings`, `get_group_overview`, `get_top_scorers`, `simulate_group_scenarios` |
| **Team & squad** | `get_team_form`, `analyze_team_for_worldcup`, `compare_teams_for_worldcup`, `get_tournament_favorites` |
| **Player search** | `get_player_club_stats`, `get_nation_top_performers`, `get_nation_top_defenders`, `get_squad_league_breakdown`, `search_players` |

**19 tools** total. Each tool's MCP description comes from its function docstring in `tools/*.py`.

---

## Architecture

```
LLM client (Claude / Cursor)
        │
        ▼
   server.py          ← FastMCP entrypoint, tool registration, server instructions
        │
   tools/*.py         ← Business logic, caching, formatted string output
        │
   ┌────┴────────────────────────────┐
   ▼                                 ▼
clients/bzzoiro.py              data/loader.py
(live WC data)                  (pre-loaded CSVs: bzzoiro squads,
                                 understat xG, ML predictions)
   │
clients/api_football.py         clients/football_data.py
(legacy / paid tier)            (legacy free tier)
```

**Design rules**

- **Clients know APIs. Tools know questions.** HTTP lives in `clients/`; tools never call APIs directly.
- **Every tool is async** and returns a **formatted string** (not raw JSON).
- **Cache before fetch** via `cache/cache_manager.py` (TTL per data type).
- **Team names** resolve through `resolve_team_id()` in `config.py` (48 nations + aliases).

### Data sources

| Source | Used for |
|--------|----------|
| **[bzzoiro](https://sports.bzzoiro.com)** (default) | Live scores, standings, fixtures, H2H, form, ML predictions |
| **Pre-loaded CSVs** (`data/`, repo root) | Squad rosters, 2025–26 club xG (Understat top-6 leagues), defending ratings, fixture predictions |
| **API-Football** / **football-data.org** | Legacy mode (`LIVE_DATA_SOURCE=legacy`) and `get_match_preview` |

Set `LIVE_DATA_SOURCE=bzzoiro` (default) for tournament day operations.

---

## Quick start

### Requirements

- Python 3.11+
- API keys (see [Environment variables](#environment-variables))

### Install

```bash
git clone https://github.com/YOUR_USERNAME/worldcup-analysis-mcp.git
cd worldcup-analysis-mcp
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

### Run locally (stdio — Claude Desktop)

```bash
python server.py
```

### Run HTTP (no auth)

```bash
python server.py --http
# MCP endpoint: http://localhost:8000/mcp
```

### Run HTTP + OAuth (production)

```bash
python server.py --sse
# Requires BASE_URL or RAILWAY_PUBLIC_DOMAIN — see docs/OAUTH.md
```

---

## Connect an MCP client

### Claude Desktop

Edit your config:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "worldcup-analysis-mcp": {
      "command": "python",
      "args": ["C:/absolute/path/to/worldcup-analysis-mcp/server.py"],
      "env": {
        "API_FOOTBALL_KEY": "your_key",
        "FOOTBALL_DATA_KEY": "your_key",
        "BZZOIRO_KEY": "your_key",
        "LIVE_DATA_SOURCE": "bzzoiro",
        "API_FOOTBALL_TIER": "free"
      }
    }
  }
}
```

Use the full absolute path to `server.py`. Restart Claude Desktop after saving.

### Cursor

Add the same server under **Settings → MCP**, or point at your deployed Railway URL with OAuth (see [docs/OAUTH.md](docs/OAUTH.md)).

### Remote (Railway)

Deploy with the included `Procfile` (`python server.py --sse`). Full setup: [docs/RAILWAY.md](docs/RAILWAY.md).

---

## Environment variables

Copy `.env.example` to `.env` and fill in values.

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `BZZOIRO_KEY` | Yes | — | Live tournament data (default source) |
| `API_FOOTBALL_KEY` | Yes* | — | Legacy live tools / `get_match_preview` |
| `FOOTBALL_DATA_KEY` | Yes* | — | Legacy free-tier fixtures & standings |
| `LIVE_DATA_SOURCE` | No | `bzzoiro` | `bzzoiro` or `legacy` |
| `API_FOOTBALL_TIER` | No | `free` | `free` or `paid` (legacy routing only) |
| `BASE_URL` | OAuth only | — | Public URL for OAuth discovery |
| `OAUTH_DB_PATH` | No | `data/oauth.db` | SQLite path for token persistence |
| `CACHE_TTL_*` | No | see `.env.example` | Per-cache TTL overrides (seconds) |
| `CACHE_BUST` | No | — | Set `1` once to clear in-memory caches on startup |

\* Required when `LIVE_DATA_SOURCE=legacy` or when using `get_match_preview`.

---

## Tools reference

### Live & fixtures

| Tool | Description |
|------|-------------|
| `get_today_matches()` | Today's schedule bucketed into LIVE / UPCOMING / FINISHED |
| `get_live_match(team)` | Real-time score, stats, cards, and recent events for an in-progress match |
| `get_fixtures_range(date_from, date_to)` | Multi-day fixtures with bzzoiro ML predictions (YYYY-MM-DD) |
| `get_team_fixtures(team)` | Full group-stage schedule for one nation |

### Analysis

| Tool | Description |
|------|-------------|
| `get_match_preview(team_a, team_b)` | Pre-match form, xG profile, H2H, key stats |
| `get_h2h(team_a, team_b, last_n=10)` | Historical head-to-head (WC meetings flagged) |
| `get_team_form(team, last_n=5)` | In-tournament WC form and stats |
| `simulate_group_scenarios(group, team)` | What a team needs to qualify from their group |

### Standings & scorers

| Tool | Description |
|------|-------------|
| `get_group_standings(group="all")` | Group tables with qualification markers |
| `get_group_overview(group)` | Full group preview: standings + 4 team profiles + predicted order |
| `get_top_scorers(top_n=10)` | Golden Boot leaderboard |

### Squad intelligence (all 48 nations)

| Tool | Description |
|------|-------------|
| `analyze_team_for_worldcup(team)` | Full team analysis: WC stats + squad + club xG + projection |
| `compare_teams_for_worldcup(team_a, team_b)` | Side-by-side squad comparison |
| `get_tournament_favorites(top_n=10)` | Power rankings by squad strength |
| `get_nation_top_performers(team, top_n=5)` | Top attackers by adjusted club xG |
| `get_nation_top_defenders(team, top_n=5)` | Top DF/GK by defending attribute |
| `get_squad_league_breakdown(team)` | Where a nation's squad plays club football |
| `get_player_club_stats(player_name)` | Individual player's 2025–26 club season |
| `search_players(...)` | Search players by name, position, league, xG, or defending rating |

---

## Project structure

```
worldcup-analysis-mcp/
├── server.py              # FastMCP entrypoint
├── config.py              # Settings, TEAM_ID_MAP, resolve_team_id()
├── requirements.txt
├── Procfile               # Railway: python server.py --sse
├── clients/
│   ├── bzzoiro.py         # Live WC API client
│   ├── api_football.py    # API-Football client
│   └── football_data.py   # football-data.org client
├── tools/                 # One module per domain; each tool = async def + docstring
├── cache/cache_manager.py # TTL cache singleton
├── data/
│   ├── loader.py          # CSV squad / understat / bzzoiro data access
│   └── *.csv              # Pre-loaded fixtures, players, predictions
├── auth/
│   ├── oauth_provider.py  # OAuth 2.0 + PKCE for remote MCP
│   └── token_store.py     # SQLite token persistence
├── tests/                 # Unit tests (fixture JSON, no live API)
└── docs/
    ├── OAUTH.md
    ├── RAILWAY.md
    └── worldcup-analysis-mcp-architecture.pdf
```

---

## Development

### Smoke-test a tool

```bash
python -c "
import asyncio
from tools.standings import get_group_standings
print(asyncio.run(get_group_standings('A')))
"
```

### Run tests

```bash
# Unit tests only (no live API calls)
pytest tests/ -m "not integration" -v

# Live bzzoiro integration (costs API quota)
pytest tests/test_bzzoiro_live.py -m integration -v
```

### Regenerate architecture PDF

```bash
pip install fpdf2
python generate_architecture_pdf.py
# Output: docs/worldcup-analysis-mcp-architecture.pdf
```

### Game-day checklist

1. Set `LIVE_DATA_SOURCE=bzzoiro` on Railway (or in `.env` locally).
2. Confirm `BZZOIRO_KEY` is set.
3. Mount a Railway volume at `/data` for OAuth persistence ([docs/RAILWAY.md](docs/RAILWAY.md)).
4. After squad-logic deploys, restart the service or set `CACHE_BUST=1` once.

---

## Example prompts

Once connected, try:

- *"What World Cup matches are on today?"*
- *"Show Group D standings."*
- *"Analyze Brazil for the World Cup."*
- *"Compare France vs Argentina."*
- *"What does Mexico need to qualify from Group A?"*
- *"Live stats for the USA game."*
- *"Fixtures and predictions for June 11–13."*
- *"Who are the tournament favorites?"*

---

## Documentation

- [OAuth setup](docs/OAUTH.md) — remote MCP auth flow and token persistence
- [Railway deployment](docs/RAILWAY.md) — volumes, env vars, cache behavior
- [Architecture PDF](docs/worldcup-analysis-mcp-architecture.pdf) — full system design
- [claude.md](claude.md) — internal dev spec (tool contracts, cache TTLs, output formats)

---

## License

MIT — see [LICENSE](LICENSE) if present, or add your preferred license before publishing.
