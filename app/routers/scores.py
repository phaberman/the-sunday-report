"""Legacy routes → scoreboard."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/results")
def results():
    return RedirectResponse("/scoreboard", status_code=307)


@router.get("/season")
def season():
    return RedirectResponse("/scoreboard", status_code=307)
