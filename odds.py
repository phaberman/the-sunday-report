"""DraftKings spread pull → games.vegas_margin."""

from __future__ import annotations

import csv
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from db import ROOT, upsert_game
from spreads import norm_team

API_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds/"
SCHEDULE_PATH = ROOT / "data" / "schedules" / "2026_schedule.csv"
DISPLAY_TZ = timezone(timedelta(hours=8))  # UTC+8; NFL week rolls Tue after MNF.
ET = ZoneInfo("America/New_York")

# Odds API full names → our codes
NFL_NAMES = {
    "Arizona Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LA",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}


def load_dotenv(path: Path) -> None:
    # ponytail: tiny .env reader; ceiling = no quotes/export syntax.
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip(chr(34))
        os.environ[key] = value


def team_code(name: str) -> str:
    n = (name or "").strip()
    if n in NFL_NAMES:
        return NFL_NAMES[n]
    return norm_team(n)


def load_schedule(path: Path | None = None) -> list[dict]:
    p = path or SCHEDULE_PATH
    rows = []
    with p.open(newline="") as f:
        for row in csv.DictReader(f):
            if row.get("game_type") != "REG":
                continue
            rows.append(
                {
                    "season": int(row["season"]),
                    "week": int(row["week"]),
                    "gameday": row["gameday"],
                    "gametime": row.get("gametime") or "",
                    "away_team": norm_team(row["away_team"]),
                    "home_team": norm_team(row["home_team"]),
                }
            )
    return rows


def _week_last_days(
    schedule: list[dict] | None = None,
) -> dict[tuple[int, int], date]:
    sched = schedule if schedule is not None else load_schedule()
    last_by: dict[tuple[int, int], date] = {}
    for r in sched:
        key = (r["season"], r["week"])
        d = datetime.strptime(r["gameday"], "%Y-%m-%d").date()
        prev = last_by.get(key)
        last_by[key] = d if prev is None else max(prev, d)
    return last_by


def schedule_kickoff(gameday: str, gametime: str) -> str | None:
    # ponytail: treat nflverse kickoff as ET. Ceiling = London/Melbourne slots. Upgrade: venue TZ.
    if not gameday:
        return None
    t = (gametime or "00:00").strip()
    try:
        dt = datetime.strptime(f"{gameday} {t}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_kickoff(iso: str | None) -> str:
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(DISPLAY_TZ).strftime("%Y-%m-%d %H:%M")


def current_week(
    schedule: list[dict] | None = None, today: date | None = None
) -> tuple[int, int]:
    """Smallest REG week whose last gameday is today or later."""
    last_by = _week_last_days(schedule)
    today = today or datetime.now(DISPLAY_TZ).date()
    live = sorted(k for k, last in last_by.items() if last >= today)
    if live:
        return live[0]
    return max(last_by)


def past_weeks(
    schedule: list[dict] | None = None, today: date | None = None
) -> list[tuple[int, int]]:
    last_by = _week_last_days(schedule)
    today = today or datetime.now(DISPLAY_TZ).date()
    return sorted(k for k, last in last_by.items() if last < today)


def week_row(schedule: list[dict], away: str, home: str, commence_time: str) -> dict | None:
    hits = [r for r in schedule if r["away_team"] == away and r["home_team"] == home]
    if not hits:
        return None
    if not commence_time:
        return hits[0]
    ct = datetime.fromisoformat(commence_time.replace("Z", "+00:00")).date()
    return min(
        hits,
        key=lambda r: abs((datetime.strptime(r["gameday"], "%Y-%m-%d").date() - ct).days),
    )


def dk_home_point(game: dict) -> float | None:
    home = game.get("home_team")
    for book in game.get("bookmakers") or []:
        if book.get("key") != "draftkings":
            continue
        for market in book.get("markets") or []:
            if market.get("key") != "spreads":
                continue
            for o in market.get("outcomes") or []:
                if o.get("name") == home and o.get("point") is not None:
                    return float(o["point"])
    return None


def fetch_dk(api_key: str) -> tuple[list[dict], dict[str, str]]:
    params = urllib.parse.urlencode(
        {
            "apiKey": api_key,
            "regions": "us",
            "markets": "spreads",
            "oddsFormat": "american",
            "bookmakers": "draftkings",
        }
    )
    req = urllib.request.Request(f"{API_URL}?{params}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"API error {e.code}: {detail}") from e
    if not isinstance(body, list):
        raise RuntimeError(f"Unexpected response: {body!r}")
    return body, headers


def apply_dk_games(
    conn,
    games: list[dict],
    schedule: list[dict] | None = None,
    *,
    only: tuple[int, int] | None = None,
) -> int:
    """Upsert vegas_margin from DK home points. Returns games updated."""
    sched = schedule if schedule is not None else load_schedule()
    n = 0
    for game in games:
        point = dk_home_point(game)
        if point is None:
            continue
        away = team_code(game.get("away_team") or "")
        home = team_code(game.get("home_team") or "")
        hit = week_row(sched, away, home, game.get("commence_time") or "")
        if hit is None:
            continue
        if only is not None and (hit["season"], hit["week"]) != only:
            continue
        upsert_game(
            conn,
            season=hit["season"],
            week=hit["week"],
            away_team=away,
            home_team=home,
            vegas_margin=-point,
            kickoff=game.get("commence_time") or None,
            replace_kickoff=True,
        )
        n += 1
    conn.commit()
    return n


def refresh_spreads(conn) -> dict[str, str | int]:
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("ODDS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing ODDS_API_KEY")
    games, headers = fetch_dk(api_key)
    n = apply_dk_games(conn, games, only=current_week())
    return {
        "n": n,
        "remaining": headers.get("x-requests-remaining", "?"),
        "used": headers.get("x-requests-used", "?"),
        "pulled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def export_week_xlsx(rows: list[dict]) -> bytes:
    from openpyxl import Workbook
    from io import BytesIO

    wb = Workbook()
    ws = wb.active
    ws.title = "spreads"
    ws.append(["Index", "Kickoff", "Matchup", "Home Team", "Away Team", "Spread"])
    for r in rows:
        ws.append(
            [
                r.get("index") or "",
                r.get("kickoff") or "",
                r["game"],
                r["home_team"],
                r["away_team"],
                r["vegas"],
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
