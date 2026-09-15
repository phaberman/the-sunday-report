from pathlib import Path

import db
import ingest
from spreads import ats, closer, explain_spread, format_spread, to_home_margin


def test_home_favorite():
    assert to_home_margin("NE", "SEA", "SEA -3.5") == 3.5
    assert format_spread("NE", "SEA", 3.5) == "SEA -3.5"
    assert explain_spread("DET", "BUF", 4.5) == "BUF is favored by 4.5 points."
    assert explain_spread("BUF", "HOU", -1.0) == "BUF is favored by 1 point."
    assert explain_spread("NE", "SEA", 0.0) == "Neither team is favored (pick'em)."


def test_away_favorite_and_lar():
    assert to_home_margin("SF", "LAR", "LAR -3.5") == 3.5
    assert to_home_margin("BUF", "HOU", "BUF -1") == -1.0


def test_closer_and_ats():
    assert closer(3.5, 7.0, 7.0) == "vegas"
    assert closer(7.0, 3.5, 7.0) == "model"
    assert closer(3.5, 3.5, 7.0) == "tie"
    # model SEA -2.5 (home 2.5), vegas SEA -3.5 (home 3.5) → bet away
    assert ats(2.5, 3.5, 7.0) == "loss"
    assert ats(2.5, 3.5, 2.0) == "cover"
    assert ats(3.5, 3.5, 7.0) == "no_bet"
    assert ats(2.5, 3.5, 3.5) == "push"


def test_ingest_week01(tmp_path: Path):
    conn = db.init(db.connect(tmp_path / "t.db"))
    n = ingest.seed_week01(conn)
    assert n == 16
    g = db.games_for(conn, 2026, 1)
    sea = next(r for r in g if r["home_team"] == "SEA")
    assert sea["away_team"] == "NE"
    assert sea["model_margin"] == 3.5
    lar = next(r for r in g if r["home_team"] == "LA")
    assert lar["model_margin"] == 3.5
    hou = next(r for r in g if r["home_team"] == "HOU")
    assert hou["model_margin"] == -1.0
    ingest.ingest_rows(
        conn,
        [{"away_team": "NE", "home_team": "SEA", "spread": "SEA -7"}],
        season=2026,
        week=1,
        kind="vegas",
    )
    sea = db.games_for(conn, 2026, 1)[0]
    sea = next(r for r in db.games_for(conn, 2026, 1) if r["home_team"] == "SEA")
    assert sea["vegas_margin"] == 7.0
    assert sea["model_margin"] == 3.5
