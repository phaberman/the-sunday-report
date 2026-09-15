from io import BytesIO

import db
import ingest
from datetime import date

from odds import (
    apply_dk_games,
    current_week,
    dk_home_point,
    export_week_xlsx,
    format_kickoff,
    past_weeks,
    team_code,
    week_row,
)
from score import view_game


def _sched():
    return [
        {
            "season": 2026,
            "week": 1,
            "gameday": "2026-09-14",
            "away_team": "DEN",
            "home_team": "KC",
        },
        {
            "season": 2026,
            "week": 2,
            "gameday": "2026-09-21",
            "away_team": "DET",
            "home_team": "BUF",
        },
        {
            "season": 2026,
            "week": 3,
            "gameday": "2026-09-24",
            "away_team": "ATL",
            "home_team": "GB",
        },
    ]


def test_team_code_and_home_point():
    assert team_code("Los Angeles Rams") == "LA"
    game = {
        "home_team": "Buffalo Bills",
        "away_team": "Detroit Lions",
        "bookmakers": [
            {
                "key": "draftkings",
                "markets": [
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": "Buffalo Bills", "point": -3.0},
                            {"name": "Detroit Lions", "point": 3.0},
                        ],
                    }
                ],
            }
        ],
    }
    assert dk_home_point(game) == -3.0


def test_week_row_thursday_utc_next_day():
    hit = week_row(_sched(), "DET", "BUF", "2026-09-18T00:15:00Z")
    assert hit["week"] == 2
    assert format_kickoff("2026-09-18T00:15:00Z") == "2026-09-18 08:15"


def test_current_week_skips_finished_and_future():
    s = _sched()
    assert current_week(s, today=date(2026, 9, 13)) == (2026, 1)
    assert current_week(s, today=date(2026, 9, 15)) == (2026, 2)
    assert current_week(s, today=date(2026, 9, 22)) == (2026, 3)
    assert past_weeks(s, today=date(2026, 9, 13)) == []
    assert past_weeks(s, today=date(2026, 9, 15)) == [(2026, 1)]
    assert past_weeks(s, today=date(2026, 9, 22)) == [(2026, 1), (2026, 2)]


def test_apply_dk_and_export(tmp_path):
    conn = db.init(db.connect(tmp_path / "t.db"))
    ingest.ensure_schedule(conn)
    games = [
        {
            "commence_time": "2026-09-18T00:15:00Z",
            "home_team": "Buffalo Bills",
            "away_team": "Detroit Lions",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "markets": [
                        {
                            "key": "spreads",
                            "outcomes": [
                                {"name": "Buffalo Bills", "point": -3.0},
                                {"name": "Detroit Lions", "point": 3.0},
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    n = apply_dk_games(conn, games, only=(2026, 2))
    assert n == 1
    row = next(r for r in db.games_for(conn, 2026, 2) if r["home_team"] == "BUF")
    assert row["vegas_margin"] == 3.0
    assert row["kickoff"] == "2026-09-18T00:15:00Z"
    w2 = db.games_for(conn, 2026, 2)
    assert w2[0]["home_team"] == "BUF"
    xlsx = export_week_xlsx([view_game(row)])
    assert xlsx[:2] == b"PK"  # zip/xlsx
    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(xlsx))
    ws = wb.active
    assert [c.value for c in ws[1]] == [
        "Index",
        "Kickoff",
        "Matchup",
        "Home Team",
        "Away Team",
        "Spread",
    ]
    assert ws["A2"].value == "2026_02_det_buf"
    assert ws["B2"].value == "2026-09-18 08:15"
    assert ws["C2"].value == "DET @ BUF"
    assert ws["D2"].value == "BUF"
    assert ws["E2"].value == "DET"
    assert ws["F2"].value == "BUF -3"
