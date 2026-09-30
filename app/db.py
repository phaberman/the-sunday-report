"""SQLAlchemy engine, sessions, and queries."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import and_, create_engine, delete, func, select, text
from sqlalchemy.orm import Session, selectinload

from app.models import Base, Matchup, Pick, matchup_id

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_VEGAS_BOOK = "DraftKings"
UPLOAD_USERS: tuple[str, ...] = ("Brett", "Phillip")
UPLOAD_SUMMARY_ROWS: tuple[tuple[str, str], ...] = (
    ("vegas", "Vegas"),
    ("model", "Model"),
    ("Brett", "Brett"),
    ("Phillip", "Phillip"),
)
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
    cols = {row[1] for row in s.execute(text("PRAGMA table_info(picks)"))}
    if cols and "decision" not in cols:
        s.execute(text("ALTER TABLE picks ADD COLUMN decision TEXT"))
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
    decision: str | None,
    username: str | None,
    model_version: str | None,
    bookmaker: str | None,
) -> bool:
    q = select(Pick.id).where(
        Pick.matchup_id == matchup_id,
        Pick.source == source,
        Pick.spread == spread,
        Pick.decision.is_(decision) if decision is None else Pick.decision == decision,
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


def slot_key_for_upload(source: str, username: str | None = None) -> str:
    if source == "vegas":
        return "vegas"
    if source == "model":
        return "model"
    if source == "user" and username:
        return username
    raise ValueError("invalid upload source identity")


def _slot_meta(slot_key: str) -> tuple[str, str | None]:
    """Map summary row key to pick source + username."""
    if slot_key == "vegas":
        return "vegas", None
    if slot_key == "model":
        return "model", None
    if slot_key in UPLOAD_USERS:
        return "user", slot_key
    raise ValueError(f"unknown upload slot: {slot_key}")


def _slot_pick_filters(source: str, username: str | None) -> list:
    if source == "vegas":
        return [Pick.source == "vegas", Pick.bookmaker == UPLOAD_VEGAS_BOOK]
    if source == "model":
        return [Pick.source == "model"]
    return [Pick.source == "user", Pick.username == username]


def latest_slot_pick(
    session: Session,
    *,
    matchup_id: str,
    slot_key: str,
) -> Pick | None:
    """Latest pick for a week upload slot (one model per game, fixed Vegas book)."""
    source, username = _slot_meta(slot_key)
    q = (
        select(Pick)
        .where(Pick.matchup_id == matchup_id, *_slot_pick_filters(source, username))
        .order_by(Pick.created_at.desc(), Pick.id.desc())
        .limit(1)
    )
    return session.scalars(q).first()


def slot_uploaded(
    session: Session,
    *,
    season: int,
    week: int,
    slot_key: str,
) -> bool:
    """True if any pick exists for this slot in the week."""
    source, username = _slot_meta(slot_key)
    q = (
        select(Pick.id)
        .join(Matchup, Matchup.id == Pick.matchup_id)
        .where(
            Matchup.season_year == season,
            Matchup.season_week == week,
            *_slot_pick_filters(source, username),
        )
        .limit(1)
    )
    return session.scalar(q) is not None


def week_slots_uploaded(session: Session, *, season: int, week: int) -> dict[str, bool]:
    return {
        key: slot_uploaded(session, season=season, week=week, slot_key=key)
        for key, _ in UPLOAD_SUMMARY_ROWS
    }


def week_slots_uploaded_at(
    session: Session, *, season: int, week: int
) -> dict[str, datetime | None]:
    """Latest pick timestamp per upload slot for a week (adjust/replace updates this)."""
    times: dict[str, datetime | None] = {key: None for key, _ in UPLOAD_SUMMARY_ROWS}
    for slot_key, _ in UPLOAD_SUMMARY_ROWS:
        source, username = _slot_meta(slot_key)
        times[slot_key] = session.scalar(
            select(func.max(Pick.created_at))
            .join(Matchup, Matchup.id == Pick.matchup_id)
            .where(
                Matchup.season_year == season,
                Matchup.season_week == week,
                *_slot_pick_filters(source, username),
            )
        )
    return times


def week_upload_complete(session: Session, *, season: int, week: int) -> bool:
    return all(week_slots_uploaded(session, season=season, week=week).values())


def upload_summary(
    session: Session,
    *,
    season: int,
    max_week: int = 18,
) -> list[dict]:
    """Rows for upload summary table: slot label + week -> uploaded bool."""
    weeks = list(range(1, max_week + 1))
    uploaded: dict[str, set[int]] = {key: set() for key, _ in UPLOAD_SUMMARY_ROWS}
    for slot_key, _ in UPLOAD_SUMMARY_ROWS:
        source, username = _slot_meta(slot_key)
        rows = session.execute(
            select(Matchup.season_week)
            .join(Pick, Pick.matchup_id == Matchup.id)
            .where(
                Matchup.season_year == season,
                *_slot_pick_filters(source, username),
            )
            .distinct()
        ).all()
        uploaded[slot_key] = {int(r.season_week) for r in rows}
    return [
        {
            "key": key,
            "label": label,
            "weeks": {w: w in uploaded[key] for w in weeks},
        }
        for key, label in UPLOAD_SUMMARY_ROWS
    ]


def delete_slot(
    session: Session,
    *,
    season: int,
    week: int,
    slot_key: str,
) -> int:
    """Delete all picks for one upload slot in a week. Returns rows deleted."""
    source, username = _slot_meta(slot_key)
    ids = list(
        session.scalars(
            select(Matchup.id).where(
                Matchup.season_year == season, Matchup.season_week == week
            )
        ).all()
    )
    if not ids:
        return 0
    res = session.execute(
        delete(Pick).where(
            Pick.matchup_id.in_(ids),
            *_slot_pick_filters(source, username),
        )
    )
    session.commit()
    return res.rowcount or 0


def add_pick(
    session: Session,
    *,
    matchup: Matchup,
    spread: float,
    source: str,
    decision: str | None = None,
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
        decision=decision,
        username=username,
        model_version=model_version,
        bookmaker=bookmaker,
    ):
        return None
    pick = Pick(
        matchup_id=matchup.id,
        spread=spread,
        decision=decision,
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


def _scheduled_matchup_filter():
    """Real NFL slate rows from schedule refresh (pick-only upserts have no kickoff)."""
    return and_(Matchup.kickoff.isnot(None), Matchup.kickoff != "")


def matchups_for(session: Session, season: int, week: int) -> list[Matchup]:
    return list(
        session.scalars(
            select(Matchup)
            .where(
                Matchup.season_year == season,
                Matchup.season_week == week,
                _scheduled_matchup_filter(),
            )
            .options(selectinload(Matchup.picks))
            .order_by(
                Matchup.kickoff,
                Matchup.away_team,
                Matchup.home_team,
            )
        ).all()
    )


def matchups_for_season(session: Session, season: int) -> list[Matchup]:
    return list(
        session.scalars(
            select(Matchup)
            .where(Matchup.season_year == season, _scheduled_matchup_filter())
            .options(selectinload(Matchup.picks))
            .order_by(
                Matchup.season_week,
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


def teams(session: Session) -> list[str]:
    codes: set[str] = set()
    for away, home in session.execute(select(Matchup.away_team, Matchup.home_team)):
        codes.add(away)
        codes.add(home)
    return sorted(codes)


def wipe_week_uploads(session: Session, season: int, week: int) -> dict[str, int]:
    """Delete all picks for a week and remove pick-only matchups (no kickoff)."""
    ids = list(
        session.scalars(
            select(Matchup.id).where(
                Matchup.season_year == season, Matchup.season_week == week
            )
        ).all()
    )
    picks_n = 0
    if ids:
        res = session.execute(delete(Pick).where(Pick.matchup_id.in_(ids)))
        picks_n = res.rowcount or 0
    orphan_res = session.execute(
        delete(Matchup).where(
            Matchup.season_year == season,
            Matchup.season_week == week,
            Matchup.kickoff.is_(None) | (Matchup.kickoff == ""),
        )
    )
    session.commit()
    return {
        "picks_deleted": picks_n,
        "orphan_matchups_deleted": orphan_res.rowcount or 0,
    }


def wipe_model_and_user_uploads(
    session: Session, *, usernames: tuple[str, ...] = ("Brett", "Phillip")
) -> dict[str, int]:
    """Delete model picks and named user picks; leave Vegas lines. Prune orphan matchups."""
    model_res = session.execute(delete(Pick).where(Pick.source == "model"))
    user_res = session.execute(
        delete(Pick).where(Pick.source == "user", Pick.username.in_(usernames))
    )
    orphan_res = session.execute(
        delete(Matchup).where(Matchup.kickoff.is_(None) | (Matchup.kickoff == ""))
    )
    session.commit()
    return {
        "model_picks_deleted": model_res.rowcount or 0,
        "user_picks_deleted": user_res.rowcount or 0,
        "orphan_matchups_deleted": orphan_res.rowcount or 0,
    }
