"""Boards, scoreboard grading, and pick display."""

from __future__ import annotations

from app.models import Matchup, Pick
from app.odds import format_kickoff
from app.spreads import (
    explain_spread,
    format_ats_result,
    format_decision,
    format_grade,
    format_spread,
    grade_decision,
)


def actual_margin(m: Matchup) -> float | None:
    if m.home_score is None or m.away_score is None:
        return None
    return float(m.home_score) - float(m.away_score)


MODEL_SLOT = "model"


def pick_label(p: Pick) -> str:
    if p.source == "vegas":
        return f"vegas:{p.bookmaker or '?'}"
    if p.source == "model":
        return f"model:{MODEL_SLOT}"
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
            bucket, name = "model", MODEL_SLOT
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


def week_identities(matchups: list[Matchup]) -> tuple[bool, list[str]]:
    has_model = False
    users: set[str] = set()
    for m in matchups:
        for p in m.picks:
            if p.source == "model" and p.decision:
                has_model = True
            elif p.source == "user" and p.username and p.decision:
                users.add(p.username)
    return has_model, sorted(users)


def merge_scoreboard_users(found: list[str], defaults: tuple[str, ...]) -> list[str]:
    out = list(defaults)
    for u in found:
        if u not in out:
            out.append(u)
    return out


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
    usernames: list[str],
) -> dict:
    by_source = _latest_by_source(list(m.picks))
    vegas_pick = _fixed_vegas_pick(by_source, bookmaker)
    vegas_margin = vegas_pick.spread if vegas_pick and not vegas_pick.decision else None
    actual = actual_margin(m)
    played = m.away_score is not None and m.home_score is not None

    model_pick = by_source["model"].get(MODEL_SLOT)
    model_decision = format_decision(model_pick.decision) if model_pick and model_pick.decision else ""
    model_grade = format_grade(_grade_pick(model_pick, vegas_margin, actual))

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
        "ats_result": format_ats_result(vegas_margin, actual if played else None),
        "model": model_decision,
        "model_grade": model_grade,
        "users": users,
        "user_grades": user_grades,
    }


def scoreboard_board(
    matchups: list[Matchup],
    *,
    bookmaker: str,
    default_users: tuple[str, ...],
) -> dict:
    _, found_users = week_identities(matchups)
    usernames = merge_scoreboard_users(found_users, default_users)

    rows = [
        _matchup_row(m, bookmaker=bookmaker, usernames=usernames)
        for m in matchups
    ]
    records = tally_decision_records(matchups, bookmaker=bookmaker)
    record_cards = ordered_record_cards(records, usernames=usernames)
    return {
        "rows": rows,
        "usernames": usernames,
        "records": records,
        "record_cards": record_cards,
    }


def matchups_board(
    matchups: list[Matchup],
    *,
    bookmaker: str,
    usernames: tuple[str, ...],
) -> dict:
    data = scoreboard_board(
        matchups,
        bookmaker=bookmaker,
        default_users=usernames,
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
                "model": r["model"],
                "model_grade": r["model_grade"],
                "users": r["users"],
                "user_grades": r["user_grades"],
            }
        )
    return {
        "rows": rows,
        "usernames": data["usernames"],
    }


def pick_counts(rows: list[dict], *, usernames: tuple[str, ...] = ()) -> dict[str, int]:
    total = len(rows)
    user_counts = {
        name: sum(1 for r in rows if (r.get("users") or {}).get(name))
        for name in usernames
    }
    return {
        "vegas": sum(1 for r in rows if r.get("vegas")),
        "model": sum(1 for r in rows if r.get("model")),
        "users": user_counts,
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
            pick = by_source["model"].get(MODEL_SLOT)
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


def _record_card_title(label: str) -> str:
    if label.startswith("model:"):
        return "Model"
    if label.startswith("user:"):
        return label.split(":", 1)[1]
    return label


def ordered_record_cards(
    records: dict[str, dict[str, int]],
    *,
    usernames: list[str],
) -> list[dict]:
    """Model + user cards for scoreboard (always W-L-P + win %)."""
    cards: list[dict] = []
    label = f"model:{MODEL_SLOT}"
    cards.append(
        {
            "label": label,
            "title": _record_card_title(label),
            **enrich_record(records.get(label, _empty_record())),
        }
    )
    for name in usernames:
        label = f"user:{name}"
        cards.append(
            {
                "label": label,
                "title": _record_card_title(label),
                **enrich_record(records.get(label, _empty_record())),
            }
        )
    return cards


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
    usernames: tuple[str, ...],
) -> dict:
    """Season ATS records: model + each user, with per-week breakdown."""
    weeks = sorted({m.season_week for m in matchups})
    weekly: list[dict] = []
    cum_model = 0
    cum_users = {u: 0 for u in usernames}
    max_week_wins = 1
    for w in weeks:
        wm = [m for m in matchups if m.season_week == w]
        mr = record_for_identity(
            wm, bookmaker=bookmaker, source="model", name=MODEL_SLOT
        )
        user_rows = {
            u: enrich_record(
                record_for_identity(
                    wm, bookmaker=bookmaker, source="user", name=u
                )
            )
            for u in usernames
        }
        cum_model += mr["win"]
        for u in usernames:
            cum_users[u] += user_rows[u]["win"]
            max_week_wins = max(max_week_wins, user_rows[u]["win"])
        max_week_wins = max(max_week_wins, mr["win"])
        weekly.append(
            {
                "week": w,
                "model": enrich_record(mr),
                "users": user_rows,
                "cum_model": cum_model,
                "cum_users": dict(cum_users),
            }
        )

    model_total = enrich_record(
        record_for_identity(
            matchups,
            bookmaker=bookmaker,
            source="model",
            name=MODEL_SLOT,
        )
    )
    users_total = {
        u: enrich_record(
            record_for_identity(
                matchups,
                bookmaker=bookmaker,
                source="user",
                name=u,
            )
        )
        for u in usernames
    }
    chart = _cumulative_chart_multi(weekly, usernames)
    has_graded = model_total["settled"] > 0 or any(
        u["settled"] > 0 for u in users_total.values()
    )
    return {
        "model": model_total,
        "users": users_total,
        "usernames": list(usernames),
        "weekly": weekly,
        "max_week_wins": max_week_wins,
        "has_graded": has_graded,
        "chart_points": chart["points"],
        "chart_model_line": chart["model_line"],
        "chart_user_lines": chart["user_lines"],
    }


def _cumulative_chart_multi(weekly: list[dict], usernames: tuple[str, ...]) -> dict:
    if not weekly:
        return {"points": [], "model_line": "", "user_lines": {}}
    last = weekly[-1]
    max_y = last["cum_model"]
    for u in usernames:
        max_y = max(max_y, last["cum_users"].get(u, 0))
    max_y = max(max_y, 1)
    points: list[dict] = []
    n = len(weekly)
    user_lines: dict[str, list[str]] = {u: [] for u in usernames}
    model_pts: list[str] = []
    for i, row in enumerate(weekly):
        x = round(100.0 * i / max(n - 1, 1), 2)
        my = round(100.0 - 100.0 * row["cum_model"] / max_y, 2)
        model_pts.append(f"{x},{my}")
        pt: dict = {"week": row["week"], "x": x, "model_y": my}
        for u in usernames:
            uy = round(100.0 - 100.0 * row["cum_users"][u] / max_y, 2)
            user_lines[u].append(f"{x},{uy}")
            pt[f"{u}_y"] = uy
        points.append(pt)
    return {
        "points": points,
        "model_line": " ".join(model_pts),
        "user_lines": {u: " ".join(user_lines[u]) for u in usernames},
    }


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
