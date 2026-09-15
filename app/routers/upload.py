"""CSV/Excel upload into SQLite."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app import ingest
from app.deps import DbConn, templates

router = APIRouter()


@router.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request, flash: str = "", error: str = ""):
    return templates.TemplateResponse(
        request,
        "upload.html",
        {"flash": flash, "error": error, "nav": "upload"},
    )


@router.post("/upload")
async def upload(
    conn: DbConn,
    season: int = Form(...),
    week: int = Form(...),
    kind: str = Form(...),
    file: UploadFile = File(...),
):
    data = await file.read()
    name = file.filename or "upload.csv"
    try:
        rows = ingest.parse_upload(name, data)
        n = ingest.ingest_rows(conn, rows, season=season, week=week, kind=kind)
        ingest.save_upload(kind, week, name, data)
    except Exception as e:
        return RedirectResponse(f"/upload?error={quote(str(e))}", status_code=303)
    return RedirectResponse(f"/upload?flash=upserted+{n}+rows", status_code=303)
