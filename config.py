import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    API_FOOTBALL_KEY: str = os.getenv("API_FOOTBALL_KEY", "")
    FOOTBALL_DATA_KEY: str = os.getenv("FOOTBALL_DATA_KEY", "")
    TIER: str = os.getenv("API_FOOTBALL_TIER", "free")
    CACHE_TTL_LIVE: int = int(os.getenv("CACHE_TTL_LIVE", 30))
    CACHE_TTL_LINEUPS: int = int(os.getenv("CACHE_TTL_LINEUPS", 300))
    CACHE_TTL_FORM: int = int(os.getenv("CACHE_TTL_FORM", 3600))
    CACHE_TTL_FIXTURES: int = int(os.getenv("CACHE_TTL_FIXTURES", 86400))
    CACHE_TTL_STANDINGS: int = int(os.getenv("CACHE_TTL_STANDINGS", 300))
    CACHE_TTL_H2H: int = int(os.getenv("CACHE_TTL_H2H", 3600))
    CACHE_TTL_SCORERS: int = int(os.getenv("CACHE_TTL_SCORERS", 300))
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")


settings = Settings()

# IDs are football-data.org IDs (free tier during dev).
# When switching to API_FOOTBALL_TIER=paid, replace with api-sports.io IDs
# by calling: GET /teams?league=1&season=2026
TEAM_ID_MAP: dict[str, int] = {
    # Group A
    "czechia": 798,
    "czech republic": 798,
    "mexico": 769,
    "south africa": 774,
    "south korea": 772,
    "korea": 772,

    # Group B
    "bosnia": 1060,
    "bosnia-herzegovina": 1060,
    "bosnia and herzegovina": 1060,
    "canada": 828,
    "qatar": 8030,
    "switzerland": 788,

    # Group C
    "brazil": 764,
    "morocco": 815,
    "haiti": 836,
    "scotland": 8873,

    # Group D
    "turkey": 803,
    "turkiye": 803,
    "united states": 771,
    "usa": 771,
    "us": 771,
    "usmnt": 771,
    "paraguay": 761,
    "australia": 779,

    # Group E
    "germany": 759,
    "curacao": 9460,
    "curaçao": 9460,
    "ivory coast": 1935,
    "cote d'ivoire": 1935,
    "ecuador": 791,

    # Group F
    "sweden": 792,
    "netherlands": 8601,
    "holland": 8601,
    "japan": 766,
    "tunisia": 802,

    # Group G
    "belgium": 805,
    "egypt": 825,
    "iran": 840,
    "new zealand": 783,
    "nz": 783,

    # Group H
    "spain": 760,
    "cape verde": 1930,
    "cape verde islands": 1930,
    "saudi arabia": 801,
    "uruguay": 758,

    # Group I
    "iraq": 8062,
    "france": 773,
    "senegal": 804,
    "norway": 8872,

    # Group J
    "argentina": 762,
    "algeria": 778,
    "austria": 816,
    "jordan": 8049,

    # Group K
    "dr congo": 1934,
    "congo dr": 1934,
    "congo": 1934,
    "portugal": 765,
    "uzbekistan": 8070,
    "colombia": 818,

    # Group L
    "england": 770,
    "three lions": 770,
    "croatia": 799,
    "ghana": 763,
    "black stars": 763,
    "panama": 1836,

    # Nicknames & common shorthand
    "el tri": 769,          # Mexico
    "bafana bafana": 774,   # South Africa
    "la roja": 760,         # Spain
    "die mannschaft": 759,  # Germany
    "les bleus": 773,       # France
    "socceroos": 779,       # Australia
    "all whites": 783,      # New Zealand
    "les lions": 804,       # Senegal
    "drc": 1934,            # DR Congo
    "uzbek": 8070,
    "swiss": 788,
    "czechs": 798,
    "civ": 1935,            # Côte d'Ivoire
}

GROUP_MAP: dict[str, list[int]] = {
    "A": [798, 769, 774, 772],
    "B": [1060, 828, 8030, 788],
    "C": [764, 815, 836, 8873],
    "D": [803, 771, 761, 779],
    "E": [759, 9460, 1935, 791],
    "F": [792, 8601, 766, 802],
    "G": [805, 825, 840, 783],
    "H": [760, 1930, 801, 758],
    "I": [8062, 773, 804, 8872],
    "J": [762, 778, 816, 8049],
    "K": [1934, 765, 8070, 818],
    "L": [770, 799, 763, 1836],
}


def resolve_team_id(name: str) -> int | None:
    """Fuzzy match a team name to its team ID."""
    key = name.lower().strip()
    if key in TEAM_ID_MAP:
        return TEAM_ID_MAP[key]
    for k, v in TEAM_ID_MAP.items():
        if key in k or k in key:
            return v
    return None
