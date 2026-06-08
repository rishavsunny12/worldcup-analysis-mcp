# Railway deployment

## Start command

The [`Procfile`](../Procfile) runs:

```
web: python server.py --sse
```

This enables OAuth-protected HTTP MCP at `/mcp`.

## OAuth persistence (required for no re-auth on redeploy)

Without a volume, OAuth tokens live only until the container restarts. To keep users connected across deploys:

1. Open your Railway service → **Volumes** → **Add Volume**
2. Mount path: `/data`
3. Add variable (optional; auto-detected when `/data` exists):
   ```
   OAUTH_DB_PATH=/data/oauth.db
   ```
4. Redeploy once to create the database file on the volume.

After this, Bearer tokens and client registrations persist for up to 30 days. See [OAUTH.md](./OAUTH.md) for the full auth flow.

## Other variables

Railway injects `RAILWAY_PUBLIC_DOMAIN` automatically; the server uses it as `BASE_URL` for OAuth discovery.

Set these in Railway **Variables**:

| Variable | Required |
|----------|----------|
| `API_FOOTBALL_KEY` | Yes |
| `FOOTBALL_DATA_KEY` | Yes |
| `BZZOIRO_KEY` | Yes |
| `LIVE_DATA_SOURCE` | Optional (`bzzoiro` default — live scores, standings, form; set `legacy` for API-Football / football-data.org) |
| `API_FOOTBALL_TIER` | Yes (`free` or `paid`; used only when `LIVE_DATA_SOURCE=legacy` or `get_match_preview`) |
| `OAUTH_DB_PATH` | Recommended (`/data/oauth.db`) |
| `CACHE_BUST` | Optional — set `1` on one deploy to wipe in-memory tool caches at startup |

## Cache and redeploys

Squad analysis tools cache formatted output in **process memory** (default TTL: 1 hour for form tools, 5 minutes for group overview). A redeploy restarts the process and clears cache automatically.

If you deploy code without restarting (e.g. local MCP subprocess still running), restart the MCP server or set `CACHE_BUST=1` once, redeploy, then remove the variable.

After squad-logic changes, bump cache `source` keys in code or restart the service before re-testing.
