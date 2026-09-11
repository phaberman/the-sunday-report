# The Sunday Report

Probabilistic NFL game forecasts, published before kickoff and frozen. Market odds are the yardstick.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
python app.py
```

## Odds snapshots

One-shot pull of NFL spreads from [The Odds API](https://the-odds-api.com/). Run by hand.

```bash
cp .env.example .env
# edit .env and set ODDS_API_KEY=...
python scripts/fetch_odds_once.py
```

Writes a timestamped CSV under `data/odds/snapshots/`. Columns: `pulled_at`, game id/teams/kickoff, `bookmaker`, `market`, `outcome`, `price`, `point`.

## Tests

```bash
python -m pytest -q
```

## Matchup ranks

Rebuild historical PF/PA ranks (2016–2025, point-in-time, no look-ahead):

```bash
python scripts/build_matchup_ranks.py
```

Writes `data/features/matchups_pf_pa_ranks.csv`.
