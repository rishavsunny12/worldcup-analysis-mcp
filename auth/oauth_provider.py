import asyncio
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from mcp.server.auth.provider import AuthorizationCode, AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from fastmcp.server.auth import AccessToken, OAuthProvider
from fastmcp.server.auth.auth import ClientRegistrationOptions

logger = logging.getLogger(__name__)

TOKEN_TTL = 30 * 24 * 3600  # 30 days


def _default_state_file() -> Path:
    """Prefer /data (Railway persistent volume mount point) if it exists."""
    data_dir = Path("/data")
    if data_dir.exists() and os.access(data_dir, os.W_OK):
        return data_dir / "oauth_state.json"
    return Path("oauth_state.json")


class SimpleOAuthProvider(OAuthProvider):
    """
    Minimal OAuth 2.0 provider for self-hosted MCP.
    Shows a one-click approval page — no username/password required.
    Tokens expire after 30 days. State is persisted to disk so tokens
    survive process restarts (and Railway redeployments when /data is mounted).
    """

    def __init__(self, base_url: str, state_file: Path | None = None):
        super().__init__(
            base_url=base_url,
            client_registration_options=ClientRegistrationOptions(enabled=True),
        )
        self._state_file = state_file or _default_state_file()
        self._lock = asyncio.Lock()
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._codes: dict[str, AuthorizationCode] = {}
        self._tokens: dict[str, AccessToken] = {}
        self._pending: dict[str, dict] = {}
        self._load_state()

    # ── persistence ──────────────────────────────────────────────────────────

    def _load_state(self) -> None:
        if not self._state_file.exists():
            return
        try:
            raw = json.loads(self._state_file.read_text())
            now = time.time()

            for cid, c in raw.get("clients", {}).items():
                try:
                    self._clients[cid] = OAuthClientInformationFull(**c)
                except Exception:
                    pass

            for tok, t in raw.get("tokens", {}).items():
                if t.get("expires_at", 0) > now:
                    self._tokens[tok] = AccessToken(**t)

            logger.info(
                f"OAuth state loaded from {self._state_file} "
                f"({len(self._clients)} clients, {len(self._tokens)} tokens)"
            )
        except Exception as exc:
            logger.warning(f"Could not load OAuth state from {self._state_file}: {exc}")

    def _save_state(self) -> None:
        try:
            payload = {
                "clients": {
                    cid: c.model_dump(mode="json") for cid, c in self._clients.items()
                },
                "tokens": {
                    tok: {
                        "token": t.token,
                        "client_id": t.client_id,
                        "scopes": list(t.scopes or []),
                        "expires_at": t.expires_at,
                    }
                    for tok, t in self._tokens.items()
                },
            }
            self._state_file.write_text(json.dumps(payload, indent=2))
        except Exception as exc:
            logger.warning(f"Could not persist OAuth state to {self._state_file}: {exc}")

    # ── OAuthProvider interface ───────────────────────────────────────────────

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        async with self._lock:
            self._clients[client_info.client_id] = client_info
            self._save_state()

    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        return self._clients.get(client_id)

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        session_id = secrets.token_hex(16)
        self._pending[session_id] = {
            "client_id": client.client_id,
            "redirect_uri": str(params.redirect_uri),
            "state": params.state or "",
            "code_challenge": params.code_challenge or "",
            "scopes": list(params.scopes or []),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
        }
        base = str(self.base_url).rstrip("/")
        return f"{base}/oauth/approve?session={session_id}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> Optional[AuthorizationCode]:
        return self._codes.get(authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        code_str = authorization_code.code
        if code_str not in self._codes:
            raise ValueError("Invalid or expired authorization code")

        async with self._lock:
            del self._codes[code_str]
            token_str = secrets.token_hex(32)
            self._tokens[token_str] = AccessToken(
                token=token_str,
                client_id=client.client_id,
                scopes=authorization_code.scopes,
                expires_at=int(time.time()) + TOKEN_TTL,
            )
            self._save_state()

        return OAuthToken(access_token=token_str, token_type="bearer", expires_in=TOKEN_TTL)

    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        at = self._tokens.get(token)
        if at and at.expires_at and at.expires_at < time.time():
            async with self._lock:
                self._tokens.pop(token, None)
                self._save_state()
            return None
        return at

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        return await self.load_access_token(token)

    async def load_refresh_token(self, client, refresh_token: str):
        return None

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        raise NotImplementedError("Refresh tokens not supported")

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> None:
        async with self._lock:
            self._tokens.pop(token, None)
            self._save_state()

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        base_routes = super().get_routes(mcp_path)

        provider = self

        async def approval_page(request: Request):
            session_id = request.query_params.get("session", "")
            if session_id not in provider._pending:
                return HTMLResponse("<h2>Invalid or expired session.</h2>", status_code=400)
            return HTMLResponse(_APPROVAL_HTML.format(session_id=session_id))

        async def do_approve(request: Request):
            form = await request.form()
            session_id = form.get("session_id", "")
            if session_id not in provider._pending:
                return HTMLResponse("<h2>Invalid or expired session.</h2>", status_code=400)

            data = provider._pending.pop(session_id)
            code_str = secrets.token_hex(32)
            provider._codes[code_str] = AuthorizationCode(
                code=code_str,
                scopes=data["scopes"],
                expires_at=int(time.time()) + 300,
                client_id=data["client_id"],
                code_challenge=data["code_challenge"] or None,
                redirect_uri=data["redirect_uri"],
                redirect_uri_provided_explicitly=data["redirect_uri_provided_explicitly"],
            )
            redirect_uri = data["redirect_uri"]
            state = data["state"]
            sep = "&" if "?" in redirect_uri else "?"
            return RedirectResponse(
                f"{redirect_uri}{sep}code={code_str}&state={state}", status_code=302
            )

        return base_routes + [
            Route("/oauth/approve", approval_page, methods=["GET"]),
            Route("/oauth/approve", do_approve, methods=["POST"]),
        ]


_APPROVAL_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Authorize worldcup-analysis-mcp</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{ font-family: -apple-system, sans-serif; max-width: 420px;
           margin: 80px auto; text-align: center; padding: 0 20px; }}
    h2 {{ font-size: 1.4rem; margin-bottom: 8px; }}
    p  {{ color: #555; margin-bottom: 32px; }}
    button {{ background: #1a1a2e; color: white; padding: 14px 36px;
              border: none; border-radius: 8px; font-size: 16px;
              cursor: pointer; width: 100%; }}
    button:hover {{ background: #2a2a4e; }}
  </style>
</head>
<body>
  <h2>⚽ worldcup-analysis-mcp</h2>
  <p>Allow access to FIFA World Cup 2026 analysis tools?</p>
  <form method="POST" action="/oauth/approve">
    <input type="hidden" name="session_id" value="{session_id}">
    <button type="submit">Approve Access</button>
  </form>
</body>
</html>"""
