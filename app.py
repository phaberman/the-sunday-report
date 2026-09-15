from __future__ import annotations

from collections import defaultdict
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import db
import ingest
import mail
import odds
from score import tally, view_game

SEASON = 2026


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.init()
    ingest.ensure_schedule(conn)
    if db.count_games(conn) == 0:
        ingest.seed_week01(conn)
    conn.close()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def _conn():
    c = db.connect()
    db.init(c)
    return c


def _live_week() -> tuple[int, int]:
    return odds.current_week()


def _pick_week(conn, week: int | None) -> tuple[int, int]:
    wlist = db.weeks(conn) or [(SEASON, 1)]
    if week is not None:
        for s, w in wlist:
            if w == week:
                return s, w
    lined = conn.execute(
        """
        SELECT season, week FROM games
        WHERE vegas_margin IS NOT NULL
        ORDER BY season, week
        """
    ).fetchall()
    if lined:
        return lined[-1]["season"], lined[-1]["week"]
    return wlist[0]


@app.get("/", response_class=HTMLResponse)
def picks(request: Request, flash: str = "", error: str = ""):
    conn = _conn()
    try:
        season, week = _live_week()
        rows = [view_game(r) for r in db.games_for(conn, season, week)]
        return templates.TemplateResponse(
            request,
            "picks.html",
            {
                "season": season,
                "week": week,
                "rows": rows,
                "flash": flash,
                "error": error,
                "nav": "now",
            },
        )
    finally:
        conn.close()


@app.post("/refresh")
def refresh():
    conn = _conn()
    try:
        info = odds.refresh_spreads(conn)
        msg = (
            f"updated {info['n']} games · "
            f"API calls remaining {info['remaining']} (used {info['used']})"
        )
        return RedirectResponse(f"/?flash={quote(msg)}", status_code=303)
    except Exception as e:
        return RedirectResponse(f"/?error={quote(str(e))}", status_code=303)
    finally:
        conn.close()


@app.get("/export")
def export_xlsx():
    conn = _conn()
    try:
        season, week = _live_week()
        rows = [view_game(r) for r in db.games_for(conn, season, week)]
        data = odds.export_week_xlsx(rows)
        name = f"{season}_week_{week:02d}_spreads.xlsx"
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )
    finally:
        conn.close()


@app.post("/email")
def email_week():
    conn = _conn()
    try:
        to = mail.recipients_from_env()
        season, week = _live_week()
        rows = [view_game(r) for r in db.games_for(conn, season, week)]
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
    finally:
        conn.close()


@app.get("/past", response_class=HTMLResponse)
def past(request: Request, week: int | None = None):
    conn = _conn()
    try:
        stored = set(db.weeks_with_spreads(conn))
        week_list = [w for w in odds.past_weeks() if w in stored]
        if not week_list:
            return templates.TemplateResponse(
                request,
                "past.html",
                {
                    "season": SEASON,
                    "week": None,
                    "week_list": [],
                    "rows": [],
                    "nav": "past",
                },
            )
        season, shown = week_list[-1]
        if week is not None:
            for s, w in week_list:
                if w == week:
                    season, shown = s, w
                    break
        rows = [view_game(r) for r in db.games_for(conn, season, shown)]
        return templates.TemplateResponse(
            request,
            "past.html",
            {
                "season": season,
                "week": shown,
                "week_list": week_list,
                "rows": rows,
                "nav": "past",
            },
        )
    finally:
        conn.close()


@app.get("/export/past")
def export_past_xlsx(week: int | None = None):
    conn = _conn()
    try:
        stored = set(db.weeks_with_spreads(conn))
        week_list = [w for w in odds.past_weeks() if w in stored]
        if not week_list:
            return RedirectResponse("/past", status_code=303)
        season, w = week_list[-1]
        if week is not None:
            for s, ww in week_list:
                if ww == week:
                    season, w = s, ww
                    break
        rows = [view_game(r) for r in db.games_for(conn, season, w)]
        data = odds.export_week_xlsx(rows)
        name = f"{season}_week_{w:02d}_spreads.xlsx"
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )
    finally:
        conn.close()


@app.get("/results", response_class=HTMLResponse)
def results(request: Request, week: int | None = None):
    conn = _conn()
    try:
        season, week = _pick_week(conn, week)
        rows = [view_game(r) for r in db.games_for(conn, season, week)]
        return templates.TemplateResponse(
            request,
            "results.html",
            {
                "season": season,
                "week": week,
                "week_list": db.weeks(conn) or [(season, week)],
                "rows": rows,
                "closer": tally(rows, "closer", ("model", "vegas", "tie")),
                "ats": tally(rows, "ats", ("cover", "loss", "push", "no_bet")),
            },
        )
    finally:
        conn.close()


@app.get("/season", response_class=HTMLResponse)
def season(request: Request):
    conn = _conn()
    try:
        grouped: dict[tuple[int, int], list] = defaultdict(list)
        all_rows = []
        for raw in db.all_games(conn):
            v = view_game(raw)
            if not v["closer"]:
                continue
            grouped[(raw["season"], raw["week"])].append(v)
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
            },
        )
    finally:
        conn.close()


@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request, flash: str = "", error: str = ""):
    return templates.TemplateResponse(request, "upload.html", {"flash": flash, "error": error})


@app.post("/upload")
async def upload(
    season: int = Form(...),
    week: int = Form(...),
    kind: str = Form(...),
    file: UploadFile = File(...),
):
    data = await file.read()
    name = file.filename or "upload.csv"
    try:
        rows = ingest.parse_upload(name, data)
        conn = _conn()
        try:
            n = ingest.ingest_rows(conn, rows, season=season, week=week, kind=kind)
        finally:
            conn.close()
        ingest.save_upload(kind, week, name, data)
    except Exception as e:
        return RedirectResponse(f"/upload?error={quote(str(e))}", status_code=303)
    return RedirectResponse(f"/upload?flash=upserted+{n}+rows", status_code=303)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", reload=True)
