"""CSV/Excel upload or in-UI enter-spreads into picks."""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import db, ingest, odds
from app.db import (
    UPLOAD_SUMMARY_ROWS,
    UPLOAD_VEGAS_BOOK,
    UPLOAD_USERS,
    delete_slot,
    upload_summary,
    week_slots_uploaded,
    week_slots_uploaded_at,
    week_upload_complete,
)
from app.deps import DbConn, SEASON, is_htmx, templates
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

_SLOT_LABELS = {key: label for key, label in UPLOAD_SUMMARY_ROWS}
_VALID_SLOTS = frozenset(_SLOT_LABELS)


def _upload_ctx(
    conn,
    *,
    flash: str = "",
    error: str = "",
    season: int | None = None,
    week: int = 1,
    view: str = "status",
    pick_slot: str = "vegas",
    username: str = "",
    model_version: str = "",
    entry_rows: list[dict] | None = None,
    past_weeks: set[tuple[int, int]] | None = None,
    adjust: bool = False,
) -> dict:
    season = season or date.today().year
    slots = week_slots_uploaded(conn, season=season, week=week)
    slot_times = week_slots_uploaded_at(conn, season=season, week=week)
    complete = week_upload_complete(conn, season=season, week=week)
    form_source, slot_username, _ = _source_for_slot(pick_slot)
    slot_blocked = slots.get(pick_slot, False) and not adjust
    slot_rows = [
        {
            "key": key,
            "label": label,
            "uploaded": slots.get(key, False),
            "uploaded_at": odds.format_display_datetime(slot_times.get(key)),
        }
        for key, label in UPLOAD_SUMMARY_ROWS
    ]
    return {
        "flash": flash,
        "error": error,
        "nav": "upload",
        "view": view,
        "default_season": season,
        "week": week,
        "weeks": list(range(1, 19)),
        "summary_weeks": list(range(1, 19)),
        "upload_summary": upload_summary(conn, season=season),
        "usernames": list(UPLOAD_USERS),
        "sample_rows_vegas": SAMPLE_ROWS_VEGAS,
        "sample_rows_decision": SAMPLE_ROWS_DECISION,
        "pick_slot": pick_slot,
        "pick_slot_label": _SLOT_LABELS.get(pick_slot, pick_slot),
        "form_source": form_source,
        "entry_source": form_source,
        "bookmaker": UPLOAD_VEGAS_BOOK,
        "username": slot_username or username,
        "model_version": model_version,
        "entry_rows": entry_rows or [],
        "past_weeks": past_weeks or set(),
        "week_slots": slots,
        "week_complete": complete,
        "slot_rows": slot_rows,
        "adjust": adjust,
        "adjust_slot": pick_slot if adjust else "",
        "form_disabled": slot_blocked,
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


def _resolve_pick_slot(conn, season: int, week: int, slot: str) -> str:
    if slot in _VALID_SLOTS:
        return slot
    slots = week_slots_uploaded(conn, season=season, week=week)
    for key, _ in UPLOAD_SUMMARY_ROWS:
        if not slots.get(key):
            return key
    return "vegas"


def _resolve_view(view: str, adjust: bool, slot: str) -> str:
    if adjust and slot:
        return "add"
    if view in ("status", "add"):
        return view
    return "status"


def _model_note_for_slot(conn, season: int, week: int, pick_slot: str) -> str:
    if pick_slot != "model":
        return ""
    for m in db.matchups_for(conn, season, week):
        pick = db.latest_slot_pick(conn, matchup_id=m.id, slot_key="model")
        if pick and pick.model_version:
            return pick.model_version
    return ""


def _render_upload(
    request: Request,
    conn,
    *,
    flash: str = "",
    error: str = "",
    week: int | None = None,
    view: str = "status",
    slot: str = "",
    model_version: str = "",
    adjust: int = 0,
):
    season, shown = _resolve_week(conn, week)
    adjusting = bool(adjust) and bool(slot)
    shown_view = _resolve_view(view, adjusting, slot)
    pick_slot = _resolve_pick_slot(conn, season, shown, slot)
    form_source, slot_user, _ = _source_for_slot(pick_slot)
    note = (model_version or "").strip() or _model_note_for_slot(
        conn, season, shown, pick_slot
    )
    bm, user, ver = _norm_meta(form_source, slot_user, note)
    entry_rows: list[dict] = []
    if shown_view == "add":
        entry_rows = ingest.entry_rows_for(
            conn,
            season=season,
            week=shown,
            source=form_source,
            username=user,
            model_version=ver,
            bookmaker=bm,
            adjust=adjusting,
        )
    ctx = _upload_ctx(
        conn,
        flash=flash,
        error=error,
        season=season,
        week=shown,
        view=shown_view,
        pick_slot=pick_slot,
        username=slot_user,
        model_version=note,
        entry_rows=entry_rows,
        past_weeks=set(odds.past_weeks(odds.load_schedule(conn))),
        adjust=adjusting,
    )
    name = "partials/upload_panel.html" if is_htmx(request) else "upload.html"
    return templates.TemplateResponse(request, name, ctx)


@router.get("/upload", response_class=HTMLResponse)
def upload_form(
    request: Request,
    conn: DbConn,
    flash: str = "",
    error: str = "",
    week: int | None = None,
    view: str = "status",
    slot: str = "",
    model_version: str = "",
    adjust: int = 0,
):
    return _render_upload(
        request,
        conn,
        flash=flash,
        error=error,
        week=week,
        view=view,
        slot=slot,
        model_version=model_version,
        adjust=adjust,
    )


@router.get("/upload/template")
def upload_template(
    conn: DbConn,
    week: int | None = None,
    season: int | None = None,
    source: str = "model",
):
    source = (source or "model").strip().lower()
    if source not in ingest.SOURCES:
        source = "model"
    picked_season, shown = _resolve_week(conn, week)
    season = season or picked_season
    body = ingest.upload_template_csv(conn, season=season, week=shown, source=source)
    name = f"{season}_week_{shown:02d}_{source}_template.csv"
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
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
            f"/upload?view=status&error={quote('Week complete — use Adjust on a slot')}&week={week}",
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
        return RedirectResponse(
            f"/upload?view=add&error={quote(str(e))}&week={week}",
            status_code=303,
        )
    return RedirectResponse(
        f"/upload?view=status&flash={quote(msg)}&week={week}",
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
            f"/upload?view=status&error={quote(str(e))}&week={week}",
            status_code=303,
        )
    return RedirectResponse(
        f"/upload?view=status&flash={quote(flash)}&week={week}",
        status_code=303,
    )
