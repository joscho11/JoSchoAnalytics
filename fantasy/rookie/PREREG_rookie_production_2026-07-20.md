# PRE-REGISTRATION — ROOKIE PRODUCTION SCORE (2026-07-20)

**STATUS: DESIGN LOCKED, NOTHING FIT.** This file was authored in a scope/recon/design
session that fit NO model and computed NO feature-vs-target relationship. It freezes the
targets, thresholds, panel, feature set, models, and validation BEFORE any model sees the
data. Rules below are frozen; results go only in `## OUTCOMES` (appended after the fact,
rules never edited).

**AUTHOR / PROVENANCE.** Design ruled by Joseph 2026-07-20 (four rulings, all as
recommended): (1) hit thresholds QB12 / RB24 / WR24 / TE12; (2) feature set = all four
groups + age; (3) hit model = penalized logistic + CatBoost, both probability-calibrated,
nested-CV selection; (4) validation = temporal backtest + three-way ablation. Base rates,
panel counts, and combine-coverage numbers below were measured this session on observed
OUTCOMES only (never on features, never to tune a threshold).

**REVISION 2026-07-20 (pre-commit, still blind — one ruling + two fixes).** (1) MISSING-DATA
RULED (§5, §6) — omit-not-fabricate, per-model, with the college-only within-position-median /
no-flag / no-NaN "market back-door close" exception (the missing-data ruling is Joseph's; the
college-only close + the §7c-bis combine-out sub-arm were delegated to the intermediary).
(2) DECISION RULE (§8) — pinned the 5-fold held-out set (test classes 2019–2023, K=5), and
loosened consistency (c) to ≥3/5 and the per-position floor (d) to −0.030 scoped to RB/WR
(QB/TE reported descriptive/underpowered), with (a)/(b)/(e) held at H4/A4 severity
(intermediary drafted; Joseph steered the small-sample loosening). All edits blind; the
no-loosening ratchet binds from commit forward.

---

## 0. WHAT THIS IS / SCOPE

A per-position system that scores draftable NFL rookies for a "rookie board" page, with two
model outputs plus descriptive display:

- **(A) HEADLINE — HIT PROBABILITY 0–100:** calibrated probability the rookie becomes a
  productive NFL fantasy player, defined MULTI-YEAR (best of his first 3 NFL seasons). The
  new model this program builds.
- **(B) ROOKIE-YEAR PROJECTION (half-PPR PPG):** SURFACED from the existing rookie engine
  `fantasy/seasonal_projections/models/rookie_ppg_model.pkl` — NOT rebuilt here.
- **(C) DISPLAY (descriptive, not modeled):** each rookie's feature stat columns and his
  PERCENTILES within the whole college dataset.

This program is a PRODUCT that ships regardless, under honest labels (§10). It sits under
the H8r rookie fence and can never claim live accuracy until future classes accrue.

DRAFT CAPITAL IS AN ALLOWED FEATURE here — this is a production/projection model, not a
descriptive talent SCORE (the draft-capital exclusion applies only to the talent scores in
`fantasy/talent/`, which this file does not touch).

---

## 1. TARGETS

### 1A. HIT PROBABILITY (the new model, headline)

