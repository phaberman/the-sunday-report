"""Attach closer / ATS to game rows for templates."""

from __future__ import annotations

from spreads import ats, closer, explain_spread, format_spread
from odds import format_kickoff


def actual_margin(row) -> float | None:
    hs, aws = row["home_score"], row["away_score"]
    if hs is None or aws is None:
        return None
    return float(hs) - float(aws)


def game_index(row) -> str:
    # nflverse-style: year_week_away_home (DET @ BUF → 2026_02_det_buf)
    return (
        f"{row['season']}_{int(row['week']):02d}_"
        f"{row['away_team'].lower()}_{row['home_team'].lower()}"
    )


def view_game(row) -> dict:
    actual = actual_margin(row)
    model, vegas = row["model_margin"], row["vegas_margin"]
    kickoff = format_kickoff(row["kickoff"] if "kickoff" in row.keys() else None)
    out = {
        "away_team": row["away_team"],
        "home_team": row["home_team"],
        "game": f"{row['away_team']} @ {row['home_team']}",
        "model": format_spread(row["away_team"], row["home_team"], model),
        "vegas": format_spread(row["away_team"], row["home_team"], vegas),
        "vegas_hint": explain_spread(row["away_team"], row["home_team"], vegas),
        "actual": format_spread(row["away_team"], row["home_team"], actual),
        "closer": "",
        "ats": "",
        "home_score": row["home_score"],
        "away_score": row["away_score"],
        "kickoff": kickoff,
        "index": game_index(row),
    }
    if actual is not None and model is not None and vegas is not None:
        out["closer"] = closer(model, vegas, actual)
        out["ats"] = ats(model, vegas, actual)
    return out


def tally(rows: list[dict], key: str, values: tuple[str, ...]) -> dict[str, int]:
    counts = {v: 0 for v in values}
    for r in rows:
        v = r.get(key) or ""
        if v in counts:
            counts[v] += 1
    return counts
