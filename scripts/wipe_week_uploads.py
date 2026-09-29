"""Remove all picks for a season week (+ orphan matchups). Schedule rows stay."""

from __future__ import annotations

import argparse
import sys

from app import db


def main() -> None:
    p = argparse.ArgumentParser(description="Wipe uploaded picks for one NFL week")
    p.add_argument("season", type=int, help="e.g. 2026")
    p.add_argument("week", type=int, help="e.g. 3")
    args = p.parse_args()
    session = db.init(db.connect())
    info = db.wipe_week_uploads(session, args.season, args.week)
    print(
        f"season={args.season} week={args.week} "
        f"picks_deleted={info['picks_deleted']} "
        f"orphan_matchups_deleted={info['orphan_matchups_deleted']}"
    )
    session.close()


if __name__ == "__main__":
    main()
    sys.exit(0)
