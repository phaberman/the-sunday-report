"""Shared FastAPI dependencies and template env."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates

from app import db

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
SEASON = 2026


def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = db.connect()
    db.init(conn)
    try:
        yield conn
    finally:
        conn.close()


DbConn = Annotated[sqlite3.Connection, Depends(get_db)]


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"
