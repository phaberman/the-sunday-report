from pathlib import Path

from app import db, ingest
from app.models import matchup_id
from app.spreads import (
    ats,
    closer,
    explain_spread,
    favorite_and_line,
    format_spread,
    grade_decision,
    norm_team,
    to_home_margin,
)


def test_favorite_and_line():
    assert favorite_and_line("NE", "SEA", 3.5) == ("SEA", "3.5")
    assert favorite_and_line("BUF", "HOU", -1.0) == ("BUF", "1")
    assert favorite_and_line("NE", "SEA", 0.0) == ("", "PK")


def test_home_favorite():
    assert to_home_margin("NE", "SEA", "SEA -3.5") == 3.5
    assert format_spread("NE", "SEA", 3.5) == "SEA -3.5"
    assert explain_spread("DET", "BUF", 4.5) == "BUF is favored by 4.5 points."
    assert explain_spread("BUF", "HOU", -1.0) == "BUF is favored by 1 point."
    assert explain_spread("NE", "SEA", 0.0) == "Neither team is favored (pick'em)."


def test_away_favorite_and_lar():
    assert to_home_margin("SF", "LAR", "LAR -3.5") == 3.5
    assert to_home_margin("BUF", "HOU", "BUF -1") == -1.0


def test_numeric_spread():
    assert to_home_margin("NE", "SEA", "3.5") == -3.5
    assert to_home_margin("CHI", "CAR", "-2.5") == 2.5
    assert to_home_margin("NE", "SEA", "PK") == 0.0


def test_closer_and_ats():
    assert closer({"model": 3.5, "vegas": 7.0}, 7.0) == "vegas"
    assert closer({"model": 7.0, "vegas": 3.5}, 7.0) == "model"
    assert closer({"model": 3.5, "vegas": 3.5}, 7.0) == "tie"
    assert closer({"model": 3.5, "vegas": 7.0, "user:Brett": 6.5}, 7.0) == "vegas"
    assert ats(2.5, 3.5, 7.0) == "loss"
    assert ats(2.5, 3.5, 2.0) == "cover"
    assert ats(3.5, 3.5, 7.0) == "no_bet"
    assert ats(2.5, 3.5, 3.5) == "push"


def test_matchup_id():
    assert matchup_id(2026, 2, "SEA", "NE") == "2026_02_sea_ne"


def test_spread_text_prefers_signed_spread_line():
    row = {
        "away_team": "BAL",
        "home_team": "IND",
        "spread": "3.5",
        "spread_line": "-3.5",
    }
    assert ingest._spread_text(row) == "-3.5"
    assert to_home_margin("BAL", "IND", ingest._spread_text(row)) == 3.5


def test_grade_decision_cover_points():
    # GB -5.5 at home vs ATL: dog covers when home margin < 5.5
    assert grade_decision("cover", 5.5, 3.0) == "loss"
    assert grade_decision("points", 5.5, 3.0) == "win"
    assert grade_decision("cover", 5.5, 5.5) == "push"
    # PK: cover = home
    assert grade_decision("cover", 0.0, 7.0) == "win"
    assert grade_decision("points", 0.0, 7.0) == "loss"


def test_ingest_and_dups(tmp_path: Path):
    from app.schedule import apply_schedule_rows

    session = db.init(db.connect(tmp_path / "t.db"))
    path = db.ROOT / "data" / "picks" / "202601_model.csv"
    rows = ingest.parse_upload(path.name, path.read_bytes())
    apply_schedule_rows(
        session,
        [
            {
                "season": 2026,
                "week": 1,
                "gameday": "2026-09-09",
                "gametime": "20:20",
                "away_team": norm_team(r.get("away_team") or ""),
                "home_team": norm_team(r.get("home_team") or ""),
                "away_score": None,
                "home_score": None,
            }
            for r in rows
            if (r.get("away_team") or r.get("home_team"))
        ],
    )
    inserted, skipped = ingest.ingest_rows(
        session, rows, season=2026, week=1, source="model", model_version="preseason"
    )
    assert inserted == 16
    assert skipped == 0
    m = next(x for x in db.matchups_for(session, 2026, 1) if x.home_team == "SEA")
    assert m.id == "2026_01_sea_ne"
    assert m.away_team == "NE"
    assert any(p.decision == "cover" and p.source == "model" for p in m.picks)

    inserted2, skipped2 = ingest.ingest_rows(
        session, rows, season=2026, week=1, source="model", model_version="preseason"
    )
    assert inserted2 == 0
    assert skipped2 == 16

    ingest.ingest_rows(
        session,
        [{"away_team": "NE", "home_team": "SEA", "spread": "SEA -7"}],
        season=2026,
        week=1,
        source="vegas",
        bookmaker="DraftKings",
    )
    m = next(x for x in db.matchups_for(session, 2026, 1) if x.home_team == "SEA")
    vegas = [p for p in m.picks if p.source == "vegas"]
    assert len(vegas) == 1
    assert vegas[0].spread == 7.0
