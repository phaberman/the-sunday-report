"""Spread strings ↔ home-minus-away margin. Team code aliases."""

from __future__ import annotations

import re

TEAM_ALIAS = {
    "LAR": "LA",
    "WSH": "WAS",
    "JAC": "JAX",
    "GNB": "GB",
    "KAN": "KC",
    "NWE": "NE",
    "NOR": "NO",
    "SFO": "SF",
    "TAM": "TB",
    "SD": "LAC",
    "OAK": "LV",
}

SPREAD_RE = re.compile(
    r"^\s*([A-Z]{2,3})\s*([+-]?\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)


def norm_team(code: str) -> str:
    c = (code or "").strip().upper()
    return TEAM_ALIAS.get(c, c)


def _trim_num(n: float) -> str:
    if n == int(n):
        return str(int(n))
    return str(n)


def parse_spread_cell(text: str) -> tuple[str, float] | None:
    """'SEA -3.5' → (SEA, -3.5) favorite-centric point. PK → None."""
    raw = (text or "").strip()
    if not raw or raw.upper() == "PK":
        return None
    m = SPREAD_RE.match(raw)
    if not m:
        raise ValueError(f"bad spread: {text!r}")
    return norm_team(m.group(1)), float(m.group(2))


def to_home_margin(away: str, home: str, spread_text: str) -> float:
    away, home = norm_team(away), norm_team(home)
    parsed = parse_spread_cell(spread_text)
    if parsed is None:
        return 0.0
    team, point = parsed
    # point is signed for that team (SEA -3.5 → -3.5). Home margin = -away_point if team is away.
    if team == home:
        return -point
    if team == away:
        return point
    raise ValueError(f"spread team {team} not in {away}@{home}")


def format_spread(away: str, home: str, margin: float | None) -> str:
    if margin is None:
        return ""
    if abs(margin) < 1e-9:
        return "PK"
    if margin > 0:
        return f"{home} -{_trim_num(margin)}"
    return f"{away} -{_trim_num(-margin)}"


def closer(model: float, vegas: float, actual: float) -> str:
    me, ve = abs(model - actual), abs(vegas - actual)
    if me < ve:
        return "model"
    if ve < me:
        return "vegas"
    return "tie"


def ats(model: float, vegas: float, actual: float) -> str:
    """Bet model's side of the Vegas line. Same line = no_bet."""
    if abs(model - vegas) < 1e-9:
        return "no_bet"
    if abs(actual - vegas) < 1e-9:
        return "push"
    bet_home = model > vegas
    covered = actual > vegas if bet_home else actual < vegas
    return "cover" if covered else "loss"
