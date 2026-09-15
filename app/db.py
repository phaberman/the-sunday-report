"""SQLAlchemy engine, sessions, and game queries."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.models import Base, Game, VegasSpread

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "sunday.db"


def connect(path: Path | None = None) -> Session:
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{p}", connect_args={"check_same_thread": False})
    return Session(engine)


def init(session: Session | None = None) -> Session:
    s = session or connect()
    bind = s.get_bind()
    Base.metadata.create_all(bind)
    cols = {row[1] for row in s.execute(text("PRAGMA table_info(games)"))}
    if cols and "kickoff" not in cols:
        s.execute(text("ALTER TABLE games ADD COLUMN kickoff TEXT"))
        s.commit()
    return s


def upsert_game(
    session: Session,
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
) -> Game:
    game = session.get(Game, (season, week, away_team, home_team))
    if game is None:
        game = Game(
            season=season,
            week=week,
            away_team=away_team,
            home_team=home_team,
            model_margin=model_margin,
            vegas_margin=vegas_margin,
            home_score=home_score,
            away_score=away_score,
            kickoff=kickoff,
        )
        session.add(game)
        return game
    if model_margin is not None:
        game.model_margin = model_margin
    if vegas_margin is not None:
        game.vegas_margin = vegas_margin
    if home_score is not None:
        game.home_score = home_score
    if away_score is not None:
        game.away_score = away_score
    if kickoff is not None and (replace_kickoff or game.kickoff is None):
        game.kickoff = kickoff
    return game


def weeks(session: Session) -> list[tuple[int, int]]:
    rows = session.execute(
        select(Game.season, Game.week).distinct().order_by(Game.season, Game.week)
    ).all()
    return [(r.season, r.week) for r in rows]


def weeks_with_spreads(session: Session) -> list[tuple[int, int]]:
    rows = session.execute(
        select(Game.season, Game.week)
        .where(Game.vegas_margin.is_not(None))
        .distinct()
        .order_by(Game.season, Game.week)
    ).all()
    return [(r.season, r.week) for r in rows]


def games_for(session: Session, season: int, week: int) -> list[Game]:
    return list(
        session.scalars(
            select(Game)
            .where(Game.season == season, Game.week == week)
            .order_by(Game.kickoff.is_(None), Game.kickoff, Game.away_team, Game.home_team)
        ).all()
    )


def all_games(session: Session) -> list[Game]:
    return list(
        session.scalars(select(Game).order_by(Game.season, Game.week, Game.away_team)).all()
    )


def count_games(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(Game)) or 0)


def vegas_spreads_for(session: Session) -> list[VegasSpread]:
    return list(session.scalars(select(VegasSpread).order_by(VegasSpread.id)).all())
