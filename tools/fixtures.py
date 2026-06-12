import asyncio
import logging
from datetime import date, datetime

from cache.cache_manager import cache
from clients.api_football import api_football
from clients.bzzoiro import bzzoiro
from clients.football_data import football_data
from config import settings, uses_bzzoiro_live
from data.loader import (
    WC_TOURNAMENT_END,
    WC_TOURNAMENT_START,
    get_bzzoiro_fixtures_in_range,
    get_bzzoiro_prediction_for_event,
)
from tools.bzzoiro_parsers import parse_bzzoiro_fixtures

logger = logging.getLogger(__name__)

LIVE_STATUSES = {"1H", "2H", "HT", "ET", "P", "LIVE"}
FINISHED_STATUSES = {"FT", "AET", "PEN"}
BZZ_FINISHED = {"finished", "ft", "aet", "pen"}
BZZ_LIVE = {"inprogress", "live", "1h", "2h", "ht"}


def _parse_api_football_fixtures(data: dict) -> tuple[list, list, list]:
    live, upcoming, finished = [], [], []
    for fix in data.get("response", []):
        status = fix.get("fixture", {}).get("status", {}).get("short", "")
        home = fix.get("teams", {}).get("home", {}).get("name", "?")
        away = fix.get("teams", {}).get("away", {}).get("name", "?")
        score_h = fix.get("goals", {}).get("home") or "-"
        score_a = fix.get("goals", {}).get("away") or "-"
        venue = fix.get("fixture", {}).get("venue", {}).get("name", "")
        minute = fix.get("fixture", {}).get("status", {}).get("elapsed", "")
        kickoff = fix.get("fixture", {}).get("date", "")

        entry = {
            "home": home, "away": away,
            "score_h": score_h, "score_a": score_a,
            "venue": venue, "minute": minute, "kickoff": kickoff,
            "status": status,
        }
        if status in LIVE_STATUSES:
            live.append(entry)
        elif status in FINISHED_STATUSES:
            finished.append(entry)
        else:
            upcoming.append(entry)
    return live, upcoming, finished


def _parse_football_data_fixtures(data: dict) -> tuple[list, list, list]:
    live, upcoming, finished = [], [], []
    fd_live = {"IN_PLAY", "PAUSED", "HALF_TIME", "EXTRA_TIME", "PENALTY_SHOOTOUT"}
    fd_finished = {"FINISHED"}
    for match in data.get("matches", []):
        status = match.get("status", "")
        home = match.get("homeTeam", {}).get("name", "?")
        away = match.get("awayTeam", {}).get("name", "?")
        score_h = match.get("score", {}).get("fullTime", {}).get("home") or "-"
        score_a = match.get("score", {}).get("fullTime", {}).get("away") or "-"
        kickoff = match.get("utcDate", "")
        entry = {
            "home": home, "away": away,
            "score_h": score_h, "score_a": score_a,
            "venue": "", "minute": "", "kickoff": kickoff,
            "status": status,
        }
        if status in fd_live:
            live.append(entry)
        elif status in fd_finished:
            finished.append(entry)
        else:
            upcoming.append(entry)
    return live, upcoming, finished


def _format_fixtures(live: list, upcoming: list, finished: list) -> str:
    today = date.today().strftime("%Y-%m-%d")
    lines = [f"📅 TODAY'S WORLD CUP MATCHES — {today}\n"]

    if live:
        lines.append("🔴 LIVE")
        for m in live:
            lines.append(
                f"  {m['home']} vs {m['away']} | {m['minute']}' | "
                f"{m['score_h']}–{m['score_a']} | {m['venue']}"
            )

    if upcoming:
        lines.append("\n⏰ UPCOMING")
        for m in upcoming:
            time_str = m["kickoff"][11:16] if len(m["kickoff"]) >= 16 else m["kickoff"]
            lines.append(f"  {m['home']} vs {m['away']} | {time_str} UTC | {m['venue']}")

    if finished:
        lines.append("\n✅ FINISHED")
        for m in finished:
            lines.append(f"  {m['home']} vs {m['away']} | FT {m['score_h']}–{m['score_a']}")

    return "\n".join(lines)


