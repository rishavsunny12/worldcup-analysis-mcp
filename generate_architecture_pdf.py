"""One-off script: generates the MCP deploy & auth architecture PDF."""
from fpdf import FPDF, XPos, YPos

NAVY = (26, 26, 46)
BLUE = (30, 80, 160)
LIGHT_BLUE = (230, 240, 255)
LIGHT_GRAY = (248, 248, 252)
BORDER_GRAY = (200, 200, 215)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
DARK_GRAY = (60, 60, 60)
MID_GRAY = (120, 120, 130)


class PDF(FPDF):
    def header(self):
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 16, "F")
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*WHITE)
        self.set_xy(0, 4)
        self.cell(0, 8, "worldcup-analysis-mcp  |  Deploy & Auth Architecture Guide", align="C")
        self.set_text_color(*BLACK)
        self.set_y(20)

    def footer(self):
        self.set_y(-13)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*MID_GRAY)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")
        self.set_text_color(*BLACK)

    def section(self, num: str, title: str):
        self.ln(6)
        self.set_fill_color(*NAVY)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 9, f"  {num}.  {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        self.set_text_color(*BLACK)
        self.ln(3)

    def subsection(self, title: str):
        self.ln(3)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*BLUE)
        self.cell(0, 6, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*BLACK)
        self.ln(1)

    def body(self, text: str):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*DARK_GRAY)
        self.multi_cell(0, 5.5, text)
        self.set_text_color(*BLACK)
        self.ln(1)

    def bullets(self, items: list[str]):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*DARK_GRAY)
        for item in items:
            self.cell(6, 5.5, "-", new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.multi_cell(0, 5.5, item)
        self.set_text_color(*BLACK)
        self.ln(1)

    def code(self, text: str):
        self.set_fill_color(*LIGHT_GRAY)
        self.set_draw_color(*BORDER_GRAY)
        self.set_font("Courier", "", 8.5)
        self.set_text_color(40, 40, 90)
        self.multi_cell(0, 5, text, border=1, fill=True)
        self.set_text_color(*BLACK)
        self.ln(2)

    def step_box(self, num: int, actor: str, action: str, detail: str = ""):
        self.set_fill_color(*LIGHT_BLUE)
        self.set_draw_color(*BLUE)
        self.set_font("Helvetica", "B", 9.5)
        self.set_text_color(*NAVY)
        self.cell(0, 7, f"  Step {num}  [{actor}]  ->  {action}",
                  border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        if detail:
            self.set_font("Helvetica", "I", 8.5)
            self.set_fill_color(240, 245, 255)
            self.set_text_color(*DARK_GRAY)
            self.multi_cell(0, 5.5, f"       {detail}", border="LRB", fill=True)
        self.set_text_color(*BLACK)
        self.ln(1.5)

    def key_value(self, label: str, value: str):
        self.set_font("Helvetica", "B", 9.5)
        self.set_text_color(*NAVY)
        self.cell(48, 6, label, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*DARK_GRAY)
        self.multi_cell(0, 6, value)
        self.set_text_color(*BLACK)


def build() -> None:
    pdf = PDF()
    pdf.set_left_margin(14)
    pdf.set_right_margin(14)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # ── Cover block ───────────────────────────────────────────────────────────
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 12, "worldcup-analysis-mcp", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font("Helvetica", "", 13)
    pdf.set_text_color(*BLUE)
    pdf.cell(0, 8, "Deploy & Authentication Architecture Guide", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*MID_GRAY)
    pdf.cell(0, 6, "FIFA World Cup 2026 Analysis MCP Server", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_text_color(*BLACK)
    pdf.ln(6)

    pdf.set_draw_color(*NAVY)
    pdf.set_line_width(0.5)
    pdf.line(14, pdf.get_y(), 196, pdf.get_y())
    pdf.ln(8)

    # ── 1. WHAT IS THIS PROJECT ───────────────────────────────────────────────
    pdf.section("1", "What Is This Project?")
    pdf.body(
        "worldcup-analysis-mcp is a Model Context Protocol (MCP) server that gives AI assistants "
        "like Claude live access to FIFA World Cup 2026 data. Instead of Claude relying on its "
        "training data (which goes stale), it calls our server's tools to get real-time scores, "
        "standings, player stats, and match analysis."
    )
    pdf.subsection("What MCP Is (in plain terms)")
    pdf.body(
        "MCP (Model Context Protocol) is a standard way for AI assistants to connect to external "
        "tools and data sources. Think of it like a USB standard for AI: instead of building "
        "custom integrations for every AI tool, you build one MCP server and any compatible AI "
        "client can use it. Claude, our AI, supports MCP natively."
    )
    pdf.subsection("What Our Server Provides")
    pdf.bullets([
        "17 tools: live scores, group standings, team form, head-to-head, top scorers, match previews...",
        "Data from two APIs: API-Football (api-sports.io) and football-data.org",
        "Player club stats from Understat (2025-26 season CSVs pre-loaded at startup)",
        "Intelligent caching so repeated questions don't burn API quota",
    ])

    # ── 2. DEPLOY ARCHITECTURE ────────────────────────────────────────────────
    pdf.section("2", "Deploy Architecture")
    pdf.body(
        "The server runs on Railway, a cloud platform that builds and hosts the container "
        "automatically every time you push to GitHub."
    )
    pdf.subsection("The Deploy Stack")
    pdf.bullets([
        "Railway: builds the Docker image, injects environment variables, exposes HTTPS",
        "Railpack (v0.26): Railway's builder - detects Python, reads Procfile, installs requirements.txt",
        "Uvicorn: the ASGI web server that FastMCP uses to serve HTTP requests",
        "FastMCP 3.4.0: the Python framework that wraps our tools into an MCP-compliant server",
        "Python 3.13: the runtime",
    ])
    pdf.subsection("Startup Command (Procfile)")
    pdf.code("web: python server.py --sse")
    pdf.body(
        "The '--sse' flag tells server.py to start in HTTP mode with OAuth auth enabled. "
        "Without this flag it starts in stdio mode (for local Claude Desktop use), which never "
        "binds to a port and so Railway's health check would fail."
    )
    pdf.subsection("Key Environment Variables")
    pdf.key_value("API_FOOTBALL_KEY", "Your api-sports.io key (for live match data)")
    pdf.key_value("FOOTBALL_DATA_KEY", "Your football-data.org token (for standings, fixtures)")
    pdf.key_value("API_FOOTBALL_TIER", '"free" during dev, "paid" from June 11 (tournament start)')
    pdf.key_value("PORT", "Injected automatically by Railway - server reads this to bind Uvicorn")
    pdf.key_value("RAILWAY_PUBLIC_DOMAIN", "Injected by Railway - server uses this to build the OAuth base URL")
    pdf.ln(2)
    pdf.body(
        "We do NOT need to set BASE_URL manually on Railway because the server auto-detects it:"
    )
    pdf.code(
        "railway_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', '')\n"
        "base_url = settings.BASE_URL or f'https://{railway_domain}'"
    )

    pdf.subsection("How Railway Routes Traffic")
    pdf.body(
        "Railway puts an HTTPS reverse proxy in front of your container. "
        "All requests arrive at your Railway domain over HTTPS (port 443) and are forwarded "
        "to your container's HTTP port (e.g. 8080). This means:"
    )
    pdf.bullets([
        "Your container only listens on HTTP (no TLS to manage yourself)",
        "All external URLs use HTTPS automatically",
        "Railway provides the domain: worldcup-analysis-mcp-production.up.railway.app",
    ])

    # ── 3. AUTH ARCHITECTURE ──────────────────────────────────────────────────
    pdf.add_page()
    pdf.section("3", "Authentication Architecture")
    pdf.subsection("Why Auth Is Required")
    pdf.body(
        "When Claude connects to a remote MCP server (one hosted on the internet, not running "
        "locally on your machine), Anthropic mandates that the server implements OAuth 2.0. "
        "This prevents Claude from calling arbitrary unauthenticated servers on your behalf. "
        "Our server implements a minimal OAuth 2.0 provider directly in Python - no third-party "
        "auth service needed."
    )
    pdf.subsection("The Auth Protocol: OAuth 2.0 Authorization Code Flow + PKCE")
    pdf.body(
        "OAuth 2.0 is an industry-standard authorization protocol. We use the 'Authorization Code "
        "Flow with PKCE' variant, which is designed for public clients (apps that cannot safely "
        "store a client secret). Here is what each part means:"
    )
    pdf.bullets([
        "Authorization Code Flow: instead of Claude receiving a token directly, it first gets a "
        "short-lived 'authorization code'. The code is then exchanged for a long-lived access token. "
        "This two-step process means the token never travels through the browser.",
        "PKCE (Proof Key for Code Exchange): Claude generates a random 'code verifier' and sends "
        "a hashed version ('code challenge') at the start. When exchanging the code for a token, "
        "it must prove it has the original verifier. This prevents a malicious app from stealing "
        "the authorization code mid-flow.",
        "Dynamic Client Registration: Claude registers itself with our server at the start of each "
        "new session. Our server issues it a client_id. This means we don't need to pre-configure "
        "any clients.",
    ])

    pdf.subsection("Where Auth Lives in the Code")
    pdf.key_value("auth/oauth_provider.py", "Our custom OAuth provider: approval page, token storage, all OAuth endpoints")
    pdf.key_value("server.py (--sse mode)", "Creates SimpleOAuthProvider, passes it to FastMCP, starts HTTP server")
    pdf.key_value("FastMCP 3.4.0", "Handles the /authorize, /token, /register routes via OAuthProvider base class")
    pdf.ln(3)

    pdf.subsection("OAuth Endpoints on Our Server")
    pdf.code(
        "/.well-known/oauth-authorization-server   <- Auth server discovery (auto by FastMCP)\n"
        "/.well-known/oauth-protected-resource     <- Resource metadata: tells Claude /mcp is the endpoint\n"
        "/register                                  <- Dynamic client registration (auto by FastMCP)\n"
        "/authorize                                 <- Starts the auth flow, redirects to approval page\n"
        "/oauth/approve  (GET)                      <- Shows the one-click 'Approve Access' HTML page\n"
        "/oauth/approve  (POST)                     <- Records approval, redirects Claude back with code\n"
        "/token                                     <- Exchanges authorization code for access token\n"
        "/mcp                                       <- The actual MCP endpoint (tools live here)"
    )

    # ── 4. FULL CONNECTION FLOW ───────────────────────────────────────────────
    pdf.add_page()
    pdf.section("4", "Full Connection Flow: Step by Step")
    pdf.body(
        "This is the complete sequence of what happens the first time you connect Claude to the "
        "MCP server in the Claude connector UI."
    )
    pdf.ln(2)

    pdf.step_box(1, "Claude", "GET /mcp",
                 "Claude tries to connect to the MCP endpoint. Gets back HTTP 401 Unauthorized "
                 "with a WWW-Authenticate header pointing to the resource metadata URL.")
    pdf.step_box(2, "Claude", "GET /.well-known/oauth-protected-resource",
                 "Claude fetches resource metadata. Our server returns: { 'resource': '.../mcp', "
                 "'authorization_servers': ['https://...railway.app/'] }. "
                 "This tells Claude: the MCP endpoint is /mcp, and the auth server is at root.")
    pdf.step_box(3, "Claude", "GET /.well-known/oauth-authorization-server",
                 "Claude discovers the OAuth server's endpoints: authorization_endpoint, token_endpoint, "
                 "registration_endpoint. This JSON is auto-generated by FastMCP from our base_url.")
    pdf.step_box(4, "Claude", "POST /register (Dynamic Client Registration)",
                 "Claude registers itself: sends its name, redirect_uris. Our server issues a client_id. "
                 "No client secret - Claude is a 'public client' using PKCE instead.")
    pdf.step_box(5, "Claude", "Open browser -> GET /authorize?client_id=...&code_challenge=...&state=...",
                 "Claude builds an authorization URL with PKCE code_challenge. Redirects your browser "
                 "there. FastMCP validates parameters, calls our authorize() method which generates a "
                 "session_id and redirects to /oauth/approve?session=<session_id>.")
    pdf.step_box(6, "You (browser)", "GET /oauth/approve?session=...  ->  See approval page",
                 "Your browser loads our custom HTML approval page: 'Allow access to FIFA World Cup "
                 "2026 analysis tools?' with an Approve button. No password needed.")
    pdf.step_box(7, "You (browser)", "POST /oauth/approve  (click Approve button)",
                 "Form submits to our server. We generate a short-lived authorization code (5 min TTL), "
                 "store it in memory, and redirect your browser back to Claude's callback URL with "
                 "?code=<code>&state=<state>.")
    pdf.step_box(8, "Claude backend", "POST /token  (code exchange)",
                 "Claude's backend server (python-httpx) sends the authorization code + the original "
                 "PKCE code_verifier. Our server verifies the code challenge matches, deletes the code "
                 "(one-time use), generates a 64-character hex access token, stores it in memory with "
                 "a 30-day expiry. Returns: { 'access_token': '...', 'token_type': 'bearer', "
                 "'expires_in': 2592000 }.")
    pdf.step_box(9, "Claude backend", "GET /mcp  (with Authorization: Bearer <token>)",
                 "Claude now includes the Bearer token in every request to /mcp. FastMCP calls our "
                 "load_access_token() which looks up the token in memory. If found and not expired, "
                 "the request is authorized and proceeds to tool execution.")
    pdf.step_box(10, "Claude", "MCP session established - tools are available",
                 "Claude can now call any of the 17 tools. The connection stays alive. The token "
                 "lasts 30 days so you won't need to re-approve unless the server restarts "
                 "(token is in memory, lost on restart).")

    # ── 5. KEY FILES ─────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.section("5", "Key Files and Their Roles")

    pdf.subsection("server.py  -  The Entry Point")
    pdf.body(
        "Bootstraps the FastMCP server. In '--sse' mode (what Railway runs):"
    )
    pdf.bullets([
        "Reads PORT from env (Railway injects this - e.g. 8080)",
        "Reads RAILWAY_PUBLIC_DOMAIN to build base_url (e.g. https://worldcup-analysis-mcp-production.up.railway.app)",
        "Creates SimpleOAuthProvider(base_url=base_url)",
        "Builds FastMCP instance with auth=oauth",
        "Registers all 17 tool functions",
        "Calls mcp.run(transport='streamable-http', host='0.0.0.0', port=port)",
    ])
    pdf.code(
        "# --sse mode startup (abridged)\n"
        "railway_domain = os.getenv('RAILWAY_PUBLIC_DOMAIN', '')\n"
        "base_url = settings.BASE_URL or f'https://{railway_domain}'\n"
        "oauth = SimpleOAuthProvider(base_url=base_url)\n"
        "mcp_http = _build_mcp(auth=oauth)\n"
        "mcp_http.run(transport='streamable-http', host='0.0.0.0', port=port)"
    )

    pdf.subsection("auth/oauth_provider.py  -  The Auth Brain")
    pdf.body(
        "Implements all OAuth logic. Key responsibilities:"
    )
    pdf.bullets([
        "register_client(): stores Claude's client_id in memory when it first registers",
        "authorize(): creates a session_id, stores pending auth data, returns the approval page URL",
        "do_approve() route: handles the form submit, generates auth code, redirects to Claude callback",
        "exchange_authorization_code(): verifies PKCE, generates access token, stores in self._tokens",
        "load_access_token(): looks up token by string, checks expiry, returns AccessToken or None",
        "protected_resource_metadata() route: serves /.well-known/oauth-protected-resource so Claude "
        "knows the MCP endpoint is at /mcp (not root /)",
    ])
    pdf.body(
        "All token storage is in-memory (Python dict). Tokens are lost on server restart. "
        "This means: after Railway redeploys your app, you need to disconnect and reconnect "
        "the Claude connector (one click). With the 30-day TTL this is infrequent."
    )

    pdf.subsection("config.py  -  Settings and Team Data")
    pdf.bullets([
        "Settings class: reads all env vars at import time into typed attributes",
        "TEAM_ID_MAP: maps team names/nicknames to football-data.org team IDs for all 48 WC teams",
        "GROUP_MAP: maps group letters A-L to lists of team IDs",
        "resolve_team_id(): fuzzy-matches user input ('usa', 'USMNT', 'United States') to a team ID",
    ])

    pdf.subsection("cache/cache_manager.py  -  API Quota Protection")
    pdf.body(
        "A singleton CacheManager with separate TTLCache buckets for each data type. "
        "Every tool checks the cache before calling an API. TTLs:"
    )
    pdf.bullets([
        "Live scores: 30 seconds (always fresh)",
        "Standings: 5 minutes",
        "Top scorers: 5 minutes",
        "Team form / H2H: 1 hour",
        "Fixtures: 24 hours",
    ])

    # ── 6. IMPORTANT ENDPOINTS ────────────────────────────────────────────────
    pdf.section("6", "Important Endpoints & How to Test Them")
    pdf.subsection("Verify Everything Is Working")
    pdf.body("Open these URLs in your browser after deployment:")
    pdf.code(
        "# 1. Auth server discovery (should return JSON with all OAuth endpoints)\n"
        "https://worldcup-analysis-mcp-production.up.railway.app/.well-known/oauth-authorization-server\n\n"
        "# 2. Resource metadata (should return resource=/mcp, must NOT be 404)\n"
        "https://worldcup-analysis-mcp-production.up.railway.app/.well-known/oauth-protected-resource\n\n"
        "# 3. MCP endpoint (should return 401 - means server is running with auth)\n"
        "https://worldcup-analysis-mcp-production.up.railway.app/mcp"
    )
    pdf.subsection("Claude Connector URL")
    pdf.code("https://worldcup-analysis-mcp-production.up.railway.app/mcp")
    pdf.body("Always include /mcp at the end. This is the MCP endpoint, not the base URL.")

    # ── 7. SECURITY MODEL ─────────────────────────────────────────────────────
    pdf.section("7", "Security Model and Limitations")
    pdf.subsection("What Is Protected")
    pdf.bullets([
        "All 17 tools require a valid Bearer token to call - no anonymous access to MCP endpoint",
        "Tokens are tied to a specific registered client_id (Claude's registration)",
        "PKCE prevents authorization code interception by a third party",
        "Tokens expire after 30 days - automatic re-auth required after that",
        "Each auth code is single-use and expires in 5 minutes",
    ])
    pdf.subsection("Known Limitations (by design - acceptable for personal use)")
    pdf.bullets([
        "Single-user: the approval page has no login - anyone who can reach the URL can approve. "
        "This is fine because Railway is your personal server and you control who has the URL.",
        "In-memory token storage: tokens are lost on server restart/redeploy. Re-connecting "
        "the Claude connector takes about 30 seconds and just requires clicking 'Approve' again.",
        "No refresh tokens: when the 30-day token expires, full re-auth is needed.",
        "No user identity: our OAuth server doesn't verify who you are, it just presents an "
        "approval page. Suitable for a personal/team MCP server, not a public multi-tenant service.",
    ])

    out_path = "worldcup_mcp_architecture.pdf"
    pdf.output(out_path)
    print(f"PDF written to: {out_path}")


if __name__ == "__main__":
    build()
