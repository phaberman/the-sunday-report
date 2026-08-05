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
