"""Shared FastAPI dependencies and template env."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import db

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
SEASON = date.today().year
VEGAS_BOOKMAKER = "DraftKings"
MODEL_VERSION = "preseason"
USERNAME = "Brett"
SCOREBOARD_USERS = ("Brett", "Phillip")


def get_db() -> Generator[Session, None, None]:
    session = db.init(db.connect())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbConn = Annotated[Session, Depends(get_db)]


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"
