"""CSV/Excel upload or in-UI enter-spreads into picks."""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app import db, ingest, odds
from app.db import (
    UPLOAD_SUMMARY_ROWS,
    UPLOAD_VEGAS_BOOK,
    UPLOAD_USERS,
    delete_slot,
    slot_key_for_upload,
    upload_summary,
    week_slots_uploaded,
    week_upload_complete,
)
from app.deps import DbConn, SEASON, templates
from app.routers.matchups import _pick_week

router = APIRouter()

SAMPLE_ROWS_VEGAS = [
    {"away_team": "NE", "home_team": "SEA", "spread": "3.5"},
    {"away_team": "SF", "home_team": "LA", "spread": "3.5"},
]
SAMPLE_ROWS_DECISION = [
    {"away_team": "NE", "home_team": "SEA", "decision": "cover"},
    {"away_team": "SF", "home_team": "LA", "decision": "points"},
]


def _upload_ctx(
    conn,
    *,
    flash: str = "",
    error: str = "",
    season: int | None = None,
    week: int = 1,
    source: str = "vegas",
    username: str = "",
    model_version: str = "",
    entry_rows: list[dict] | None = None,
    past_weeks: set[tuple[int, int]] | None = None,
    adjust: bool = False,
    adjust_slot: str = "",
) -> dict:
    season = season or date.today().year
    slots = week_slots_uploaded(conn, season=season, week=week)
    complete = week_upload_complete(conn, season=season, week=week)
    slot_blocked = False
    try:
        bm, user, _ = _norm_meta(source, username, "")
        sk = slot_key_for_upload(source, user)
        slot_blocked = slots.get(sk, False) and not adjust
    except ValueError:
        slot_blocked = False
    slot_rows = []
    for key, label in UPLOAD_SUMMARY_ROWS:
        slot_rows.append(
            {
                "key": key,
                "label": label,
                "uploaded": slots.get(key, False),
            }
        )
    return {
        "flash": flash,
        "error": error,
        "nav": "upload",
        "default_season": season,
        "week": week,
        "weeks": list(range(1, 19)),
        "summary_weeks": list(range(1, 19)),
        "upload_summary": upload_summary(conn, season=season),
        "usernames": list(UPLOAD_USERS),
        "sample_rows_vegas": SAMPLE_ROWS_VEGAS,
        "sample_rows_decision": SAMPLE_ROWS_DECISION,
        "source": source,
        "entry_source": source,
        "bookmaker": UPLOAD_VEGAS_BOOK,
        "username": username,
        "model_version": model_version,
        "entry_rows": entry_rows or [],
        "past_weeks": past_weeks or set(),
        "week_slots": slots,
        "week_complete": complete,
        "slot_rows": slot_rows,
        "adjust": adjust,
        "adjust_slot": adjust_slot,
        "form_disabled": (complete and not adjust) or slot_blocked,
        "slot_blocked": slot_blocked,
    }


def _resolve_week(conn, week: int | None) -> tuple[int, int]:
    """None → current week; explicit week is kept even when empty."""
    if week is None:
        return _pick_week(conn, None)
    wlist = db.weeks(conn)
    for season, w in wlist:
        if w == week:
            return season, w
    season = wlist[0][0] if wlist else SEASON
    return season, week


def _norm_meta(source: str, username: str, model_version: str):
    username = (username or "").strip() or None
    model_version = (model_version or "").strip() or None
    bookmaker = UPLOAD_VEGAS_BOOK if source == "vegas" else None
    if source != "user":
        username = None
    if source != "model":
        model_version = None
    return bookmaker, username, model_version


def _source_for_slot(slot_key: str) -> tuple[str, str, str]:
    if slot_key == "vegas":
        return "vegas", "", ""
    if slot_key == "model":
        return "model", "", ""
    if slot_key in UPLOAD_USERS:
        return "user", slot_key, ""
    raise ValueError(f"unknown slot {slot_key}")


