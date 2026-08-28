import csv
from pathlib import Path

ROOT = Path(__file__).parent
PICKS_CSV = ROOT / "data" / "picks" / "picks.csv"
SCHEDULE_CSV = ROOT / "data" / "schedules" / "2026_schedule.csv"


def load_csv(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def load_picks():
    rows = load_csv(PICKS_CSV)
    for r in rows:
        r["pred_margin"] = float(r["pred_margin"])
        r["home_win_prob"] = float(r["home_win_prob"])
        r["clf_win_prob"] = float(r["clf_win_prob"])
    return rows


def load_schedule():
    return load_csv(SCHEDULE_CSV)
