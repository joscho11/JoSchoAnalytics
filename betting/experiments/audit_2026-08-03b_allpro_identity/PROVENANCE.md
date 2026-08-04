# Audit bundle B — All-Pro identity + sack leak, 2×2 (2026-08-03)

**This bundle carries the published number.** It supersedes
`audit_2026-08-03_sack_leak/`, which measured the sack fix while the legacy name-only
All-Pro identity was still in force. That earlier bundle is retained and is still true; it
is intermediate evidence, not the final result.

## The two defects, separated

**1. Sack leak.** `sack_pg` / `_build_situational_pbp` filtered `sack == 1` *before* the
groupby, so a zero-sack team-game produced no row; presence encoded that game's own
outcome and a downstream `fillna(0)` wrote 0 onto exactly those rows.

**2. All-Pro identity collision.** `betting/nfl_allpro_1997_2025.csv` has no player ID and
contains

    ILB,C.J. Mosley,BAL,2014,defense
    MLB,C.J. Mosley,DET,2014,defense

— two distinct players. Consumers keyed on the NAME and deduped with
`sort_values("Weight").drop_duplicates(["Player", ...])`, so one player was discarded and
*which* one depended on pandas' unstable default sort. Per target season: 2015 and 2016
both rows tie on weight (4 and 2 respectively) and one team survives arbitrarily; 2017 the
BAL player's newer weight-4 selection wins and the *separate* DET player's weight-1 record
is wrongly discarded. `kind="stable"` would only have frozen the wrong answer.

Fixed in `betting/allpro_identity.py`: a reviewed identity table plus an order-invariant
`groupby().idxmax()` reduction with **no sort at all**. Applied to `betting/features.py`
(weighted All-Pro, prev-year counts, and the injury/active-All-Pro dedupe) and
`betting/model_comparison.ipynb` cell 15.

## Environment

Identical to bundle A: Python 3.11.9, `requirements-backtest.txt`
(`requirements-ci.txt` + `openpyxl==3.1.5`), pandas 2.3.3, numpy 1.26.4, xgboost 3.1.2,
scikit-learn 1.6.1, lightgbm 4.6.0, nflreadpy 0.1.5, polars 1.40.1, pyarrow 24.0.0.
venv `C:/tmp/jsa-bt`.

## Input content identity — proven, not asserted

`nflreadpy` runs in `CacheMode.MEMORY`, so every arm re-downloads schedules/PBP/NGS. Rather
than claim "fetched the same day", content identity is demonstrated empirically: arms **A**
and **B** reproduce the bundle-A artifacts **byte-for-byte** (`0B4CF3AD…`, `8305ED0F…`)
from an independent fetch several hours later. Identical outputs from independent
downloads is direct evidence the upstream content did not move across all four arms.

Tracked inputs, hashed:

| File | sha256 (first 32) |
|---|---|
| `betting/data/nfl.xlsx` | `AE2409E8D000508BA754FFDC2F5B4428…` |
| `betting/nfl_allpro_1997_2025.csv` | `DAFEE95DE2D81171C802909689C16CE1…` |

**Residual risk:** a future nflverse revision can still move these numbers. A pinned
on-disk snapshot of the three nflverse inputs is the durable fix and is NOT yet built.

## Commands

```bash
C:/tmp/jsa-bt/Scripts/python.exe betting/experiments/walkforward_oos_preds.py \
    --line open --notebook <arm>.ipynb --out <arm>.csv     # D uses the live notebook
cd betting && C:/tmp/jsa-bt/Scripts/python.exe kelly_staking.py --preds <arm>.csv
```

Arm notebooks `nb_A/B/C` are retained here. **Arm D is the repository's live
`betting/model_comparison.ipynb`** and is therefore not duplicated; re-run D by omitting
`--notebook`.

## The 2×2

Tiers from `clv_backtest.run(min_edge=1.0)`; pushes excluded by `won_open.notna()`; Wilson
lower from `kelly_staking.wilson_lower(z=1.96)`. 2,138 OOS predictions, 2018–2025.

| Arm | sack | All-Pro identity | sha256 | HIGH | win% | Wilson lo | MEDIUM | win% | Wilson lo |
|---|---|---|---|---|---|---|---|---|---|
| A | leaking | legacy | `0B4CF3AD…` | 380/592 | 64.1892% | 60.2469% | 354/662 | 53.4743% | 49.6655% |
| B | dense | legacy | `8305ED0F…` | 133/240 | 55.4167% | 49.0918% | 389/728 | 53.4341% | 49.8020% |
| C | leaking | fixed | `F0700326…` | 378/589 | 64.1766% | 60.2239% | 359/667 | 53.8231% | 50.0285% |
| **D** | **dense** | **fixed** | `44F82833…` | **129/238** | **54.2017%** | **47.8551%** | 382/718 | 53.2033% | 49.5462% |

### Effect isolation

| Comparison | isolates | margins changed | mean abs | max abs | HIGH n | crossing |
|---|---|---|---|---|---|---|
| B vs A | sack fix @ legacy ID | 2138/2138 | 1.7687 | 7.9797 | 592 → 240 | 352 |
| D vs C | sack fix @ fixed ID | 2138/2138 | 1.7676 | 8.2136 | 589 → 238 | 351 |
| D vs B | identity fix @ dense | 2138/2138 | 0.0928 | 0.6341 | 240 → 238 | 2 |
| C vs A | identity fix @ leaking | 2138/2138 | 0.0834 | 0.5256 | 592 → 589 | 3 |

The sack repair is the dominant effect and survives the identity repair (C→D reproduces
B←A). The identity effect is small but real — and its magnitude (mean 0.0928) matches the
pandas 2.3.3-vs-3.0.3 drift measured earlier (mean 0.0942), which independently confirms
the collision was the source of that version sensitivity.

**Determinism:** arm D was run twice and is byte-identical
(`44F8283311599BA6A0E10FAC4D59B5C6BE62A005A6F9E9A292AFB546F16DCC43`).

## Published result

**D. HIGH 129/238 = 54.2017%, Wilson lower bound 47.8551% — below the 52.4% break-even.**
MEDIUM 382/718 = 53.2033%, lower 49.5462% — also below. **No tier clears break-even.**

The retraction stands and is slightly stronger than bundle A implied: the identity fix
moved the corrected figure down from 55.4167% to 54.2017% and the lower bound from 49.09%
to 47.86%. No edge is claimed. The 2026 forward record is the first real test.
