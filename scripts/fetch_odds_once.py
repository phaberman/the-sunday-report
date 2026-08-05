"""One-shot NFL odds pull → timestamped CSV. No schedule."""

from __future__ import annotations

import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "odds" / "snapshots"
API_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds/"

FIELDS = [
    "pulled_at",
    "id",
    "commence_time",
    "home_team",
    "away_team",
    "bookmaker",
    "market",
    "outcome",
    "price",
    "point",
]


def load_dotenv(path: Path) -> None:
    # ponytail: tiny .env reader; ceiling = no quotes/export syntax. Use python-dotenv if needed.
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def flatten(games: list[dict], pulled_at: str) -> list[dict]:
    rows: list[dict] = []
    for game in games:
        for book in game.get("bookmakers") or []:
            for market in book.get("markets") or []:
                for outcome in market.get("outcomes") or []:
                    rows.append(
                        {
                            "pulled_at": pulled_at,
                            "id": game.get("id"),
                            "commence_time": game.get("commence_time"),
                            "home_team": game.get("home_team"),
                            "away_team": game.get("away_team"),
                            "bookmaker": book.get("key"),
                            "market": market.get("key"),
                            "outcome": outcome.get("name"),
                            "price": outcome.get("price"),
                            "point": outcome.get("point"),
                        }
                    )
    return rows


def fetch(api_key: str) -> tuple[list[dict], dict[str, str]]:
    params = urllib.parse.urlencode(
        {
            "apiKey": api_key,
            "regions": "us",
            "markets": "spreads",
            "oddsFormat": "american",
        }
    )
    req = urllib.request.Request(f"{API_URL}?{params}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise SystemExit(f"API error {e.code}: {detail}") from e
    if not isinstance(body, list):
        raise SystemExit(f"Unexpected response: {body!r}")
    return body, headers


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("ODDS_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "Missing ODDS_API_KEY. Copy .env.example → .env and paste your key."
        )

    pulled_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    games, headers = fetch(api_key)
    rows = flatten(games, pulled_at)

    stamp = pulled_at.replace(":", "-")
    out = OUT_DIR / f"{stamp}.csv"
    write_csv(rows, out)

    remaining = headers.get("x-requests-remaining", "?")
    used = headers.get("x-requests-used", "?")
    print(f"games={len(games)} rows={len(rows)} -> {out.relative_to(ROOT)}")
    print(f"quota used={used} remaining={remaining}")


if __name__ == "__main__":
    main()
    sys.exit(0)
