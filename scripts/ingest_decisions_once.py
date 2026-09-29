"""Backfill model/Brett decisions from data/picks/2026{week}_{model|brett}.csv."""

from __future__ import annotations

import sys

from app import db, ingest


def main() -> None:
    session = db.init(db.connect())
    totals = ingest.ingest_decisions_from_dir(session, season=2026)
    print(
        f"model_inserted={totals['model']} user_inserted={totals['user']} "
        f"skipped_dups={totals['skipped']}"
    )
    session.close()


if __name__ == "__main__":
    main()
    sys.exit(0)