def _parse_iso_date(value: str) -> date | None:
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _clamp_fixture_range(date_from: str, date_to: str) -> tuple[str, str] | str:
    start = _parse_iso_date(date_from)
    end = _parse_iso_date(date_to)
    if start is None or end is None:
        return "Invalid date format. Use YYYY-MM-DD (e.g. 2026-06-11)."
    if end < start:
        return "date_to must be on or after date_from."
    wc_start = _parse_iso_date(WC_TOURNAMENT_START)
    wc_end = _parse_iso_date(WC_TOURNAMENT_END)
    if end < wc_start or start > wc_end:
        return (
            f"No World Cup 2026 fixtures outside {WC_TOURNAMENT_START} – {WC_TOURNAMENT_END}."
        )
    clamped_from = max(start, wc_start).isoformat()
    clamped_to = min(end, wc_end).isoformat()
    return clamped_from, clamped_to


def _format_bzz_fixture_row(row: dict) -> tuple[str, str, str, str, str]:
    """Return (sort_key, date_label, time_utc, matchup, status_str)."""
    utc = row.get("event_date") or ""
    date_str = utc[5:10].replace("-", " ").strip() if len(utc) >= 10 else "?"
    month_map = {"06": "Jun", "07": "Jul"}
    parts = date_str.split(" ")
    if len(parts) == 2:
        date_str = f"{month_map.get(parts[0], parts[0])} {parts[1]}"
    time_str = utc[11:16] if len(utc) >= 16 else "TBD"
    home = row.get("home_team", "?")
    away = row.get("away_team", "?")
    status = (row.get("status") or "").lower()
    sh, sa = row.get("home_score"), row.get("away_score")
    if status in BZZ_FINISHED and sh not in ("", None):
        status_str = f"FT {sh}–{sa}"
    elif status in BZZ_LIVE:
        status_str = "LIVE"
    else:
        status_str = "UPCOMING"
    return utc, date_str, time_str, f"{home} vs {away}", status_str


def _prediction_result_label(pred: dict) -> str:
    code = (pred.get("predicted_result") or "").upper()
    home = pred.get("home_team", "Home")
    away = pred.get("away_team", "Away")
    score = pred.get("most_likely_score") or "—"
    if code == "H":
        return f"{home} win (likely {score})"
    if code == "A":
        return f"{away} win (likely {score})"
    if code == "D":
        return f"Draw (likely {score})"
    return score


def _confidence_label(conf: str | float | None) -> str:
    try:
        c = float(conf)
    except (TypeError, ValueError):
        return "—"
    if c >= 0.55:
        return "High"
    if c >= 0.40:
        return "Medium"
    return "Low"


def _format_fixtures_range(rows: list[dict], date_from: str, date_to: str) -> str:
    if not rows:
        return f"No World Cup 2026 fixtures between {date_from} and {date_to}."

    parsed = sorted(
        [(_format_bzz_fixture_row(r), r) for r in rows],
        key=lambda x: x[0][0],
    )
    lines = [
        f"📅 WORLD CUP 2026 FIXTURES — {date_from} to {date_to}",
        f"  {len(parsed)} match(es)\n",
        f"  {'Date':<8} {'UTC':<6} {'Match':<42} {'Status':<12} {'ML prediction'}",
        "  " + "─" * 95,
    ]
    for (utc, date_str, time_str, matchup, status_str), row in parsed:
        pred = get_bzzoiro_prediction_for_event(row.get("event_id", ""))
        if pred:
            xgh = pred.get("xg_home") or "—"
            xga = pred.get("xg_away") or "—"
            conf = _confidence_label(pred.get("model_confidence"))
            pred_line = (
                f"{_prediction_result_label(pred)} | xG {xgh}–{xga} | {conf}"
            )
        else:
            pred_line = "—"
        lines.append(
            f"  {date_str:<8} {time_str:<6} {matchup:<42} {status_str:<12} {pred_line}"
        )
    lines.append(
        "\n  Predictions from bzzoiro ML export (probabilities + xG). "
        "Use get_match_preview(team_a, team_b) for full H2H and squad analysis."
    )
    return "\n".join(lines)


