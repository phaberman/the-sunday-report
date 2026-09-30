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
    from app.deps import MODEL_VERSION, SCOREBOARD_USERS, USERNAME, VEGAS_BOOKMAKER
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
        usernames=SCOREBOARD_USERS,
    )
    assert board["usernames"] == list(SCOREBOARD_USERS)
    row = board["rows"][0]
    assert row["matchup"] == "NE @ SEA"
    assert row["vegas"] == "SEA -3.5"
    assert row["model"] == "Cover"
    assert row["users"][USERNAME] == "Points"

    with TestClient(app) as client:
        r = client.get("/matchups")
        assert r.status_code == 200
        assert "Matchup" in r.text
        assert "Line" in r.text
        assert USERNAME in r.text
        assert "Phillip" in r.text
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

        r = client.get("/spreads", headers={"HX-Request": "true"}, params={"week": 1})
        assert r.status_code == 200
        assert 'id="spreads-panel"' in r.text
        assert "Week 1" in r.text
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

        r = client.get("/matchups", headers={"HX-Request": "true"}, params={"week": 1})
        assert r.status_code == 200
        assert 'id="matchups-panel"' in r.text
        assert "Week 1" in r.text
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

        r = client.get(
            "/scoreboard",
            params={"view": "season"},
            headers={"HX-Request": "true"},
        )
        assert r.status_code == 200
        assert "Season record mix" in r.text
        assert 'hx-get="/scoreboard?view=week&amp;week=' in r.text
        assert "week=&amp;" not in r.text

        r = client.get(
            "/scoreboard",
            params={"view": "week", "week": 1},
            headers={"HX-Request": "true"},
        )
        assert r.status_code == 200
        assert "matchups-weeks" in r.text


def test_upload_page_defaults_to_status_view():
    with TestClient(app) as client:
        r = client.get("/upload")
        assert r.status_code == 200
        assert "Season overview" in r.text
        assert "slot-checklist" in r.text
        assert "upload-panel" in r.text
        assert 'value="status"' in r.text


def test_upload_add_view_has_entry_form():
    with TestClient(app) as client:
        r = client.get("/upload", params={"view": "add", "week": 1, "slot": "vegas"})
        assert r.status_code == 200
        assert "Enter spreads" in r.text
        assert 'id="mode-enter"' in r.text
        assert "Download CSV template" in r.text


def test_upload_template_csv(tmp_path: Path):
    import csv
    import io

    from app.schedule import apply_schedule_rows

    session = db.init(db.connect(tmp_path / "tpl.db"))
    apply_schedule_rows(
        session,
        [
            {
                "season": 2026,
                "week": 3,
                "gameday": "2026-09-20",
                "gametime": "13:00",
                "away_team": "NE",
                "home_team": "SEA",
                "away_score": None,
                "home_score": None,
            },
        ],
    )
    raw = ingest.upload_template_csv(session, season=2026, week=3, source="model")
    rows = list(csv.DictReader(io.StringIO(raw.decode())))
    assert rows == [{"away_team": "NE", "home_team": "SEA", "decision": ""}]
    vegas = list(
        csv.DictReader(
            io.StringIO(
                ingest.upload_template_csv(session, season=2026, week=3, source="vegas").decode()
            )
        )
    )
    assert vegas == [{"away_team": "NE", "home_team": "SEA", "spread": ""}]


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
    from app.schedule import apply_schedule_rows

    session = db.init(db.connect(tmp_path / "t.db"))
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
            {
                "season": 2026,
                "week": 1,
                "gameday": "2026-09-13",
                "gametime": "16:25",
                "away_team": "SF",
                "home_team": "LA",
                "away_score": None,
                "home_score": None,
            },
        ],
    )
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

    import pytest

    with pytest.raises(ValueError, match="already uploaded"):
        ingest.ingest_entries(
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

    rows = ingest.entry_rows_for(
        session, season=2026, week=1, source="vegas", bookmaker="DraftKings"
    )
    sea = next(r for r in rows if r["home_team"] == "SEA")
    assert sea["locked"] is True
    assert sea["locked_spread"] == "SEA -3.5"
    assert sea["locked_favorite"] == "SEA"
    assert sea["locked_points"] == "3.5"
    model_rows = ingest.entry_rows_for(session, season=2026, week=1, source="model")
    sea_model = next(r for r in model_rows if r["home_team"] == "SEA")
    assert sea_model["vegas_line"] == "SEA -3.5"
    la_model = next(r for r in model_rows if r["home_team"] == "LA")
    assert la_model["vegas_line"] == ""


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
        usernames=("Brett", "Phillip"),
    )
    assert board["model"]["wlp"] == "1-0-0"
    assert board["users"]["Brett"]["wlp"] == "0-1-0"
    assert board["users"]["Phillip"]["wlp"] == "0-0-0"
    assert len(board["weekly"]) == 1
    assert board["chart_model_line"]
    assert board["chart_user_lines"]["Brett"]


def test_matchups_for_excludes_pick_only_rows(tmp_path: Path):
    from app.schedule import apply_schedule_rows

    session = db.init(db.connect(tmp_path / "m.db"))
    apply_schedule_rows(
        session,
        [
            {
                "season": 2026,
                "week": 3,
                "gameday": "2026-09-20",
                "gametime": "13:00",
                "away_team": "NE",
                "home_team": "SEA",
                "away_score": None,
                "home_score": None,
            },
        ],
    )
    db.upsert_matchup(session, season=2026, week=3, away_team="BUF", home_team="LAC")
    session.commit()
    rows = db.matchups_for(session, 2026, 3)
    assert len(rows) == 1
    assert rows[0].away_team == "NE"


