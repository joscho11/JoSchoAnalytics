# Audit bundle C — FINAL (2026-08-03)

**This bundle carries the published number.** It supersedes `audit_2026-08-03b_allpro_identity/`
(All-Pro *aggregate* identity) and `audit_2026-08-03_sack_leak/` (dense sack only). Both
earlier bundles remain valid, unmodified evidence for their own scope.

## What this adds

Bundle B fixed All-Pro identity in the **aggregate** weighted lookback but the **injury**
path still matched on name:

* training — `model_comparison.ipynb` cell 36: `ap_wt = pd.concat(...).drop_duplicates(["Player","season"])`
  then a join on `["norm_name","season"]`;
* serving — `features.py` resolved `allpro_id` and then **dropped it**, merging
  `inj_all` to `allpro_wh` on `["_name_norm","season"]`.

With two same-name All-Pro players in one weight window that merge FANS OUT — one injury
row matches two All-Pro rows and the weight is subtracted twice, corrupting
`diff_active_allpro_weighted` (`PROD_FEATURES_35` #11). Both paths now call one shared
helper, `allpro_identity.injured_allpro_weight`, which asserts no fan-out and aborts on any
ambiguity its reviewed crosswalk does not cover. Team disambiguates a collision only; it is
never a general join key, so the BAL→NYJ C.J. Mosley lineage still matches.

## Environment and inputs

Identical to bundles A and B: Python 3.11.9, `requirements-backtest.txt`, pandas 2.3.3,
numpy 1.26.4, xgboost 3.1.2, scikit-learn 1.6.1, lightgbm 4.6.0, nflreadpy 0.1.5,
polars 1.40.1, pyarrow 24.0.0, openpyxl 3.1.5. venv `C:/tmp/jsa-bt`.
Tracked inputs: `betting/data/nfl.xlsx` `AE2409E8…`, `betting/nfl_allpro_1997_2025.csv`
`DAFEE95D…`.

## Command

```
C:/tmp/jsa-bt/Scripts/python.exe betting/experiments/walkforward_oos_preds.py \
    --line open --out E_final_dense_identity_injury.csv
cd betting && C:/tmp/jsa-bt/Scripts/python.exe kelly_staking.py --preds <path>
```
(Arm E is the live repository notebook; no `--notebook` override.)

## Result — the injury correction does not move the published number

| Arm | scope | sha256 | HIGH | win% | Wilson lo | MEDIUM | win% | Wilson lo |
|---|---|---|---|---|---|---|---|---|
| D (bundle B) | dense sack + aggregate identity | `44F82833…` | 129/238 | 54.2017% | 47.8551% | 382/718 | 53.2033% | 49.5462% |
| **E (this bundle)** | **+ injury identity** | `37830520…` | **129/238** | **54.2017%** | **47.8551%** | **382/718** | **53.2033%** | **49.5462%** |

**E vs D:** 1,047 of 2,138 margins changed; mean |Δ| **0.000069**, max |Δ| **0.003780**;
HIGH n 238 → 238, MEDIUM n 718 → 718; **zero tier crossings**. The fan-out was real but
confined to the one colliding name in the seasons where both selections sit in the weight
window, so it perturbs margins without moving any threshold.

**Determinism:** run twice, byte-identical
(`3783052092A9B300F15CAF9A071F99B7B8D9424CFFC8993E19BCA861530E25BA`).

## Published result

**HIGH 129/238 = 54.2017%, Wilson lower bound 47.8551% — below the 52.4% break-even.**
MEDIUM 382/718 = 53.2033%, lower 49.5462%. **No tier clears break-even.** No edge is
claimed. The 2026 forward record is the first real test.
