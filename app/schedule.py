"""Pull NFL schedule/scores from nflreadpy into matchups."""

from __future__ import annotations

from app.db import upsert_matchup
from app.odds import schedule_kickoff
from app.spreads import norm_team


def _int_or_none(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def fetch_nfl_reg_rows(season: int) -> list[dict]:
    """REG games from nflverse as plain dicts (no CSV)."""
    import nflreadpy as nfl

    df = nfl.load_schedules(season)
    df = df.filter(df["game_type"] == "REG")
    cols = [
        "season",
        "week",
        "gameday",
        "gametime",
        "away_team",
        "home_team",
        "away_score",
        "home_score",
    ]
    return df.select(cols).to_dicts()


def apply_schedule_rows(session, rows: list[dict]) -> dict[str, int]:
    """Upsert matchups (dup-safe by matchup_id). Returns counts."""
    n = 0
    with_scores = 0
    for row in rows:
        away = norm_team(str(row.get("away_team") or ""))
        home = norm_team(str(row.get("home_team") or ""))
        if not away or not home:
            continue
        season = int(row["season"])
        week = int(row["week"])
        gameday = str(row.get("gameday") or "")
        gametime = str(row.get("gametime") or "")
        away_score = _int_or_none(row.get("away_score"))
        home_score = _int_or_none(row.get("home_score"))
        upsert_matchup(
            session,
            season=season,
            week=week,
            away_team=away,
            home_team=home,
            kickoff=schedule_kickoff(gameday, gametime),
            away_score=away_score,
            home_score=home_score,
            replace_kickoff=True,
        )
        n += 1
        if away_score is not None and home_score is not None:
            with_scores += 1
    session.commit()
    return {"n": n, "with_scores": with_scores}


def refresh_schedule(session, season: int, *, rows: list[dict] | None = None) -> dict[str, int]:
    """Fetch (or use injected rows) and upsert into matchups."""
    data = rows if rows is not None else fetch_nfl_reg_rows(season)
    return apply_schedule_rows(session, data)
