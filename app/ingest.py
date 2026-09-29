"""Load CSV/Excel into picks (+ ensure matchups)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from app.db import ROOT, add_pick, latest_identity_pick, upsert_matchup
from app.spreads import (
    favorite_and_line,
    format_decision,
    format_spread,
    is_numeric_margin,
    norm_decision,
    norm_team,
    to_home_margin,
)

# ponytail: decision picks use spread=0 in SQLite; grading uses decision + vegas line only.
DECISION_SPREAD = 0.0

PICKS_DIR = ROOT / "data" / "picks"
SOURCES = frozenset({"vegas", "user", "model"})


def _norm_row(row: dict) -> dict:
    return {
        (k or "").strip().lower(): (v or "").strip()
        for k, v in row.items()
        if k and str(k).strip()
    }


def _rows_from_csv(text: str) -> list[dict]:
    f = io.StringIO(text)
    reader = csv.DictReader(f)
    rows = []
    for raw in reader:
        row = _norm_row(raw)
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
        row = _norm_row(row)
        if any(row.values()):
            rows.append(row)
    return rows


def parse_upload(filename: str, data: bytes) -> list[dict]:
    name = filename.lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return _rows_from_xlsx(data)
    return _rows_from_csv(data.decode("utf-8-sig"))


def _decision_text(row: dict) -> str:
    row = _norm_row(row)
    val = row.get("decision", "")
    if not val:
        raise ValueError(f"missing decision in {list(row)}")
    return norm_decision(val)


def _spread_text(row: dict) -> str:
    """Signed home margin from spread_line/spread, else team line (SEA -3.5)."""
    row = _norm_row(row)
    spread_line = row.get("spread_line", "")
    if spread_line and is_numeric_margin(spread_line):
        return spread_line
    spread = row.get("spread", "")
    if spread and is_numeric_margin(spread):
        return spread
    for key in ("spread", "fair_spread", "line", "vegas"):
        val = row.get(key, "")
        if val:
            return val
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
        matchup = upsert_matchup(
            session, season=season, week=week, away_team=away, home_team=home
        )
        if source == "vegas":
            margin = to_home_margin(away, home, _spread_text(row))
            pick = add_pick(
                session,
                matchup=matchup,
                spread=margin,
                source=source,
                username=username,
                model_version=model_version,
                bookmaker=bookmaker,
            )
        else:
            decision = _decision_text(row)
            pick = add_pick(
                session,
                matchup=matchup,
                spread=DECISION_SPREAD,
                decision=decision,
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
    """Insert picks from UI rows.

    Vegas: {away, home, points} signed spread.
    Model/user: {away, home, decision} cover|points.

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
        if not away or not home:
            raise ValueError(f"missing teams in {entry}")
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
        if source == "vegas":
            pts_raw = (entry.get("points") or "").strip()
            if not pts_raw:
                skipped += 1
                continue
            try:
                signed = float(pts_raw)
            except ValueError as e:
                raise ValueError(f"bad points: {pts_raw!r}") from e
            if signed > 0:
                margin = to_home_margin(away, home, f"{home} -{signed:g}")
            elif signed < 0:
                margin = to_home_margin(away, home, f"{away} -{abs(signed):g}")
            else:
                margin = 0.0
            pick = add_pick(
                session,
                matchup=matchup,
                spread=margin,
                source=source,
                username=username,
                model_version=model_version,
                bookmaker=bookmaker,
            )
        else:
            dec_raw = (entry.get("decision") or "").strip()
            if not dec_raw:
                skipped += 1
                continue
            decision = norm_decision(dec_raw)
            pick = add_pick(
                session,
                matchup=matchup,
                spread=DECISION_SPREAD,
                decision=decision,
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
        locked_favorite = ""
        locked_points = ""
        locked_spread = ""
        locked_decision = ""
        if prior:
            if prior.decision:
                locked_decision = format_decision(prior.decision)
            else:
                locked_favorite, locked_points = favorite_and_line(
                    m.away_team, m.home_team, prior.spread
                )
                locked_spread = format_spread(m.away_team, m.home_team, prior.spread)
        rows.append(
            {
                "id": m.id,
                "away_team": m.away_team,
                "home_team": m.home_team,
                "game": f"{m.away_team} @ {m.home_team}",
                "locked": locked,
                "locked_favorite": locked_favorite,
                "locked_points": locked_points,
                "locked_spread": locked_spread,
                "locked_decision": locked_decision,
            }
        )
    return rows


def seed_week01(session) -> tuple[int, int]:
    path = PICKS_DIR / "202601_model.csv"
    if not path.is_file():
        return 0, 0
    rows = parse_upload(path.name, path.read_bytes())
    return ingest_rows(
        session, rows, season=2026, week=1, source="model", model_version="preseason"
    )


def ingest_decisions_from_dir(session, season: int = 2026) -> dict[str, int]:
    """Load data/picks/2026{week:02d}_{brett|model}.csv decision columns."""
    totals = {"model": 0, "user": 0, "skipped": 0}
    for path in sorted(PICKS_DIR.glob(f"{season}??_*.csv")):
        parts = path.stem.split("_")
        if len(parts) < 2:
            continue
        week_chunk = parts[0]
        if len(week_chunk) != 6 or not week_chunk.startswith(str(season)):
            continue
        week = int(week_chunk[4:6])
        kind = parts[1].lower()
        if kind == "model":
            inserted, skipped = ingest_rows(
                session,
                parse_upload(path.name, path.read_bytes()),
                season=season,
                week=week,
                source="model",
                model_version="preseason",
            )
            totals["model"] += inserted
            totals["skipped"] += skipped
        elif kind == "brett":
            inserted, skipped = ingest_rows(
                session,
                parse_upload(path.name, path.read_bytes()),
                season=season,
                week=week,
                source="user",
                username="Brett",
            )
            totals["user"] += inserted
            totals["skipped"] += skipped
    return totals


def ensure_schedule(session, season: int | None = None) -> dict[str, int]:
    """Seed matchups from nflreadpy when the table is empty. No-op if already loaded."""
    from app import db
    from app.deps import SEASON
    from app.schedule import refresh_schedule

    if db.count_matchups(session) > 0:
        return {"n": 0, "with_scores": 0}
    try:
        return refresh_schedule(session, season or SEASON)
    except Exception:
        # ponytail: offline/CI without nflverse — leave empty; Refresh button retries.
        return {"n": 0, "with_scores": 0}
