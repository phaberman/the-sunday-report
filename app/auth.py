"""Shared username/password session. One account from the environment."""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.deps import templates

ROOT = Path(__file__).resolve().parent.parent
WINDOW_SEC = 15 * 60
MAX_FAILS = 5
# ponytail: in-memory lockout; ceiling = one process, resets on restart.
_fails: dict[str, list[float]] = {}

router = APIRouter()


class LoginRequired(Exception):
    """Raised by the router dependency when the session is missing."""


def _fill_from_dotenv() -> None:
    """Set auth vars from .env only when they are not already in the environment."""
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in {"AUTH_USER", "AUTH_PASSWORD", "SESSION_SECRET"}:
            continue
        value = value.strip().strip("'").strip(chr(34))
        os.environ.setdefault(key, value)


def credentials() -> tuple[str, str, str]:
    _fill_from_dotenv()
    return (
        os.environ.get("AUTH_USER", "").strip(),
        os.environ.get("AUTH_PASSWORD", "").strip(),
        os.environ.get("SESSION_SECRET", "").strip(),
    )


def configured() -> bool:
    user, password, secret = credentials()
    return bool(user and password and secret)


def session_secret() -> str:
    _, _, secret = credentials()
    return secret or "unset"


def https_only() -> bool:
    return os.environ.get("RENDER", "").lower() == "true"


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded.strip():
        return forwarded.split(",")[0].strip()
    if request.client is None:
        return "unknown"
    return request.client.host


def _recent(ip: str, now: float) -> list[float]:
    stamps = [t for t in _fails.get(ip, []) if now - t < WINDOW_SEC]
    if stamps:
        _fails[ip] = stamps
    else:
        _fails.pop(ip, None)
    return stamps


def locked(ip: str, now: float | None = None) -> bool:
    return len(_recent(ip, now if now is not None else time.time())) >= MAX_FAILS


def record_fail(ip: str, now: float | None = None) -> None:
    now = now if now is not None else time.time()
    stamps = _recent(ip, now)
    stamps.append(now)
    _fails[ip] = stamps


def clear_fails(ip: str | None = None) -> None:
    if ip is None:
        _fails.clear()
    else:
        _fails.pop(ip, None)


def session_ok(request: Request) -> bool:
    user, _, secret = credentials()
    if not user or not secret or not os.environ.get("AUTH_PASSWORD", "").strip():
        return False
    return request.session.get("user") == user


def login_required(request: Request) -> None:
    if not session_ok(request):
        raise LoginRequired()


def _page(request: Request, error: str = "") -> HTMLResponse:
    return templates.TemplateResponse(
        request, "login.html", {"error": error, "nav": ""}
    )


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if session_ok(request):
        return RedirectResponse("/scoreboard", status_code=303)
    return _page(request)


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
):
    ip = client_ip(request)
    if locked(ip):
        return _page(request, "Try again later.")
    user, expected, secret = credentials()
    ok = bool(
        user
        and expected
        and secret
        and secrets.compare_digest(username, user)
        and secrets.compare_digest(password, expected)
    )
    if not ok:
        record_fail(ip)
        if locked(ip):
            return _page(request, "Try again later.")
        return _page(request, "Wrong username or password.")
    clear_fails(ip)
    request.session["user"] = user
    return RedirectResponse("/scoreboard", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