@router.get("/upload", response_class=HTMLResponse)
def upload_form(
    request: Request,
    conn: DbConn,
    flash: str = "",
    error: str = "",
    week: int | None = None,
    source: str = "vegas",
    username: str = "",
    model_version: str = "",
    adjust: int = 0,
    slot: str = "",
):
    season, shown = _resolve_week(conn, week)
    adjusting = bool(adjust) and slot
    if adjusting:
        source, username, model_version = _source_for_slot(slot)
        if slot == "model" and not model_version:
            model_version = ""
    bm, user, ver = _norm_meta(source, username, model_version)
    rows = ingest.entry_rows_for(
        conn,
        season=season,
        week=shown,
        source=source,
        username=user,
        model_version=ver,
        bookmaker=bm,
        adjust=adjusting,
    )
    if adjusting and slot == "model":
        for m in db.matchups_for(conn, season, shown):
            pick = db.latest_slot_pick(conn, matchup_id=m.id, slot_key="model")
            if pick and pick.model_version and not model_version:
                model_version = pick.model_version
                break
    return templates.TemplateResponse(
        request,
        "upload.html",
        _upload_ctx(
            conn,
            flash=flash,
            error=error,
            season=season,
            week=shown,
            source=source,
            username=username or (user or ""),
            model_version=model_version or (ver or ""),
            entry_rows=rows,
            past_weeks=set(odds.past_weeks(odds.load_schedule(conn))),
            adjust=adjusting,
            adjust_slot=slot if adjusting else "",
        ),
    )


@router.get("/upload/entries", response_class=HTMLResponse)
def upload_entries(
    request: Request,
    conn: DbConn,
    week: int | None = None,
    season: int | None = None,
    source: str = "vegas",
    username: str = "",
    model_version: str = "",
    adjust: int = 0,
):
    picked_season, shown = _resolve_week(conn, week)
    season = season or picked_season
    bm, user, ver = _norm_meta(source, username, model_version)
    rows = ingest.entry_rows_for(
        conn,
        season=season,
        week=shown,
        source=source,
        username=user,
        model_version=ver,
        bookmaker=bm,
        adjust=bool(adjust),
    )
    complete = week_upload_complete(conn, season=season, week=shown)
    return templates.TemplateResponse(
        request,
        "partials/upload_entries.html",
        {
            "entry_rows": rows,
            "week": shown,
            "season": season,
            "entry_source": source,
            "form_disabled": complete and not adjust,
            "adjust": bool(adjust),
        },
    )


def _entries_from_form(form, source: str) -> list[dict]:
    """Parse pts_<id> or decision_<id> plus away/home fields."""
    ids: set[str] = set()
    for key in form.keys():
        if key.startswith("pts_"):
            ids.add(key[4:])
        if key.startswith("decision_"):
            ids.add(key[9:])
    entries = []
    for mid in sorted(ids):
        base = {
            "away_team": form.get(f"away_{mid}") or "",
            "home_team": form.get(f"home_{mid}") or "",
        }
        if source == "vegas":
            pts = (form.get(f"pts_{mid}") or "").strip()
            if not pts:
                continue
            base["points"] = pts
        else:
            dec = (form.get(f"decision_{mid}") or "").strip()
            if not dec:
                continue
            base["decision"] = dec
        entries.append(base)
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
    adjust: str = Form(""),
    file: UploadFile | None = File(None),
):
    bm, user, ver = _norm_meta(source, username, model_version)
    replace = bool((adjust or "").strip())
    if week_upload_complete(conn, season=season, week=week) and not replace:
        return RedirectResponse(
            f"/upload?error={quote('Week complete — use Adjust on a slot to change picks')}&week={week}",
            status_code=303,
        )
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
                model_version=ver or model_version.strip() or None,
                bookmaker=bm,
                replace_slot=replace,
            )
            msg = f"inserted+{inserted}+skipped+{skipped}+dups"
        else:
            form = await request.form()
            entries = _entries_from_form(form, source)
            inserted, skipped, dups = ingest.ingest_entries(
                conn,
                entries,
                season=season,
                week=week,
                source=source,
                username=user,
                model_version=ver or model_version.strip() or None,
                bookmaker=bm,
                replace_slot=replace,
            )
            msg = f"inserted+{inserted}+skipped+{skipped}+locked_or_blank+dups+{dups}"
    except Exception as e:
        return RedirectResponse(f"/upload?error={quote(str(e))}&week={week}", status_code=303)
    return RedirectResponse(
        f"/upload?flash={quote(msg)}&week={week}&source={quote(source)}",
        status_code=303,
    )


@router.post("/upload/delete")
def upload_delete(
    conn: DbConn,
    season: int = Form(...),
    week: int = Form(...),
    slot: str = Form(...),
):
    try:
        n = delete_slot(conn, season=season, week=week, slot_key=slot)
        flash = f"deleted+{n}+picks+from+{slot}"
    except Exception as e:
        return RedirectResponse(
            f"/upload?error={quote(str(e))}&week={week}",
            status_code=303,
        )
    return RedirectResponse(f"/upload?flash={quote(flash)}&week={week}", status_code=303)
