# The Sunday Report

Probabilistic NFL game forecasts, published before kickoff and frozen.

## Setup

`.python-version` is `3.12` so Render installs a real Python. Dependencies live in the `the-sunday-report-env` virtualenv. In each terminal where you run the app, tests, or scripts:

```bash
pyenv shell the-sunday-report-env
```

Use `pyenv shell`, not `pyenv local`. `pyenv local` writes the env name into `.python-version` and breaks the Render build.

Or use a venv instead: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. `/` redirects to `/scoreboard`.

Copy `.env.example` to `.env` for `ODDS_API_KEY` (odds refresh), SMTP vars (email button), and the shared login (`AUTH_USER`, `AUTH_PASSWORD`, `SESSION_SECRET`). The app reads those from the environment; a `.env` file is optional when the variables are already set. Set the same values on Render. If any login variable is missing, every page redirects to `/login` and login fails. Five wrong passwords from one IP in 15 minutes lock that IP until the window passes. The lock is in memory on the one web process.

Layout:

- `app/` — FastAPI app (`main.py`, `routers/`, Jinja templates, static)
- `data/` — default SQLite file `data/sunday.db` (tracked in git), schedule, pick CSVs
- `scripts/` — one-shot fetches, not the web process

The database path is `SUNDAY_DB` if set, otherwise `data/sunday.db`. Locally leave `SUNDAY_DB` unset. On Render it is `/var/data/sunday.db` on the persistent disk. Those files do not sync.

Startup creates the file if it is missing, drops legacy `games` / `vegas_spreads` tables, and loads the schedule only when `matchups` is empty. A clone that already has `data/sunday.db` keeps the picks in that file.

## Deploy (Render)

Python web service, one instance. Build: `pip install -r requirements.txt`. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Attach a disk at `/var/data` and set `SUNDAY_DB=/var/data/sunday.db` plus the same secrets as `.env.example`. Do not scale past one instance; the disk is not shared. Do not copy the git `data/sunday.db` over the disk file after the site is live.

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
