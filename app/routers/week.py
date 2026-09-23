"""This-week and past-week spread boards."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import db, mail, odds
from app.deps import DbConn, SEASON, is_htmx, templates
from app.routers.matchups import _pick_week
from app.score import view_matchup

router = APIRouter()


def _xlsx(rows: list[dict], season: int, week: int) -> Response:
    name = f"{season}_week_{week:02d}_spreads.xlsx"
    return Response(
        content=odds.export_week_xlsx(rows),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


def _live_week() -> tuple[int, int]:
    return odds.current_week()


def _past_week_list(conn) -> list[tuple[int, int]]:
    stored = set(db.weeks_with_vegas(conn))
    return [w for w in odds.past_weeks() if w in stored]


def _pick_past(week_list: list[tuple[int, int]], week: int | None) -> tuple[int, int]:
    season, shown = week_list[-1]
    if week is not None:
        for s, w in week_list:
            if w == week:
                return s, w
    return season, shown


@router.get("/")
def home():
    return RedirectResponse("/matchups", status_code=303)


@router.get("/picks")
def picks(week: int | None = None):
    url = "/matchups" if week is None else f"/matchups?week={week}"
    return RedirectResponse(url, status_code=303)


@router.post("/refresh")
def refresh(conn: DbConn):
    return RedirectResponse("/spreads/refresh", status_code=307)


@router.get("/export")
def export_xlsx():
    return RedirectResponse("/spreads/export", status_code=307)


@router.post("/email")
def email_week(conn: DbConn):
    try:
        to = mail.recipients_from_env()
        season, week = _live_week()
        rows = [view_matchup(m) for m in db.matchups_for(conn, season, week)]
        filename = f"{season}_week_{week:02d}_spreads.xlsx"
        n = mail.send_xlsx(
            to=to,
            subject=f"The Sunday Report: Week {week} Spreads",
            body=f"Attached are the spreads for week {week} of the 2026 NFL Season.",
            filename=filename,
            data=odds.export_week_xlsx(rows),
        )
        return RedirectResponse(f"/?flash={quote(f'sent to {n} addresses')}", status_code=303)
    except Exception as e:
        return RedirectResponse(f"/?error={quote(str(e))}", status_code=303)


@router.get("/past", response_class=HTMLResponse)
def past(request: Request, conn: DbConn, week: int | None = None):
    week_list = _past_week_list(conn)
    ctx = {
        "season": SEASON,
        "week": None,
        "week_list": week_list,
        "rows": [],
        "nav": "past",
    }
    if week_list:
        season, shown = _pick_past(week_list, week)
        ctx.update(
            {
                "season": season,
                "week": shown,
                "rows": [view_matchup(m) for m in db.matchups_for(conn, season, shown)],
            }
        )
    if is_htmx(request):
        return templates.TemplateResponse(request, "partials/past_board.html", ctx)
    return templates.TemplateResponse(request, "past.html", ctx)


@router.get("/export/past")
def export_past_xlsx(conn: DbConn, week: int | None = None):
    week_list = _past_week_list(conn)
    if not week_list:
        return RedirectResponse("/past", status_code=303)
    season, w = _pick_past(week_list, week)
    rows = [view_matchup(m) for m in db.matchups_for(conn, season, w)]
    return _xlsx(rows, season, w)
