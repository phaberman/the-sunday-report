from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app import db, ingest
from app.main import app
from app.models import matchup_id


def test_html_pages_render():
    with TestClient(app) as client:
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/scoreboard"
        for path in ("/scoreboard", "/matchups", "/spreads", "/upload"):
            r = client.get(path)
            assert r.status_code == 200, path
            assert "The Sunday Report" in r.text

        r = client.get("/scoreboard", params={"view": "season"})
        assert r.status_code == 200
        assert "Season record mix" in r.text

        r = client.get("/season", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == "/scoreboard?view=season"

        r = client.get("/picks", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/matchups"


def test_matchups_board_with_picks(tmp_path: Path):
    from app.deps import MODEL_VERSION, USERNAME, VEGAS_BOOKMAKER
    from app.models import Pick
    from app.schedule import apply_schedule_rows
    from app.score import matchups_board

    session = db.init(db.connect(tmp_path / "p.db"))
    apply_schedule_rows(
        session,
        [
            {
                "season": 2026,
                "week": 1,
                "gameday": "2026-09-09",
                "gametime": "20:20",
                "away_team": "NE",
                "home_team": "SEA",
                "away_score": None,
                "home_score": None,
            },
        ],
    )
    m = db.matchups_for(session, 2026, 1)[0]
    session.add(
        Pick(
            matchup_id=m.id,
            spread=3.5,
            source="vegas",
            bookmaker="DraftKings",
        )
    )
    session.add(
        Pick(
            matchup_id=m.id,
            spread=0.0,
            decision="cover",
            source="model",
            model_version=MODEL_VERSION,
        )
    )
    session.add(
        Pick(
            matchup_id=m.id,
            spread=0.0,
            decision="points",
            source="user",
            username=USERNAME,
        )
    )
    session.commit()

    board = matchups_board(
        db.matchups_for(session, 2026, 1),
        bookmaker=VEGAS_BOOKMAKER,
        model_version=MODEL_VERSION,
        username=USERNAME,
    )
    assert board["user_col"] == USERNAME
    row = board["rows"][0]
    assert row["matchup"] == "NE @ SEA"
    assert row["vegas"] == "SEA -3.5"
    assert row["model"] == "Cover"
    assert row["user"] == "Points"

    with TestClient(app) as client:
        r = client.get("/matchups")
        assert r.status_code == 200
        assert "Matchup" in r.text
        assert "Line" in r.text
        assert USERNAME in r.text
        assert "Diff" not in r.text

        r = client.get("/matchups", headers={"HX-Request": "true"})
        assert r.status_code == 200
        assert 'id="board"' in r.text
        assert "<html" not in r.text.lower()


def test_spreads_page_and_export(monkeypatch):
    from app import odds

    monkeypatch.setattr(odds, "current_week", lambda *a, **k: (2026, 99))

    with TestClient(app) as client:
        r = client.get("/spreads")
        assert r.status_code == 200
        assert 'aria-label="Get current spreads"' in r.text
        assert 'aria-label="Export week to Excel"' in r.text
        assert ">Date<" in r.text
        assert 'href="/spreads"' in r.text
        assert r.text.index('href="/spreads"') < r.text.index("Upload")

        r = client.get("/spreads", headers={"HX-Request": "true"})
        assert r.status_code == 200
        assert 'id="board"' in r.text
        assert "<html" not in r.text.lower()

        x = client.get("/spreads/export", params={"week": 1})
        assert x.status_code == 200
        assert "spreadsheetml" in x.headers["content-type"]
        assert x.content[:2] == b"PK"

        r = client.get("/spreads", params={"week": 1})
        assert "disabled" in r.text

        r = client.get("/export", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == "/spreads/export"


def test_spreads_refresh_toast(monkeypatch):
    from app import odds

    monkeypatch.setattr(
        odds,
        "refresh_spreads",
        lambda conn: {
            "n": 3,
            "remaining": "497",
            "used": "3",
            "last": "1",
            "pulled_at": "2026-09-23T00:00:00Z",
        },
    )

    with TestClient(app) as client:
        r = client.post("/spreads/refresh", data={"week": 1}, follow_redirects=False)
        assert r.status_code == 303
        assert "toast=" in r.headers["location"]
        r = client.get(r.headers["location"])
        assert r.status_code == 200
        assert 'class="toast"' in r.text
        assert "497 credits remaining" in r.text


def test_matchups_page_and_export():
    with TestClient(app) as client:
        r = client.get("/matchups")
        assert r.status_code == 200
        assert "Matchup" in r.text
        assert 'aria-label="Export week to Excel"' in r.text
        assert 'aria-label="Refresh schedule and scores"' in r.text

        r = client.get("/matchups", headers={"HX-Request": "true"})
        assert r.status_code == 200
        assert 'id="board"' in r.text
        assert "<html" not in r.text.lower()

        x = client.get("/matchups/export", params={"week": 1})
        assert x.status_code == 200
        assert "spreadsheetml" in x.headers["content-type"]
        assert x.content[:2] == b"PK"


def test_matchups_rows(tmp_path: Path):
    from app.routers import matchups as matchups_router
    from app.schedule import apply_schedule_rows

    session = db.init(db.connect(tmp_path / "m.db"))
    apply_schedule_rows(
        session,
        [
            {
                "season": 2026,
                "week": 1,
                "gameday": "2026-09-09",
                "gametime": "20:20",
                "away_team": "NE",
                "home_team": "SEA",
                "away_score": 10,
                "home_score": 13,
            },
            {
                "season": 2026,
                "week": 1,
                "gameday": "2026-09-13",
                "gametime": "13:00",
                "away_team": "CHI",
                "home_team": "CAR",
                "away_score": None,
                "home_score": None,
            },
        ],
    )
    board = matchups_router._board(session, 2026, 1)
    rows = board["rows"]
    assert len(rows) == 2
    sea = next(r for r in rows if r["matchup"] == "NE @ SEA")
    assert sea["away_points"] == 10
    assert sea["home_points"] == 13
    assert not sea["vegas"]
    chi = next(r for r in rows if r["matchup"] == "CHI @ CAR")
    assert chi["away_points"] is None
    assert not chi["vegas"]
    assert not chi["model"]


def test_refresh_schedule_upsert_no_dups(tmp_path: Path):
    from app.schedule import refresh_schedule

    session = db.init(db.connect(tmp_path / "r.db"))
    rows = [
        {
            "season": 2026,
            "week": 2,
            "gameday": "2026-09-17",
            "gametime": "20:15",
            "away_team": "DET",
            "home_team": "BUF",
            "away_score": None,
            "home_score": None,
        }
    ]
    info = refresh_schedule(session, 2026, rows=rows)
    assert info["n"] == 1
    assert info["with_scores"] == 0
    assert db.count_matchups(session) == 1

    rows[0]["away_score"] = 21
    rows[0]["home_score"] = 24
    info2 = refresh_schedule(session, 2026, rows=rows)
    assert info2["n"] == 1
    assert info2["with_scores"] == 1
    assert db.count_matchups(session) == 1
    m = db.matchups_for(session, 2026, 2)[0]
    assert m.away_score == 21 and m.home_score == 24
    assert m.kickoff is not None


def test_load_schedule_from_db(tmp_path: Path):
    from app.odds import current_week, load_schedule
    from app.schedule import apply_schedule_rows

    session = db.init(db.connect(tmp_path / "s.db"))
    apply_schedule_rows(
        session,
        [
            {
                "season": 2026,
                "week": 1,
                "gameday": "2026-09-14",
                "gametime": "20:15",
                "away_team": "DEN",
                "home_team": "KC",
                "away_score": 10,
                "home_score": 31,
            },
            {
                "season": 2026,
                "week": 2,
                "gameday": "2026-09-21",
                "gametime": "13:00",
                "away_team": "DET",
                "home_team": "BUF",
                "away_score": None,
                "home_score": None,
            },
        ],
    )
    sched = load_schedule(session)
    assert len(sched) == 2
    assert current_week(sched, today=date(2026, 9, 15)) == (2026, 2)


def test_scoreboard_htmx_returns_board_fragment():
    with TestClient(app) as client:
        r = client.get("/scoreboard", headers={"HX-Request": "true"})
        assert r.status_code == 200
        assert 'id="board"' in r.text
        assert "<html" not in r.text.lower()


def test_upload_page_defaults_to_enter_spreads():
    with TestClient(app) as client:
        r = client.get("/upload")
        assert r.status_code == 200
        assert "Enter spreads" in r.text
        assert 'id="mode-enter"' in r.text
        assert "away_team" in r.text
        assert "decision" in r.text


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
                "points": "3.5",
            },
            {
                "away_team": "SF",
                "home_team": "LA",
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
    assert sea["locked_favorite"] == "SEA"
    assert sea["locked_points"] == "3.5"


def test_ingest_entries_decision(tmp_path: Path):
    session = db.init(db.connect(tmp_path / "signed.db"))
    inserted, skipped, dups = ingest.ingest_entries(
        session,
        [{"away_team": "DET", "home_team": "BUF", "decision": "points"}],
        season=2026,
        week=2,
        source="user",
        username="Brett",
    )
    assert inserted == 1
    assert skipped == 0
    assert dups == 0
    mid = matchup_id(2026, 2, "BUF", "DET")
    pick = db.latest_identity_pick(session, matchup_id=mid, source="user", username="Brett")
    assert pick is not None
    assert pick.decision == "points"


def test_season_compare_totals(tmp_path: Path):
    from app.deps import MODEL_VERSION, USERNAME, VEGAS_BOOKMAKER
    from app.models import Pick
    from app.schedule import apply_schedule_rows
    from app.score import season_compare

    session = db.init(db.connect(tmp_path / "season.db"))
    apply_schedule_rows(
        session,
        [
            {
                "season": 2026,
                "week": 1,
                "gameday": "2026-09-09",
                "gametime": "20:20",
                "away_team": "NE",
                "home_team": "SEA",
                "away_score": 17,
                "home_score": 24,
            },
        ],
    )
    m = db.matchups_for(session, 2026, 1)[0]
    session.add(
        Pick(matchup_id=m.id, spread=3.5, source="vegas", bookmaker="DraftKings")
    )
    session.add(
        Pick(
            matchup_id=m.id,
            spread=0.0,
            decision="cover",
            source="model",
            model_version=MODEL_VERSION,
        )
    )
    session.add(
        Pick(
            matchup_id=m.id,
            spread=0.0,
            decision="points",
            source="user",
            username=USERNAME,
        )
    )
    session.commit()

    board = season_compare(
        db.matchups_for_season(session, 2026),
        bookmaker=VEGAS_BOOKMAKER,
        model_version=MODEL_VERSION,
        username=USERNAME,
    )
    assert board["model"]["wlp"] == "1-0-0"
    assert board["user"]["wlp"] == "0-1-0"
    assert len(board["weekly"]) == 1
    assert board["chart_model_line"]
    assert board["chart_user_line"]
