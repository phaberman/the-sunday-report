"""Schedule / matchups board."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import db, odds
from app.deps import DbConn, SEASON, is_htmx, templates
from app.models import Matchup
from app.odds import format_kickoff
from app.schedule import refresh_schedule

router = APIRouter()


def _score_text(m: Matchup) -> str:
    if m.away_score is None or m.home_score is None:
        return "—"
    return f"{m.away_score}–{m.home_score}"


def _row(m: Matchup) -> dict:
    return {
        "away_team": m.away_team,
        "home_team": m.home_team,
        "kickoff": format_kickoff(m.kickoff),
        "score": _score_text(m),
    }


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


def _filtered_rows(conn, season: int, week: int, team: str | None) -> list[dict]:
    matchups = db.matchups_for(conn, season, week)
    if team:
        t = team.upper()
        matchups = [m for m in matchups if m.away_team == t or m.home_team == t]
    return [_row(m) for m in matchups]


def _ctx(conn, *, week: int | None, team: str | None, flash: str = "", error: str = ""):
    season, shown = _pick_week(conn, week)
    team = (team or "").strip().upper() or None
    return {
        "season": season,
        "week": shown,
        "week_list": db.weeks(conn) or [(season, shown)],
        "teams": db.teams(conn),
        "team": team or "",
        "rows": _filtered_rows(conn, season, shown, team),
        "flash": flash,
        "error": error,
        "nav": "matchups",
    }


@router.get("/matchups", response_class=HTMLResponse)
def matchups(
    request: Request,
    conn: DbConn,
    week: int | None = None,
    team: str | None = None,
    flash: str = "",
    error: str = "",
):
    ctx = _ctx(conn, week=week, team=team, flash=flash, error=error)
    if is_htmx(request):
        return templates.TemplateResponse(request, "partials/matchups_board.html", ctx)
    return templates.TemplateResponse(request, "matchups.html", ctx)


@router.post("/matchups/refresh")
def refresh(
    conn: DbConn,
    week: int | None = Form(None),
    team: str | None = Form(None),
):
    q_team = f"&team={quote(team)}" if team else ""
    try:
        info = refresh_schedule(conn, SEASON)
        msg = f"Updated {info['n']} matchups ({info['with_scores']} with scores)."
        w = week if week is not None else _pick_week(conn, None)[1]
        return RedirectResponse(
            f"/matchups?flash={quote(msg)}&week={w}{q_team}",
            status_code=303,
        )
    except Exception as e:
        w = week if week is not None else 1
        return RedirectResponse(
            f"/matchups?error={quote(str(e))}&week={w}{q_team}",
            status_code=303,
        )


@router.get("/matchups/export")
def export_xlsx(conn: DbConn, week: int | None = None, team: str | None = None):
    season, shown = _pick_week(conn, week)
    team = (team or "").strip().upper() or None
    rows = _filtered_rows(conn, season, shown, team)
    name = f"{season}_week_{shown:02d}_matchups.xlsx"
    return Response(
        content=odds.export_matchups_xlsx(rows),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
