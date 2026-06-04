"""
Integration test for bzzoiro live events API.
Run manually: pytest tests/test_bzzoiro_live.py -v
Requires BZZOIRO_KEY in .env
"""
import os

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://sports.bzzoiro.com/api/v2"
API_KEY = os.getenv("BZZOIRO_KEY", "")


@pytest.fixture
def headers():
    assert API_KEY, "BZZOIRO_KEY not set in .env"
    return {"Authorization": f"Token {API_KEY}"}


@pytest.mark.integration
def test_live_events_status(headers):
    """API returns 200 with a valid key."""
    r = httpx.get(f"{BASE_URL}/events/live/", headers=headers, timeout=10)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:300]}"


@pytest.mark.integration
def test_live_events_is_json(headers):
    """Response body is valid JSON."""
    r = httpx.get(f"{BASE_URL}/events/live/", headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()
    assert isinstance(data, (list, dict)), f"Unexpected type: {type(data)}"


@pytest.mark.integration
def test_live_events_fields(headers):
    """Each event has expected top-level fields (adjust after first run)."""
    r = httpx.get(f"{BASE_URL}/events/live/", headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()

    # Unwrap common envelope shapes
    events = data if isinstance(data, list) else data.get("results", data.get("data", data.get("events", [])))

    if not events:
        pytest.skip("No live events right now — re-run when matches are live")

    first = events[0]
    print(f"\nSample event keys: {list(first.keys())}")
    print(f"Sample event: {first}")

    # Basic sanity — update expected_keys once you know the schema
    expected_keys = {"id"}
    missing = expected_keys - first.keys()
    assert not missing, f"Missing keys in event: {missing}"
