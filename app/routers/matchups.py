"""Schedule / matchups board."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import db, odds
from app.deps import (
    DbConn,
    MODEL_VERSION,
    SEASON,
    USERNAME,
    VEGAS_BOOKMAKER,
    is_htmx,
    templates,
)
from app.score import matchups_board, pick_counts
from app.schedule import refresh_schedule

router = APIRouter()


def _pick_week(conn, week: int | None) -> tuple[int, int]:
    wlist = db.weeks(conn)
    if week is not None and wlist:
        for s, w in wlist:
            if w == week:
                return s, w
    live = odds.current_week(odds.load_schedule(conn))
    if wlist:
        for s, w in wlist:
            if (s, w) == live:
                return s, w
        return wlist[0]
    return live


def _board(conn, season: int, week: int) -> dict:
    return matchups_board(
        db.matchups_for(conn, season, week),
        bookmaker=VEGAS_BOOKMAKER,
        model_version=MODEL_VERSION,
        username=USERNAME,
    )


def _ctx(conn, *, week: int | None, flash: str = "", error: str = ""):
    season, shown = _pick_week(conn, week)
    board = _board(conn, season, shown)
    return {
        "season": season,
        "week": shown,
        "week_list": db.weeks(conn) or [(season, shown)],
        "past_weeks": set(odds.past_weeks(odds.load_schedule(conn))),
        "flash": flash,
        "error": error,
        "nav": "matchups",
        **board,
    }


@router.get("/matchups", response_class=HTMLResponse)
def matchups(
    request: Request,
    conn: DbConn,
    week: int | None = None,
    flash: str = "",
    error: str = "",
):
    ctx = _ctx(conn, week=week, flash=flash, error=error)
    if is_htmx(request):
        return templates.TemplateResponse(request, "partials/matchups_panel.html", ctx)
    return templates.TemplateResponse(request, "matchups.html", ctx)


@router.post("/matchups/refresh")
def refresh(conn: DbConn, week: int | None = Form(None)):
    try:
        info = refresh_schedule(conn, SEASON)
        w = week if week is not None else _pick_week(conn, None)[1]
        season, shown = _pick_week(conn, w)
        counts = pick_counts(_board(conn, season, shown)["rows"])
        msg = (
            f"Updated {info['n']} matchups ({info['with_scores']} with scores). "
            f"Picks: Vegas {counts['vegas']}/{counts['total']} · "
            f"Model {counts['model']}/{counts['total']} · "
            f"{USERNAME} {counts['user']}/{counts['total']}"
        )
        return RedirectResponse(
            f"/matchups?flash={quote(msg)}&week={w}",
            status_code=303,
        )
    except Exception as e:
        w = week if week is not None else 1
        return RedirectResponse(
            f"/matchups?error={quote(str(e))}&week={w}",
            status_code=303,
        )


@router.get("/matchups/export")
def export_xlsx(conn: DbConn, week: int | None = None):
    season, shown = _pick_week(conn, week)
    board = _board(conn, season, shown)
    name = f"{season}_week_{shown:02d}_matchups.xlsx"
    return Response(
        content=odds.export_matchups_xlsx(board["rows"], user_col=board["user_col"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
