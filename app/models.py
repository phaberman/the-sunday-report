"""SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"

    season: Mapped[int] = mapped_column(Integer, primary_key=True)
    week: Mapped[int] = mapped_column(Integer, primary_key=True)
    away_team: Mapped[str] = mapped_column(String, primary_key=True)
    home_team: Mapped[str] = mapped_column(String, primary_key=True)
    model_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    vegas_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kickoff: Mapped[str | None] = mapped_column(String, nullable=True)


class VegasSpread(Base):
    __tablename__ = "vegas_spreads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kickoff: Mapped[str | None] = mapped_column(String, nullable=True)
    home_team: Mapped[str] = mapped_column(String, nullable=False)
    away_team: Mapped[str] = mapped_column(String, nullable=False)
    spread: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
