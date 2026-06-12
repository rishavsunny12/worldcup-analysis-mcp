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
    "Liga Portugal Betclic":   0.82,
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
    "South African Premiership": 0.58,
    "PSL":                     0.58,
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


def _name_tokens(name: str) -> list[str]:
    """Normalized name parts (hyphens treated as spaces)."""
    return [t for t in _normalize(name).replace("-", " ").split() if t]


def find_player(name: str) -> list[dict]:
    """Return understat CSV rows matching a player name.

    Matching order: exact normalized name → shared surname (multi-part names) →
    high-confidence fuzzy (0.92+). Substring and loose fuzzy matches are excluded
    to avoid false positives (e.g. Mohamed Kanno → Mohamed Kaba).
    """
    key = _normalize(name)
    if key in PLAYER_INDEX:
        return PLAYER_INDEX[key]

    tokens = _name_tokens(name)
    if len(tokens) >= 2:
        surname = tokens[-1]
        matches: list[dict] = []
        for indexed_key, rows in PLAYER_INDEX.items():
            idx_tokens = indexed_key.replace("-", " ").split()
            if not idx_tokens or idx_tokens[-1] != surname:
                continue
            if difflib.SequenceMatcher(None, key, indexed_key).ratio() >= 0.85:
                matches.extend(rows)
        if matches:
            return matches

    close = difflib.get_close_matches(key, PLAYER_INDEX.keys(), n=1, cutoff=0.92)
    if close:
        return PLAYER_INDEX[close[0]]
    return []


def find_player_for_squad(name: str, bzz_row: dict | None = None) -> list[dict]:
    """Match understat rows for a national-squad player, rejecting cross-player false hits.

    Requires exact normalized name match, or a club name match when the bzzoiro row
    is available (prevents e.g. a South Africa name loosely matching Jayden Addai).
    """
    key = _normalize(name)
    rows = find_player(name)
    if not rows:
        return []

    exact = [r for r in rows if _normalize(r.get("player_name", "")) == key]
    if exact:
        return exact

    if not bzz_row:
        return []

    club = _normalize(bzz_row.get("club_name") or "")
    if club:
        club_matches = [
            r for r in rows
            if club in _normalize(r.get("team_title") or "")
            or _normalize(r.get("team_title") or "") in club
        ]
        if club_matches:
            return club_matches
    return []


# Labels that are cups/old tournaments — not a player's current domestic league.
_STALE_LEAGUE_LABELS = frozenset({
    "Africa Cup of Nations 2023",
    "International Friendly Games",
})

# Continental cups stored on the club row — infer domestic league from country instead.
_CONTINENTAL_CUP_LABELS = frozenset({
    "CAF Champions League",
    "AFC Champions League",
    "UEFA Champions League",
    "UEFA Europa League",
})

_COUNTRY_DOMESTIC_LEAGUE: dict[str, str] = {
    "South Africa": "South African Premiership",
    "Norway": "Norwegian Eliteserien",
    "Germany": "Bundesliga",
    "USA": "MLS",
    "England": "Premier League",
    "Italy": "Serie A",
    "Spain": "La Liga",
    "France": "Ligue 1",
    "Portugal": "Liga Portugal",
    "Cyprus": "Cypriot First Division",
}


def resolve_club_league_name(row: dict) -> str:
    """Return a display-ready current league for a bzzoiro player row."""
    raw = (row.get("club_league_name") or "").strip()
    if raw in BZZ_LEAGUE_MAP:
        return raw

    low = raw.lower()
    if "liga portugal" in low:
        return "Liga Portugal"

    country = (row.get("club_country") or row.get("nationality") or "").strip()
    if raw in _STALE_LEAGUE_LABELS or raw in _CONTINENTAL_CUP_LABELS or not raw:
        domestic = _COUNTRY_DOMESTIC_LEAGUE.get(country)
        if domestic:
            return domestic

    return raw or "Unknown"


# ── Bzzoiro data ──────────────────────────────────────────────────────────────

def normalize_bzz_player(row: dict) -> dict:
    """Adapt a bzzoiro player row to understat-compatible field names so all
    downstream profile/formatting code can handle both sources uniformly.
    Includes _league_quality and _adj_xg for cross-league fair comparison."""
    raw_league = resolve_club_league_name(row)
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


def get_bzzoiro_squad(team_name: str, official_only: bool = True) -> list[dict]:
    """Return bzzoiro player rows for a national team, looked up by name.

    official_only=True (default) keeps the 26-man WC list and excludes preliminary
    call-ups so all squad tools report the same roster size.
    """
    key = _normalize(team_name)
    team = BZZ_TEAMS_BY_NAME.get(key)
    if not team:
        close = difflib.get_close_matches(key, BZZ_TEAMS_BY_NAME.keys(), n=1, cutoff=0.70)
        team = BZZ_TEAMS_BY_NAME[close[0]] if close else None
    if not team:
        return []
    tid = int(team["team_id"])
    squad = BZZ_SQUAD_INDEX.get(tid, [])
    if official_only:
        official = [p for p in squad if (p.get("wc_status") or "").lower() == "official"]
        if official:
            return official
    return squad


