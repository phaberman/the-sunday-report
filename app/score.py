"""Boards, scoreboard grading, and pick display."""

from __future__ import annotations

from app.models import Matchup, Pick
from app.odds import format_kickoff
from app.spreads import (
    explain_spread,
    format_decision,
    format_grade,
    format_spread,
    grade_decision,
)


def actual_margin(m: Matchup) -> float | None:
    if m.home_score is None or m.away_score is None:
        return None
    return float(m.home_score) - float(m.away_score)


def pick_label(p: Pick) -> str:
    if p.source == "vegas":
        return f"vegas:{p.bookmaker or '?'}"
    if p.source == "model":
        return f"model:{p.model_version or '?'}"
    if p.source == "user":
        return f"user:{p.username or '?'}"
    return p.source


def primary_vegas(by_label: dict[str, Pick]) -> Pick | None:
    if "vegas:DraftKings" in by_label:
        return by_label["vegas:DraftKings"]
    for label, pick in by_label.items():
        if label.startswith("vegas:"):
            return pick
    return None


def latest_picks(picks: list[Pick]) -> dict[str, Pick]:
    best: dict[str, Pick] = {}
    for p in picks:
        label = pick_label(p)
        prev = best.get(label)
        if prev is None or (p.created_at, p.id) > (prev.created_at, prev.id):
            best[label] = p
    return best


def _latest_by_source(picks: list[Pick]) -> dict[str, dict[str, Pick]]:
    out: dict[str, dict[str, Pick]] = {"vegas": {}, "model": {}, "user": {}}
    for p in picks:
        if p.source == "vegas":
            bucket, name = "vegas", p.bookmaker or "?"
        elif p.source == "model":
            bucket, name = "model", p.model_version or "?"
        elif p.source == "user":
            bucket, name = "user", p.username or "?"
        else:
            continue
        prev = out[bucket].get(name)
        if prev is None or (p.created_at, p.id) > (prev.created_at, prev.id):
            out[bucket][name] = p
    return out


def _fixed_vegas_pick(by_source: dict[str, dict[str, Pick]], bookmaker: str) -> Pick | None:
    pick = by_source["vegas"].get(bookmaker)
    if pick is not None:
        return pick
    by_label = {pick_label(p): p for p in by_source["vegas"].values()}
    return primary_vegas(by_label)


def week_identities(matchups: list[Matchup]) -> tuple[list[str], list[str]]:
    models: set[str] = set()
    users: set[str] = set()
    for m in matchups:
        for p in m.picks:
            if p.source == "model" and p.model_version and p.decision:
                models.add(p.model_version)
            elif p.source == "user" and p.username and p.decision:
                users.add(p.username)
    return sorted(models), sorted(users)


def _grade_pick(
    pick: Pick | None, vegas_margin: float | None, actual: float | None
) -> str:
    if pick is None or not pick.decision:
        return "pending"
    return grade_decision(pick.decision, vegas_margin, actual)


def _matchup_row(
    m: Matchup,
    *,
    bookmaker: str,
    model_versions: list[str],
    usernames: list[str],
) -> dict:
    by_source = _latest_by_source(list(m.picks))
    vegas_pick = _fixed_vegas_pick(by_source, bookmaker)
    vegas_margin = vegas_pick.spread if vegas_pick and not vegas_pick.decision else None
    actual = actual_margin(m)
    played = m.away_score is not None and m.home_score is not None

    models: dict[str, str] = {}
    model_grades: dict[str, str] = {}
    for ver in model_versions:
        pick = by_source["model"].get(ver)
        models[ver] = format_decision(pick.decision) if pick and pick.decision else ""
        model_grades[ver] = format_grade(_grade_pick(pick, vegas_margin, actual))

    users: dict[str, str] = {}
    user_grades: dict[str, str] = {}
    for name in usernames:
        pick = by_source["user"].get(name)
        users[name] = format_decision(pick.decision) if pick and pick.decision else ""
        user_grades[name] = format_grade(_grade_pick(pick, vegas_margin, actual))

    return {
        "matchup": f"{m.away_team} @ {m.home_team}",
        "kickoff": format_kickoff(m.kickoff),
        "away_points": m.away_score if played else None,
        "home_points": m.home_score if played else None,
        "vegas": format_spread(m.away_team, m.home_team, vegas_margin),
        "models": models,
        "model_grades": model_grades,
        "users": users,
        "user_grades": user_grades,
    }


