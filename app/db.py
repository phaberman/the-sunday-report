"""SQLAlchemy engine, sessions, and queries."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, selectinload

from app.models import Base, Matchup, Pick, matchup_id

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "sunday.db"
LEGACY_TABLES = ("games", "vegas_spreads")


def connect(path: Path | None = None) -> Session:
    p = path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{p}", connect_args={"check_same_thread": False})
    return Session(engine)


def init(session: Session | None = None) -> Session:
    s = session or connect()
    bind = s.get_bind()
    for name in LEGACY_TABLES:
        s.execute(text(f"DROP TABLE IF EXISTS {name}"))
    s.commit()
    Base.metadata.create_all(bind)
    cols = {row[1] for row in s.execute(text("PRAGMA table_info(picks)"))}
    if cols and "bookmaker" not in cols:
        s.execute(text("ALTER TABLE picks ADD COLUMN bookmaker TEXT"))
        s.commit()
    return s


def upsert_matchup(
    session: Session,
    *,
    season: int,
    week: int,
    away_team: str,
    home_team: str,
    kickoff: str | None = None,
    home_score: int | None = None,
    away_score: int | None = None,
    replace_kickoff: bool = False,
) -> Matchup:
    mid = matchup_id(season, week, home_team, away_team)
    row = session.get(Matchup, mid)
    if row is None:
        row = Matchup(
            id=mid,
            season_year=season,
            season_week=week,
            home_team=home_team,
            away_team=away_team,
            kickoff=kickoff,
            home_score=home_score,
            away_score=away_score,
        )
        session.add(row)
        return row
    if home_score is not None:
        row.home_score = home_score
    if away_score is not None:
        row.away_score = away_score
    if kickoff is not None and (replace_kickoff or row.kickoff is None):
        row.kickoff = kickoff
    return row


def pick_exists(
    session: Session,
    *,
    matchup_id: str,
    source: str,
    spread: float,
    username: str | None,
    model_version: str | None,
    bookmaker: str | None,
) -> bool:
    q = select(Pick.id).where(
        Pick.matchup_id == matchup_id,
        Pick.source == source,
        Pick.spread == spread,
        Pick.username.is_(username) if username is None else Pick.username == username,
        Pick.model_version.is_(model_version)
        if model_version is None
        else Pick.model_version == model_version,
        Pick.bookmaker.is_(bookmaker) if bookmaker is None else Pick.bookmaker == bookmaker,
    )
    return session.scalar(q) is not None


def _identity_filters(
    source: str,
    username: str | None,
    model_version: str | None,
    bookmaker: str | None,
) -> list:
    return [
        Pick.source == source,
        Pick.username.is_(username) if username is None else Pick.username == username,
        Pick.model_version.is_(model_version)
        if model_version is None
        else Pick.model_version == model_version,
        Pick.bookmaker.is_(bookmaker) if bookmaker is None else Pick.bookmaker == bookmaker,
    ]


def latest_identity_pick(
    session: Session,
    *,
    matchup_id: str,
    source: str,
    username: str | None = None,
    model_version: str | None = None,
    bookmaker: str | None = None,
) -> Pick | None:
    """Any prior pick for this matchup + source identity (locks the row)."""
    q = (
        select(Pick)
        .where(Pick.matchup_id == matchup_id, *_identity_filters(source, username, model_version, bookmaker))
        .order_by(Pick.created_at.desc(), Pick.id.desc())
        .limit(1)
    )
    return session.scalars(q).first()


def add_pick(
    session: Session,
    *,
    matchup: Matchup,
    spread: float,
    source: str,
    username: str | None = None,
    model_version: str | None = None,
    bookmaker: str | None = None,
) -> Pick | None:
    """Insert pick unless an identical row already exists. Returns None on dup."""
    if pick_exists(
        session,
        matchup_id=matchup.id,
        source=source,
        spread=spread,
        username=username,
        model_version=model_version,
        bookmaker=bookmaker,
    ):
        return None
    pick = Pick(
        matchup_id=matchup.id,
        spread=spread,
        source=source,
        username=username,
        model_version=model_version,
        bookmaker=bookmaker,
    )
    session.add(pick)
    return pick


def weeks(session: Session) -> list[tuple[int, int]]:
    rows = session.execute(
        select(Matchup.season_year, Matchup.season_week)
        .distinct()
        .order_by(Matchup.season_year, Matchup.season_week)
    ).all()
    return [(r.season_year, r.season_week) for r in rows]


def weeks_with_vegas(session: Session) -> list[tuple[int, int]]:
    rows = session.execute(
        select(Matchup.season_year, Matchup.season_week)
        .join(Pick, Pick.matchup_id == Matchup.id)
        .where(Pick.source == "vegas")
        .distinct()
        .order_by(Matchup.season_year, Matchup.season_week)
    ).all()
    return [(r.season_year, r.season_week) for r in rows]


def matchups_for(session: Session, season: int, week: int) -> list[Matchup]:
    return list(
        session.scalars(
            select(Matchup)
            .where(Matchup.season_year == season, Matchup.season_week == week)
            .options(selectinload(Matchup.picks))
            .order_by(
                Matchup.kickoff.is_(None),
                Matchup.kickoff,
                Matchup.away_team,
                Matchup.home_team,
            )
        ).all()
    )


def all_matchups(session: Session) -> list[Matchup]:
    return list(
        session.scalars(
            select(Matchup)
            .options(selectinload(Matchup.picks))
            .order_by(Matchup.season_year, Matchup.season_week, Matchup.away_team)
        ).all()
    )


def count_matchups(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(Matchup)) or 0)
