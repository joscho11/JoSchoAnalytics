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
| 1 | `fetch_adp.py` | `sleeper_adp_2020_2026.csv` | Caches Sleeper preseason ADP (`adp_half_ppr`) + Sleeper's own season projection. ADP exists 2020+; 2026 already has ~245 players and grows toward late-August. |
| 2 | `build_season_dataset.py` | `season_dataset_2014_2025.csv` | One row per (player, season): prior-only features, two targets, ADP/Sleeper joined for 2020+. |
| 3 | `train_model_a.py` | `models/{pos}_ppg_model.pkl` | Model A (PPG), one CatBoost per position, games-weighted, 2014-2024 train / 2025 holdout. |
| 4 | `train_model_b.py` | `models/availability_model.pkl` | Model B (games played), one pooled CatBoost incl. reconstructed 0-game seasons. |
| 5 | `train_rookie_model.py` | `models/rookie_ppg_model.pkl` | Rookie PPG model (CatBoost on draft + combine + landing spot); used for rookies inside the board blend. |
| 6 | `build_2026_board.py` | `season_dataset_2014_2026.csv` | Seeds upcoming-season (2026) rows from rosters + rookies + 2025 priors; keeps 2014-2025 verbatim. Run before building a 2026 board. |
| 7 | `build_draft_board.py` | `draft_board_{season}.csv` | A x B -> VOR -> **three-way blend** (our/ADP/Sleeper) for the recommended order; runs the edge backtest. Globs newest dataset; season via `BOARD_SEASON`. |
| - | `rookie_features.py` | - | Shared rookie-model features (combine join + ROOKIE_FEATS). Source of truth for the trainer, board, and experiments. |
| - | `three_way_blend_test.py` | - | Sweeps the our/ADP/Sleeper blend weights (simplex grid + LOSO). Confirmed 0.2/0.3/0.5 beats the 2-way 5/5 seasons. |
| - | `blend_experiment.py` | - | The original our/ADP two-way weight sweep (found 0.30). Superseded by the three-way blend. |
| - | `diagnose_vet_rookie.py`, `rookie_model_experiment.py`, `rookie_blend_test.py` | - | Diagnostics behind the rookie model (vet/rookie split, standalone bakeoff, A/B/C blend test). |

`_utils.py` holds shared helpers (`norm_name`, constants). `test_seasonal_projections.py`
is a hermetic test suite (no network) for the transformation logic.
`model_a_compare.ipynb` is the 3-way bakeoff (CatBoost vs XGBoost vs LightGBM) kept
for reference; CatBoost won and is what `train_model_a.py` ships.

