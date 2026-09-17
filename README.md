# The Sunday Report

Probabilistic NFL game forecasts, published before kickoff and frozen.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

Layout:

- `app/` — FastAPI app (`main.py`, `routers/`, Jinja templates, static)
- `data/` — SQLite file (gitignored), schedule, optional pick CSVs for re-upload
- `scripts/` — one-shot fetches, not the web process

First launch creates `data/sunday.db`, loads the schedule into `matchups`, and creates empty `picks`. Legacy `games` / `vegas_spreads` tables are dropped on startup.

## Data model

- **matchups** — one row per game (`id` = `2026_02_sea_ne`, kickoff, scores)
- **picks** — opinions linked by `matchup_id`: numeric home-margin `spread`, `source` (`vegas` | `user` | `model`), optional `username` / `model_version`, `created_at`

## Upload

`/upload` accepts CSV or Excel (`away_team, home_team, spread`). Rows go straight into SQLite (no file copy). Exact duplicates are skipped.

## Tests

```bash
python -m pytest -q
```