`hit = 1` iff the player's BEST positional finish over his first 3 NFL seasons ≤ the locked
position threshold (§2). "Positional finish" = rank within (season, position) by
**season-total half-PPR**, half-PPR computed as `fantasy_points + 0.5·receptions`
(regular season, the repo's own formula, `build_season_dataset.py:90`), 1 = best. Total
points (not PPG) is the finish convention because fantasy draft value is total season
output and rewards availability. Best-of-3 encodes "became a startable fantasy asset at
some point in his first three years."

### 1B. ROOKIE-YEAR PROJECTION (surfaced, not fit)

The existing CatBoost `rookie_ppg_model.pkl` (draft capital + combine + landing spot;
games-weighted, walk-forward-tuned, train 2014–2024 / holdout 2025). Documented standalone
rho ~0.26 vs ADP ~0.46 — it does NOT beat the market alone; blended 30/70 with ADP it lifts
the ROOKIE slice of the draft board (rho 0.457 → 0.488). This program wires its output to
the rookie board. **No fit, no retrain, no md5 change to this pkl is authorized by this
prereg.**

---

## 2. LOCKED HIT THRESHOLDS + OBSERVED BASE RATES

Thresholds chosen on FOOTBALL grounds only (top-24 = startable in a 12-team league; top-12
= weekly starter; QB in 1-QB leagues = top-12). NOT tuned to the data. Base rates measured
this session on the hit panel (§3), reported for design transparency (they are outcome base
rates, not a feature relationship):

| Pos | Threshold (meaning) | n drafted | n hit | base rate |
|---|---|---|---|---|
| QB | top-12 (weekly starter) | 101 | 15 | 14.9% |
| RB | top-24 (RB2, startable)  | 189 | 54 | 28.6% |
| WR | top-24 (WR2, startable)  | 290 | 47 | 16.2% |
| TE | top-12 (weekly starter)  | 132 | 19 | 14.4% |
| **All** | — | **712** | **135** | **19.0%** |

Disclosed honestly: (1) WR top-24 (16.2%) is rarer than RB top-24 (28.6%) because ~290 WRs
compete for the same 24 slots — a positional-supply effect, not a defect; thresholds stay
football-anchored. (2) QB (15 hits) and TE (19 hits) positive counts are thin → their
discrimination CIs will be wide; this is a pre-committed power caveat (§8), not something to
iterate around. These thresholds are LOCKED; no post-hoc threshold change (Amendment-4
prohibition applies).

---

## 3. PANEL DEFINITIONS + COUNTS

Universe = **drafted** skill-position rookies (QB/RB/WR/TE) from `nflreadpy.load_draft_picks`
(UDFAs EXCLUDED — draft capital is a core feature and the board is for draftable rookies;
the exclusion is disclosed and can be revisited only by a fresh blind prereg). Entry year =
draft season = first NFL season.

- **HIT TRAINING PANEL = entry classes 2015–2023 (9 classes, n=712).** A 2023 entrant has
  3 fully-observed seasons (2023/24/25) because the 2025 NFL season is complete as of this
  writing — so the panel legitimately extends one class past the prompt's "≈2014–2021"
  estimate. Per-class drafted counts (QB/RB/WR/TE): 2015 {7/18/34/19}, 2016 {15/20/31/11},
  2017 {10/27/32/14}, 2018 {13/21/34/15}, 2019 {11/25/28/16}, 2020 {12/18/35/12},
  2021 {10/19/35/11}, 2022 {9/23/28/19}, 2023 {14/18/33/15}.
- **SCORING SET = entry classes 2024–2026** (scored, NOT trained): 2024 {11/19/35/12}
  has 2 observed seasons, 2025 {14/25/30/16} has 1, 2026 {9/11/33/20} has 0. These accrue
  toward the future-class live test (§10).

No-censoring note: best-of-first-3 is well-defined even for players who leave the league —
absent seasons simply contribute no good finish; a player who never records a qualifying
season is `hit=0`.

---

## 4. FEATURE SET (grouped) + JOINS

All features are point-in-time AT DRAFT, so they precede the outcome by construction (no
target leakage possible). Five groups:

1. **DRAFT CAPITAL** — `draft_pick`, `draft_round`, `draft_ovr` (log-pick derived). This
   group alone is the DRAFT-CAPITAL-ONLY baseline (§7b). It is the MARKET.
2. **ATHLETIC / COMBINE** (`nflreadpy.load_combine`) — forty, vertical, broad_jump, cone,
   shuttle, bench, height (inches), weight + derived (BMI, speed score, weight-adjusted
   speed).
3. **COLLEGE BOX / PRODUCTION (cfbfastR)** — dominator, breakout class/age, receiving &
   rushing shares, YPC/YPR, career scrimmage yds/TD, final-season production, games
   (from `college_features.csv`).
4. **COLLEGE PFF (2014–2025, 11 tables/yr)** — position-specific: WR/TE receiving grade,
   YPRR, contested catch, drop rate, aDOT; RB rushing grade, forced missed tackles, YAC;
   QB passing grade, depth, pressure. *CAUTIONARY PRIOR: PFF-college was FIRED **DEAD**
   for the veteran talent latent (RB/WR/TE 2026-07-19). That is a different target; here it
   is a fresh question for PRODUCTION, carried with a low prior and measured by its own
   ablation (does PFF add beyond cfbfastR box).*
5. **AGE at draft** (breakout-age signal).

**Joins (verified this session):**
- Panel key = **`gsis_id`** (the repo's NFL `player_id`).
- Combine → panel: `load_draft_picks.pfr_player_id` → `load_combine.pfr_id`. Measured
  match to a combine row: **85.8%** of drafted skill players 2015–2022 (QB91/RB86/WR84/TE85%),
  84–93% on 2023–2025.
- College (cfbfastR) and College PFF → panel: by **`norm_name`** (~90%). There is NO shared
  college↔NFL id (cfbfastR uses ESPN ids, PFF its own ids, draft uses sports-ref slugs);
  the combine's own `cfb_id` is a sports-ref slug ≠ the cfbfastR ESPN id, so college cannot
  id-join to combine either. This corrects the "one global player_id namespace" prior:
  it holds for NFL/combine, not for college.

---

## 5. MISSING-DATA HANDLING (RULED — not a tuned choice)

Governing principle (Joseph, 2026-07-20): a missing combine value is OMITTED, never
fabricated — no missing measurable is filled with a feature average and used as if it were a
real measurement, and no player is dropped for missing combine (row deletion would gut the
2022+ classes and the scoring set, where the 40 falls to ~67–71% and bench/3-cone/shuttle to
~17–31%). Handled per-model:

- **CatBoost (primary/headline; full model + draft-capital-only baseline):** native NaN
  routing — a missing measurable stays NaN and the model learns a split for "unknown." This
  is the faithful implementation of "omit" (repo precedent, `rookie_features.py`); nothing is
  invented.
- **Penalized logistic (secondary comparator; full model + draft-only):** logistic cannot
  accept NaN, so it uses the missing-indicator method — each combine drill becomes (centered
  value, was-missing flag), the value set to 0 after centering. The flag makes a missing
  entry read as "unknown," NOT as a real league-average measurement — deliberately not naive
  mean-imputation. This is the only mechanically valid way to keep logistic under the
  no-fabrication rule; if the flag proves load-bearing it is disclosed.
- **COLLEGE-ONLY ablation arm ONLY (both families) — the market back-door close (intermediary,
  delegated 2026-07-20):** here combine missingness is made UNINFORMATIVE. Missing combine
  values are set to the within-position median with NO missing flag and NO NaN routing;
  measured values kept as-is. Rationale: combine missingness is non-random and proxies draft
  capital (elite prospects skip drills; late-round players run everything to prove themselves)
  — in the one arm whose job is to isolate signal INDEPENDENT of the market, the model must
  not reconstruct draft position from the pattern of what is missing. This is the single
  deliberate fill, used precisely because we do NOT want the model to see missingness there.

Asymmetry is intentional: the full model MAY exploit informative missingness (it is trying to
be the best predictor and already contains draft capital); the college-only arm MUST NOT. For
full-vs-draft-only (the §8 CLAIM gate) this asymmetry only makes the test more conservative,
so the headline is protected.

---

## 6. MODEL FAMILIES + NESTED-CV SELECTION PROTOCOL

Hit-probability model families (both compared):
- **Penalized logistic** (L2 / elastic-net), impute+flag inputs.
- **CatBoost** — pooled across positions with `position` as a categorical feature and the
  position-specific `hit` labels of §2 (shares strength across positions; helps thin
  QB/TE). House pattern (matches the existing rookie engine).

Both carry **PROBABILITY CALIBRATION** (isotonic or Platt, fit on inner out-of-fold
predictions — the headline is a probability, so calibration is mandatory).

**Selection is nested; feature-sets and missing-data are RULED, not tuned.** Missing-data
handling is RULED per §5 (not a tuned choice). Arm feature-sets (§7) are fixed by the
ablation, not CV-selected; the full model uses all five groups. Inner CV selects only
hyperparameters, regularization strength, and calibration method — on the training classes
only, by a proper score (log loss / Brier) ranked co-equally with fold consistency
(% positive folds — the D16/D17 lesson). No choice is made on the temporal hold-out; there
is NO peeking at the held-out later classes during selection.

---

## 7. VALIDATION DESIGN + THE THREE-WAY "BEAT DRAFT CAPITAL" TEST

**7a. Temporal backtest (primary framework).** Expanding-window over entry classes: train
on classes ≤ Y, score class Y+1, roll forward across the hold-out classes. Report on
held-out later classes only. Metrics, per position AND pooled:
- **CALIBRATION:** reliability curve + ECE (does a 30%-hit-prob cohort hit ~30%?).
- **DISCRIMINATION:** AUC (ROC), plus rank-correlation of predicted prob vs realized
  best-finish.

**7b. DRAFT-CAPITAL-ONLY baseline.** Same protocol, features = group 1 only. This is the
MARKET null — the rookie analog of the FAILED veteran "beat ADP" test (H4). Honest prior:
beating draft capital is HARD; the existing rookie PPG engine already fails to beat ADP
standalone.

**7c. COLLEGE-ONLY ablation.** Same protocol, features = groups 2–5 (attributes minus draft
capital). Measures whether college/athletic signal exists independent of the market, and
disambiguates a full-model edge from a draft-capital proxy (§5). Missing combine in THIS arm
is handled by the §5 market-back-door close (within-position median, NO missing flag, NO NaN
routing). The asymmetry is intentional: the full model MAY exploit informative missingness
(it already contains draft capital), this arm MUST NOT — it may not reconstruct draft
position from the pattern of what combine data is missing.

**7c-bis. COMBINE-OUT SUB-ARM.** Features = college box + PFF + age only (no combine at all,
hence no combine-missingness question exists in this arm). Reported as the cleanest read of
market-independent signal — a DIAGNOSTIC only; the §8 CLAIM gate stays full-vs-draft-only,
unchanged.

**7d. Sub-ablation.** Within the college-only arm, a PFF-in vs PFF-out contrast measures
whether PFF college adds beyond cfbfastR box (the §4 group-4 cautionary prior).

**7e. Placebo/permutation check.** Shuffle `hit` labels WITHIN (position, entry class),
1,000 draws; the observed full-vs-draft-only improvement must exceed the 95th percentile of
the shuffled distribution.

**7f. Blind power / MDE.** Before any fire, compute — using structure only (class sizes,
base rates, simulated placebo; ZERO outcome-vs-feature values) — the minimum detectable
full-vs-draft-only improvement at 80% power. Given thin positives (QB 15, TE 19), if the MDE
exceeds the decision threshold (§8), the position's discrimination test is recorded as
DESIGNED-BUT-UNDERPOWERED (an H5-style finding), not fired as decorative. A placebo-controlled
PASS stays meaningful regardless of power; low power inflates false negatives only.

---

## 8. DECISION RULE (the CLAIM gate) + PRE-COMMITTED OUTCOMES

The PRODUCT (full calibrated model's hit probabilities + percentiles + surfaced projection)
SHIPS REGARDLESS (§10). This decision rule gates only the CLAIM that **college/athletic
features add signal BEYOND draft capital**.

**Held-out fold set (PINNED):** expanding-window backtest, minimum 4 training classes; the 5
held-out test classes are **2019, 2020, 2021, 2022, 2023** (train ≤ Y−1, test Y, roll).
**K = 5.**

**Primary metric:** pooled OOS mean **log loss**, full model vs draft-capital-only.
**Co-primary:** pooled **AUC**. 3 decimals, pooled and per position.

**The CLAIM "college/athletic features add signal beyond draft capital" is ACCEPTED iff ALL hold:**
- (a) pooled OOS log-loss improvement Δ ≥ **0.010** absolute (full below draft-only);
- (b) pooled AUC improvement ≥ **+0.020**;
- (c) improvement positive in ≥ **3 of the 5** held-out folds (loosened from the impossible
  "≥6" — deliberately permissive given panel size, Joseph 2026-07-20);
- (d) among the adequately-powered positions (**RB, WR**), neither has AUC worse than
  draft-only by more than **−0.030**; QB and TE are underpowered (15 and 19 positives) and are
  reported as **descriptive** — they neither ratify nor sink the CLAIM;
- (e) passes the §7e placebo (observed Δ > shuffled 95th pct).

**One shot. Rejection final: no metric shopping, no alternative mappings, no threshold
changes, no panel swaps** (Amendment-4). (a)/(b)/(e) are held at H4/A4 severity; (c)/(d) are
the small-sample loosening and are **not loosened further post-commit.**

**Pre-committed outcomes (both directions):**
- **If the CLAIM PASSES:** the rookie board may state that college/athletic features add
  measured discrimination beyond draft capital, on held-out classes, backtested-not-live.
  It licenses nothing about live accuracy and nothing about beating ADP for veterans.
- **If the CLAIM FAILS (the honest prior):** report as-is — "the hit probabilities ≈ draft
  capital; college/athletic add no measured edge beyond the market." The product still ships
  (the full calibrated model is still the best available predictor and the calibration is
  the contribution), labeled with the null. This is the rookie H4 result and is NOT iterated
  around.

---

## 9. BLINDNESS DISCLOSURE (required reading before accepting this prereg)

No feature-vs-target relationship has been computed in this workspace for this program. This
session measured ONLY: combine drill coverage rates, join match rates, panel counts, and
outcome base rates at football-locked thresholds — all structure/outcome-only, never a
feature's association with the target, never a threshold tuned to a result. The thresholds
(§2) are football-anchored and inherited from standard fantasy startability, not chosen after
seeing model behavior. The PFF-college cautionary prior (§4) comes from the SEPARATE veteran
talent program (a different target) and is disclosed so it cannot be used to excuse or
inflate a result post-hoc. This prereg is therefore substantially BLIND on the hit-probability
question; Joseph ruled on the design (2026-07-20) before any fit. Amendments while still blind
are allowed only if each makes the test strictly harder, adds a disclosure, or pins an
underspecified rule.

The §5 missing-data ruling, the §8 fold-set/criteria, and the §7c revisions were made
2026-07-20 while still BLIND (no model fit, no feature×target computed) and before commit —
clean design edits, not post-hoc amendments; the no-loosening ratchet applies from Joseph's
commit forward.

---

## 10. SHIP-REGARDLESS + BACKTEST-NOT-LIVE

The rookie board ships with the label **"BACKTESTED, NOT LIVE-VALIDATED."** Hit probabilities
are calibrated on historical entry classes (2015–2023) and validated on a temporal hold-out
of later historical classes — a backtest, not a live forward test. The clean out-of-sample
test is FUTURE rookie classes; the first accrues at the end of the 2026 NFL season. Under the
H8r rookie fence, this product can NEVER claim live accuracy until future classes accrue.
Every displayed hit probability, and any public/video claim derived from it, carries the
backtest-not-live qualifier and its n / class range / baseline.

---

## 11. FENCES / WHAT THIS SESSION DID (AND DID NOT) DO

- Fit NO model; computed NO feature-vs-target relationship; tuned NO threshold to data.
- Did NOT touch: the frozen richer-talent harness `fire_pff_richer_rho.py`
  (sha `4402219c…`, SPENT — fired 2026-07-20, now archived in `pff/frozen_fires/`);
  `talent_score_2026.csv` and the
  rest of `fantasy/talent/` (owned by the talent thread, including the pre-existing dirty
  `PREREG_pff_richer_rookie_2026-07-20.md`); seasons 2008–2015 (sealed from market-evaluation).
- Combine/college/PFF recon written only to the session scratchpad; nothing else added to the
  repo besides this file and the new `fantasy/rookie/` directory.

---

## OUTCOMES (recorded after the fact; rules above were not modified)

**FIRED 2026-07-20 — ONE SHOT, run exactly once. Blind spent.** Frozen harness committed at
`fantasy/rookie/harness/` (harness.py sha256 `81b83a7f…`, assemble_panel `cd6d43cf…`,
assemble_features `3a530f2d…`, feature_groups `c44f322a…`; all re-verified == manifest at fire).
Interpreter: AI_hedge_fund venv. Panel reproduced 712 (135 hits); headline = CatBoost, full vs
draft-capital-only, pooled OOS on test classes 2019–2023 (391 rows). Build proofs (synthetic
noise/planted/peek + real-shape fire-path + decide self-test) all passed pre-fire; blind-MDE pooled
≈ +0.020 ΔAUC = the §8(b) bar (pooled gate adequately powered, not decorative; QB/TE descriptive).

**§8 CLAIM — "college/athletic features add signal beyond draft capital" — REJECTED (ACCEPT = False):**

| criterion | measured | bar | verdict |
|---|---|---|---|
| (a) pooled Δlog-loss | **+0.017** | ≥ 0.010 | PASS |
| (b) pooled ΔAUC | **+0.005** | ≥ 0.020 | **FAIL** |
| (c) folds improved | **2 / 5** | ≥ 3 / 5 | **FAIL** |
| (d) RB/WR per-pos AUC floor | RB −0.024, WR +0.001 | ≥ −0.030 | PASS |
| (e) placebo | obs **+0.005** vs shuffled-95th **+0.069** | obs > bar | **FAIL** |

Headline metrics (CatBoost, pooled OOS 2019–2023): **full log-loss 0.373 / AUC 0.843** vs
**draft-only log-loss 0.390 / AUC 0.838**. Draft capital ALONE reaches AUC 0.838; the full feature
set adds only **+0.005 AUC**, inside the placebo null (+0.069) → indistinguishable from zero. The
+0.017 log-loss gain is minor calibration refinement, not discrimination, and does not clear the joint
gate. Secondary comparator (logistic): full AUC 0.809 vs draft-only 0.862 — draft-only WINS; no
full-model edge in either family.

**Diagnostics (one mechanism covers all observations — the market already prices college/athletic):**
- **college-only** (attributes minus draft, §5 median-no-flag "back-door close"): CatBoost AUC **0.713**
  — real signal (≫ 0.5) but far below draft-only's 0.838.
- **combine-out** (college box + PFF + age, no combine): AUC **0.676**. Combine adds a little; the whole
  non-market bundle still trails draft capital badly.
- Per-position CatBoost full/draft AUC: QB 0.842/0.758, RB 0.853/0.877, WR 0.808/0.807, TE 0.867/0.856
  — mixed, no consistent edge (QB/TE reported descriptive/underpowered per §8d).

**Calibration (§7a):** log-loss (a proper, calibration-aware score) = **0.373** (full CatBoost). The
fire results pkl saved metrics only (no per-row y/p), so ECE / reliability is NOT computable post-hoc;
that would require a harness change — NOT done here (no re-fire, no harness edit). Log-loss stands as
the calibration-aware score.

**Pre-committed consequence (§8 FAIL branch — the honest prior; rookie H4 analog):** reported AS-IS —
**"the hit probabilities ≈ draft capital; college/athletic add no measured edge beyond the market."**
NOT iterated around. **Rejection is FINAL** (Amendment-4: no metric-shopping, no re-cut, no threshold
change, no panel swap). The PRODUCT SHIPS REGARDLESS (§10): the full calibrated CatBoost hit-probability
(AUC 0.843, log-loss 0.373, backtested 2019–2023) + the surfaced rookie-year projection + college
percentiles, labeled **"BACKTESTED, NOT LIVE-VALIDATED"** (H8r; first live test = the 2026 class).

**Board disclosure copy (ship-regardless):** "Rookie hit probabilities are calibrated on 2015–2023
draft classes and backtested on 2019–2023 (not live-validated). At this sample, college production and
athletic testing add no measured edge beyond draft capital — the probability tracks where a player was
drafted. Backtested, not live-validated; the first live test is the 2026 class."

Derived-only results archived at `fantasy/rookie/harness/fire_rookie_results.pkl` (metrics + verdict; no
raw PFF, no per-row values). Rules above (§0–§11) were not modified.