def scoreboard_board(
    matchups: list[Matchup],
    *,
    bookmaker: str,
    default_model: str,
    default_user: str,
) -> dict:
    model_versions, usernames = week_identities(matchups)
    if not model_versions:
        model_versions = [default_model]
    if not usernames:
        usernames = [default_user]

    rows = [
        _matchup_row(
            m,
            bookmaker=bookmaker,
            model_versions=model_versions,
            usernames=usernames,
        )
        for m in matchups
    ]
    records = tally_decision_records(matchups, bookmaker=bookmaker)
    return {
        "rows": rows,
        "model_versions": model_versions,
        "usernames": usernames,
        "records": records,
    }


def matchups_board(
    matchups: list[Matchup],
    *,
    bookmaker: str,
    model_version: str,
    username: str,
) -> dict:
    data = scoreboard_board(
        matchups,
        bookmaker=bookmaker,
        default_model=model_version,
        default_user=username,
    )
    rows = []
    for r in data["rows"]:
        rows.append(
            {
                "matchup": r["matchup"],
                "kickoff": r["kickoff"],
                "away_points": r["away_points"],
                "home_points": r["home_points"],
                "vegas": r["vegas"],
                "model": r["models"].get(model_version, ""),
                "model_grade": r["model_grades"].get(model_version, "—"),
                "user": r["users"].get(username, ""),
                "user_grade": r["user_grades"].get(username, "—"),
            }
        )
    return {"rows": rows, "user_col": username, "model_version": model_version}


def pick_counts(rows: list[dict]) -> dict[str, int]:
    total = len(rows)
    return {
        "vegas": sum(1 for r in rows if r.get("vegas")),
        "model": sum(1 for r in rows if r.get("model")),
        "user": sum(1 for r in rows if r.get("user")),
        "total": total,
    }


def _empty_record() -> dict[str, int]:
    return {"win": 0, "loss": 0, "push": 0, "pending": 0}


def record_for_identity(
    matchups: list[Matchup],
    *,
    bookmaker: str,
    source: str,
    name: str,
) -> dict[str, int]:
    """W-L-P for one model version or user vs the configured Vegas book."""
    bucket = _empty_record()
    for m in matchups:
        by_source = _latest_by_source(list(m.picks))
        vegas_pick = _fixed_vegas_pick(by_source, bookmaker)
        vegas_margin = vegas_pick.spread if vegas_pick and not vegas_pick.decision else None
        actual = actual_margin(m)
        if source == "model":
            pick = by_source["model"].get(name)
        elif source == "user":
            pick = by_source["user"].get(name)
        else:
            continue
        if pick is None or not pick.decision:
            continue
        g = grade_decision(pick.decision, vegas_margin, actual)
        if g in bucket:
            bucket[g] += 1
    return bucket


def enrich_record(r: dict[str, int]) -> dict:
    settled = r["win"] + r["loss"] + r["push"]
    win_pct = round(100.0 * r["win"] / settled, 1) if settled else None
    bar = (
        {
            "win": round(100.0 * r["win"] / settled, 2),
            "loss": round(100.0 * r["loss"] / settled, 2),
            "push": round(100.0 * r["push"] / settled, 2),
        }
        if settled
        else {"win": 0.0, "loss": 0.0, "push": 0.0}
    )
    return {
        **r,
        "wlp": f'{r["win"]}-{r["loss"]}-{r["push"]}',
        "settled": settled,
        "win_pct": win_pct,
        "bar": bar,
    }


