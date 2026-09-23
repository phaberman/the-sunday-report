"""DraftKings spreads board."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import db, odds
from app.deps import DbConn, is_htmx, templates
from app.routers.matchups import _pick_week
from app.score import view_matchup

router = APIRouter()


def _rows(conn, season: int, week: int) -> list[dict]:
    out: list[dict] = []
    for m in db.matchups_for(conn, season, week):
        row = view_matchup(m)
        row["date"] = odds.format_kickoff_date(m.kickoff)
        out.append(row)
    return out


def _is_current_week(conn, season: int, week: int) -> bool:
    schedule = odds.load_schedule(conn)
    return (season, week) == odds.current_week(schedule)


def _ctx(
    conn,
    *,
    week: int | None,
    toast: str = "",
    error: str = "",
) -> dict:
    season, shown = _pick_week(conn, week)
    schedule = odds.load_schedule(conn)
    current = odds.current_week(schedule)
    return {
        "season": season,
        "week": shown,
        "week_list": db.weeks(conn) or [(season, shown)],
        "past_weeks": set(odds.past_weeks(schedule)),
        "is_current_week": (season, shown) == current,
        "rows": _rows(conn, season, shown),
        "toast": toast,
        "error": error,
        "nav": "spreads",
    }


def _toast_message(info: dict[str, str | int]) -> str:
    n = info["n"]
    remaining = info["remaining"]
    used = info["used"]
    last = info.get("last", "?")
    msg = f"Updated {n} spreads · {remaining} credits remaining ({used} used this month)"
    if last not in ("?", "", None):
        cost = "credit" if str(last) == "1" else "credits"
        msg += f" · this call cost {last} {cost}"
    try:
        total = int(remaining) + int(used)
        if 495 <= total <= 505:
            msg += f" · {remaining} of {total} on free tier"
    except (TypeError, ValueError):
        pass
    return msg


@router.get("/spreads", response_class=HTMLResponse)
def spreads_page(
    request: Request,
    conn: DbConn,
    week: int | None = None,
    toast: str = "",
    error: str = "",
):
    ctx = _ctx(conn, week=week, toast=toast, error=error)
    if is_htmx(request):
        return templates.TemplateResponse(request, "partials/spreads_board.html", ctx)
    return templates.TemplateResponse(request, "spreads.html", ctx)


@router.post("/spreads/refresh")
def refresh_spreads(conn: DbConn, week: int | None = Form(None)):
    w = week if week is not None else _pick_week(conn, None)[1]
    try:
        info = odds.refresh_spreads(conn)
        msg = _toast_message(info)
        return RedirectResponse(
            f"/spreads?toast={quote(msg)}&week={w}",
            status_code=303,
        )
    except Exception as e:
        return RedirectResponse(
            f"/spreads?error={quote(str(e))}&week={w}",
            status_code=303,
        )


@router.get("/spreads/export")
def export_spreads(conn: DbConn, week: int | None = None):
    season, shown = _pick_week(conn, week)
    rows = _rows(conn, season, shown)
    name = f"{season}_week_{shown:02d}_spreads.xlsx"
    return Response(
        content=odds.export_spreads_xlsx(rows),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
