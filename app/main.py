from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import auth, db, ingest
from app.deps import APP_DIR
from app.routers import matchups, scoreboard, scores, spreads, upload, week


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.init()
    ingest.ensure_schedule(conn)
    if db.count_matchups(conn) == 0:
        ingest.seed_week01(conn)
    conn.close()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=auth.session_secret(),
    session_cookie="sunday_session",
    same_site="lax",
    https_only=auth.https_only(),
)


@app.exception_handler(auth.LoginRequired)
def _login_required(request: Request, exc: auth.LoginRequired):
    return RedirectResponse("/login", status_code=303)


_guard = [Depends(auth.login_required)]
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
app.include_router(auth.router)
app.include_router(week.router, dependencies=_guard)
app.include_router(scoreboard.router, dependencies=_guard)
app.include_router(matchups.router, dependencies=_guard)
app.include_router(spreads.router, dependencies=_guard)
app.include_router(scores.router, dependencies=_guard)
app.include_router(upload.router, dependencies=_guard)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", reload=True)
