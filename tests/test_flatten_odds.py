from scripts.fetch_odds_once import flatten


def test_flatten_spreads():
    games = [
        {
            "id": "g1",
            "commence_time": "2026-09-10T00:20:00Z",
            "home_team": "Kansas City Chiefs",
            "away_team": "Baltimore Ravens",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "markets": [
                        {
                            "key": "spreads",
                            "outcomes": [
                                {"name": "Kansas City Chiefs", "price": -110, "point": -3.5},
                                {"name": "Baltimore Ravens", "price": -110, "point": 3.5},
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    rows = flatten(games, "2026-08-05T08:00:00Z")
    assert len(rows) == 2
    assert rows[0]["bookmaker"] == "draftkings"
    assert rows[0]["market"] == "spreads"
    assert rows[0]["point"] == -3.5
