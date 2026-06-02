# Seasonal Projections

A pre-season fantasy projection system, separate from the in-season weekly
model in `fantasy/`. The goal: project each player's upcoming season, rank them
into a draft board, and compare to the market (Sleeper ADP) to surface values
and reaches. It is the fantasy analog of the betting side's "model vs the Vegas
line" thesis (here the market line is ADP).

## Why this is a different model than the weekly one

The weekly model leans on *in-season* rolling features (recent EPA, recent
target share). None of those exist before Week 1. So this is a distinct problem:
a season-long projection built only from information known at draft time
(prior-season aggregates, multi-year trend, age, draft capital, team context).

## Pipeline (run in order)

| Step | File | Output | Notes |
|------|------|--------|-------|
| 1 | `fetch_adp.py` | `sleeper_adp_2020_2025.csv` | Caches Sleeper preseason ADP (`adp_half_ppr`) + Sleeper's own season projection as benchmarks. ADP exists 2020+ only. |
| 2 | `build_season_dataset.py` | `season_dataset_2014_2025.csv` | One row per (player, season): prior-only features, two targets, ADP joined for 2020+. |
| 3 | `train_model_a.py` | `models/{pos}_ppg_model.pkl` | Model A (PPG), one CatBoost per position, games-weighted, 2014-2024 train / 2025 holdout. |
| 4 | `train_model_b.py` | `models/availability_model.pkl` | Model B (games played), one pooled CatBoost incl. reconstructed 0-game seasons. |
| 5 | `build_draft_board.py` | `draft_board_2025.csv` | Combines A x B into VOR, ranks vs ADP, and runs the walk-forward edge backtest. |

`_utils.py` holds shared helpers (`norm_name`, constants). `test_seasonal_projections.py`
is a hermetic test suite (no network) for the transformation logic.
`model_a_compare.ipynb` is the 3-way bakeoff (CatBoost vs XGBoost vs LightGBM) kept
for reference; CatBoost won and is what `train_model_a.py` ships.

```bash
python fantasy/seasonal_projections/fetch_adp.py
python fantasy/seasonal_projections/build_season_dataset.py
python fantasy/seasonal_projections/test_seasonal_projections.py
python fantasy/seasonal_projections/train_model_a.py
python fantasy/seasonal_projections/train_model_b.py
python fantasy/seasonal_projections/build_draft_board.py
```

## What the models do, and the honest verdict

**Model A (PPG)** is per-position CatBoost, games-weighted. 2025 holdout, matched-row
MAE (rookies excluded so the naive baseline can compete): QB 2.78, RB 2.41, WR 1.84,
TE 1.36, and it beats a 3-year-average baseline at all four spots. **Model B (games)**
is one pooled CatBoost trained on every player-season including the reconstructed
full-miss years. 2025 holdout MAE 3.73 games, beating "repeat last year" (4.11) and
"predict the mean" (5.34). It does what we wanted: separate durable from fragile
tiers, not nail exact games (most injury variance is a freak hit no feature sees).

Combined into a board, value = PPG x games, then value-over-replacement (VOR) so the
cross-position ranking is sane (raw points would stack every QB at the top).

**Does it beat the market? No.** Walk-forward backtest 2020-2024 (retrain on seasons
before each year, drafted pool only, judged on actual VOR): our ranking ρ averages
0.488 vs ADP's 0.552, and ADP wins every single year. Worse, the players we would
"value pick" (rank well above ADP) finished with a 125-point mean vs 160 for players
we are neutral on and 157 for players we would fade. When our model disagrees with
ADP, ADP is usually right. This is the same lesson as the spread and totals models:
a market consensus already prices in offseason news, camp reports, and depth-chart
moves that a prior-season-stats model cannot see. The board is a fine projection and
cross-check tool (our season totals land within ~2 points of Sleeper's own
projection on 2025), but it is not a source of draft-board alpha over ADP. We are not
shipping it as an edge.

## Two targets (two-model design)

- **`target_ppg`** — half-PPR points per game (Model A, production). NaN when the
  player played 0 games or fewer than 3 (a tiny sample is a noisy label).
- **`target_games`** — games played (Model B, availability). Present for every
  row, including reconstructed full-miss seasons.
- **`sample_weight`** — games played, so Model A trusts a 2-game season far less
  than a 16-game one.

Final draft value = projected PPG × projected games, ranked against ADP.

## Key design decisions (intentional, not bugs)

- **ADP is a benchmark, never a feature.** It only constrains evaluation (2020+),
  not the training window. The model trains on 2014+ from nflreadpy.
- **Full-miss seasons are reconstructed.** A season a player skipped entirely
  leaves no stats row, so Model B would never see a 0-game outcome. We synthesize
  a `games=0` row for every gap *between* a player's first and last active season.
  This leans toward injury/IR (the player returned) rather than left-the-league.
- **`is_rookie` vs `missed_prior_season`.** Both produce a NaN-ish prior, but mean
  opposite things (no NFL history vs a veteran who sat out hurt). Both are flags.
- **Prior features use an explicit season-(N-1) join, not `shift(1)`,** so a
  missed season correctly yields NaN priors instead of pulling 2-year-stale data.
- **Missing priors are NaN, never 0** (zero is a real value to a tree; NaN gets
  routed natively by XGBoost). Same lesson as the spread side's time-decay bug.
- **Low-snap player-seasons are kept, not filtered.** Usage drives points, so a
  17-game / 15%-snap line is real signal; `snap_share_pg` lets the model learn it.
  The ADP join means low-relevance players never reach the board anyway.

## Known caveats (honest)

- **`qb_changed` and `vacated_target_share` / `vacated_rush_share`** use season-N
  primary-passer / roster info. At a real late-August draft this is ~known, but
  it is mild hindsight in a strict backtest. `coach_changed` is fully clean.
- **Reconstructed gaps** capture injury plus some non-injury cases (a backup who
  sat a year). The ADP join ignores them, so they only inform Model B's
  durability gradient, not the board.
- **`games_played`** is snap-based where snaps exist (2013+), else stat-line
  weeks. It can still blur a true injury absence vs a healthy inactive.
- **Sleeper data floors:** ADP 2020+, Sleeper point projections 2018+. Neither
  limits the model (both are benchmarks).
