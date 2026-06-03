import csv
import difflib
import logging
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent

LEAGUE_FILES: dict[str, str] = {
    "EPL":        "understat_EPL_2025_26_player_stats.csv",
    "La Liga":    "understat_La_Liga_2025_26_player_stats.csv",
    "Bundesliga": "understat_Bundesliga_2025_26_player_stats.csv",
    "Serie A":    "understat_Serie_A_2025_26_player_stats.csv",
    "Ligue 1":    "understat_Ligue_1_2025_26_player_stats.csv",
    "RFPL":       "understat_RFPL_2025_26_player_stats.csv",
}


def _normalize(name: str) -> str:
    """Lowercase, strip accents, strip whitespace."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_name.lower().strip()


def _load_all() -> tuple[dict[str, list[dict]], list[dict]]:
    index: dict[str, list[dict]] = {}
    flat: list[dict] = []

    for league, filename in LEAGUE_FILES.items():
        path = ROOT / filename
        if not path.exists():
            logger.warning(f"CSV not found: {path}")
            continue
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                row["league"] = league
                flat.append(row)
                key = _normalize(row["player_name"])
                index.setdefault(key, []).append(row)

    logger.info(f"CSV loader: {len(flat)} players across {len(LEAGUE_FILES)} leagues")
    return index, flat


PLAYER_INDEX, ALL_PLAYERS = _load_all()


def find_player(name: str) -> list[dict]:
    """Return all CSV rows matching a player name. Three-tier: exact → substring → fuzzy."""
    key = _normalize(name)

    if key in PLAYER_INDEX:
        return PLAYER_INDEX[key]

    # substring match
    matches = []
    for indexed_key, rows in PLAYER_INDEX.items():
        if key in indexed_key or indexed_key in key:
            matches.extend(rows)
    if matches:
        return matches

    # fuzzy fallback
    close = difflib.get_close_matches(key, PLAYER_INDEX.keys(), n=1, cutoff=0.80)
    if close:
        return PLAYER_INDEX[close[0]]

    return []