def season_compare(
    matchups: list[Matchup],
    *,
    bookmaker: str,
    model_version: str,
    username: str,
) -> dict:
    """Season Model vs user ATS records and per-week breakdown."""
    weeks = sorted({m.season_week for m in matchups})
    weekly: list[dict] = []
    cum_model = 0
    cum_user = 0
    max_week_wins = 1
    for w in weeks:
        wm = [m for m in matchups if m.season_week == w]
        mr = record_for_identity(
            wm, bookmaker=bookmaker, source="model", name=model_version
        )
        ur = record_for_identity(
            wm, bookmaker=bookmaker, source="user", name=username
        )
        cum_model += mr["win"]
        cum_user += ur["win"]
        max_week_wins = max(max_week_wins, mr["win"], ur["win"])
        weekly.append(
            {
                "week": w,
                "model": enrich_record(mr),
                "user": enrich_record(ur),
                "cum_model": cum_model,
                "cum_user": cum_user,
            }
        )

    model_total = enrich_record(
        record_for_identity(
            matchups,
            bookmaker=bookmaker,
            source="model",
            name=model_version,
        )
    )
    user_total = enrich_record(
        record_for_identity(
            matchups,
            bookmaker=bookmaker,
            source="user",
            name=username,
        )
    )
    leader = None
    if model_total["settled"] and user_total["settled"]:
        if model_total["win"] > user_total["win"]:
            leader = "model"
        elif user_total["win"] > model_total["win"]:
            leader = "user"

    chart = _cumulative_chart(weekly)
    return {
        "model": model_total,
        "user": user_total,
        "model_version": model_version,
        "username": username,
        "weekly": weekly,
        "max_week_wins": max_week_wins,
        "leader": leader,
        "chart_points": chart,
        "chart_model_line": " ".join(f"{p['x']},{p['model_y']}" for p in chart),
        "chart_user_line": " ".join(f"{p['x']},{p['user_y']}" for p in chart),
    }


def _cumulative_chart(weekly: list[dict]) -> list[dict]:
    if not weekly:
        return []
    last = weekly[-1]
    max_y = max(last["cum_model"], last["cum_user"], 1)
    out: list[dict] = []
    n = len(weekly)
    for i, row in enumerate(weekly):
        x = round(100.0 * i / max(n - 1, 1), 2)
        out.append(
            {
                "week": row["week"],
                "x": x,
                "model_y": round(100.0 - 100.0 * row["cum_model"] / max_y, 2),
                "user_y": round(100.0 - 100.0 * row["cum_user"] / max_y, 2),
            }
        )
    return out


def tally_decision_records(
    matchups: list[Matchup], *, bookmaker: str
) -> dict[str, dict[str, int]]:
    """Per identity W-L-P across matchups."""
    out: dict[str, dict[str, int]] = {}
    for m in matchups:
        by_source = _latest_by_source(list(m.picks))
        vegas_pick = _fixed_vegas_pick(by_source, bookmaker)
        vegas_margin = vegas_pick.spread if vegas_pick and not vegas_pick.decision else None
        actual = actual_margin(m)
        for pick in list(by_source["model"].values()) + list(by_source["user"].values()):
            if not pick.decision:
                continue
            label = pick_label(pick)
            bucket = out.setdefault(label, {"win": 0, "loss": 0, "push": 0, "pending": 0})
            g = grade_decision(pick.decision, vegas_margin, actual)
            if g in bucket:
                bucket[g] += 1
    return out


def view_matchup(m: Matchup) -> dict:
    """Spreads page row (Vegas line + actual)."""
    by_label = latest_picks(list(m.picks))
    vegas_pick = primary_vegas(by_label)
    vegas_margin = vegas_pick.spread if vegas_pick else None
    actual = actual_margin(m)

    return {
        "id": m.id,
        "away_team": m.away_team,
        "home_team": m.home_team,
        "game": f"{m.away_team} @ {m.home_team}",
        "kickoff": format_kickoff(m.kickoff),
        "index": m.id,
        "vegas": format_spread(m.away_team, m.home_team, vegas_margin),
        "vegas_hint": explain_spread(m.away_team, m.home_team, vegas_margin),
        "actual": format_spread(m.away_team, m.home_team, actual),
        "home_score": m.home_score,
        "away_score": m.away_score,
        "date": "",
    }

