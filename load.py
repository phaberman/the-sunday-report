import csv
from pathlib import Path

ROOT = Path(__file__).parent
PICKS_CSV = ROOT / "data" / "picks" / "2026-wk01-preseason_model.csv"
SCHEDULE_CSV = ROOT / "data" / "schedules" / "2026_schedule.csv"


def load_csv(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def load_picks():
    return load_csv(PICKS_CSV)


def load_schedule():
    return load_csv(SCHEDULE_CSV)
