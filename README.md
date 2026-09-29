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
- **picks** — linked by `matchup_id`: `source` (`vegas` | `user` | `model`). Vegas stores home-margin `spread`. Model/user store `decision` (`cover` = favorite ATS, `points` = underdog). Optional `username` / `model_version`.

## Upload

- **Vegas:** CSV/Excel `away_team, home_team, spread` (or enter lines in UI).
- **Model / user:** `away_team, home_team, decision` (`cover` or `points`).

Grading uses the **Vegas line in the DB** vs final scores. **Scoreboard** is the home page.

Backfill decisions from `data/picks/2026*_model.csv` and `*_brett.csv`:

```bash
python scripts/ingest_decisions_once.py
```

## Tests

```bash
python -m pytest -q
```
