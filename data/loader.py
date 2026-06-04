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

# Maps bzzoiro club_league_name → understat league key (top-6 only)
BZZ_LEAGUE_MAP: dict[str, str] = {
    "Premier League":        "EPL",
    "La Liga":               "La Liga",
    "LaLiga":                "La Liga",
    "Bundesliga":            "Bundesliga",
    "Serie A":               "Serie A",
    "Ligue 1":               "Ligue 1",
    "Russian Premier League": "RFPL",
    "RPL":                   "RFPL",
}

# bzzoiro wc_position codes → understat-style single letter
BZZ_POS_MAP: dict[str, str] = {"FW": "F", "MF": "M", "DF": "D", "GK": "GK"}

# League quality factors (0–1). Used to adjust raw xG for cross-league comparisons.
# Rationale: a player with 20 xG in the Saudi Pro League is not equal to 20 xG in the
# Premier League. Multiplying by this factor produces a competition-normalised xG.
LEAGUE_QUALITY: dict[str, float] = {
    # Understat keys (top-6)
    "EPL":        1.00,
    "La Liga":    1.00,
    "Bundesliga": 0.95,
    "Serie A":    0.95,
    "Ligue 1":    0.90,
    "RFPL":       0.75,
    # Bzzoiro names for top-6
    "Premier League":          1.00,
    "LaLiga":                  1.00,
    "Russian Premier League":  0.75,
    "RPL":                     0.75,
    # Other European
    "Eredivisie":              0.82,
    "Primeira Liga":           0.82,
    "Liga Portugal":           0.82,
    "Pro League":              0.78,   # Belgian
    "Jupiler Pro League":      0.78,
    "Süper Lig":               0.78,
    "Super Lig":               0.78,
    "Austrian Bundesliga":     0.72,
    "Swiss Super League":      0.72,
    "Scottish Premiership":    0.72,
    "Scottish Premier League": 0.72,
    "Danish Superliga":        0.70,
    "Stoiximan Super League":  0.68,
    "Greek Super League":      0.68,
    "Ekstraklasa":             0.68,
    "Czech First League":      0.68,
    "HNL":                     0.68,   # Croatian
    "Norwegian Eliteserien":   0.65,
    "Swedish Allsvenskan":     0.65,
    "Romanian Liga 1":         0.65,
    # Americas
    "Liga MX":                 0.72,
    "MLS":                     0.68,
    "Brasileirao":             0.78,
    "Serie A (Brazil)":        0.78,
    "Argentine Primera":       0.78,
    "Liga Profesional":        0.78,
    "Uruguayan Primera":       0.65,
    "Colombiana":              0.63,
    "Chilean Primera":         0.63,
    "Ecuadorian Serie A":      0.62,
    "Bolivian Liga":           0.58,
    # Middle East
    "Saudi Pro League":        0.68,
    "UAE Pro League":          0.62,
    "Qatar Stars League":      0.62,
    # Asia
    "J-League":                0.70,
    "J1 League":               0.70,
    "K League 1":              0.65,
    "Chinese Super League":    0.60,
    "A-League":                0.60,
    "Iran Pro League":         0.62,
    "AFC Champions League":    0.65,
    # Africa
    "CAF Champions League":    0.65,
    "Egyptian Premier League": 0.62,
    "Botola Pro":              0.58,
    "Algerian Ligue Professionnelle": 0.58,
    "Tunisian Ligue 1":        0.58,
    "NPFL":                    0.55,
    # Catch-alls
    "International Friendly Games": 0.40,
    "Unknown":                 0.50,
}


def get_league_quality(league_name: str) -> float:
    """Return the quality factor (0–1) for a league. Works for both understat keys
    and raw bzzoiro club_league_name strings. Falls back to 0.55 for unknown leagues."""
    if not league_name:
        return 0.55
    if league_name in LEAGUE_QUALITY:
        return LEAGUE_QUALITY[league_name]
    low = league_name.lower()
    for name, q in LEAGUE_QUALITY.items():
        if name.lower() in low or low in name.lower():
            return q
    return 0.55


def quality_label(q: float) -> str:
    """Return a compact star label showing league tier and quality factor.
    Example: '★★★★★ (1.00)' for the Premier League, '★★☆☆☆ (0.68)' for Saudi Pro League."""
    if q >= 0.98:   stars = "★★★★★"
    elif q >= 0.88: stars = "★★★★☆"
    elif q >= 0.75: stars = "★★★☆☆"
    elif q >= 0.63: stars = "★★☆☆☆"
    else:           stars = "★☆☆☆☆"
    return f"{stars} ({q:.2f})"


def get_adj_xg(row: dict) -> float:
    """Return quality-adjusted xG for any player row (understat or normalised bzzoiro).
    Adjusted xG = raw npxG × league quality factor. Use this for cross-league ranking."""
    try:
        raw = float(row.get("npxG") or 0)
    except (TypeError, ValueError):
        raw = 0.0
    if row.get("_source") == "bzzoiro":
        q = row.get("_league_quality") or 0.55
    else:
        q = get_league_quality(row.get("league", ""))
    return round(raw * q, 2)


