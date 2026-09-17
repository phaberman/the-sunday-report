"""SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def matchup_id(season: int, week: int, home_team: str, away_team: str) -> str:
    """Human-readable PK: year_week_home_away → 2026_02_sea_ne."""
    return f"{season}_{week:02d}_{home_team.lower()}_{away_team.lower()}"


class Matchup(Base):
    __tablename__ = "matchups"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    season_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    season_week: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    home_team: Mapped[str] = mapped_column(String, nullable=False)
    away_team: Mapped[str] = mapped_column(String, nullable=False)
    kickoff: Mapped[str | None] = mapped_column(String, nullable=True)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    picks: Mapped[list["Pick"]] = relationship(back_populates="matchup")


class Pick(Base):
    __tablename__ = "picks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    matchup_id: Mapped[str] = mapped_column(
        String, ForeignKey("matchups.id"), nullable=False, index=True
    )
    spread: Mapped[float] = mapped_column(Float, nullable=False)  # home margin
    source: Mapped[str] = mapped_column(String, nullable=False)  # vegas|user|model
    bookmaker: Mapped[str | None] = mapped_column(String, nullable=True)  # vegas only
    model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    matchup: Mapped[Matchup] = relationship(back_populates="picks")
