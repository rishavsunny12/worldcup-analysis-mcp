import logging

from fastmcp import FastMCP

from config import settings
from tools.compare import compare_teams_for_worldcup
from tools.favorites import get_tournament_favorites
from tools.fixtures import get_team_fixtures, get_today_matches
from tools.head_to_head import get_h2h
from tools.match import get_live_match, get_match_preview
from tools.players import get_top_scorers
from tools.scenarios import simulate_group_scenarios
from tools.squad_analysis import get_nation_top_performers, get_player_club_stats, get_squad_league_breakdown, search_players
from tools.team_analysis import analyze_team_for_worldcup
from tools.standings import get_group_overview, get_group_standings
from tools.team import get_team_form

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
    get_player_club_stats,
    get_nation_top_performers,
    get_squad_league_breakdown,
    analyze_team_for_worldcup,
    compare_teams_for_worldcup,
    get_team_fixtures,
    get_group_overview,
    get_tournament_favorites,
    search_players,
]

_INSTRUCTIONS = """
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
- get_group_overview      → full Group X preview: standings + all 4 team profiles + predicted order
- get_tournament_favorites → power rankings of all 48 teams by squad strength
- search_players          → search 2025-26 club stats by name, position, league, or xG threshold

ALWAYS call a tool before answering any question about:
- current standings, points, or group positions
- live or recent match scores
- team form, xG, or stats this tournament
- qualification status or scenarios
Never answer these from training data — the tournament is live.

Output formatting rules:
- Always display tool output as-is, in plain text or a markdown code block.
- Never reformat tool output into HTML, JSX, JavaScript template literals, or Artifacts.
- Never re-render the data into cards, tables, or UI components — the tool already formatted it.

Important rules clarification:
- Host nation status (USA, Canada, Mexico) means automatic qualification FOR the tournament only.
  It does NOT guarantee advancement past the group stage. All 48 teams must earn their place in
  the Round of 32 on merit: finish top 2 in their group, or be among the 8 best third-place teams.
"""


def _build_mcp(auth=None) -> FastMCP:
    m = FastMCP(name="worldcup-analysis-mcp", instructions=_INSTRUCTIONS, auth=auth)
    for tool in TOOLS:
        m.tool()(tool)
    return m


# Module-level instance for stdio / Claude Desktop local use (no auth needed)
mcp = _build_mcp()

logger.info(f"worldcup-analysis-mcp started | {len(TOOLS)} tools | tier={settings.TIER}")

if __name__ == "__main__":
    import os
    import sys
    port = int(os.getenv("PORT", 8000))
    if "--http" in sys.argv:
        logger.info(f"Starting HTTP server (no auth) on http://0.0.0.0:{port}/mcp")
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    elif "--sse" in sys.argv:
        from auth.oauth_provider import SimpleOAuthProvider
        oauth = SimpleOAuthProvider(base_url=settings.BASE_URL)
        mcp_http = _build_mcp(auth=oauth)
        logger.info(f"Starting HTTP+OAuth server on {settings.BASE_URL}/mcp")
        mcp_http.run(transport="streamable-http", host="0.0.0.0", port=port)
    else:
        mcp.run()
