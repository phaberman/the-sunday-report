"""Results and season tally pages."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import db
from app.deps import DbConn, SEASON, is_htmx, templates
from app.score import tally, view_game

router = APIRouter()


def _pick_week(conn, week: int | None) -> tuple[int, int]:
    wlist = db.weeks(conn) or [(SEASON, 1)]
    if week is not None:
        for s, w in wlist:
            if w == week:
                return s, w
    lined = db.weeks_with_spreads(conn)
    if lined:
        return lined[-1]
    return wlist[0]


@router.get("/results", response_class=HTMLResponse)
def results(request: Request, conn: DbConn, week: int | None = None):
    season, week = _pick_week(conn, week)
    rows = [view_game(r) for r in db.games_for(conn, season, week)]
    ctx = {
        "season": season,
        "week": week,
        "week_list": db.weeks(conn) or [(season, week)],
        "rows": rows,
        "closer": tally(rows, "closer", ("model", "vegas", "tie")),
        "ats": tally(rows, "ats", ("cover", "loss", "push", "no_bet")),
        "nav": "results",
    }
    if is_htmx(request):
        return templates.TemplateResponse(request, "partials/results_board.html", ctx)
    return templates.TemplateResponse(request, "results.html", ctx)


@router.get("/season", response_class=HTMLResponse)
def season(request: Request, conn: DbConn):
    grouped: dict[tuple[int, int], list] = defaultdict(list)
    all_rows = []
    for raw in db.all_games(conn):
        v = view_game(raw)
        if not v["closer"]:
            continue
        grouped[(raw.season, raw.week)].append(v)
        all_rows.append(v)
    by_week = []
    for (s, w), rows in sorted(grouped.items()):
        by_week.append(
            {
                "season": s,
                "week": w,
                "closer": tally(rows, "closer", ("model", "vegas", "tie")),
                "ats": tally(rows, "ats", ("cover", "loss", "push", "no_bet")),
            }
        )
    return templates.TemplateResponse(
        request,
        "season.html",
        {
            "by_week": by_week,
            "closer": tally(all_rows, "closer", ("model", "vegas", "tie")),
            "ats": tally(all_rows, "ats", ("cover", "loss", "push", "no_bet")),
            "nav": "season",
        },
    )
