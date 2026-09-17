"""Attach closer / ATS to matchup + picks for templates."""

from __future__ import annotations

from app.models import Matchup, Pick
from app.odds import format_kickoff
from app.spreads import ats, closer, explain_spread, format_spread


def actual_margin(m: Matchup) -> float | None:
    if m.home_score is None or m.away_score is None:
        return None
    return float(m.home_score) - float(m.away_score)


def pick_label(p: Pick) -> str:
    if p.source == "vegas":
        return "vegas"
    if p.source == "model":
        return f"model:{p.model_version or '?'}"
    if p.source == "user":
        return f"user:{p.username or '?'}"
    return p.source


def latest_picks(picks: list[Pick]) -> dict[str, Pick]:
    """Latest pick per label (by created_at, then id)."""
    best: dict[str, Pick] = {}
    for p in picks:
        label = pick_label(p)
        prev = best.get(label)
        if prev is None or (p.created_at, p.id) > (prev.created_at, prev.id):
            best[label] = p
    return best


def view_matchup(m: Matchup) -> dict:
    actual = actual_margin(m)
    by_label = latest_picks(list(m.picks))
    vegas_pick = by_label.get("vegas")
    vegas_margin = vegas_pick.spread if vegas_pick else None

    spreads = {
        label: format_spread(m.away_team, m.home_team, p.spread)
        for label, p in sorted(by_label.items())
    }
    margins = {label: p.spread for label, p in by_label.items()}

    out: dict = {
        "id": m.id,
        "away_team": m.away_team,
        "home_team": m.home_team,
        "game": f"{m.away_team} @ {m.home_team}",
        "kickoff": format_kickoff(m.kickoff),
        "index": m.id,
        "vegas": format_spread(m.away_team, m.home_team, vegas_margin),
        "vegas_hint": explain_spread(m.away_team, m.home_team, vegas_margin),
        "spreads": spreads,
        "labels": list(spreads.keys()),
        "actual": format_spread(m.away_team, m.home_team, actual),
        "home_score": m.home_score,
        "away_score": m.away_score,
        "closer": "",
        "ats": {},
    }

    if actual is not None and len(margins) >= 1:
        out["closer"] = closer(margins, actual)

    if vegas_margin is not None and actual is not None:
        ats_map = {}
        for label, margin in margins.items():
            if label == "vegas":
                continue
            ats_map[label] = ats(margin, vegas_margin, actual)
        out["ats"] = ats_map

    return out


def tally(rows: list[dict], key: str, values: tuple[str, ...]) -> dict[str, int]:
    counts = {v: 0 for v in values}
    for r in rows:
        v = r.get(key) or ""
        if v in counts:
            counts[v] += 1
    return counts


def tally_closer(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        c = r.get("closer") or ""
        if not c or c == "tie":
            if c == "tie":
                counts["tie"] = counts.get("tie", 0) + 1
            continue
        counts[c] = counts.get(c, 0) + 1
    return counts


def tally_ats(rows: list[dict]) -> dict[str, dict[str, int]]:
    """Per-label ATS totals across games."""
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        for label, result in (r.get("ats") or {}).items():
            bucket = out.setdefault(
                label, {"cover": 0, "loss": 0, "push": 0, "no_bet": 0}
            )
            if result in bucket:
                bucket[result] += 1
    return out