def get_bzzoiro_team(team_name: str) -> dict | None:
    """Return bzzoiro team-level stats row by team name."""
    key = _normalize(team_name)
    if key in BZZ_TEAMS_BY_NAME:
        return BZZ_TEAMS_BY_NAME[key]
    close = difflib.get_close_matches(key, BZZ_TEAMS_BY_NAME.keys(), n=1, cutoff=0.70)
    return BZZ_TEAMS_BY_NAME[close[0]] if close else None


# Common aliases where config/football-data names differ from bzzoiro CSV names.
BZZ_NAME_ALIASES: dict[str, str] = {
    "united states": "USA",
    "usa": "USA",
    "us": "USA",
    "usmnt": "USA",
    "korea": "South Korea",
    "holland": "Netherlands",
    "turkey": "Türkiye",
    "ivory coast": "Côte d'Ivoire",
    "cote d'ivoire": "Côte d'Ivoire",
    "civ": "Côte d'Ivoire",
    "curacao": "Curaçao",
    "bosnia": "Bosnia & Herzegovina",
    "bosnia-herzegovina": "Bosnia & Herzegovina",
    "bosnia and herzegovina": "Bosnia & Herzegovina",
    "cape verde": "Cabo Verde",
    "cape verde islands": "Cabo Verde",
    "dr congo": "DR Congo",
    "congo dr": "DR Congo",
    "congo": "DR Congo",
    "drc": "DR Congo",
    "czech republic": "Czechia",
    "nz": "New Zealand",
    "swiss": "Switzerland",
    "three lions": "England",
    "black stars": "Ghana",
    "el tri": "Mexico",
    "bafana bafana": "South Africa",
    "la roja": "Spain",
    "die mannschaft": "Germany",
    "les bleus": "France",
    "socceroos": "Australia",
    "all whites": "New Zealand",
    "les lions": "Senegal",
    "uzbek": "Uzbekistan",
}


def _build_bzz_group_map() -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for row in BZZ_TEAMS_BY_ID.values():
        grp = (row.get("wc_group") or "").upper().strip()
        if not grp:
            continue
        try:
            tid = int(row["team_id"])
        except (KeyError, ValueError):
            continue
        groups.setdefault(grp, []).append(tid)
    for grp in groups:
        groups[grp].sort()
    return groups


BZZ_GROUP_MAP: dict[str, list[int]] = _build_bzz_group_map()


def resolve_bzzoiro_team_id(name: str) -> int | None:
    """Resolve a user-facing team name to a bzzoiro team_id."""
    team = get_bzzoiro_team(name)
    if team:
        return int(team["team_id"])
    key = name.lower().strip()
    alias = BZZ_NAME_ALIASES.get(key)
    if alias:
        team = get_bzzoiro_team(alias)
        if team:
            return int(team["team_id"])
    for alias_key, canonical in BZZ_NAME_ALIASES.items():
        if key in alias_key or alias_key in key:
            team = get_bzzoiro_team(canonical)
            if team:
                return int(team["team_id"])
    return None


def get_bzzoiro_team_name(team_id: int) -> str | None:
    row = BZZ_TEAMS_BY_ID.get(team_id)
    return row.get("team_name") if row else None


# ── Defensive profile (bzzoiro attr_defending) ────────────────────────────────

DEFENSIVE_WC_POSITIONS = frozenset({"DF", "GK"})


def parse_attr_defending(row: dict) -> int | None:
    """Return bzzoiro defending attribute (0–100) or None if missing."""
    val = row.get("attr_defending")
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def is_defensive_player(row: dict) -> bool:
    """True for centre-backs, full-backs, and goalkeepers in bzzoiro/understat rows."""
    pos = (row.get("wc_position") or row.get("position") or "").upper()
    if pos in DEFENSIVE_WC_POSITIONS:
        return True
    return pos.startswith("D") or pos == "GK"


def defense_score_from_avg(avg: float | None) -> float:
    """Map average attr_defending (typical 55–85) to a 0–1 composite weight."""
    if avg is None:
        return 0.0
    return round(max(0.0, min(1.0, (avg - 55) / 30)), 3)


