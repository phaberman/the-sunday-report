"""Remove all model picks and Brett/Phillip user picks. Vegas lines stay."""

from __future__ import annotations

import sys

from app import db


def main() -> None:
    session = db.init(db.connect())
    info = db.wipe_model_and_user_uploads(session)
    print(
        f"model_picks_deleted={info['model_picks_deleted']} "
        f"user_picks_deleted={info['user_picks_deleted']} "
        f"orphan_matchups_deleted={info['orphan_matchups_deleted']}"
    )
    session.close()


if __name__ == "__main__":
    main()
    sys.exit(0)
