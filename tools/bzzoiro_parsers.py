"""Normalize bzzoiro API responses into tool-friendly structures."""

from datetime import datetime

BZZ_LIVE_STATUSES = {"inprogress", "penalties"}
BZZ_FINISHED_STATUSES = {"finished"}
BZZ_UPCOMING_STATUSES = {"notstarted"}


def _parse_event_date(event_date: str) -> str:
    if not event_date:
        return ""
    try:
        dt = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
        return dt.strftime("%H:%M")
    except ValueError:
        return event_date[11:16] if len(event_date) >= 16 else event_date


def parse_bzzoiro_fixtures(
    today_events: list[dict],
    live_events: list[dict] | None = None,
) -> tuple[list, list, list]:
    """Bucket today's WC events into live / upcoming / finished lists."""
    live, upcoming, finished = [], [], []
    live_ids = {e.get("id") for e in (live_events or [])}

    for ev in today_events:
        status = (ev.get("status") or "").lower()
        home = ev.get("home_team", "?")
        away = ev.get("away_team", "?")
        score_h = ev.get("home_score") if ev.get("home_score") is not None else "-"
        score_a = ev.get("away_score") if ev.get("away_score") is not None else "-"
        minute = ev.get("current_minute") or ""
        kickoff = ev.get("event_date", "")
        entry = {
            "home": home,
            "away": away,
            "score_h": score_h,
            "score_a": score_a,
            "venue": "",
            "minute": minute,
            "kickoff": kickoff,
            "status": status,
        }
        if ev.get("id") in live_ids or status in BZZ_LIVE_STATUSES:
            live.append(entry)
        elif status in BZZ_FINISHED_STATUSES:
            finished.append(entry)
        else:
            upcoming.append(entry)

    for ev in live_events or []:
        eid = ev.get("id")
        if eid and not any(
            x["home"] == ev.get("home_team") and x["away"] == ev.get("away_team")
            for x in live
        ):
            live.append({
                "home": ev.get("home_team", "?"),
                "away": ev.get("away_team", "?"),
                "score_h": ev.get("home_score") if ev.get("home_score") is not None else 0,
                "score_a": ev.get("away_score") if ev.get("away_score") is not None else 0,
                "venue": "",
                "minute": ev.get("current_minute") or "?",
                "kickoff": ev.get("event_date", ""),
                "status": ev.get("status", "inprogress"),
            })

    return live, upcoming, finished


def normalize_group_letter(grp: str) -> str:
    """Normalize bzzoiro / football-data group labels to a single letter A–L."""
    s = str(grp).upper().strip()
    s = s.replace("GROUP_", "").replace("GROUP ", "").strip()
    if len(s) == 1 and s in "ABCDEFGHIJKL":
        return s
    return s


def _row_group_letter(entry: dict) -> str:
    """Extract group letter from a flat standings row, if present."""
    for field in ("group", "group_name", "wc_group", "group_letter"):
        raw = entry.get(field)
        if raw:
            letter = normalize_group_letter(str(raw))
            if len(letter) == 1 and letter in "ABCDEFGHIJKL":
                return letter
    return ""


def parse_bzzoiro_standings(data: dict) -> dict[str, list[dict]]:
    """Return {group_letter: [row_dict]} from bzzoiro standings payload."""
    groups: dict[str, list[dict]] = {}

    def _row(entry: dict) -> dict:
        return {
            "team": entry.get("team_name") or entry.get("team", "?"),
            "team_id": entry.get("team_id"),
            "played": entry.get("played", 0),
            "won": entry.get("won", 0),
            "draw": entry.get("drawn", entry.get("draw", 0)),
            "lost": entry.get("lost", 0),
            "gf": entry.get("gf", 0),
            "ga": entry.get("ga", 0),
            "gd": entry.get("gd", 0),
            "pts": entry.get("pts", 0),
            "form": entry.get("form", ""),
            "xgf": entry.get("xgf"),
            "xga": entry.get("xga"),
            "xgd": entry.get("xgd"),
        }

    if data.get("grouped") and data.get("groups"):
        for grp, rows in data["groups"].items():
            letter = normalize_group_letter(str(grp))
            if letter:
                groups[letter] = [_row(r) for r in rows]
        return groups

    flat = data.get("standings", [])
    if flat:
        for entry in flat:
            letter = _row_group_letter(entry)
            row = _row(entry)
            if letter:
                groups.setdefault(letter, []).append(row)
            else:
                groups.setdefault("ALL", []).append(row)
    return groups


def bzz_standing_row_for_team(data: dict, team_id: int) -> dict | None:
    for rows in parse_bzzoiro_standings(data).values():
        for row in rows:
            if row.get("team_id") == team_id:
                return row
    return None


def parse_bzz_team_form(
    standing: dict | None,
    recent_events: list[dict],
    team_id: int,
    last_n: int,
) -> dict:
    """Build team form dict from standings row + recent finished events."""
    team_name = standing.get("team", "Unknown") if standing else "Unknown"
    played = standing.get("played", 0) if standing else 0
    won = standing.get("won", 0) if standing else 0
    drawn = standing.get("draw", 0) if standing else 0
    lost = standing.get("lost", 0) if standing else 0
    gf = standing.get("gf", 0) if standing else 0
    ga = standing.get("ga", 0) if standing else 0
    form_str = standing.get("form", "") if standing else ""
    if form_str:
        form_str = " ".join(list(form_str.replace(" ", ""))[:last_n])

    xgf_total = float(standing.get("xgf") or 0) if standing else 0.0
    xga_total = float(standing.get("xga") or 0) if standing else 0.0
    xg_games = played or 1
    xgf_avg = round(xgf_total / xg_games, 2) if xgf_total else 0.0
    xga_avg = round(xga_total / xg_games, 2) if xga_total else 0.0
    gf_avg = round(gf / played, 2) if played else 0.0
    ga_avg = round(ga / played, 2) if played else 0.0

    match_lines = []
    for ev in recent_events[:last_n]:
        home_id = ev.get("home_team_id")
        home = ev.get("home_team", "?")
        away = ev.get("away_team", "?")
        sh = ev.get("home_score") or 0
        sa = ev.get("away_score") or 0
        is_home = home_id == team_id
        opponent = away if is_home else home
        tg, og = (sh, sa) if is_home else (sa, sh)
        if tg > og:
            result = "W"
        elif tg < og:
            result = "L"
        else:
            result = "D"
        date_str = (ev.get("event_date") or "")[:10]
        match_lines.append(f"  {result} {sh}–{sa} vs {opponent} | {date_str}")

    return {
        "team_name": team_name,
        "played": played,
        "won": won,
        "drawn": drawn,
        "lost": lost,
        "gf": gf,
        "ga": ga,
        "gf_avg": gf_avg,
        "ga_avg": ga_avg,
        "xgf_avg": xgf_avg,
        "xga_avg": xga_avg,
        "form_str": form_str or "N/A",
        "match_lines": match_lines,
    }
