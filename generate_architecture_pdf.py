"""
Generate the complete worldcup-analysis-mcp architecture PDF.

Run:  python generate_architecture_pdf.py
Output: docs/worldcup-analysis-mcp-architecture.pdf
"""
from __future__ import annotations

from fpdf import FPDF, XPos, YPos

OUT_PATH = "docs/worldcup-analysis-mcp-architecture.pdf"

NAVY = (26, 26, 46)
BLUE = (30, 80, 160)
LIGHT_BLUE = (230, 240, 255)
LIGHT_GRAY = (248, 248, 252)
BORDER_GRAY = (200, 200, 215)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
DARK_GRAY = (60, 60, 60)
MID_GRAY = (120, 120, 130)


class ArchPDF(FPDF):
    def header(self):
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 14, "F")
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*WHITE)
        self.set_xy(0, 3)
        self.cell(0, 8, "worldcup-analysis-mcp  |  Complete Architecture Reference", align="C")
        self.set_text_color(*BLACK)
        self.set_y(18)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*MID_GRAY)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")
        self.set_text_color(*BLACK)

    def section(self, num: str, title: str):
        self.ln(4)
        if self.get_y() > 255:
            self.add_page()
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 8, f"  {num}.  {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*BLACK)
        self.ln(2)

    def subsection(self, title: str):
        self.ln(2)
        if self.get_y() > 268:
            self.add_page()
        self.set_font("Helvetica", "B", 9.5)
        self.set_text_color(*BLUE)
        self.cell(0, 5.5, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*BLACK)
        self.ln(0.5)

    def body(self, text: str):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*DARK_GRAY)
        self.multi_cell(0, 4.8, text)
        self.set_text_color(*BLACK)
        self.ln(0.5)

    def bullets(self, items: list[str]):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*DARK_GRAY)
        x0 = self.l_margin
        for item in items:
            if self.get_y() > 275:
                self.add_page()
            self.set_x(x0)
            self.cell(5, 4.8, "-", new_x=XPos.RIGHT, new_y=YPos.TOP)
            w = self.w - self.l_margin - self.r_margin - 5
            self.multi_cell(w, 4.8, item)
        self.set_text_color(*BLACK)
        self.ln(0.5)

    def code(self, text: str):
        if self.get_y() > 250:
            self.add_page()
        self.set_fill_color(*LIGHT_GRAY)
        self.set_draw_color(*BORDER_GRAY)
        self.set_font("Courier", "", 7.5)
        self.set_text_color(40, 40, 90)
        self.multi_cell(0, 4.2, text, border=1, fill=True)
        self.set_text_color(*BLACK)
        self.ln(1.5)

    def table_row(self, cols: list[str], widths: list[int], bold: bool = False):
        self.set_font("Helvetica", "B" if bold else "", 8)
        for col, w in zip(cols, widths):
            self.cell(w, 5.5, col, border=1)
        self.ln()

    def tool_block(
        self,
        name: str,
        purpose: str,
        trigger: str,
        flow: str,
        data: str,
        cache_ttl: str,
    ):
        if self.get_y() > 240:
            self.add_page()
        self.subsection(name)
        self.body(f"Purpose: {purpose}")
        self.body(f"When the LLM calls it: {trigger}")
        self.body(f"Execution flow: {flow}")
        self.body(f"Data sources: {data}")
        self.body(f"Cache: {cache_ttl}")


