"""Persistent SQLite store for OAuth access tokens and client registrations."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path

from fastmcp.server.auth import AccessToken
from mcp.shared.auth import OAuthClientInformationFull

logger = logging.getLogger(__name__)


def default_db_path() -> Path:
    """Resolve OAuth DB path: env var > Railway /data volume > local data/."""
    env = os.getenv("OAUTH_DB_PATH", "").strip()
    if env:
        return Path(env)
    if Path("/data").is_dir():
        return Path("/data/oauth.db")
    return Path(__file__).resolve().parent.parent / "data" / "oauth.db"


class TokenStore:
    """SQLite-backed persistence for access tokens and OAuth clients."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        removed = self.purge_expired()
        if removed:
            logger.info(f"Purged {removed} expired OAuth token(s) from {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS access_tokens (
                    token TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    scopes_json TEXT NOT NULL,
                    expires_at INTEGER,
                    resource TEXT,
                    claims_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS oauth_clients (
                    client_id TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def save_token(self, access_token: AccessToken) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO access_tokens
                    (token, client_id, scopes_json, expires_at, resource, claims_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    access_token.token,
                    access_token.client_id,
                    json.dumps(access_token.scopes),
                    access_token.expires_at,
                    access_token.resource,
                    json.dumps(access_token.claims or {}),
                ),
            )
            conn.commit()

    def get_token(self, token: str) -> AccessToken | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM access_tokens WHERE token = ?", (token,)
            ).fetchone()
        if row is None:
            return None
        return AccessToken(
            token=row["token"],
            client_id=row["client_id"],
            scopes=json.loads(row["scopes_json"]),
            expires_at=row["expires_at"],
            resource=row["resource"],
            claims=json.loads(row["claims_json"] or "{}"),
        )

    def delete_token(self, token: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM access_tokens WHERE token = ?", (token,))
            conn.commit()

    def token_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM access_tokens").fetchone()
        return int(row["n"]) if row else 0

    def save_client(self, client: OAuthClientInformationFull) -> None:
        payload = client.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO oauth_clients (client_id, data_json)
                VALUES (?, ?)
                """,
                (client.client_id, json.dumps(payload)),
            )
            conn.commit()

    def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json FROM oauth_clients WHERE client_id = ?", (client_id,)
            ).fetchone()
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate(json.loads(row["data_json"]))

    def purge_expired(self) -> int:
        now = int(time.time())
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM access_tokens WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            conn.commit()
            return cur.rowcount
