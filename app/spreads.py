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
NUM_SPREAD_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*$")


def is_numeric_margin(text: str) -> bool:
    return bool(NUM_SPREAD_RE.match((text or "").strip()))


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
    raw = (spread_text or "").strip()
    if raw.upper() == "PK":
        return 0.0
    num = NUM_SPREAD_RE.match(raw)
    if num:
        # ponytail: bare numbers use the nflverse spread_line convention (negative = home favored)
        return -float(num.group(1))
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


def favorite_and_line(away: str, home: str, margin: float) -> tuple[str, str]:
    """Favorite team code and line for display (e.g. SEA, 3.5). PK → ('', 'PK')."""
    if abs(margin) < 1e-9:
        return "", "PK"
    fav = home if margin > 0 else away
    return fav, _trim_num(abs(margin))


def format_spread(away: str, home: str, margin: float | None) -> str:
    if margin is None:
        return ""
    if abs(margin) < 1e-9:
        return "PK"
    if margin > 0:
        return f"{home} -{_trim_num(margin)}"
    return f"{away} -{_trim_num(-margin)}"


def explain_spread(away: str, home: str, margin: float | None) -> str:
    if margin is None:
        return ""
    if abs(margin) < 1e-9:
        return "Neither team is favored (pick'em)."
    pts = abs(margin)
    word = "point" if pts == 1 else "points"
    fav = home if margin > 0 else away
    return f"{fav} is favored by {_trim_num(pts)} {word}."


def closer(margins: dict[str, float], actual: float) -> str:
    """Label of the spread closest to actual. 'tie' if two or more share the min error."""
    if not margins:
        return ""
    errors = {label: abs(m - actual) for label, m in margins.items()}
    best = min(errors.values())
    winners = [label for label, e in errors.items() if abs(e - best) < 1e-9]
    if len(winners) == 1:
        return winners[0]
    return "tie"


def ats(pick: float, vegas: float, actual: float) -> str:
    """Bet pick's side of the Vegas line. Same line = no_bet."""
    if abs(pick - vegas) < 1e-9:
        return "no_bet"
    if abs(actual - vegas) < 1e-9:
        return "push"
    bet_home = pick > vegas
    covered = actual > vegas if bet_home else actual < vegas
    return "cover" if covered else "loss"


DECISIONS = frozenset({"cover", "points"})


def norm_decision(text: str) -> str:
    d = (text or "").strip().lower()
    if d in DECISIONS:
        return d
    raise ValueError(f"decision must be cover or points, got {text!r}")


def format_decision(decision: str | None) -> str:
    if not decision:
        return ""
    d = decision.lower()
    if d == "cover":
        return "Cover"
    if d == "points":
        return "Points"
    return decision


def favorite_covers(vegas_margin: float, actual_margin: float) -> bool:
    """True when the favorite covers the Vegas spread."""
    if abs(vegas_margin) < 1e-9:
        return actual_margin > 0
    if vegas_margin > 0:
        return actual_margin > vegas_margin
    return actual_margin < vegas_margin


def actual_ats_decision(
    vegas_margin: float | None, actual_margin: float | None
) -> str:
    """Who won ATS in cover/points terms: cover, points, push, or "" if unknown."""
    if vegas_margin is None or actual_margin is None:
        return ""
    if abs(actual_margin - vegas_margin) < 1e-9:
        return "push"
    if abs(vegas_margin) < 1e-9:
        if actual_margin > 0:
            return "cover"
        if actual_margin < 0:
            return "points"
        return "push"
    return "cover" if favorite_covers(vegas_margin, actual_margin) else "points"


def format_ats_result(
    vegas_margin: float | None, actual_margin: float | None
) -> str:
    d = actual_ats_decision(vegas_margin, actual_margin)
    if not d:
        return ""
    if d == "push":
        return "Push"
    return format_decision(d)


def grade_decision(
    decision: str | None,
    vegas_margin: float | None,
    actual_margin: float | None,
) -> str:
    """cover = favorite ATS, points = underdog ATS. PK → cover=home, points=away."""
    if not decision or vegas_margin is None or actual_margin is None:
        return "pending"
    d = norm_decision(decision)
    if abs(actual_margin - vegas_margin) < 1e-9:
        return "push"
    if abs(vegas_margin) < 1e-9:
        if d == "cover":
            if actual_margin > 0:
                return "win"
            if actual_margin < 0:
                return "loss"
            return "push"
        if actual_margin < 0:
            return "win"
        if actual_margin > 0:
            return "loss"
        return "push"
    fav = favorite_covers(vegas_margin, actual_margin)
    if d == "cover":
        return "win" if fav else "loss"
    return "win" if not fav else "loss"


def format_grade(result: str) -> str:
    if result == "win":
        return "W"
    if result == "loss":
        return "L"
    if result == "push":
        return "P"
    return "—"