def build() -> None:
    pdf = ArchPDF()
    pdf.set_left_margin(12)
    pdf.set_right_margin(12)
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()

    # Cover
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 10, "worldcup-analysis-mcp", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(*BLUE)
    pdf.cell(0, 7, "Complete Architecture Reference", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*MID_GRAY)
    pdf.cell(0, 6, "Data loading  |  Tools  |  APIs  |  Cache  |  OAuth  |  Deployment", align="C")
    pdf.set_text_color(*BLACK)
    pdf.ln(8)
    pdf.body(
        "This document explains every layer of the FIFA World Cup 2026 MCP server: how data is "
        "loaded at startup, how requests flow from Claude/Cursor to tools, which external APIs "
        "each tool uses, and how OAuth protects the production deployment on Railway."
    )

    # 1 Overview
    pdf.section("1", "System Overview")
    pdf.body(
        "worldcup-analysis-mcp is a FastMCP server exposing 19 async Python tools. An MCP client "
        "(Claude Desktop, Cursor, or any MCP-compatible assistant) sends natural-language questions; "
        "the model chooses a tool, the server executes it, and returns a formatted plain-text string "
        "that the model shows to the user."
    )
    pdf.subsection("Core design rules")
    pdf.bullets([
        "Clients know APIs. Tools know questions. HTTP calls live only in clients/*.py.",
        "Every tool is async, returns str (never raw JSON), and checks cache before calling APIs.",
        "Team names resolve through resolve_team_id() or resolve_bzzoiro_team_id() - never hardcoded.",
        "Live tournament data routes to bzzoiro when LIVE_DATA_SOURCE=bzzoiro (default).",
        "Squad/club analytics use pre-loaded CSVs (bzzoiro + understat) via data/loader.py.",
    ])
    pdf.subsection("High-level request flow")
    pdf.code(
        "User question in chat\n"
        "    -> MCP client (Claude/Cursor) picks a tool + arguments\n"
        "    -> HTTP POST /mcp  (Bearer token in production)\n"
        "    -> FastMCP (server.py) dispatches to registered tool function\n"
        "    -> tools/<name>.py: cache.get() -> client API or data/loader -> format str\n"
        "    -> cache.set() -> return text to MCP client -> shown to user"
    )

    # 2 Runtime modes
    pdf.section("2", "Server Runtime Modes (server.py)")
    pdf.table_row(["Mode", "Command", "Transport", "Auth"], [22, 55, 40, 63], bold=True)
    pdf.table_row(
        ["Local", "python server.py", "stdio", "None - Claude Desktop subprocess"],
        [22, 55, 40, 63],
    )
    pdf.table_row(
        ["HTTP dev", "python server.py --http", "streamable-http", "None"],
        [22, 55, 40, 63],
    )
    pdf.table_row(
        ["Production", "python server.py --sse", "streamable-http", "OAuth 2.0 + PKCE"],
        [22, 55, 40, 63],
    )
    pdf.ln(2)
    pdf.body(
        "Railway Procfile runs: web: python server.py --sse. The server reads PORT from the "
        "environment, builds BASE_URL from RAILWAY_PUBLIC_DOMAIN, creates SimpleOAuthProvider, "
        "registers all 19 tools, and binds Uvicorn to 0.0.0.0:PORT."
    )

    # 3 Data loading
    pdf.add_page()
    pdf.section("3", "Data Loading Layer (data/loader.py)")
    pdf.body(
        "Most static data is loaded once at Python import time (module-level singletons). "
        "This avoids repeated disk I/O and keeps squad analytics fast. Live scores and standings "
        "during the tournament come from the bzzoiro HTTP API instead."
    )
    pdf.subsection("CSV files loaded at startup")
    widths = [70, 108]
    pdf.table_row(["File", "Loaded into"], widths, bold=True)
    for row in [
        ("understat_*_2025_26_player_stats.csv (6 leagues)", "PLAYER_INDEX, ALL_PLAYERS"),
        ("data/bzzoiro_wc_players.csv", "BZZ_PLAYER_INDEX - 48-team squads"),
        ("data/bzzoiro_wc_teams.csv", "BZZ_TEAMS_BY_NAME, BZZ_TEAMS_BY_ID"),
        ("data/bzzoiro_wc_fixtures.csv", "BZZ_FIXTURES - group-stage schedule"),
        ("data/bzzoiro_wc_predictions.csv", "BZZ_PREDICTIONS - ML win/xG predictions"),
        ("worldcup_squad_players.csv", "Supplementary squad metadata"),
    ]:
        pdf.table_row(list(row), widths)
    pdf.ln(2)

    pdf.subsection("Key loader functions")
    pdf.bullets([
        "find_player(name) - fuzzy match against understat top-6 league CSVs.",
        "find_player_for_squad(name, bzz_row) - squad-safe match; rejects false hits.",
        "get_bzzoiro_squad(team) - all players for a nation from bzzoiro export.",
        "resolve_bzzoiro_team_id(name) - maps Mexico, usa, etc. to bzzoiro team_id.",
        "get_bzzoiro_fixtures(team) / get_bzzoiro_fixtures_in_range(from, to) - schedules.",
        "find_bzzoiro_prediction(team_a, team_b) - ML prediction row for a pairing.",
        "get_adj_xg(row) - league-quality-adjusted xG for cross-league comparisons.",
        "BZZ_GROUP_MAP - group A-L to bzzoiro team IDs (built from fixtures CSV).",
    ])
    pdf.subsection("Understat + bzzoiro merge logic (team_analysis.py)")
    pdf.body(
        "_build_csv_profile() joins bzzoiro squad rows with understat club stats where names "
        "and clubs match. Players in leagues outside the top-6 (Saudi Pro League, MLS, etc.) "
        "use bzzoiro-only stats. League quality factors (LEAGUE_QUALITY dict) normalize xG "
        "so a Saudi league striker is not ranked equal to a Premier League striker."
    )

    # 4 External APIs
    pdf.section("4", "External API Clients (clients/)")
    pdf.subsection("bzzoiro.py - primary live tournament source (LIVE_DATA_SOURCE=bzzoiro)")
    pdf.bullets([
        "Base: https://sports.bzzoiro.com/api/v2  |  Auth: Token {BZZOIRO_KEY}",
        "League ID 27 = FIFA World Cup 2026",
        "get_live_events(), get_events_today(), get_events(), get_standings()",
        "Per-match: get_event(), get_event_stats(), get_event_incidents(), get_event_lineups()",
        "get_top_scorers() aggregates player-stats across finished events",
        "get_head_to_head_events(team_a, team_b) for H2H during tournament",
    ])
    pdf.subsection("api_football.py - legacy live + match previews")
    pdf.bullets([
        "Base: https://v3.football.api-sports.io  |  Used when LIVE_DATA_SOURCE=legacy",
        "Always used by get_match_preview (team stats + H2H from API-Football)",
        "get_live_fixtures(), get_fixture_stats(), get_fixture_events(), get_fixture_lineups()",
    ])
    pdf.subsection("football_data.py - legacy static (free tier)")
    pdf.bullets([
        "Base: https://api.football-data.org/v4  |  competition WC",
        "Used when LIVE_DATA_SOURCE=legacy and API_FOOTBALL_TIER=free",
        "get_matches(), get_standings(), get_scorers(), get_team_squad()",
    ])

    # 5 Cache
    pdf.section("5", "Cache Layer (cache/cache_manager.py)")
    pdf.body(
        "Singleton CacheManager with separate TTLCache buckets. Keys are MD5 hashes of kwargs. "
        "Set CACHE_BUST=1 to clear all caches on startup (one-time after deploy)."
    )
    pdf.table_row(["Bucket", "TTL (default)", "Used by"], [28, 28, 124], bold=True)
    for row in [
        ("live", "30s", "get_live_match; get_today_matches on live days"),
        ("fixtures", "24h", "get_today_matches (no live); get_team_fixtures; get_fixtures_range"),
        ("standings", "5m", "get_group_standings; get_group_overview"),
        ("scorers", "5m", "get_top_scorers"),
        ("form", "1h", "get_team_form; get_match_preview"),
        ("h2h", "1h", "get_h2h"),
        ("squad", "1h", "analyze_team, compare, squad_analysis tools"),
        ("lineups", "5m", "reserved for lineup data"),
    ]:
        pdf.table_row(list(row), [28, 28, 124])

    # 6 Routing
    pdf.add_page()
    pdf.section("6", "Data Source Routing (config.py)")
    pdf.code(
        "uses_bzzoiro_live()  ->  LIVE_DATA_SOURCE.lower() == 'bzzoiro'\n\n"
        "When True (default):\n"
        "  get_today_matches, get_live_match, get_group_standings,\n"
        "  get_team_form, get_top_scorers, get_h2h, simulate_group_scenarios\n"
        "  -> bzzoiro client + resolve_bzzoiro_team_id()\n\n"
        "When False (legacy):\n"
        "  API_FOOTBALL_TIER=free  -> football_data for static tools\n"
        "  API_FOOTBALL_TIER=paid  -> api_football for all legacy tools\n"
        "  get_live_match always used api_football even in legacy mode\n\n"
        "Always CSV/bzzoiro (not affected by LIVE_DATA_SOURCE):\n"
        "  Squad tools, get_team_fixtures (CSV first), get_fixtures_range (CSV first),\n"
        "  get_match_preview (API-Football + bzzoiro prediction overlay)"
    )

    # 7 All tools
    pdf.section("7", "All 19 MCP Tools - Purpose, Flow, and Data Sources")

    tools = [
        (
            "get_today_matches()",
            "Today's WC schedule bucketed LIVE / UPCOMING / FINISHED.",
            "User asks what matches are on today, live scores now, today's games.",
            "cache fixtures/live -> if bzzoiro: gather(events_today, live_events) -> "
            "parse_bzzoiro_fixtures -> format. Legacy: football_data or api_football.",
            "bzzoiro events/ + events/live/  OR  legacy APIs",
            "30s if live games; else 24h (fixtures bucket)",
        ),
        (
            "get_live_match(team)",
            "Real-time score, xG, shots, possession, cards, last 5 events for one team.",
            "What's the score in the Mexico game? Is Brazil playing now?",
            "resolve team_id -> cache live -> bzzoiro.get_live_events(team_id) -> "
            "match event -> gather(stats, incidents, lineups) -> _format_bzzoiro_live_match.",
            "bzzoiro live API (4 parallel calls per match)",
            "30s per team_id",
        ),
        (
            "get_fixtures_range(date_from, date_to)",
            "Multi-day fixture list with bzzoiro ML predictions (win prob, xG, score).",
            "Opening weekend schedule, fixtures Jun 11-13, predict all games this week.",
            "clamp dates to WC window -> cache -> CSV fixtures first -> API fallback -> "
            "attach prediction per event_id -> format table.",
            "data/bzzoiro_wc_fixtures.csv + bzzoiro_wc_predictions.csv; API if CSV empty",
            "24h (fixtures bucket, source=range_v1)",
        ),
        (
            "get_team_fixtures(team)",
            "One team's full group-stage schedule with results.",
            "When does Brazil play? Mexico schedule, team calendar.",
            "resolve_team_id -> cache -> bzzoiro fixtures CSV for team -> "
            "else football_data matches filtered by team_id.",
            "bzzoiro_wc_fixtures.csv primary; football-data.org fallback",
            "24h (fixtures, source=fixtures_v3)",
        ),
        (
            "get_match_preview(team_a, team_b)",
            "Pre-match analysis: WC form, xG profile, H2H, key stats, bzzoiro ML prediction.",
            "Preview France vs Germany, who will win, matchup analysis.",
            "resolve both IDs -> cache form -> gather(api team_stats x2, h2h) -> "
            "format -> append bzzoiro club-season profiles if squads exist.",
            "api_football (always) + data/loader predictions/squads",
            "1h (form bucket, preview=True)",
        ),
        (
            "get_team_form(team, last_n)",
            "In-tournament W/D/L, goals, xG averages, last N match results.",
            "How is Argentina doing in the tournament? Recent WC form.",
            "bzzoiro: gather(standings, finished events) -> parse_bzz_team_form. "
            "Legacy: api_football.get_team_stats.",
            "bzzoiro standings + events  OR  api_football",
            "1h per team_id + last_n",
        ),
        (
            "get_h2h(team_a, team_b, last_n)",
            "Head-to-head record, goals, results list with WC flag.",
            "Brazil vs Argentina history, last 10 meetings.",
            "bzzoiro: resolve bzz IDs -> get_head_to_head_events. "
            "Legacy: api_football.get_h2h.",
            "bzzoiro events  OR  api_football headtohead",
            "1h per team pair + last_n",
        ),
        (
            "get_group_standings(group)",
            "Group table with qualification markers (top 2, 3rd, eliminated).",
            "Group A standings, show all groups, points table.",
            "cache -> bzzoiro.get_standings -> parse_bzzoiro_standings -> format.",
            "bzzoiro leagues/27/standings/  OR  legacy standings APIs",
            "5m per group letter",
        ),
        (
            "get_top_scorers(top_n)",
            "Golden Boot leaderboard with goals and assists.",
            "Top scorers, Golden Boot, leading goalscorer.",
            "bzzoiro: aggregate goals from player-stats on all finished events. "
            "Legacy: football_data or api_football scorers endpoint.",
            "bzzoiro (computed)  OR  legacy scorers API",
            "5m",
        ),
        (
            "simulate_group_scenarios(group, team)",
            "Enumerates remaining fixture outcomes; says what team needs to qualify.",
            "What does Mexico need to advance? Qualification scenarios.",
            "fetch current standings + remaining fixtures -> enumerate 3^N outcomes -> "
            "apply tiebreakers -> plain-English summary. No cache (always fresh).",
            "bzzoiro standings + events  OR  legacy APIs",
            "None - recomputed every call",
        ),
        (
            "get_group_overview(group)",
            "Standings + all 4 team squad profiles + predicted finish order.",
            "Tell me about Group A, group preview, strongest group.",
            "parallel: get_group_standings + analyze each of 4 teams -> merge overview.",
            "standings API + bzzoiro squads + understat via loader",
            "5m (standings, source=overview_v4)",
        ),
        (
            "get_tournament_favorites(top_n)",
            "Power rankings of all 48 teams by squad strength (adj xG).",
            "Who are the favorites? Power rankings, strongest teams.",
            "score all 48 squads via _build_csv_profile -> sort by pedigree -> format.",
            "bzzoiro_wc_players.csv + understat CSVs only (no HTTP)",
            "1h (squad bucket)",
        ),
        (
            "analyze_team_for_worldcup(team)",
            "Full squad analysis: pedigree %, top performers, league breakdown, proj goals.",
            "Analyze Brazil for the World Cup, squad strength, team profile.",
            "get_bzzoiro_squad -> _build_csv_profile -> format multi-section report.",
            "bzzoiro + understat CSVs",
            "1h (squad bucket)",
        ),
        (
            "compare_teams_for_worldcup(team_a, team_b)",
            "Side-by-side squad comparison table.",
            "Compare France and England, who's stronger?",
            "analyze both squads in parallel -> comparison table.",
            "bzzoiro + understat CSVs",
            "1h (squad bucket)",
        ),
        (
            "get_player_club_stats(player_name)",
            "Club-season xG, goals, league for one player.",
            "Messi stats this season, player club form.",
            "find_player + find_bzzoiro_player -> merge rows -> format.",
            "understat CSVs + bzzoiro players CSV",
            "1h (squad bucket)",
        ),
        (
            "get_nation_top_performers(team, top_n)",
            "Top attackers by adjusted xG for a nation.",
            "Brazil's best attackers, top performers for Spain.",
            "get_bzzoiro_squad -> rank by get_adj_xg -> format.",
            "bzzoiro + understat CSVs",
            "1h (squad bucket)",
        ),
        (
            "get_nation_top_defenders(team, top_n)",
            "Top DF/GK by bzzoiro attr_defending score.",
            "Best defenders in France squad.",
            "defensive_profile_from_squad -> format.",
            "bzzoiro players CSV (attr_defending field)",
            "1h (squad bucket)",
        ),
        (
            "get_squad_league_breakdown(team)",
            "Pie-style breakdown of where squad players play by league.",
            "Where do USA players play club football?",
            "count leagues in squad -> format percentages.",
            "bzzoiro players CSV",
            "1h (squad bucket)",
        ),
        (
            "search_players(...)",
            "Search all WC squad players by name, position, league, xG, defending.",
            "Find all Brazilian strikers in top leagues, search players.",
            "filter BZZ squads with optional filters -> format matches.",
            "bzzoiro + understat CSVs",
            "1h (squad bucket)",
        ),
    ]

    for t in tools:
        pdf.tool_block(*t)

    # 8 OAuth
    pdf.add_page()
    pdf.section("8", "OAuth Authentication (Production)")
    pdf.body(
        "Remote MCP clients must authenticate. The server implements OAuth 2.0 Authorization "
        "Code + PKCE. Tokens persist in SQLite (not RAM) so users stay connected after Railway "
        "redeploys when a volume is mounted at /data."
    )
    pdf.subsection("Auth files")
    pdf.bullets([
        "auth/oauth_provider.py - SimpleOAuthProvider: approval page, code exchange, token issue.",
        "auth/token_store.py - SQLite persistence for access_tokens and oauth_clients tables.",
        "OAUTH_DB_PATH env - default /data/oauth.db on Railway volume, else data/oauth.db local.",
    ])
    pdf.subsection("OAuth endpoints")
    pdf.code(
        "/.well-known/oauth-authorization-server  - discovery (auto by FastMCP)\n"
        "/.well-known/oauth-protected-resource      - tells client MCP is at /mcp\n"
        "/register                                   - dynamic client registration\n"
        "/authorize                                  - starts flow -> /oauth/approve\n"
        "/oauth/approve (GET)                        - one-click Approve Access HTML page\n"
        "/oauth/approve (POST)                       - issues auth code, redirects to client\n"
        "/token                                      - exchanges code + PKCE for Bearer token\n"
        "/mcp                                        - MCP tool endpoint (requires Bearer)"
    )
    pdf.subsection("Connection sequence (first time)")
    pdf.bullets([
        "1. Client GET /mcp -> 401 + WWW-Authenticate header.",
        "2. Client reads /.well-known/oauth-protected-resource and authorization-server metadata.",
        "3. Client POST /register -> receives client_id.",
        "4. Browser opens /authorize with PKCE code_challenge.",
        "5. User clicks Approve on /oauth/approve.",
        "6. Client POST /token with code + code_verifier -> 30-day Bearer token (stored in SQLite).",
        "7. All /mcp requests include Authorization: Bearer <token>.",
    ])
    pdf.subsection("What persists vs ephemeral")
    pdf.table_row(["Data", "Storage", "Survives redeploy?"], [55, 45, 80], bold=True)
    pdf.table_row(["Access tokens (30d)", "SQLite", "Yes (with /data volume)"], [55, 45, 80])
    pdf.table_row(["OAuth client registrations", "SQLite", "Yes"], [55, 45, 80])
    pdf.table_row(["Pending approval sessions", "In-memory", "No"], [55, 45, 80])
    pdf.table_row(["Auth codes (5 min)", "In-memory", "No"], [55, 45, 80])
    pdf.table_row(["Tool result caches", "In-memory TTLCache", "No - cleared on restart"], [55, 45, 80])

    # 9 Project structure
    pdf.add_page()
    pdf.section("9", "Complete Project Structure")
    pdf.body("Every file and its role in the system:")
    structure = [
        ("server.py", "Entry point. Registers 19 tools on FastMCP. --sse=OAuth HTTP, --http=plain HTTP, default=stdio."),
        ("config.py", "Settings from env vars. TEAM_ID_MAP (48 teams). GROUP_MAP. uses_bzzoiro_live()."),
        ("Procfile", "Railway start command: python server.py --sse"),
        (".env.example", "Template for API keys, LIVE_DATA_SOURCE, cache TTLs, OAuth path."),
        ("requirements.txt", "fastmcp, httpx, cachetools, pytest, python-dotenv."),
        ("clients/api_football.py", "API-Football HTTP client (legacy live + previews)."),
        ("clients/football_data.py", "football-data.org HTTP client (legacy free tier)."),
        ("clients/bzzoiro.py", "bzzoiro live tournament API client (primary during WC)."),
        ("cache/cache_manager.py", "TTLCache singleton; cache.get/set with hashed keys."),
        ("data/loader.py", "CSV loading, player/squad/fixture/prediction lookups, adj xG."),
        ("data/bzzoiro_wc_*.csv", "Pre-exported squads, teams, fixtures, ML predictions."),
        ("data/oauth.db", "Local SQLite OAuth store (gitignored)."),
        ("understat_*.csv", "Top-6 European league player stats 2025-26 season."),
        ("worldcup_squad_players.csv", "Supplementary squad metadata."),
        ("tools/fixtures.py", "get_today_matches, get_fixtures_range, get_team_fixtures."),
        ("tools/match.py", "get_live_match, get_match_preview."),
        ("tools/standings.py", "get_group_standings, get_group_overview."),
        ("tools/team.py", "get_team_form."),
        ("tools/head_to_head.py", "get_h2h."),
        ("tools/players.py", "get_top_scorers."),
        ("tools/scenarios.py", "simulate_group_scenarios."),
        ("tools/team_analysis.py", "analyze_team_for_worldcup, _build_csv_profile."),
        ("tools/compare.py", "compare_teams_for_worldcup."),
        ("tools/favorites.py", "get_tournament_favorites."),
        ("tools/squad_analysis.py", "Player search, top performers/defenders, league breakdown."),
        ("tools/bzzoiro_parsers.py", "Normalize bzzoiro API responses to tool-friendly dicts."),
        ("auth/oauth_provider.py", "OAuth provider with approval page and token exchange."),
        ("auth/token_store.py", "SQLite persistence for tokens and registered clients."),
        ("tests/test_*.py", "Unit tests with JSON fixtures; no live API in unit tests."),
        ("tests/fixtures/*.json", "Saved API responses for offline testing."),
        ("tests/test_bzzoiro_live.py", "Integration test for bzzoiro live endpoint (manual)."),
        ("scripts/generate_csvs.py", "Regenerate understat CSV exports."),
        ("scripts/generate_bzzoiro_stats.py", "Regenerate bzzoiro data exports."),
        ("docs/OAUTH.md", "OAuth setup and persistence guide."),
        ("docs/RAILWAY.md", "Railway deploy checklist and env vars."),
        ("claude.md", "Agent instructions: architecture rules, tool specs, build order."),
    ]
    widths = [62, 116]
    pdf.table_row(["Path", "Role"], widths, bold=True)
    for path, role in structure:
        if pdf.get_y() > 272:
            pdf.add_page()
            pdf.table_row(["Path", "Role"], widths, bold=True)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*DARK_GRAY)
        pdf.cell(62, 5, path, border=1)
        pdf.multi_cell(116, 5, role, border=1)
        pdf.set_text_color(*BLACK)

    # 10 Env vars
    pdf.add_page()
    pdf.section("10", "Environment Variables")
    envs = [
        ("API_FOOTBALL_KEY", "Required", "api-sports.io key for legacy live + match previews"),
        ("FOOTBALL_DATA_KEY", "Required", "football-data.org token for legacy free tier"),
        ("BZZOIRO_KEY", "Required", "bzzoiro API token for live tournament data"),
        ("LIVE_DATA_SOURCE", "Optional", "bzzoiro (default) or legacy"),
        ("API_FOOTBALL_TIER", "Optional", "free or paid - legacy routing + previews"),
        ("CACHE_TTL_*", "Optional", "Override per-bucket TTL seconds"),
        ("CACHE_BUST", "Optional", "Set 1 to clear in-memory caches on startup"),
        ("BASE_URL", "Railway auto", "Public URL for OAuth; from RAILWAY_PUBLIC_DOMAIN"),
        ("OAUTH_DB_PATH", "Recommended", "/data/oauth.db on Railway volume"),
        ("PORT", "Railway auto", "HTTP port for Uvicorn"),
    ]
    pdf.table_row(["Variable", "Required?", "Purpose"], [40, 22, 118], bold=True)
    for row in envs:
        pdf.table_row(list(row), [40, 22, 118])

    # 11 Testing
    pdf.section("11", "Testing Strategy")
    pdf.bullets([
        "Unit tests: pytest tests/ -m 'not integration' - mock APIs, load tests/fixtures/*.json.",
        "Integration: pytest tests/test_bzzoiro_live.py - hits real bzzoiro API (needs BZZOIRO_KEY).",
        "Every tool should have happy-path, invalid-team, and cache-hit tests where applicable.",
        "test_bzzoiro_tool_coverage.py verifies all 48 teams have squad data and tools are registered.",
    ])

    # 12 Game day checklist
    pdf.section("12", "Game-Day Checklist (June 11+)")
    pdf.bullets([
        "Confirm LIVE_DATA_SOURCE=bzzoiro and BZZOIRO_KEY set on Railway.",
        "Confirm /data volume mounted with OAUTH_DB_PATH=/data/oauth.db.",
        "Unset CACHE_BUST in production after any one-time cache clear.",
        "Smoke test: get_today_matches(), get_group_standings('A'), get_live_match('<team>').",
        "Monitor bzzoiro rate limits in Railway logs (status=429).",
        "get_top_scorers becomes slower as more matches finish (N player-stats calls).",
    ])

    pdf.output(OUT_PATH)
    print(f"PDF written to: {OUT_PATH}")


if __name__ == "__main__":
    build()
