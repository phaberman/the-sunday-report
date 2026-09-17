"""Load CSV/Excel into picks (+ ensure matchups)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from app.db import ROOT, add_pick, upsert_matchup
from app.spreads import norm_team, to_home_margin

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


def _validate_meta(source: str, username: str | None, model_version: str | None) -> None:
    if source not in SOURCES:
        raise ValueError(f"source must be one of {sorted(SOURCES)}")
    if source == "user" and not username:
        raise ValueError("username required when source=user")
    if source == "model" and not model_version:
        raise ValueError("model_version required when source=model")
    if source == "vegas" and (username or model_version):
        raise ValueError("vegas picks cannot have username or model_version")


def ingest_rows(
    session,
    rows: list[dict],
    *,
    season: int,
    week: int,
    source: str,
    username: str | None = None,
    model_version: str | None = None,
) -> tuple[int, int]:
    """Insert picks. Returns (inserted, skipped_dups)."""
    username = (username or "").strip() or None
    model_version = (model_version or "").strip() or None
    _validate_meta(source, username, model_version)
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
        )
        if pick is None:
            skipped += 1
        else:
            inserted += 1
    session.commit()
    return inserted, skipped


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
