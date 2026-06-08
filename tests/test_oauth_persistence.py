"""Unit tests for OAuth token persistence across provider restarts."""

import time
from pathlib import Path

import pytest
from fastmcp.server.auth import AccessToken
from mcp.shared.auth import OAuthClientInformationFull

from auth.oauth_provider import SimpleOAuthProvider
from auth.token_store import TokenStore


@pytest.fixture
def oauth_db(tmp_path: Path) -> Path:
    return tmp_path / "oauth.db"


@pytest.fixture
def store(oauth_db: Path) -> TokenStore:
    return TokenStore(db_path=oauth_db)


def _sample_client() -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id="test-client-1",
        client_secret="secret",
        redirect_uris=["http://localhost/callback"],
    )


def test_token_store_roundtrip(store: TokenStore) -> None:
    token = AccessToken(
        token="abc123",
        client_id="test-client-1",
        scopes=["mcp"],
        expires_at=int(time.time()) + 3600,
    )
    store.save_token(token)
    loaded = store.get_token("abc123")
    assert loaded is not None
    assert loaded.client_id == "test-client-1"
    assert loaded.scopes == ["mcp"]


def test_token_store_purges_expired(store: TokenStore) -> None:
    store.save_token(
        AccessToken(
            token="expired",
            client_id="c",
            scopes=[],
            expires_at=int(time.time()) - 10,
        )
    )
    store.save_token(
        AccessToken(
            token="valid",
            client_id="c",
            scopes=[],
            expires_at=int(time.time()) + 3600,
        )
    )
    removed = store.purge_expired()
    assert removed == 1
    assert store.get_token("expired") is None
    assert store.get_token("valid") is not None


def test_client_store_roundtrip(store: TokenStore) -> None:
    client = _sample_client()
    store.save_client(client)
    loaded = store.get_client("test-client-1")
    assert loaded is not None
    assert loaded.client_id == "test-client-1"
    assert str(loaded.redirect_uris[0]).startswith("http://localhost")


@pytest.mark.asyncio
async def test_token_survives_provider_restart(oauth_db: Path) -> None:
    """Simulate redeploy: new provider instance, same SQLite file."""
    store1 = TokenStore(db_path=oauth_db)
    provider1 = SimpleOAuthProvider(base_url="https://example.com", store=store1)

    client = _sample_client()
    await provider1.register_client(client)

    token_str = "persist-me-token"
    store1.save_token(
        AccessToken(
            token=token_str,
            client_id=client.client_id,
            scopes=["mcp"],
            expires_at=int(time.time()) + 86400,
        )
    )

    store2 = TokenStore(db_path=oauth_db)
    provider2 = SimpleOAuthProvider(base_url="https://example.com", store=store2)

    loaded_client = await provider2.get_client(client.client_id)
    assert loaded_client is not None
    assert loaded_client.client_id == client.client_id

    loaded_token = await provider2.load_access_token(token_str)
    assert loaded_token is not None
    assert loaded_token.client_id == client.client_id


@pytest.mark.asyncio
async def test_expired_token_rejected_after_restart(oauth_db: Path) -> None:
    store = TokenStore(db_path=oauth_db)
    provider = SimpleOAuthProvider(base_url="https://example.com", store=store)
    store.save_token(
        AccessToken(
            token="old-token",
            client_id="c",
            scopes=[],
            expires_at=int(time.time()) - 1,
        )
    )
    result = await provider.load_access_token("old-token")
    assert result is None
    assert store.get_token("old-token") is None
