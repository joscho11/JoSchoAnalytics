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
| 3 | *(next)* | models + board | Model A (PPG) and Model B (availability), not built yet. |

`_utils.py` holds shared helpers (`norm_name`, constants). `test_seasonal_projections.py`
is a hermetic test suite (no network) for the transformation logic.

```bash
python fantasy/seasonal_projections/fetch_adp.py
python fantasy/seasonal_projections/build_season_dataset.py
python fantasy/seasonal_projections/test_seasonal_projections.py
```

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
