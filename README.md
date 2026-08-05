# The Sunday Report

Probabilistic NFL game forecasts, published before kickoff and frozen. Market odds are the yardstick.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Odds snapshots (M04)

One-shot pull of current NFL spreads from [The Odds API](https://the-odds-api.com/) (free tier). No schedule yet — run by hand.

**What it does:** hits the API → flattens bookmaker spreads → writes a timestamped CSV under `data/odds/snapshots/`.

### 1. API key

```bash
cp .env.example .env
# edit .env and set ODDS_API_KEY=...
```

`.env` is gitignored. Never commit the key.

### 2. Pull once

```bash
python scripts/fetch_odds_once.py
```

Example output:

```
games=... rows=... -> data/odds/snapshots/2026-08-05T08-46-44Z.csv
quota used=... remaining=...
```

Open the CSV. Expect columns: `pulled_at`, game id/teams/kickoff, `bookmaker`, `market`, `outcome`, `price`, `point`.

### 3. Tests (no API key needed)

```bash
python -m pytest -q
```

Covers smoke + flatten logic for the odds CSV shape.

## Matchup ranks dataset

Historical REG-season games (2016–2025) with **point-in-time** offense/defense ranks from season-to-date points for / points against.

Rules:
- Week 1 → everyone tied at rank 1 (no games yet)
- Week N ranks use only weeks `1..N-1` (no look-ahead)
- Ties share a dense rank; bye weeks carry cumulative totals forward
- Scores on the row are **labels** for training, not features for that week

```bash
python scripts/build_matchup_ranks.py
```

Writes `data/features/matchups_pf_pa_ranks.csv`.

Columns: `season`, `week`, `game_id`, `away_team`, `home_team`, `away_off_rank`, `away_def_rank`, `home_off_rank`, `home_def_rank`, `away_score`, `home_score`.
