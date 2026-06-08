# OAuth for worldcup-analysis-mcp

Production runs `python server.py --sse` with a minimal OAuth 2.0 provider (Authorization Code + PKCE).

## Flow

1. MCP client (Cursor, Claude Desktop) connects to `https://your-app.up.railway.app/mcp`.
2. Unauthenticated requests receive **401**; the client discovers OAuth endpoints via `/.well-known/oauth-*`.
3. Client registers dynamically (`POST /register`) and opens `/authorize` in your browser.
4. You click **Approve Access** on `/oauth/approve` (no password).
5. Client exchanges the auth code for a **Bearer token** (30-day TTL).
6. All `/mcp` tool calls include `Authorization: Bearer <token>`.

## Persistence across redeploys

Tokens and OAuth client registrations are stored in **SQLite** (`OAUTH_DB_PATH`), not in RAM.

| Data | Storage | Survives redeploy? |
|------|---------|-------------------|
| Access tokens (30 days) | SQLite | Yes |
| OAuth client registrations | SQLite | Yes |
| Pending approval sessions | In-memory | No (re-open browser if interrupted) |
| Auth codes (5 min) | In-memory | No |

**With a Railway volume mounted at `/data`**, users who already approved stay connected after routine deploys. They only re-authorize when:

- The 30-day token expires
- They disconnect the MCP server in client settings
- The SQLite database is deleted or the volume is not mounted

## Railway setup

1. In your Railway service, add a **Volume** mounted at `/data`.
2. Set env var (optional — this is the default when `/data` exists):
   ```
   OAUTH_DB_PATH=/data/oauth.db
   ```
3. Redeploy. Existing tokens on the volume are loaded on startup.

Local development defaults to `data/oauth.db` in the project (gitignored).

## Environment variables

| Variable | Purpose |
|----------|---------|
| `BASE_URL` | Public URL for OAuth discovery (auto-set via `RAILWAY_PUBLIC_DOMAIN` on Railway) |
| `OAUTH_DB_PATH` | SQLite file path for tokens/clients (default: `/data/oauth.db` or `data/oauth.db`) |

## Security notes

- One-click approval with no user login — suitable for personal/team servers.
- Anyone who can reach `/oauth/approve` during an active session could approve; keep the URL private.
- Refresh tokens are not implemented; re-approve after 30 days or use persistent access tokens until expiry.
