# Audit bundle — sack-leak retraction (2026-08-03)

> **SUPERSEDED AS THE PUBLISHED NUMBER — retained as intermediate evidence.**
> Everything here is true, but it measures the dense-sack change while the **legacy
> name-only All-Pro identity** was still in force. That identity scheme merged two distinct
> players named C.J. Mosley and left the survivor to an unstable sort. A later bundle
> (`audit_2026-08-03b_allpro_identity/`) re-measures on top of the identity fix and carries
> the published number. Do not cite 133/240 from this bundle as final.

Immutable evidence for the retraction of the published **64.2% ATS** headline. Everything
here was produced in one declared, pinned environment. Do not regenerate these files in
place; a new investigation gets a new dated bundle.

## The defect

`sack_pg` (`model_comparison.ipynb` §7) and `_build_situational_pbp`
(`betting/features.py`) filtered `sack == 1` **before** the groupby, so a defense that
recorded zero sacks in a game produced **no row at all**. Consequences:

1. `shift(1).rolling(5)` stepped over the previous *sack-positive* game, skipping zero-sack
   games instead of averaging a 0 (upward bias).
2. Row **presence** encoded the current game's own outcome. The left-merge in the
   attach-rolling-features cell left NaN exactly on zero-sack team-games, and the
   subsequent `.fillna(0)` wrote 0 onto precisely those rows — contemporaneous information
   inside a pregame feature.

`sack_diff` and `sack_diff_reverse` are `PROD_FEATURES_35` #2 and #3.

## Environment (canonical)

| | |
|---|---|
| Python | 3.11.9 |
| Requirements | `requirements-backtest.txt` (= `requirements-ci.txt` + `openpyxl==3.1.5`) |
| pandas | 2.3.3 (the `requirements-ci.txt` pin) |
| numpy | 1.26.4 |
| xgboost | 3.1.2 |
| scikit-learn | 1.6.1 |
| lightgbm | 4.6.0 |
| nflreadpy | 0.1.5 |
| polars | 1.40.1 |
| pyarrow | 24.0.0 |
| openpyxl | 3.1.5 |
| venv used | `C:/tmp/jsa-bt` |

`requirements-ci.txt` alone **cannot** run this command: `betting/historical_lines.py`
reads `betting/data/nfl.xlsx` with `engine="openpyxl"` and openpyxl is in no requirements
file. That is why `requirements-backtest.txt` exists.

## Exact commands

```bash
python -m venv C:/tmp/jsa-bt
C:/tmp/jsa-bt/Scripts/python.exe -m pip install -r requirements-backtest.txt

# corrected (dense sack table) — from the repo root
C:/tmp/jsa-bt/Scripts/python.exe betting/experiments/walkforward_oos_preds.py \
    --line open --out <out>/corrected_dense_sack.csv

# leaking control (same env, same inputs, legacy sack build)
C:/tmp/jsa-bt/Scripts/python.exe betting/experiments/walkforward_oos_preds.py \
    --line open     --notebook betting/experiments/audit_2026-08-03_sack_leak/model_comparison_LEGACYSACK_control.ipynb \
    --out <out>/control_leaking_sack.csv

# metrics — from betting/
cd betting && C:/tmp/jsa-bt/Scripts/python.exe kelly_staking.py --preds <out>/<file>.csv
```

## Inputs

* Schedules / play-by-play / NGS: `nflreadpy==0.1.5`, seasons 2014–2025, fetched
  2026-08-03. nflreadpy resolves nflverse GitHub release assets; it exposes no per-asset
  snapshot timestamp, so the fetch date is the provenance available. **This is the one
  input that is not content-pinned** — a future nflverse revision can move these numbers.
* Opening lines: `betting/data/nfl.xlsx` (aussportsbetting), tracked in-repo,
  sha256 recorded below.
* All-Pro rosters: `betting/nfl_allpro_1997_2025.csv`, tracked in-repo.

## Output hashes

See `SHA256SUMS.txt`. The corrected artifact is
`8305ED0FB190F354926270A3D26335ADF27E3B446250CDA2FA6383AD6331876D` and was produced
**byte-identically by two independent runs** in this environment.

## Tier derivation, pushes, Wilson

* Tiers come from `betting/clv_backtest.run(min_edge, preds_path)` with `min_edge = 1.0`:
  HIGH = all three direction voters agree **and** `|ens_model_edge| >= 3`; MEDIUM = agree
  and `>= 1`; PASS otherwise. Games below `min_edge` fall in no tier, so tier counts do not
  sum to 2,138.
* **Pushes excluded** by `df["won_open"].notna()` in `kelly_staking.tier_stats` — a push
  yields `1.0 - nan = nan` in `_cover` and drops out.
* Win rate is ATS **against the opening line you would have bet**, out of sample.
* Wilson lower bound: `kelly_staking.wilson_lower(wins, n, z=1.96)`. Note this uses
  `z = 1.96`, not the exact 95% `z = 1.959964`; an independent reproduction using the exact
  z reports 49.09195% where this function reports 49.09184%. The repo's own function is
  what publishes, so its value is the canonical one.

## Results

| Run | HIGH | win% | Wilson lower (z=1.96) | Clears 52.4%? |
|---|---|---|---|---|
| Published (June 2026 artifact, leaking) | 380 / 592 | 64.19% | 60.25% | yes |
| **Control** — leaking build, this env, these inputs | **380 / 592** | **64.1892%** | **60.24690%** | yes |
| **Corrected** — dense sack table | **133 / 240** | **55.4167%** | **49.09184%** | **no** |

MEDIUM corrected: 389 / 728 = 53.4341%, Wilson lower 49.80197% — also below.
PASS corrected: 153 / 283 = 54.0636%, Wilson lower 48.24171%.

The control reproduces the published figure **exactly** (380/592), which is what licenses
the causal claim: the collapse is the leak, not data drift and not environment drift.

## Known nondeterminism (documented, NOT fixed here)

An earlier run of the corrected path under **pandas 3.0.3** produced HIGH **131/237**
instead of 133/240. Cause, traced: exactly **4 of the 35** production features differ
between pandas 2.3.3 and 3.0.3 — `diff_active_allpro_weighted`,
`diff_allpro_last_3_years_weighted`, `allpro_diff_home_off_away_def_3_years`,
`away_defense_allpro_3_years` — by ~2 counts in total. The origin is
`combined.sort_values("weight", ascending=False).drop_duplicates(["Player","season"])` in
the All-Pro cell: `sort_values` defaults to `kind="quicksort"`, which is **not stable**, so
a tied key's surviving row is implementation-dependent. There is exactly **one** ambiguous
key in the source — **C.J. Mosley, 2014, listed for both BAL and DET at equal weight** (1 of
2,046 (Player, Year) keys). That single row shifts model margins by mean ~0.09–0.25 points,
which flips borderline games across the HIGH tier's `|edge| >= 3` and 3-voter-agreement
thresholds, moving HIGH from 240 games to 237.

This is a real latent defect (the pipeline's output depends on unstable sort tie-breaking),
but it is **deliberately not fixed in this bundle**: changing it would alter the canonical
artifact and invalidate the hash agreement above. Fix + regenerate as a separate, dated
change — add `kind="stable"` plus an explicit deterministic tie-break key, then publish a
new bundle.

## What is claimed after this bundle

Nothing. 55.4167% on 240 picks is a point estimate above break-even whose 95% interval
contains it. The system has **no demonstrated ATS edge**; the 2026 forward record is the
first real test.