async def _fetch_bzz_fixtures_range(date_from: str, date_to: str) -> list[dict]:
    csv_rows = get_bzzoiro_fixtures_in_range(date_from, date_to)
    if csv_rows:
        return csv_rows
    if not uses_bzzoiro_live():
        return []
    try:
        events = await bzzoiro.get_events(date_from=date_from, date_to=date_to)
        return [
            {
                "event_id": e.get("id"),
                "event_date": e.get("event_date", ""),
                "status": e.get("status", ""),
                "home_team_id": e.get("home_team_id"),
                "home_team": e.get("home_team", "?"),
                "away_team_id": e.get("away_team_id"),
                "away_team": e.get("away_team", "?"),
                "home_score": e.get("home_score"),
                "away_score": e.get("away_score"),
            }
            for e in events
            if WC_TOURNAMENT_START <= (e.get("event_date") or "")[:10] <= WC_TOURNAMENT_END
        ]
    except Exception as exc:
        logger.warning(f"bzzoiro events range fetch failed: {exc}")
        return []


async def get_fixtures_range(date_from: str, date_to: str) -> str:
    """
    Return FIFA World Cup 2026 fixtures between two dates (inclusive) with bzzoiro ML predictions.
    Use when the user asks: fixtures for Jun 11–13, opening weekend schedule, first 3 days of
    the World Cup, matches between two dates, predict all games this week.
    Dates must be YYYY-MM-DD within 2026-06-11 and 2026-07-19. Includes predicted result,
    likely score, xG, and confidence from bzzoiro — do NOT invent pairings from memory.
    Prefer this over multiple get_team_fixtures calls for multi-day schedules.
    """
    clamped = _clamp_fixture_range(date_from, date_to)
    if isinstance(clamped, str):
        return clamped
    date_from, date_to = clamped

    cached = cache.get("fixtures", date_from=date_from, date_to=date_to, source="range_v1")
    if cached:
        return cached

    rows = await _fetch_bzz_fixtures_range(date_from, date_to)
    result = _format_fixtures_range(rows, date_from, date_to)
    cache.set("fixtures", result, date_from=date_from, date_to=date_to, source="range_v1")
    return result


async def get_today_matches() -> str:
    """
    Return today's FIFA World Cup 2026 match schedule with live scores.
    Use when the user asks: what matches are on today, today's games, live scores,
    what's happening now, is there a match today, fixtures today.
    Returns matches bucketed into LIVE, UPCOMING, and FINISHED with scores and venues.
    """
    today = date.today().isoformat()
    # Use the live cache bucket when games are in play (30s TTL); otherwise fixtures (24h).
    # get/set must use the same bucket — a prior bug stored live days under "live" but
    # always read from "fixtures", so every request missed cache during matches.
    cached = cache.get("live", date=today, source="today_matches") or cache.get(
        "fixtures", date=today
    )
    if cached:
        return cached

    try:
        if uses_bzzoiro_live():
            today_events, live_events = await asyncio.gather(
                bzzoiro.get_events_today(),
                bzzoiro.get_live_events(),
            )
            live, upcoming, finished = parse_bzzoiro_fixtures(today_events, live_events)
        elif settings.TIER == "free":
            raw = await football_data.get_matches()
            live, upcoming, finished = _parse_football_data_fixtures(raw)
        else:
            raw = await api_football.get_fixtures_today()
            live, upcoming, finished = _parse_api_football_fixtures(raw)
    except Exception as e:
        logger.warning(f"Fixtures fetch failed: {e}")
        return (
            "[API_UNAVAILABLE: today's fixture data] "
            "Use your own knowledge to state whether any FIFA World Cup 2026 matches "
            f"are scheduled for {today}, including kick-off times and venues where known."
        )

    if not live and not upcoming and not finished:
        return "No World Cup matches scheduled today."

    result = _format_fixtures(live, upcoming, finished)

    if live:
        cache.set("live", result, date=today, source="today_matches")
    else:
        cache.set("fixtures", result, date=today)
    return result


