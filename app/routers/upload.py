"""CSV/Excel upload into picks."""

from __future__ import annotations

from datetime import date
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
        {
            "flash": flash,
            "error": error,
            "nav": "upload",
            "default_season": date.today().year,
        },
    )


@router.post("/upload")
async def upload(
    conn: DbConn,
    season: int = Form(...),
    week: int = Form(...),
    source: str = Form(...),
    file: UploadFile = File(...),
    username: str = Form(""),
    model_version: str = Form(""),
):
    data = await file.read()
    name = file.filename or "upload.csv"
    try:
        rows = ingest.parse_upload(name, data)
        inserted, skipped = ingest.ingest_rows(
            conn,
            rows,
            season=season,
            week=week,
            source=source,
            username=username or None,
            model_version=model_version or None,
        )
    except Exception as e:
        return RedirectResponse(f"/upload?error={quote(str(e))}", status_code=303)
    msg = f"inserted+{inserted}+skipped+{skipped}+dups"
    return RedirectResponse(f"/upload?flash={msg}", status_code=303)
