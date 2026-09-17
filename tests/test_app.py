from pathlib import Path

from fastapi.testclient import TestClient

from app import db, ingest
from app.main import app
from app.models import matchup_id


def test_html_pages_render():
    with TestClient(app) as client:
        for path in ("/", "/past", "/results", "/season", "/upload"):
            r = client.get(path)
            assert r.status_code == 200, path
            assert "The Sunday Report" in r.text


def test_results_htmx_returns_board_fragment():
    with TestClient(app) as client:
        r = client.get("/results", headers={"HX-Request": "true"})
        assert r.status_code == 200
        assert 'id="board"' in r.text
        assert "<html" not in r.text.lower()


def test_upload_page_defaults_to_enter_spreads():
    with TestClient(app) as client:
        r = client.get("/upload")
        assert r.status_code == 200
        assert "Enter spreads" in r.text
        assert 'id="mode-enter"' in r.text
        assert "away_team · home_team · spread" in r.text


def test_upload_entries_empty_week():
    with TestClient(app) as client:
        r = client.get(
            "/upload/entries",
            params={
                "week": 99,
                "season": 2026,
                "source": "vegas",
                "bookmaker": "DraftKings",
            },
        )
        assert r.status_code == 200
        assert "No matchups" in r.text


def test_ingest_entries_and_lock(tmp_path: Path):
    session = db.init(db.connect(tmp_path / "t.db"))
    inserted, skipped, dups = ingest.ingest_entries(
        session,
        [
            {
                "away_team": "NE",
                "home_team": "SEA",
                "favorite": "SEA",
                "points": "3.5",
            },
            {
                "away_team": "SF",
                "home_team": "LA",
                "favorite": "LA",
                "points": "",
            },
        ],
        season=2026,
        week=1,
        source="vegas",
        bookmaker="DraftKings",
    )
    assert inserted == 1
    assert skipped == 1
    assert dups == 0
    mid = matchup_id(2026, 1, "SEA", "NE")
    prior = db.latest_identity_pick(
        session, matchup_id=mid, source="vegas", bookmaker="DraftKings"
    )
    assert prior is not None
    assert prior.spread == 3.5

    inserted2, skipped2, dups2 = ingest.ingest_entries(
        session,
        [
            {
                "away_team": "NE",
                "home_team": "SEA",
                "favorite": "SEA",
                "points": "7",
            }
        ],
        season=2026,
        week=1,
        source="vegas",
        bookmaker="DraftKings",
    )
    assert inserted2 == 0
    assert skipped2 == 1  # locked
    assert dups2 == 0

    rows = ingest.entry_rows_for(
        session, season=2026, week=1, source="vegas", bookmaker="DraftKings"
    )
    sea = next(r for r in rows if r["home_team"] == "SEA")
    assert sea["locked"] is True
    assert sea["locked_spread"] == "SEA -3.5"
