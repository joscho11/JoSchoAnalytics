# futures/

Published Season Totals projections come from the private `season_totals_v2_prod`
producer. This folder keeps the copies the Streamlit page reads. They are
backtested, not live-validated; the evidence file carries the current claim and
limitations shown on the page.

| Path | Role |
|---|---|
| `published/season_totals_2026.csv` | 2026 line_in sheet the page renders |
| `published/evidence.json` | MAE ladder and claim the page renders |
| `language_fence.py` | Banned-token list for page tests |
