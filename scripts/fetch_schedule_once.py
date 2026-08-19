"""2026 NFL Schedule Fetch and Conversion to CSV"""

from pathlib import Path
import nflreadpy as nfl
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "schedules" / "2026_schedule.csv"

def main() -> None:
    df = nfl.load_schedules(2026)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(OUT)
    print(f"games={df.height} -> {OUT.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
