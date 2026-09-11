# The Sunday Report

Probabilistic NFL game forecasts, published before kickoff and frozen.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
uvicorn app:app --reload
```

Open http://127.0.0.1:8000

First launch creates `data/sunday.db` and seeds Week 1 model lines from `data/picks/week_01.csv`.

## Upload

`/upload` accepts CSV or Excel (`away_team, home_team, spread`).

- **Model picks** → upsert `model_margin`, save `data/picks/week_NN.csv`
- **Vegas lines** → upsert `vegas_margin`, save `data/vegas/week_NN.xlsx`

Commit those files yourself. The database is gitignored.

## Tests

```bash
python -m pytest -q
```
