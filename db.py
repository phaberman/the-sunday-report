"""SQLite games table."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "sunday.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
  season INTEGER NOT NULL,
  week INTEGER NOT NULL,
  away_team TEXT NOT NULL,
  home_team TEXT NOT NULL,
  model_margin REAL,
  vegas_margin REAL,
  home_score INTEGER,
  away_score INTEGER,
  kickoff TEXT,
  PRIMARY KEY (season, week, away_team, home_team)
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    own = conn is None
    c = connect() if own else conn
    c.executescript(SCHEMA)
    cols = {r[1] for r in c.execute("PRAGMA table_info(games)")}
    if "kickoff" not in cols:
        c.execute("ALTER TABLE games ADD COLUMN kickoff TEXT")
    c.commit()
    return c


def upsert_game(
    conn: sqlite3.Connection,
    *,
    season: int,
    week: int,
    away_team: str,
    home_team: str,
    model_margin: float | None = None,
    vegas_margin: float | None = None,
    home_score: int | None = None,
    away_score: int | None = None,
    kickoff: str | None = None,
    replace_kickoff: bool = False,
) -> None:
    if kickoff is not None and replace_kickoff:
        kick_sql = ", kickoff = excluded.kickoff"
    elif kickoff is not None:
        kick_sql = ", kickoff = COALESCE(kickoff, excluded.kickoff)"
    else:
        kick_sql = ""
    conn.execute(
        f"""
        INSERT INTO games (season, week, away_team, home_team,
                           model_margin, vegas_margin, home_score, away_score, kickoff)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(season, week, away_team, home_team) DO UPDATE SET
          model_margin = COALESCE(excluded.model_margin, model_margin),
          vegas_margin = COALESCE(excluded.vegas_margin, vegas_margin),
          home_score = COALESCE(excluded.home_score, home_score),
          away_score = COALESCE(excluded.away_score, away_score)
          {kick_sql}
        """,
        (
            season,
            week,
            away_team,
            home_team,
            model_margin,
            vegas_margin,
            home_score,
            away_score,
            kickoff,
        ),
    )


def weeks(conn: sqlite3.Connection) -> list[tuple[int, int]]:
    rows = conn.execute(
        "SELECT DISTINCT season, week FROM games ORDER BY season, week"
    ).fetchall()
    return [(r["season"], r["week"]) for r in rows]


def weeks_with_spreads(conn: sqlite3.Connection) -> list[tuple[int, int]]:
    rows = conn.execute(
        """
        SELECT DISTINCT season, week FROM games
        WHERE vegas_margin IS NOT NULL
        ORDER BY season, week
        """
    ).fetchall()
    return [(r["season"], r["week"]) for r in rows]


def games_for(conn: sqlite3.Connection, season: int, week: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM games
        WHERE season = ? AND week = ?
        ORDER BY kickoff IS NULL, kickoff, away_team, home_team
        """,
        (season, week),
    ).fetchall()


def all_games(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM games ORDER BY season, week, away_team"
    ).fetchall()


def count_games(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
