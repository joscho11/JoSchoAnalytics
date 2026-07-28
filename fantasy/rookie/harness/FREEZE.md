# ROOKIE HIT-PROBABILITY HARNESS — FROZEN (build complete, NOT fired)

Built 2026-07-20 to `fantasy/rookie/PREREG_rookie_production_2026-07-20.md` (committed `6fdbba5`).
Nothing was fit on the real target; no feature-vs-target metric was computed. Blindness intact.
Interpreter: `AI_hedge_fund/.venv/Scripts/python.exe` (Python 3.11.9).

## Frozen fire-path artifacts (sha256)

| file | sha256 | role |
|---|---|---|
| `assemble_panel.py` | `cd6d43cfb9cf4190dcfb2d28dc71b8c0c6461c2a2c59736dcbdcd7bd6d78fcbc` | panel + HIT target |
| `assemble_features.py` | `3a530f2dd328cf9c7af9457e645755bc5945fe844f25986d94a4e6f4b38d5e82` | 5-group feature matrix |
| `harness.py` | `81b83a7f3811d926783e3ffbe1f0d3888461f08d5ae04edb68d2e5c02ec34fb9` | model/CV/arms/metrics/§8/fire |
| `feature_groups.json` | `c44f322a516bd19dae5ee867aac7d304cd11729459ac15122c2ab45efd320ec8` | arm feature-set definitions |
| `feature_cols.csv` | `a37e357c480d0e7fdad2026cbd5e315778ba5a7e3a93e9a94962aafee1c4c077` | 63-col feature manifest |

Data artifact (regenerable from the frozen scripts; contains PFF-derived values → scratchpad/private only):
`feat_hit.parquet` sha256 `6461c7448fef2d40ebd6f0dc9fbc1295bf8c37b0d9334113da1f17a7349a6a2e` (712×63).

## What passed at build (all synthetic / permuted / fake — no real metric)

- **Part A** panel reproduces frozen counts EXACTLY: n=712 (QB101/RB189/WR290/TE132), hits 15/54/47/19.
- **Part B** feature coverage: draft 100% / combine 86.2% / cfbfastR box 94.5% / PFF 92.4% / age 99.9%.
- **Part C** synthetic harness-proof: NOISE ≈ position-only (no hallucination); SIGNAL detected beyond
  position w/ lower logloss; PEEK AUC 1.000 (leakage screams); leakage + identity (draft_only == group1)
  + college_only-excludes-draft asserts PASS.
- **decide() self-test**: §8 arithmetic accepts a pass-case, rejects a fail-case.
- **Part C2** real-shape fire-path proof: all 4 arms × both families run on the REAL 63-feature matrix
  (391 test rows = entry 2019–2023, 5 folds), valid probabilities, no crash — target PERMUTED, no metric.

## Blind MDE (Part D, structure-only; prereg §7f)

Pooled full-vs-draft-only **MDE ≈ +0.020 ΔAUC at 80% power = the §8(b) bar** → the PRIMARY pooled gate is
ADEQUATELY POWERED (the fire is not decorative). Per-position MDE: WR +0.039, RB +0.060 (adequately-powered
per §8d), **QB +0.071 / TE +0.069 UNDERPOWERED → descriptive** — confirms §8d. (Assumed draft-baseline
BETA_D=0.85; MDE is driven by positive counts + fold structure, not model choice.)

## THE FIRE (fresh session, exactly once — Amendment-4)

1. New session. Verify the five sha256 above are unchanged (esp. `harness.py`).
2. Regenerate data from frozen code: `python assemble_panel.py` (asserts 712/135) → `python assemble_features.py` (asserts coverage).
3. `python harness.py --fire` — runs all arms×families, applies §8 (headline = CatBoost, full vs draft_only),
   1000-draw placebo, writes `fire_rookie_results.pkl` (derived-only) + prints the §8 verdict.
4. Append OUTCOMES to the committed prereg (Step 9); archive the harness to `pff/frozen_fires/` (private).
   ONE SHOT. Rejection final.

## §8 decision rule (frozen; applied at fire, headline = CatBoost, full vs draft_only)
(a) pooled Δlogloss ≥ 0.010 · (b) pooled ΔAUC ≥ 0.020 · (c) ≥3/5 folds improve · (d) RB/WR per-pos AUC
floor −0.030 (QB/TE descriptive) · (e) placebo obs > shuffled-95th. ACCEPT iff all hold.

## ⚠ PRESERVATION RISK
These files live ONLY in the temp scratchpad
`…/86d5b45d-…/scratchpad/rookie_build/`. Temp cleanup would destroy the frozen harness (the Session-9
near-loss class). Fire soon in a fresh session, OR preserve the code (`.py`+`.json`, no raw PFF) to a durable
location first. The `.parquet` need not be preserved — it regenerates from the frozen scripts.


## FIRED 2026-07-20 — SPENT. Do not execute "THE FIRE" checklist again.

Appended 2026-07-27; nothing above this line was modified.

The one-shot fired exactly once on 2026-07-20. Outcomes are recorded in
`../PREREG_rookie_production_2026-07-20.md`, and `fire_rookie_results.pkl` sits in this
directory. Headline: the §8 claim was REJECTED — CatBoost full-vs-draft-only ΔAUC was only
+0.005, inside the placebo null of +0.069, and a college-only model scored 0.713 against draft
capital's 0.838. The product ships anyway, labelled BACKTESTED NOT LIVE-VALIDATED.

**The status header at the top of this file ("build complete, NOT fired" / "Blindness intact")
describes the state on the day it was written and is no longer true.** The checklist above is
history, not instructions: re-firing a spent one-shot would destroy the result.

**The preservation risk recorded below is DISCHARGED.** These files no longer live only in a
temp scratchpad — the harness was preserved into the repo at `fantasy/rookie/harness/`.