```bash
python fantasy/seasonal_projections/fetch_adp.py
python fantasy/seasonal_projections/build_season_dataset.py
python fantasy/seasonal_projections/test_seasonal_projections.py   # dataset transform tests
python fantasy/seasonal_projections/train_model_a.py
python fantasy/seasonal_projections/train_model_b.py
python fantasy/seasonal_projections/train_rookie_model.py          # rookie PPG model (used in the blend)
python fantasy/seasonal_projections/build_2026_board.py            # seed 2026 rows (for the pre-draft board)
python fantasy/seasonal_projections/build_draft_board.py           # latest-season board (BOARD_SEASON to override)
python fantasy/seasonal_projections/test_draft_board.py            # board / blend logic tests
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

**Does our model beat the market on its own? No.** Walk-forward backtest 2020-2024
(retrain on seasons before each year, drafted pool only, judged on actual VOR): our
ranking ρ averages 0.488 vs ADP's 0.552, and ADP wins every single year. The players we
would "value pick" (rank well above ADP) finished with a 125-point mean vs 160 for
players we are neutral on and 157 for players we would fade. When our model disagrees
with ADP, ADP is usually right. Same lesson as the spread and totals models: a market
consensus already prices in offseason news, camp reports, and depth-chart moves a
prior-season-stats model cannot see. So we do not ship the standalone model as an edge.

**What we do ship is the blend** (see below), which out-ranks any single source. The
honest framing: our model is not draft-board alpha on its own, but as one ingredient in
a market blend it earns a real, small contribution. We present the board as a
sanity-checked consensus, not a secret edge.

`diagnose_vet_rookie.py` splits that backtest by rookie status to see where the gap
comes from. Veterans (86% of the drafted pool): our ρ 0.506 vs ADP 0.544, basically
parity (we even edged ADP in 2022 and 2024). Rookies (14%): our ρ 0.172 vs ADP 0.462,
a wipeout. The model has no prior-season data on rookies, so it clumps them all at the
bottom.

### Rookie model (shipped into the blend)

We built a dedicated rookie model on draft capital, combine measurables (forty, bench,
vertical, broad jump, cone, shuttle, height, weight, joined to our player id through
the draft-picks pfr bridge, about 93 percent coverage on drafted rookies), and
landing-spot features. College production is not in nflreadpy, so we do not have it.
The feature engineering is in `rookie_features.py` and the trained model is
`models/rookie_ppg_model.pkl` (`train_rookie_model.py`).

Standalone it does not beat ADP (rookie ranking rho 0.26 vs 0.46) so it is not an edge
on its own. But the right question is not whether it beats ADP alone, it is whether it
helps inside the blend, and it does. `rookie_blend_test.py` compared three ways to
handle rookies' projection in the blend: the veteran model (the old behavior), the rookie
model, and pure ADP. Walk-forward mean rookie-slice rho came out veteran 0.457, rookie
model 0.488, pure ADP 0.457. The rookie model is the only option that clears pure ADP
on rookies (its errors are independent of the market's, so the ensemble lifts it), and
it does not cost anything on the overall board. So `build_draft_board.py` uses the
rookie model for rookies' projection inside the blend. Shipping it improved the board's
2025 PPG accuracy (2.06 vs 2.01) and nudged the season-total projection closer to
Sleeper's. The standalone edge backtest deliberately does not use it, so the "we lose
to ADP standalone" result is unchanged.

### The blend (shipped into the board)

This is where our work pays off. Our standalone projection loses to the market, but it
carries independent signal, so blending it with market signals out-ranks any single
source. We never feed a market signal into the model itself (that would be circular,
the tree would just copy it); we combine rankings after the fact.

Two steps got us here. First the two-way (`blend_experiment.py`): `0.3*our + 0.7*ADP`
beats pure ADP in 5 of 5 seasons, but only by about 0.012 to 0.015 Spearman rho, inside
the noise band. Then the big one (`three_way_blend_test.py`): Sleeper also publishes its
own season point projection, which alone already beats ADP, so we added it as a third
ranker. The best mix, confirmed by a simplex weight sweep plus leave-one-season-out, is
**our 20 percent, ADP 30 percent, Sleeper 50 percent**. That lifts the board to rho
0.637 versus 0.567 for the old two-way, a plus 0.07 gain (about two standard errors)
that holds out of sample in 5 of 5 seasons. Our model still earns its 20 percent: the
full three-way beats ADP-plus-Sleeper-without-us, so the projection is not redundant.
The board uses this three-way blend as the headline recommended draft order
(`blend_rank` / `blend_pos_rank`); the raw projection is kept for the value and reach
view. It is a real ranking improvement, but it is a blended consensus, not a secret edge.

### 2026 pre-draft board (built)

A real pre-draft board for the upcoming season is built, not just a future idea. Sleeper
ADP for 2026 already exists (early best-ball drafts have run; about 245 players now,
growing toward the late-August consensus), the 2026 draft happened in April so rookie
draft and combine data exist, and 2026 rosters give the player population. The only thing
missing is 2026 stats (the season has not been played), which a pre-draft board does not
need. `build_2026_board.py` seeds a row for every 2026 rostered skill player plus the
rookies, attaches their 2025-derived priors through the same prior-join the training data
uses, and appends those rows to the dataset (the trained 2014-2025 rows are kept verbatim,
since nflreadpy data drifts and the models were trained on them). Then
`BOARD_SEASON=2026 python build_draft_board.py` builds `draft_board_2026.csv`, and the
dashboard season selector shows it. The 2026 board correctly ranks rookies like Ashton
Jeanty and Omarion Hampton via the rookie model plus their ADP.

## Annual refresh

The board is kept as a projection and cross-check tool, so it is worth regenerating
each offseason. `build_draft_board.py` is season-parameterized: by default it builds
the latest season in the dataset and backtests the ADP-era seasons before it. Override
the season with the `BOARD_SEASON` env var:

```powershell
$env:BOARD_SEASON=2026; python fantasy/seasonal_projections/build_draft_board.py
```

It degrades gracefully: a season with no rows prints a rebuild hint, a season with no
ADP yet prints projections only, and an empty backtest is skipped. Output is written to
`draft_board_{season}.csv`. To refresh for a new season: (1) extend `fetch_adp.py` to
that season once Sleeper ADP lands, around late August; (2) re-run
`build_season_dataset.py` after the prior season's actuals are final; (3) optionally
fold the prior holdout season into training and re-run `train_model_a.py` and
`train_model_b.py`; (4) run `build_draft_board.py` with the new `BOARD_SEASON`.

One limitation to know: a true pre-draft board for a season with zero games played
needs the player list seeded from rosters and depth charts joined to prior-year stats,
because dataset rows come from `load_player_stats`, which is empty until games are
played. That seeding is not built, so the pipeline today produces a board for the
current or just-completed season.

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
