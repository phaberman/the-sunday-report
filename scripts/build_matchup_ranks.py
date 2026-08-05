"""Build historical matchup table with weekly PF/PA ranks (point-in-time)."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "features" / "matchups_pf_pa_ranks.csv"
SEASONS = list(range(2016, 2026))

FIELDS = [
    "season",
    "week",
    "game_id",
    "away_team",
    "home_team",
    "away_off_rank",
    "away_def_rank",
    "home_off_rank",
    "home_def_rank",
    "away_score",
    "home_score",
]


def dense_rank(values: dict[str, float], *, higher_is_better: bool) -> dict[str, int]:
    """Same value → same rank; next distinct value gets rank+1 (dense)."""
    ordered = sorted(
        values.items(),
        key=lambda kv: (-kv[1] if higher_is_better else kv[1], kv[0]),
    )
    ranks: dict[str, int] = {}
    rank = 0
    prev: float | None = None
    for team, val in ordered:
        if prev is None or val != prev:
            rank += 1
            prev = val
        ranks[team] = rank
    return ranks


def season_teams(games: list[dict]) -> set[str]:
    teams: set[str] = set()
    for g in games:
        teams.add(g["home_team"])
        teams.add(g["away_team"])
    return teams


def ranks_entering_week(prior_games: list[dict], teams: set[str]) -> dict[str, tuple[int, int]]:
    """Season-to-date PF/PA ranks using only games already played. Bye = carry totals."""
    pf: dict[str, float] = {t: 0.0 for t in teams}
    pa: dict[str, float] = {t: 0.0 for t in teams}
    for g in prior_games:
        home, away = g["home_team"], g["away_team"]
        hs, as_ = g["home_score"], g["away_score"]
        pf[home] += hs
        pa[home] += as_
        pf[away] += as_
        pa[away] += hs
    off = dense_rank(pf, higher_is_better=True)
    deff = dense_rank(pa, higher_is_better=False)
    return {t: (off[t], deff[t]) for t in teams}


def build_matchup_rows(games: list[dict]) -> list[dict]:
    """One row per completed REG game; ranks use only prior weeks in that season."""
    by_season: dict[int, list[dict]] = defaultdict(list)
    for g in games:
        by_season[g["season"]].append(g)

    rows: list[dict] = []
    for season in sorted(by_season):
        season_games = sorted(by_season[season], key=lambda g: (g["week"], g["game_id"]))
        teams = season_teams(season_games)
        weeks = sorted({g["week"] for g in season_games})
        for week in weeks:
            prior = [g for g in season_games if g["week"] < week]
            ranks = ranks_entering_week(prior, teams)
            for g in season_games:
                if g["week"] != week:
                    continue
                away, home = g["away_team"], g["home_team"]
                rows.append(
                    {
                        "season": season,
                        "week": week,
                        "game_id": g["game_id"],
                        "away_team": away,
                        "home_team": home,
                        "away_off_rank": ranks[away][0],
                        "away_def_rank": ranks[away][1],
                        "home_off_rank": ranks[home][0],
                        "home_def_rank": ranks[home][1],
                        "away_score": g["away_score"],
                        "home_score": g["home_score"],
                    }
                )
    return rows


def load_reg_games(seasons: list[int]) -> list[dict]:
    import nflreadpy as nfl

    df = nfl.load_schedules(seasons)
    df = df.filter(
        (df["game_type"] == "REG")
        & df["home_score"].is_not_null()
        & df["away_score"].is_not_null()
    )
    cols = ["season", "week", "game_id", "home_team", "away_team", "home_score", "away_score"]
    return df.select(cols).to_dicts()


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    games = load_reg_games(SEASONS)
    rows = build_matchup_rows(games)
    write_csv(rows, OUT_PATH)
    print(f"seasons={SEASONS[0]}-{SEASONS[-1]} games={len(rows)} -> {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
