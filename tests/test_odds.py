from io import BytesIO

import db
import ingest
from odds import apply_dk_games, dk_home_point, export_week_xlsx, team_code, week_row
from score import view_game


def _sched():
    return [
        {
            "season": 2026,
            "week": 1,
            "gameday": "2026-09-09",
            "away_team": "NE",
            "home_team": "SEA",
        },
        {
            "season": 2026,
            "week": 2,
            "gameday": "2026-09-17",
            "away_team": "DET",
            "home_team": "BUF",
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
    n = apply_dk_games(conn, games)
    assert n == 1
    row = next(r for r in db.games_for(conn, 2026, 2) if r["home_team"] == "BUF")
    assert row["vegas_margin"] == 3.0
    xlsx = export_week_xlsx([view_game(row)])
    assert xlsx[:2] == b"PK"  # zip/xlsx
    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(xlsx))
    assert wb.active["C2"].value == "BUF -3"