def _normalize(name: str) -> str:
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
    """Return all understat CSV rows matching a player name (exact → substring → fuzzy)."""
    key = _normalize(name)
    if key in PLAYER_INDEX:
        return PLAYER_INDEX[key]
    matches = []
    for indexed_key, rows in PLAYER_INDEX.items():
        if key in indexed_key or indexed_key in key:
            matches.extend(rows)
    if matches:
        return matches
    close = difflib.get_close_matches(key, PLAYER_INDEX.keys(), n=1, cutoff=0.80)
    if close:
        return PLAYER_INDEX[close[0]]
    return []


# ── Bzzoiro data ──────────────────────────────────────────────────────────────

def normalize_bzz_player(row: dict) -> dict:
    """Adapt a bzzoiro player row to understat-compatible field names so all
    downstream profile/formatting code can handle both sources uniformly.
    Includes _league_quality and _adj_xg for cross-league fair comparison."""
    raw_league = row.get("club_league_name", "") or ""
    league     = BZZ_LEAGUE_MAP.get(raw_league, "")
    position   = BZZ_POS_MAP.get(row.get("wc_position", ""), row.get("wc_position", ""))
    xg         = row.get("club_xg") or "0"
    xa         = row.get("club_xa") or "0"
    goals      = row.get("club_goals") or "0"
    assists    = row.get("club_assists") or "0"
    matches    = row.get("club_matches") or "0"
    quality    = get_league_quality(raw_league)
    try:
        adj_xg = round(float(xg) * quality, 2)
    except (TypeError, ValueError):
        adj_xg = 0.0
    return {
        "player_name":     row.get("player_name", ""),
        "team_title":      row.get("club_name", ""),
        "league":          league,
        "position":        position,
        "games":           matches,
        "time":            row.get("club_minutes") or "0",
        "xG":              xg,
        "npxG":            xg,        # bzzoiro has no npxG; club_xg is the closest proxy
        "xA":              xa,
        "xGChain":         "0",
        "xGBuildup":       "0",
        "goals":           goals,
        "npg":             goals,
        "assists":         assists,
        "shots":           row.get("club_shots") or "0",
        "key_passes":      row.get("club_key_passes") or "0",
        "_source":         "bzzoiro",
        "_bzz":            row,
        "_raw_league":     raw_league,
        "_league_quality": quality,
        "_adj_xg":         adj_xg,
    }


def _load_bzzoiro() -> tuple:
    player_index: dict[str, list[dict]] = {}
    squad_index:  dict[int, list[dict]] = {}
    all_players:  list[dict] = []

    path = ROOT / "data" / "bzzoiro_wc_players.csv"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                all_players.append(row)
                key = _normalize(row.get("player_name", ""))
                player_index.setdefault(key, []).append(row)
                try:
                    tid = int(row["national_team_id"])
                    squad_index.setdefault(tid, []).append(row)
                except (KeyError, ValueError):
                    pass
    else:
        logger.warning(f"bzzoiro players CSV not found: {path}")

    teams_by_id:   dict[int, dict] = {}
    teams_by_name: dict[str, dict] = {}
    path = ROOT / "data" / "bzzoiro_wc_teams.csv"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    tid = int(row["team_id"])
                    teams_by_id[tid] = row
                except (KeyError, ValueError):
                    pass
                name_key = _normalize(row.get("team_name", ""))
                if name_key:
                    teams_by_name[name_key] = row
    else:
        logger.warning(f"bzzoiro teams CSV not found: {path}")

    logger.info(f"bzzoiro loader: {len(all_players)} players, {len(teams_by_id)} teams")
    return player_index, all_players, squad_index, teams_by_id, teams_by_name


(BZZ_PLAYER_INDEX, BZZ_ALL_PLAYERS,
 BZZ_SQUAD_INDEX, BZZ_TEAMS_BY_ID, BZZ_TEAMS_BY_NAME) = _load_bzzoiro()


def find_bzzoiro_player(name: str) -> list[dict]:
    """Find raw bzzoiro player rows by name (exact → substring → fuzzy)."""
    key = _normalize(name)
    if key in BZZ_PLAYER_INDEX:
        return BZZ_PLAYER_INDEX[key]
    matches = []
    for ikey, rows in BZZ_PLAYER_INDEX.items():
        if key in ikey or ikey in key:
            matches.extend(rows)
    if matches:
        return matches
    close = difflib.get_close_matches(key, BZZ_PLAYER_INDEX.keys(), n=1, cutoff=0.80)
    return BZZ_PLAYER_INDEX[close[0]] if close else []


def get_bzzoiro_squad(team_name: str) -> list[dict]:
    """Return raw bzzoiro player rows for a national team, looked up by name."""
    key = _normalize(team_name)
    team = BZZ_TEAMS_BY_NAME.get(key)
    if not team:
        close = difflib.get_close_matches(key, BZZ_TEAMS_BY_NAME.keys(), n=1, cutoff=0.70)
        team = BZZ_TEAMS_BY_NAME[close[0]] if close else None
    if not team:
        return []
    tid = int(team["team_id"])
    return BZZ_SQUAD_INDEX.get(tid, [])


def get_bzzoiro_team(team_name: str) -> dict | None:
    """Return bzzoiro team-level stats row by team name."""
    key = _normalize(team_name)
    if key in BZZ_TEAMS_BY_NAME:
        return BZZ_TEAMS_BY_NAME[key]
    close = difflib.get_close_matches(key, BZZ_TEAMS_BY_NAME.keys(), n=1, cutoff=0.70)
    return BZZ_TEAMS_BY_NAME[close[0]] if close else None
