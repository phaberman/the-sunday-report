"""Load CSV/Excel into picks (+ ensure matchups)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from app.db import ROOT, add_pick, latest_identity_pick, upsert_matchup
from app.spreads import format_spread, norm_team, to_home_margin

PICKS_DIR = ROOT / "data" / "picks"
SOURCES = frozenset({"vegas", "user", "model"})


def _rows_from_csv(text: str) -> list[dict]:
    f = io.StringIO(text)
    reader = csv.DictReader(f)
    rows = []
    for raw in reader:
        row = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k and k.strip()}
        if any(row.values()):
            rows.append(row)
    return rows


def _rows_from_xlsx(data: bytes) -> list[dict]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    header = [str(c).strip() if c is not None else "" for c in next(it)]
    rows = []
    for vals in it:
        row = {}
        for h, v in zip(header, vals):
            if not h:
                continue
            row[h] = "" if v is None else str(v).strip()
        if any(row.values()):
            rows.append(row)
    return rows


def parse_upload(filename: str, data: bytes) -> list[dict]:
    name = filename.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return _rows_from_xlsx(data)
    return _rows_from_csv(data.decode("utf-8-sig"))


def _spread_text(row: dict) -> str:
    for key in ("spread", "fair_spread", "line", "vegas"):
        if row.get(key):
            return row[key]
    raise ValueError(f"no spread column in {list(row)}")


def _validate_meta(
    source: str,
    username: str | None,
    model_version: str | None,
    bookmaker: str | None,
) -> None:
    if source not in SOURCES:
        raise ValueError(f"source must be one of {sorted(SOURCES)}")
    if source == "user" and not username:
        raise ValueError("username required when source=user")
    if source == "model" and not model_version:
        raise ValueError("model_version required when source=model")
    if source == "vegas" and not bookmaker:
        raise ValueError("bookmaker required when source=vegas")
    if source == "vegas" and (username or model_version):
        raise ValueError("vegas picks cannot have username or model_version")
    if source != "vegas" and bookmaker:
        raise ValueError("bookmaker only allowed when source=vegas")


def ingest_rows(
    session,
    rows: list[dict],
    *,
    season: int,
    week: int,
    source: str,
    username: str | None = None,
    model_version: str | None = None,
    bookmaker: str | None = None,
) -> tuple[int, int]:
    """Insert picks. Returns (inserted, skipped_dups)."""
    username = (username or "").strip() or None
    model_version = (model_version or "").strip() or None
    bookmaker = (bookmaker or "").strip() or None
    _validate_meta(source, username, model_version, bookmaker)
    inserted = skipped = 0
    for row in rows:
        away = norm_team(row.get("away_team") or row.get("away") or "")
        home = norm_team(row.get("home_team") or row.get("home") or "")
        if not away or not home:
            raise ValueError(f"missing teams in {row}")
        margin = to_home_margin(away, home, _spread_text(row))
        matchup = upsert_matchup(
            session, season=season, week=week, away_team=away, home_team=home
        )
        pick = add_pick(
            session,
            matchup=matchup,
            spread=margin,
            source=source,
            username=username,
            model_version=model_version,
            bookmaker=bookmaker,
        )
        if pick is None:
            skipped += 1
        else:
            inserted += 1
    session.commit()
    return inserted, skipped


def ingest_entries(
    session,
    entries: list[dict],
    *,
    season: int,
    week: int,
    source: str,
    username: str | None = None,
    model_version: str | None = None,
    bookmaker: str | None = None,
) -> tuple[int, int, int]:
    """Insert picks from UI rows {away, home, favorite, points}.

    Returns (inserted, skipped_blank_or_locked, skipped_dups).
    Locked = identity already has a pick for that matchup.
    """
    username = (username or "").strip() or None
    model_version = (model_version or "").strip() or None
    bookmaker = (bookmaker or "").strip() or None
    _validate_meta(source, username, model_version, bookmaker)
    inserted = skipped = dups = 0
    for entry in entries:
        away = norm_team(entry.get("away_team") or "")
        home = norm_team(entry.get("home_team") or "")
        fav = norm_team(entry.get("favorite") or "")
        pts_raw = (entry.get("points") or "").strip()
        if not pts_raw:
            skipped += 1
            continue
        if not away or not home or not fav:
            raise ValueError(f"missing teams in {entry}")
        if fav not in (away, home):
            raise ValueError(f"favorite {fav} not in {away}@{home}")
        try:
            pts = abs(float(pts_raw))
        except ValueError as e:
            raise ValueError(f"bad points: {pts_raw!r}") from e
        matchup = upsert_matchup(
            session, season=season, week=week, away_team=away, home_team=home
        )
        prior = latest_identity_pick(
            session,
            matchup_id=matchup.id,
            source=source,
            username=username,
            model_version=model_version,
            bookmaker=bookmaker,
        )
        if prior is not None:
            skipped += 1
            continue
        margin = to_home_margin(away, home, f"{fav} -{pts:g}")
        pick = add_pick(
            session,
            matchup=matchup,
            spread=margin,
            source=source,
            username=username,
            model_version=model_version,
            bookmaker=bookmaker,
        )
        if pick is None:
            dups += 1
        else:
            inserted += 1
    session.commit()
    return inserted, skipped, dups


def entry_rows_for(
    session,
    *,
    season: int,
    week: int,
    source: str,
    username: str | None = None,
    model_version: str | None = None,
    bookmaker: str | None = None,
) -> list[dict]:
    """Matchups for the enter-spreads table, with lock + display spread if locked."""
    from app.db import matchups_for

    username = (username or "").strip() or None
    model_version = (model_version or "").strip() or None
    bookmaker = (bookmaker or "").strip() or None
    # Incomplete identity → show unlocked (submit will validate)
    can_lock = True
    try:
        _validate_meta(source, username, model_version, bookmaker)
    except ValueError:
        can_lock = False

    rows = []
    for m in matchups_for(session, season, week):
        prior = None
        if can_lock:
            prior = latest_identity_pick(
                session,
                matchup_id=m.id,
                source=source,
                username=username,
                model_version=model_version,
                bookmaker=bookmaker,
            )
        locked = prior is not None
        rows.append(
            {
                "id": m.id,
                "away_team": m.away_team,
                "home_team": m.home_team,
                "game": f"{m.away_team} @ {m.home_team}",
                "locked": locked,
                "locked_spread": format_spread(m.away_team, m.home_team, prior.spread)
                if prior
                else "",
            }
        )
    return rows


def seed_week01(session) -> tuple[int, int]:
    path = PICKS_DIR / "week_01.csv"
    if not path.is_file():
        return 0, 0
    rows = parse_upload(path.name, path.read_bytes())
    return ingest_rows(
        session, rows, season=2026, week=1, source="model", model_version="preseason"
    )


def ensure_schedule(session, path: Path | None = None) -> int:
    """Insert 2026 REG matchups if missing."""
    from app.odds import load_schedule, schedule_kickoff

    rows = load_schedule(path)
    for row in rows:
        upsert_matchup(
            session,
            season=row["season"],
            week=row["week"],
            away_team=row["away_team"],
            home_team=row["home_team"],
            kickoff=schedule_kickoff(row["gameday"], row.get("gametime") or ""),
        )
    session.commit()
    return len(rows)
