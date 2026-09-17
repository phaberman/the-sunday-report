from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import db, ingest
from app.deps import APP_DIR
from app.routers import scores, upload, week


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.init()
    ingest.ensure_schedule(conn)
    if db.count_matchups(conn) == 0:
        ingest.seed_week01(conn)
    conn.close()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
app.include_router(week.router)
app.include_router(scores.router)
app.include_router(upload.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", reload=True)
