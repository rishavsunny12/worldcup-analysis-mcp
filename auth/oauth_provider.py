import logging
import secrets
import time
from typing import Optional

from mcp.server.auth.provider import AuthorizationCode, AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from auth.token_store import TokenStore
from fastmcp.server.auth import AccessToken, OAuthProvider
from fastmcp.server.auth.auth import ClientRegistrationOptions

logger = logging.getLogger(__name__)

TOKEN_TTL = 30 * 24 * 3600  # 30 days


class SimpleOAuthProvider(OAuthProvider):
    """
    OAuth 2.0 provider for self-hosted MCP with SQLite-backed token persistence.
    Shows a one-click approval page — no username/password required.
    Tokens expire after 30 days and survive server redeploys when OAUTH_DB_PATH is on a volume.
    """

    def __init__(self, base_url: str, store: TokenStore | None = None):
        super().__init__(
            base_url=base_url,
            client_registration_options=ClientRegistrationOptions(enabled=True),
        )
        self._store = store or TokenStore()
        self._codes: dict[str, AuthorizationCode] = {}
        self._pending: dict[str, dict] = {}
        logger.info(
            f"OAuth store ready at {self._store.db_path} "
            f"({self._store.token_count()} active token(s))"
        )

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._store.save_client(client_info)

    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        return self._store.get_client(client_id)

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

        del self._codes[code_str]
        token_str = secrets.token_hex(32)
        access = AccessToken(
            token=token_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + TOKEN_TTL,
        )
        self._store.save_token(access)
        logger.info(
            f"Token issued for client={client.client_id} expires_at={access.expires_at}"
        )
        return OAuthToken(access_token=token_str, token_type="bearer", expires_in=TOKEN_TTL)

    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        at = self._store.get_token(token)
        if at is None:
            logger.warning(
                f"load_access_token: token not found "
                f"(store has {self._store.token_count()} tokens)"
            )
            return None
        if at.expires_at and at.expires_at < time.time():
            self._store.delete_token(token)
            logger.warning("load_access_token: token expired")
            return None
        logger.info(f"load_access_token: valid token for client={at.client_id}")
        return at

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        return await self.load_access_token(token)

    async def load_refresh_token(self, client, refresh_token: str):
        return None

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        raise NotImplementedError("Refresh tokens not supported")

    async def revoke_token(self, token: str, token_type_hint: str | None = None) -> None:
        self._store.delete_token(token)

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        base_routes = super().get_routes(mcp_path)

        provider = self
        resource_path = mcp_path or "/mcp"

        async def protected_resource_metadata(request: Request):
            base = str(provider.base_url).rstrip("/")
            return JSONResponse({
                "resource": f"{base}{resource_path}",
                "authorization_servers": [f"{base}/"],
            })

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
            Route("/.well-known/oauth-protected-resource", protected_resource_metadata, methods=["GET"]),
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