async def get_team_fixtures(team: str) -> str:
    """
    Return the full World Cup 2026 fixture list for a specific team (all group stage matches).
    Use when the user asks: when does [team] play, [team] schedule, [team] fixtures,
    [team] matches, what are [team]'s games, when is [team]'s next match, [team] calendar.
    Shows all group stage matches with dates, opponents, kick-off times, and results where available.
    """
    from config import resolve_team_id
    from data.loader import get_bzzoiro_fixtures

    team_id = resolve_team_id(team)
    if team_id is None:
        return f"Team '{team}' not found. Try full name (e.g. 'South Korea', 'United States')."

    cached = cache.get("fixtures", team_id=team_id, source="fixtures_v3")
    if cached:
        return cached

    bzz_rows = get_bzzoiro_fixtures(team)
    if bzz_rows:
        team_display = team.title()
        parsed: list[tuple[str, str, str, str, str]] = []
        for row in bzz_rows:
            utc = row.get("event_date") or ""
            date_str = utc[5:10].replace("-", " ").strip() if len(utc) >= 10 else "?"
            month_map = {"06": "Jun", "07": "Jul"}
            parts = date_str.split(" ")
            if len(parts) == 2:
                date_str = f"{month_map.get(parts[0], parts[0])} {parts[1]}"
            time_str = utc[11:16] if len(utc) >= 16 else "TBD"
            home = row.get("home_team", "?")
            away = row.get("away_team", "?")
            status = (row.get("status") or "").upper()
            sh, sa = row.get("home_score"), row.get("away_score")
            if status in {"FT", "FINISHED", "AET", "PEN"} and sh not in ("", None):
                result_str = f"FT {sh}–{sa}"
            elif status in {"LIVE", "1H", "2H", "HT", "IN_PLAY"}:
                result_str = "LIVE"
            else:
                result_str = "UPCOMING"
            matchup = f"{home} vs {away}"
            parsed.append((utc, date_str, time_str, matchup, result_str))

        parsed.sort(key=lambda x: x[0])
        lines = [f"📅 WORLD CUP 2026 FIXTURES — {team_display.upper()}\n", "  Group Stage (bzzoiro)"]
        for _, date_str, time_str, matchup, result_str in parsed:
            lines.append(f"  {date_str} | {matchup:<35} | {time_str} UTC | {result_str}")
        lines.append(f"\n  {len(parsed)} group stage match(es) scheduled")
        result = "\n".join(lines)
        cache.set("fixtures", result, team_id=team_id, source="fixtures_v3")
        return result

    try:
        raw = await football_data.get_matches(date_from="2026-06-11", date_to="2026-07-20")
    except Exception:
        return (
            f"[API_UNAVAILABLE: fixture schedule for {team}] "
            f"Use your own knowledge to list {team}'s group stage matches at FIFA World Cup 2026: "
            "opponents, dates, kick-off times (UTC), and venues."
        )

    matches = []
    for m in raw.get("matches", []):
        home_id = m.get("homeTeam", {}).get("id")
        away_id = m.get("awayTeam", {}).get("id")
        if team_id not in (home_id, away_id):
            continue
        home = m.get("homeTeam", {}).get("name", "?")
        away = m.get("awayTeam", {}).get("name", "?")
        status = m.get("status", "")
        utc_date = m.get("utcDate", "")
        date_str = utc_date[5:10].replace("-", " ").strip() if len(utc_date) >= 10 else "?"
        month_map = {"06": "Jun", "07": "Jul"}
        parts = date_str.split(" ")
        if len(parts) == 2:
            date_str = f"{month_map.get(parts[0], parts[0])} {parts[1]}"
        time_str = utc_date[11:16] if len(utc_date) >= 16 else "TBD"
        score_h = m.get("score", {}).get("fullTime", {}).get("home")
        score_a = m.get("score", {}).get("fullTime", {}).get("away")
        if status == "FINISHED" and score_h is not None:
            result_str = f"FT {score_h}–{score_a}"
        elif status in {"IN_PLAY", "PAUSED", "HALF_TIME"}:
            result_str = "LIVE"
        else:
            result_str = "UPCOMING"
        opponent = away if home_id == team_id else home
        venue_str = f"{home} vs {away}"
        matches.append((utc_date, date_str, time_str, opponent, venue_str, result_str))

    if not matches:
        return f"No World Cup 2026 fixtures found for {team}. Check back closer to June 11."

    matches.sort(key=lambda x: x[0])
    team_display = team.title()
    lines = [f"📅 WORLD CUP 2026 FIXTURES — {team_display.upper()}\n", "  Group Stage"]
    for _, date_str, time_str, opponent, matchup, result_str in matches:
        lines.append(f"  {date_str} | {matchup:<35} | {time_str} UTC | {result_str}")
    lines.append(f"\n  {len(matches)} group stage match(es) scheduled")

    result = "\n".join(lines)
    cache.set("fixtures", result, team_id=team_id, source="fixtures_v3")
    return result