def test_wipe_week_uploads(tmp_path: Path):
    from app.models import Pick
    from app.schedule import apply_schedule_rows

    session = db.init(db.connect(tmp_path / "w.db"))
    apply_schedule_rows(
        session,
        [
            {
                "season": 2026,
                "week": 3,
                "gameday": "2026-09-20",
                "gametime": "13:00",
                "away_team": "NE",
                "home_team": "SEA",
                "away_score": None,
                "home_score": None,
            },
        ],
    )
    m = db.matchups_for(session, 2026, 3)[0]
    db.upsert_matchup(session, season=2026, week=3, away_team="BUF", home_team="LAC")
    session.add(
        Pick(matchup_id=m.id, spread=3.5, source="vegas", bookmaker="DraftKings")
    )
    session.commit()
    info = db.wipe_week_uploads(session, 2026, 3)
    assert info["picks_deleted"] == 1
    assert info["orphan_matchups_deleted"] == 1
    assert len(db.matchups_for(session, 2026, 3)) == 1
    assert not m.picks  # relationship may need refresh
    session.refresh(m)
    assert list(m.picks) == []


def test_season_compare_ignores_model_version_label(tmp_path: Path):
    from app.deps import USERNAME, VEGAS_BOOKMAKER
    from app.models import Pick
    from app.schedule import apply_schedule_rows
    from app.score import season_compare

    session = db.init(db.connect(tmp_path / "ver.db"))
    for wk, ver in ((1, "preseason"), (2, "v2")):
        apply_schedule_rows(
            session,
            [
                {
                    "season": 2026,
                    "week": wk,
                    "gameday": "2026-09-09",
                    "gametime": "20:20",
                    "away_team": "NE",
                    "home_team": "SEA",
                    "away_score": 10,
                    "home_score": 24,
                },
            ],
        )
        m = db.matchups_for(session, 2026, wk)[0]
        session.add(
            Pick(matchup_id=m.id, spread=3.5, source="vegas", bookmaker="DraftKings")
        )
        session.add(
            Pick(
                matchup_id=m.id,
                spread=0.0,
                decision="cover",
                source="model",
                model_version=ver,
            )
        )
    session.commit()

    board = season_compare(
        db.matchups_for_season(session, 2026),
        bookmaker=VEGAS_BOOKMAKER,
        usernames=("Brett", "Phillip"),
    )
    assert board["model"]["wlp"] == "2-0-0"
    assert len(board["weekly"]) == 2


def test_upload_slot_replace_and_delete(tmp_path: Path):
    from app.schedule import apply_schedule_rows

    session = db.init(db.connect(tmp_path / "slot.db"))
    apply_schedule_rows(
        session,
        [
            {
                "season": 2026,
                "week": 4,
                "gameday": "2026-09-20",
                "gametime": "13:00",
                "away_team": "NE",
                "home_team": "SEA",
                "away_score": None,
                "home_score": None,
            },
        ],
    )
    ingest.ingest_entries(
        session,
        [{"away_team": "NE", "home_team": "SEA", "decision": "cover"}],
        season=2026,
        week=4,
        source="model",
        model_version="note-a",
    )
    assert db.slot_uploaded(session, season=2026, week=4, slot_key="model")

    ingest.ingest_entries(
        session,
        [{"away_team": "NE", "home_team": "SEA", "decision": "points"}],
        season=2026,
        week=4,
        source="model",
        model_version="note-b",
        replace_slot=True,
    )
    m = db.matchups_for(session, 2026, 4)[0]
    model_picks = [p for p in m.picks if p.source == "model"]
    assert len(model_picks) == 1
    assert model_picks[0].decision == "points"

    n = db.delete_slot(session, season=2026, week=4, slot_key="model")
    assert n == 1
    assert not db.slot_uploaded(session, season=2026, week=4, slot_key="model")


def test_upload_summary_marks_weeks(tmp_path: Path):
    from app.models import Pick
    from app.schedule import apply_schedule_rows

    session = db.init(db.connect(tmp_path / "sum.db"))
    apply_schedule_rows(
        session,
        [
            {
                "season": 2026,
                "week": 2,
                "gameday": "2026-09-13",
                "gametime": "13:00",
                "away_team": "NE",
                "home_team": "SEA",
                "away_score": None,
                "home_score": None,
            },
        ],
    )
    m = db.matchups_for(session, 2026, 2)[0]
    session.add(
        Pick(matchup_id=m.id, spread=3.5, source="vegas", bookmaker="DraftKings")
    )
    session.commit()
    summary = db.upload_summary(session, season=2026)
    vegas_row = next(r for r in summary if r["key"] == "vegas")
    assert vegas_row["weeks"][2] is True
    assert vegas_row["weeks"][1] is False
    times = db.week_slots_uploaded_at(session, season=2026, week=2)
    assert times["vegas"] is not None
    assert times["model"] is None


def test_upload_page_shows_summary_table():
    with TestClient(app) as client:
        r = client.get("/upload", params={"view": "status"})
        assert r.status_code == 200
        assert "Season overview" in r.text
        assert "Upload at" in r.text
        assert "Actions" in r.text
        assert "Vegas" in r.text


def test_upload_panel_htmx_swap():
    with TestClient(app) as client:
        r = client.get(
            "/upload",
            params={"view": "add", "week": 2, "slot": "model"},
            headers={"HX-Request": "true"},
        )
        assert r.status_code == 200
        assert 'id="upload-panel"' in r.text
        assert "Add picks" in r.text or "Log picks" in r.text
