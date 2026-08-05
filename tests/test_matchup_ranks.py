from scripts.build_matchup_ranks import build_matchup_rows, dense_rank, ranks_entering_week


def test_dense_rank_ties():
    assert dense_rank({"A": 10, "B": 0}, higher_is_better=True) == {"A": 1, "B": 2}
    assert dense_rank({"A": 0, "B": 10}, higher_is_better=False) == {"A": 1, "B": 2}
    assert dense_rank({"A": 5, "B": 5, "C": 1}, higher_is_better=True) == {
        "A": 1,
        "B": 1,
        "C": 2,
    }


def test_week1_tied_then_week2_from_results():
    # User's 2-team example: A scores 10, gives up 0 in week 1.
    games = [
        {
            "season": 2024,
            "week": 1,
            "game_id": "g1",
            "home_team": "A",
            "away_team": "B",
            "home_score": 10,
            "away_score": 0,
        },
        {
            "season": 2024,
            "week": 2,
            "game_id": "g2",
            "home_team": "B",
            "away_team": "A",
            "home_score": 3,
            "away_score": 7,
        },
    ]
    rows = build_matchup_rows(games)
    w1 = rows[0]
    assert w1["week"] == 1
    assert w1["home_off_rank"] == w1["away_off_rank"] == 1
    assert w1["home_def_rank"] == w1["away_def_rank"] == 1

    w2 = rows[1]
    assert w2["week"] == 2
    # A: PF=10 PA=0 → off 1, def 1; B: PF=0 PA=10 → off 2, def 2
    assert w2["away_team"] == "A"
    assert w2["away_off_rank"] == 1 and w2["away_def_rank"] == 1
    assert w2["home_off_rank"] == 2 and w2["home_def_rank"] == 2


def test_bye_carries_totals():
    teams = {"A", "B", "C"}
    prior = [
        {
            "home_team": "A",
            "away_team": "B",
            "home_score": 20,
            "away_score": 10,
        }
    ]
    # C on bye — still ranked from 0 PF / 0 PA vs league
    ranks = ranks_entering_week(prior, teams)
    assert ranks["A"] == (1, 2)  # PF 20 best; PA 10 mid
    assert ranks["C"][0] == 3  # 0 PF worst offense
    assert ranks["B"][0] == 2
