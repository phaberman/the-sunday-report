"""Scoreboard: weekly and season ATS vs Vegas line."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import db
from app.deps import (
    DbConn,
    SCOREBOARD_USERS,
    SEASON,
    is_htmx,
    templates,
    VEGAS_BOOKMAKER,
)
from app.routers.matchups import _pick_week
from app.score import scoreboard_board, season_compare

router = APIRouter()


def _week_ctx(conn, *, week: int | None) -> dict:
    season, shown = _pick_week(conn, week)
    matchups = db.matchups_for(conn, season, shown)
    board = scoreboard_board(
        matchups,
        bookmaker=VEGAS_BOOKMAKER,
        default_users=SCOREBOARD_USERS,
    )
    return {
        "season": season,
        "week": shown,
        "week_list": db.weeks(conn) or [(season, shown)],
        "view": "week",
        "nav": "scoreboard",
        **board,
    }


def _season_ctx(conn) -> dict:
    _, shown = _pick_week(conn, None)
    matchups = db.matchups_for_season(conn, SEASON)
    board = season_compare(
        matchups,
        bookmaker=VEGAS_BOOKMAKER,
        usernames=SCOREBOARD_USERS,
    )
    return {
        "season": SEASON,
        "week": shown,
        "week_list": db.weeks(conn) or [(SEASON, shown)],
        "view": "season",
        "nav": "scoreboard",
        "bookmaker": VEGAS_BOOKMAKER,
        **board,
    }


@router.get("/scoreboard", response_class=HTMLResponse)
def scoreboard_page(
    request: Request,
    conn: DbConn,
    week: int | None = None,
    view: str = "week",
):
    ctx = _season_ctx(conn) if view == "season" else _week_ctx(conn, week=week)
    if is_htmx(request):
        return templates.TemplateResponse(
            request, "partials/scoreboard_panel.html", ctx
        )
    return templates.TemplateResponse(request, "scoreboard.html", ctx)
