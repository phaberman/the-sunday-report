"""CSV/Excel upload or in-UI enter-spreads into picks."""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app import ingest
from app.deps import DbConn, templates

router = APIRouter()

SAMPLE_ROWS = [
    {"away_team": "NE", "home_team": "SEA", "spread": "SEA -3.5"},
    {"away_team": "SF", "home_team": "LAR", "spread": "LAR -3.5"},
    {"away_team": "CHI", "home_team": "CAR", "spread": "CHI -2.5"},
]


def _upload_ctx(
    *,
    flash: str = "",
    error: str = "",
    season: int | None = None,
    week: int = 1,
    source: str = "vegas",
    bookmaker: str = "DraftKings",
    username: str = "",
    model_version: str = "",
    entry_rows: list[dict] | None = None,
) -> dict:
    season = season or date.today().year
    return {
        "flash": flash,
        "error": error,
        "nav": "upload",
        "default_season": season,
        "week": week,
        "weeks": list(range(1, 19)),
        "usernames": ["Brett", "Phillip", "Other"],
        "model_versions": ["preseason", "v1"],
        "bookmakers": ["DraftKings", "FanDuel", "BetMGM", "Caesars"],
        "sample_rows": SAMPLE_ROWS,
        "source": source,
        "bookmaker": bookmaker,
        "username": username,
        "model_version": model_version,
        "entry_rows": entry_rows or [],
    }


def _norm_meta(source: str, bookmaker: str, username: str, model_version: str):
    bookmaker = (bookmaker or "").strip() or None
    username = (username or "").strip() or None
    model_version = (model_version or "").strip() or None
    if source != "vegas":
        bookmaker = None
    if source != "user":
        username = None
    if source != "model":
        model_version = None
    return bookmaker, username, model_version


@router.get("/upload", response_class=HTMLResponse)
def upload_form(
    request: Request,
    conn: DbConn,
    flash: str = "",
    error: str = "",
    week: int = 1,
    source: str = "vegas",
    bookmaker: str = "DraftKings",
    username: str = "",
    model_version: str = "",
):
    season = date.today().year
    bm, user, ver = _norm_meta(source, bookmaker, username, model_version)
    rows = ingest.entry_rows_for(
        conn,
        season=season,
        week=week,
        source=source,
        username=user,
        model_version=ver,
        bookmaker=bm,
    )
    return templates.TemplateResponse(
        request,
        "upload.html",
        _upload_ctx(
            flash=flash,
            error=error,
            season=season,
            week=week,
            source=source,
            bookmaker=bookmaker or "DraftKings",
            username=username,
            model_version=model_version,
            entry_rows=rows,
        ),
    )


@router.get("/upload/entries", response_class=HTMLResponse)
def upload_entries(
    request: Request,
    conn: DbConn,
    week: int = 1,
    season: int | None = None,
    source: str = "vegas",
    bookmaker: str = "",
    username: str = "",
    model_version: str = "",
):
    season = season or date.today().year
    bm, user, ver = _norm_meta(source, bookmaker, username, model_version)
    rows = ingest.entry_rows_for(
        conn,
        season=season,
        week=week,
        source=source,
        username=user,
        model_version=ver,
        bookmaker=bm,
    )
    return templates.TemplateResponse(
        request,
        "partials/upload_entries.html",
        {"entry_rows": rows, "week": week, "season": season},
    )


def _entries_from_form(form) -> list[dict]:
    """Parse fav_<id> / pts_<id> / away_<id> / home_<id> fields."""
    ids = set()
    for key in form.keys():
        if key.startswith("pts_"):
            ids.add(key[4:])
    entries = []
    for mid in sorted(ids):
        pts = (form.get(f"pts_{mid}") or "").strip()
        if not pts:
            continue
        entries.append(
            {
                "away_team": form.get(f"away_{mid}") or "",
                "home_team": form.get(f"home_{mid}") or "",
                "favorite": form.get(f"fav_{mid}") or "",
                "points": pts,
            }
        )
    return entries


@router.post("/upload")
async def upload(
    request: Request,
    conn: DbConn,
    season: int = Form(...),
    week: int = Form(...),
    source: str = Form(...),
    mode: str = Form("enter"),
    username: str = Form(""),
    model_version: str = Form(""),
    bookmaker: str = Form(""),
    file: UploadFile | None = File(None),
):
    bm, user, ver = _norm_meta(source, bookmaker, username, model_version)
    try:
        if mode == "file":
            if file is None or not file.filename:
                raise ValueError("Choose a CSV or Excel file")
            data = await file.read()
            rows = ingest.parse_upload(file.filename, data)
            inserted, skipped = ingest.ingest_rows(
                conn,
                rows,
                season=season,
                week=week,
                source=source,
                username=user,
                model_version=ver,
                bookmaker=bm,
            )
            msg = f"inserted+{inserted}+skipped+{skipped}+dups"
        else:
            form = await request.form()
            entries = _entries_from_form(form)
            inserted, skipped, dups = ingest.ingest_entries(
                conn,
                entries,
                season=season,
                week=week,
                source=source,
                username=user,
                model_version=ver,
                bookmaker=bm,
            )
            msg = f"inserted+{inserted}+skipped+{skipped}+locked_or_blank+dups+{dups}"
    except Exception as e:
        return RedirectResponse(f"/upload?error={quote(str(e))}&week={week}", status_code=303)
    return RedirectResponse(
        f"/upload?flash={quote(msg)}&week={week}&source={quote(source)}",
        status_code=303,
    )
