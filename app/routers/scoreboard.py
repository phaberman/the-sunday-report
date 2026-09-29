"""Weekly scoreboard: cover/points W-L vs Vegas line."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import db
from app.deps import (
    DbConn,
    MODEL_VERSION,
    SEASON,
    USERNAME,
    VEGAS_BOOKMAKER,
    is_htmx,
    templates,
)
from app.routers.matchups import _pick_week
from app.score import scoreboard_board

router = APIRouter()


def _ctx(conn, *, week: int | None) -> dict:
    season, shown = _pick_week(conn, week)
    matchups = db.matchups_for(conn, season, shown)
    board = scoreboard_board(
        matchups,
        bookmaker=VEGAS_BOOKMAKER,
        default_model=MODEL_VERSION,
        default_user=USERNAME,
    )
    return {
        "season": season,
        "week": shown,
        "week_list": db.weeks(conn) or [(season, shown)],
        "nav": "scoreboard",
        **board,
    }


@router.get("/scoreboard", response_class=HTMLResponse)
def scoreboard_page(request: Request, conn: DbConn, week: int | None = None):
    ctx = _ctx(conn, week=week)
    if is_htmx(request):
        return templates.TemplateResponse(request, "partials/scoreboard_board.html", ctx)
    return templates.TemplateResponse(request, "scoreboard.html", ctx)