def parse_int_field(row: dict, key: str) -> int:
    try:
        return int(float(row.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def defender_event_score(row: dict) -> float:
    """Composite club-season defensive actions score from bulk CSV event stats."""
    pos = (row.get("wc_position") or "").upper()
    tackles = parse_int_field(row, "club_tackles")
    interceptions = parse_int_field(row, "club_interceptions")
    clearances = parse_int_field(row, "club_clearances")
    aerial = parse_int_field(row, "club_aerial_won")
    saves = parse_int_field(row, "club_saves")
    recovery = parse_int_field(row, "club_ball_recovery")
    base = tackles + interceptions * 1.2 + clearances * 0.8 + aerial * 0.5 + recovery * 0.3
    if pos == "GK":
        return saves * 2.0 + base * 0.3
    return base


def defensive_profile_from_squad(bzz_squad: list[dict], top_n: int = 5) -> dict:
    """Squad defensive summary using attr_defending + club event stats."""
    candidates: list[tuple[float, int | None, dict]] = []
    attr_vals: list[int] = []

    for row in bzz_squad:
        if not is_defensive_player(row):
            continue
        attr = parse_attr_defending(row)
        if attr is not None:
            attr_vals.append(attr)
        event = defender_event_score(row)
        attr_part = (attr or 0) * 0.4
        event_part = min(event / 80.0, 1.0) * 60.0
        composite = round(attr_part + event_part, 1)
        if attr is not None or event > 0:
            candidates.append((composite, attr, row))

    if not candidates:
        return {
            "avg_def_rating": None,
            "elite_count": 0,
            "defender_count": 0,
            "defense_score": 0.0,
            "top_defenders": [],
        }

    avg = round(sum(attr_vals) / len(attr_vals), 1) if attr_vals else None
    elite = sum(1 for v in attr_vals if v >= 75)
    top = sorted(candidates, key=lambda x: x[0], reverse=True)[:top_n]

    return {
        "avg_def_rating": avg,
        "elite_count": elite,
        "defender_count": len(candidates),
        "defense_score": defense_score_from_avg(avg),
        "top_defenders": [
            {"rating": attr or 0, "score": score, "row": row}
            for score, attr, row in top
        ],
    }


# ── Predictions & fixtures CSVs ───────────────────────────────────────────────

WC_TOURNAMENT_START = "2026-06-11"
WC_TOURNAMENT_END = "2026-07-19"


def _load_bzz_csv(path: Path) -> list[dict]:
    if not path.exists():
        logger.warning(f"bzzoiro CSV not found: {path}")
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _fixture_date_key(row: dict) -> str:
    """Return YYYY-MM-DD from a bzzoiro fixture/prediction row."""
    raw = (row.get("event_date") or "")[:10]
    return raw if len(raw) == 10 else ""


def _is_wc_2026_fixture(row: dict) -> bool:
    """Keep only FIFA World Cup 2026 tournament window (excludes 2014/2018/2022 history)."""
    day = _fixture_date_key(row)
    return WC_TOURNAMENT_START <= day <= WC_TOURNAMENT_END if day else False


def _load_bzz_fixtures() -> list[dict]:
    raw = _load_bzz_csv(ROOT / "data" / "bzzoiro_wc_fixtures.csv")
    kept = [r for r in raw if _is_wc_2026_fixture(r)]
    if len(kept) < len(raw):
        logger.info(
            f"bzzoiro fixtures: kept {len(kept)} WC 2026 rows, "
            f"dropped {len(raw) - len(kept)} historical/out-of-window"
        )
    return kept


BZZ_PREDICTIONS: list[dict] = _load_bzz_csv(ROOT / "data" / "bzzoiro_wc_predictions.csv")
BZZ_FIXTURES: list[dict] = _load_bzz_fixtures()
BZZ_PREDICTIONS_BY_EVENT: dict[str, dict] = {
    str(row["event_id"]): row for row in BZZ_PREDICTIONS if row.get("event_id")
}


def _name_in_team(name: str, query: str) -> bool:
    n = _normalize(name)
    q = _normalize(query)
    return q in n or n in q


def find_bzzoiro_prediction(team_a: str, team_b: str) -> dict | None:
    """Find ML prediction row for a fixture between two teams (either home/away order)."""
    for row in BZZ_PREDICTIONS:
        home, away = row.get("home_team", ""), row.get("away_team", "")
        if (_name_in_team(home, team_a) and _name_in_team(away, team_b)) or (
            _name_in_team(home, team_b) and _name_in_team(away, team_a)
        ):
            return row
    return None


def get_bzzoiro_fixtures(team_name: str) -> list[dict]:
    """Return WC 2026 fixture rows involving this national team (no historical WCs)."""
    return [
        row for row in BZZ_FIXTURES
        if _name_in_team(row.get("home_team", ""), team_name)
        or _name_in_team(row.get("away_team", ""), team_name)
    ]


def get_bzzoiro_fixtures_in_range(date_from: str, date_to: str) -> list[dict]:
    """Return WC 2026 fixtures with kickoff date in [date_from, date_to] (YYYY-MM-DD)."""
    return [
        row for row in BZZ_FIXTURES
        if date_from <= _fixture_date_key(row) <= date_to
    ]


def get_bzzoiro_prediction_for_event(event_id: str | int) -> dict | None:
    """Return ML prediction row for a fixture event_id, if exported."""
    return BZZ_PREDICTIONS_BY_EVENT.get(str(event_id))
