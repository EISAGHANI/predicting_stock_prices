# Vendored: day-trader-skill (`day_trader_skill/`)

- Source: https://github.com/Jakeschincariol/day-trader-skill
- Commit: `3d0f4ef` (2026-10-20, "The Trader skill v2: 11 day-trading skills")
- License: MIT (see `day_trader_skill/LICENSE`), Copyright (c) 2026 Jake Schincariol

`day_trader_skill/` is an unmodified copy (minus `.git/`). The web app runs the
scripts in `trader-*/` as subprocesses (see `stock_predictor/trader/`); it never
imports or edits them. Demo mode reads the recorded data in `tests/fixtures/`.

To update: copy a newer checkout over `day_trader_skill/`, run the tests and check the
command-line flags used in `stock_predictor/trader/catalog.py` still exist.

```powershell
python -m unittest discover -s vendor/day_trader_skill/tests
```
