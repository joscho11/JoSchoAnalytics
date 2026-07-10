# Pre-registration — seasonal projection Phase 1 (written 2026-07-09)

Committed BEFORE the extended-history (2002+) dataset or the 2008+ ADP benchmark
exists in this repo. Seasons 2008–2015 are an ADP-benchmarked evaluation slice that
has never been looked at by us or by any model in this project. This file locks the
hypotheses and decision rules so that slice is spent exactly once.

North star (set by Joseph, 2026-07-09): the target is to BEAT ADP within position,
walk-forward — not to beat Sleeper. Every result is reported against ADP first.

---

## H1 — The TE hypothesis: "a prior-stats model out-ranks ADP at TE"

**Origin.** Phase 0 (`phase0_benchmark.py`, 2026-07-09): our walk-forward Model A beat
FFC ADP at TE on 2016–2019 (Spearman ρ .400 vs .352, top-12 hit .771 vs .708, bust
29% vs 35%), but LOST at TE on 2020–2025 (ρ .308 vs .462).

**Recorded prior: this is NOISE.** It beat ADP by ρ ~.05 on four seasons of a ~24-deep
pool, then lost by ~.15 on the next six. Real edges don't flip sign like that. This
candidate emerged from scanning 4 positions × ~5 metrics × 2 panels (~40 comparisons);
the chance that SOME subgroup shows +.05 by luck is high. Expected outcome: rejection.

**The test (one shot, on unseen data).** After the extended rebuild, seasons
**2008–2015** (8 seasons, FFC ADP benchmark) are evaluated with the phase0 harness,
unchanged: pool = FFC ADP top-180 overall per season; our model = the shipped Model A
config (per-position LightGBM, injury features removed) retrained walk-forward on
seasons < t; metrics exactly as implemented in `phase0_benchmark.py` at commit time.

**Decision rule (written now, before the data exists):**
- **Primary metric:** mean within-season Spearman ρ at TE, ours vs ADP, 2008–2015.
- **CONFIRMED** only if BOTH: (1) pooled mean ρ_ours − ρ_ADP ≥ **+0.03**, and
  (2) ours wins the season-level ρ in **≥ 5 of 8** seasons.
- **Secondary consistency check (gating):** of top-12 hit rate and bust rate at TE,
  neither may favor ADP by more than a trivial margin (ADP better on BOTH ⇒ rejected
  even if the ρ rule passes).
- **REJECTED** otherwise. On rejection the TE claim is dead: no re-testing with
  different metrics, pools, sub-windows, model configs, or scoring adjustments.
- Confirmation does NOT mean "ship" — it graduates TE to a forward-tracked candidate.

**Pre-accepted caveats (may not be used post-hoc to excuse a failure):**
- FFC ADP 2008–2015 is standard-scoring (half-PPR doesn't exist that far back). TE
  scoring-format sensitivity is acknowledged and accepted now.
- The TE drafted pool is shallow (~24/season). The 5-of-8 seasons requirement exists
  because pooled ρ on shallow pools is noisy.
- 2008–2015 features will lack snap share (2013+) and have air-yards from 2006 only,
  with target_share reconstructed from raw targets for 2004–2008. Accepted now.

## H2 — The leakage fixes will make our current numbers WORSE

Phase 0 found `qb_changed` (season-N primary passer), `vacated_*` (full-season-N
rosters), and `team` (last team of season N) carry genuine hindsight. Our measured
walk-forward ρ of .30–.52 (2020–2025) is therefore **optimistically biased**.

**Pre-registered expectation:** after fixing (a) years_exp from draft year,
(b) qb_changed from preseason depth charts, (c) vacated_* from week-1 rosters,
(d) team = week-1 team, the model's ρ on the SAME 2014–2025 panel will DROP (or at
best hold). The rebuild report must show the two effects separately:
1. leakage fixes alone, old 2014–2025 panel (before vs after), THEN
2. history extension, on the corrected pipeline.
The extension is not allowed to mask the correction.

## H3 — Standing policy for subgroup claims

Any future "we beat ADP on slice X" claim (a position, an age band, post-hype
second-year players, rookies, etc.) gets this same treatment: one pre-registered
hypothesis appended to this file BEFORE evaluation on any unseen slice, with an
explicit decision rule, then exactly one test. Subgroup results discovered by
scanning are hypotheses, never results. The multiple-comparisons burden
(positions × metrics × panels) is on the claim, not on the skeptic.

---

## Amendment 1 (2026-07-09, committed BEFORE any extended data exists)

Pre-test decisions for the Step 1b extension. All four are one-way doors closed now;
source-coverage probes (row counts only — no outcome metrics) informed A2.

**A1 — Feature policy across eras: (ii) NaN-tolerant full set, frozen.** The TE test
evaluates the shipped config (per-position LightGBM, full feature set, native NaN
handling, no imputation, injury features excluded). Justification: (1) it is the
deployment config the hypothesis came from; (2) walk-forward training degrades
naturally to the era-common subset in early folds (a 2002–2007 training set simply
contains no snap/air-yards signal, so the model cannot lean on it), which biases
*against* confirmation rather than for it; (3) restricting to an era-common subset
would test a different, weaker model than the one that generated the hypothesis.
Era-availability/era-effect confounding is acknowledged and accepted.
`target_share` hole (2004–2008): filled with the reconstruction (player targets ÷
team targets) ONLY if Step 1b validation shows season-level correlation ≥ 0.95 and
|relative bias| ≤ 10% against the native series on overlap years; otherwise the hole
stays NaN. Rule fixed now, applied after validation.

**A2 — ADP series per era and the amended TE rule.** Per season, the deepest series
in preference order half-PPR > PPR > standard: Sleeper half-PPR 2020+, FFC half-PPR
2018–19, FFC PPR 2013–17 and 2010–11, FFC standard 2008–09 and 2012 (PPR too thin:
93 players). Pool = top-180 of that season's series (or all players if fewer).
**TE-gate seasons = 2010, 2011, 2013, 2014, 2015 only** (PPR-or-better with ≥150
players; standard-scoring seasons are excluded from the gate because standard ADP
underweights receptions and would bias the test TOWARD false confirmation at TE).
**Amended decision rule:** CONFIRMED only if pooled mean ρ_ours − ρ_ADP ≥ +0.03 over
those 5 seasons AND ours wins the season-level ρ in ≥ 4 of 5 (tightened from 5-of-8's
62.5% to 80% because fewer seasons carry less evidential weight). Secondary
consistency gate unchanged. 2008, 2009, 2012 are reported descriptively, never gating.

**A3 — Era normalization: none, frozen.** Target stays raw half-PPR PPG; season/era
is not a feature. The graded metrics are within-position-season rankings, which are
scale-invariant to era; point-scale metrics (MAE/VOR) on pre-2014 seasons are
descriptive only. If later development (on SEEN panels only) finds normalization
helps, that is a config change requiring a NEW pre-registered hypothesis — it may not
be swapped into this TE test.

**A4 — Extension gate (recorded).** The extension is adopted ONLY if the
corrected+extended model beats the corrected-only model on the SEEN panels:
pooled mean ρ across modeled positions on 2020–2025 improves by ≥ +0.01 AND
2016–2019 does not degrade by more than 0.01 (or vice versa). Anything else →
revert to 2014+ targets and record the negative. 2008–2015 is NOT the gate and no
model-vs-ADP metric may be computed on it outside the one-shot TE test.

## Amendment 2 (2026-07-09) — QB model dropped, measured negative

On the corrected panel the walk-forward QB model loses to its own null: ρ .268 vs
naive prior-season points .390 and ADP .431 (top-12 hit and bust rate agree). It was
also the position most inflated by the qb_changed hindsight fixed in Step 1a-2
(−.035 ρ on correction), it has the smallest sample (~750 usable rows, ~40 drafted
per season), and the naive baseline already encodes most of what prior stats know
about QBs. Decision: the QB model is DROPPED from the modeled set. QB on any board
falls back to market rank (ADP); the model-side null for QB in evals is naive
prior-points. The extension gate (A4) and all model-vs-ADP claims are computed over
RB/WR/TE. Headline hit-rate metric for QB and TE is top-12 (the drafted pool is only
~24 deep at those positions; top-24 is degenerate there). Revisiting QB requires a
new pre-registered hypothesis with a stated mechanism, not a re-run.

---

## Amendment 3 (2026-07-09) — A1/A4 conflict resolved BLIND; A4 terms pinned

Recorded with NO knowledge of any extended-data metric: at the time of this
amendment the extended dataset exists but no model has been trained on it and no
evaluation of any kind has been computed from it.

**D1 — The TE test is CONDITIONAL on A4 passing (option i).** The gate seasons
(2010–2015) can only be predicted walk-forward by a model trained on 2002+, so the
test presupposes the extension. Resolution: if A4 FAILS, we revert to 2014+ targets,
the TE hypothesis is recorded as **UNTESTABLE UNDER THIS DESIGN**, no test is run,
and seasons 2008–2015 remain unseen. Rationale for rejecting option (ii)
(decoupling): (1) testing a config that just measurably lost on the seen panels
builds in a post-hoc escape hatch — a rejection could be blamed on the weaker
config, voiding the rejection's finality; (2) a confirmation would be a claim about
a model we explicitly declined to deploy, which is not the hypothesis we care
about. Under (i) every outcome stays meaningful. A future TE-test design (e.g. a
2010+-trained panel model) would require a new pre-registered hypothesis and would
inherit 2008–2015 only if still unseen at that point.

**D2 — A4 pinned exactly.** Positions: **RB, WR, TE only** (QB was dropped by
Amendment 2, which predates any extended metric — the gate metric was defined over
"modeled positions" and the modeled set was fixed to RB/WR/TE before this gate was
ever computable; no silent change). Metric: per position, the harness ρ (mean of
within-position-season Spearman on the ADP-top-180 pool); "pooled" = unweighted
mean of the three per-position ρ values. Both configs (corrected-only 2014+ vs
corrected+extended 2002+) evaluated walk-forward with the frozen A1/A3 config on
identical pools. **PASS iff ALL of:**
  (a) Δ pooled ρ on 2020–2025 ≥ **+0.010**;
  (b) Δ pooled ρ on 2016–2019 ≥ **−0.010** (tolerance, not required to improve);
  (c) no single position's Δρ on 2020–2025 below **−0.030** (a large WR gain may
      not license a material TE/RB loss).
Numbers computed at 3 decimals; thresholds are as written; anything else → FAIL →
revert to 2014+ targets and record the extension as a measured negative.
Baseline (corrected-only, from `phase0_benchmark_results.json` at commit 5b846fd):
2020–2025 RB .520 / WR .500 / TE .323 (pooled .448); 2016–2019 RB .299 / WR .429 /
TE .392 (pooled .373).

**D3 — TE gate rule reconfirmed unchanged:** pooled ρ edge ≥ +0.03 AND ours wins
≥4 of 5 gate seasons (2010, 2011, 2013, 2014, 2015), top-12/bust consistency gate,
rejection final, no metric shopping. Runs only if A4 passes, in a fresh session,
exactly once.

*Diagnostic note (pre-declared, non-gating): after the A4 run we will report
whether the extended model uses era-missingness as a proxy (importance/split
counts on snap-share / air-yards features). It is explicitly not part of any
gate and cannot modify the frozen config.*

---

*Locked 2026-07-09. Harness of record: `phase0_benchmark.py` (+
`phase0_benchmark_results.json` for the Phase 0 numbers this file cites).
Amendments 1–2 added the same day, before any extended data was built.
Amendment 3 added the same day, after the extended dataset was built but before
any extended-data training or evaluation.*

---

## OUTCOMES (recorded after the fact; rules above were not modified)

**A4 extension gate: FAIL (2026-07-09, `extension_gate.py`, commit follows).**
Corrected+extended vs corrected-only, walk-forward, RB/WR/TE, identical pools:
2020–2025 pooled Δρ **+0.003** (< +0.010 required → criterion (a) fails);
2016–2019 pooled Δρ +0.058 (passes (b)); worst-position Δ −0.006 (passes (c)).
Per position, 2020–2025: RB +0.018, WR −0.006, TE −0.004; 2016–2019: RB +0.112,
WR −0.000, TE +0.062. Reading: doubling the history materially helps the panel
adjacent to the added seasons (2016–2019) but the gain decays to noise by
2020–2025 — the extension does not improve the deployment-era model.
**Consequences per Amendment 3 / D1:** deployed config reverts to (stays) 2014+
targets; the extension is recorded as a measured negative; **the TE hypothesis
(H1) is UNTESTABLE UNDER THIS DESIGN and the test will not run**; seasons
2008–2015 remain unseen by any model-vs-ADP metric. Any future TE-test design
requires a new pre-registered hypothesis.
*Pre-declared diagnostic (non-gating):* era-bound features rank mid-to-bottom in
the earliest extended fold (snap share 22–27/31, air-yards-share 12–15/31,
target share 7–15/31 by split importance) — no evidence the model leans on
era-missingness as a proxy; the null result above is not an artifact of that.

**H4 Step 2 residual model: FAIL (2026-07-10, `step2_residual_model.py --fire`,
sha256 57d36bab…, run exactly once).** Structural asserts and F5 provenance were
verified before firing (primary panel 100% Sleeper half-PPR; anchor = null;
λ=0 ≡ raw ADP exactly; all folds strictly walk-forward; no season < 2016
predicted). Result vs the rule: (a) pooled Δρ **−0.002** (< +0.020, FAIL);
(b) positive pooled Δ in **2/6** seasons (< 4, FAIL); (c) worst position −0.005
(pass); (d) top-12/bust identical to ADP (pass). The mechanism of the failure is
the pre-committed honest path: the inner walk-forward CV chose **λ = 0 (raw ADP)
in 28 of 30 position-folds** (TE 0.25 at t=2020/2021 only, which cost −0.005 TE
ρ out of sample). The 2025 diagnostic board is therefore all-zero corrections —
descriptive confirmation that the model has nothing to say beyond the market,
not a salvage. **Finding, as pre-committed in H4 §6: the market already contains
what our prior-stats feature set knows about drafted RB/WR/TE. The "beat ADP
with prior-stats features" question is CLOSED for this feature set. The product
direction is ADP plus a calibrated uncertainty band (Phase 4); the remaining
pre-registerable modeling angle is Step 3 (offseason/competition features), which
would require a new hypothesis and decision rule written blind.** Amendment 4
applies by analogy and was invoked in advance by Joseph: no λ-grid extensions,
no alternative residual mappings, no panel swaps.

---

## Amendment 4 (2026-07-09) — standing prohibition: no gate-shopping the failed A4

The A4 extension gate failed and the per-panel deltas are now known (2016–2019
moved, 2020–2025 did not). We will NOT search for an extension variant that
passes: no alternative history cutoffs (2010+, 2012+), no recency-weighted
sample weights, no era subsets, no re-pooling — any such attempt chosen AFTER
seeing which panels moved is gate-shopping on a question already answered
negatively. A future revisit requires a fresh pre-registration with a decision
rule written blind to any new variant's results, and must open by acknowledging
it is a second look at an answered question. (This mirrors the repo's 2026-05
time-decay/extended-training rejection on the spread model: same lever, same
verdict, same rule against re-running it.)

---

## H4 — Step 2: ADP-anchored residual model (pre-registered 2026-07-09,
## committed BEFORE any Step 2 code or metric exists)

**Architecture under test.** Final projection = ADP-implied points + shrunk
learned correction. The market prior is the anchor; the model learns only where
the market is systematically wrong, from the frozen prior-stats feature set.

**1. The null is RAW ADP, unchanged.** The gate compares the residual model to
using ADP as-is on identical pools. Secondary comparisons, reported as context
and never gating: the corrected from-scratch model (2020–2025 ρ RB .520 /
WR .500 / TE .323) and Sleeper preseason. Positions RB/WR/TE; QB stays market
rank per Amendment 2.

**2. Scope (decided blind): a better RANKER OF THE DRAFTED POOL, only.**
Step 2 makes no claim about undrafted players and is not a discovery engine.
No hybrid stitching in this test — the from-scratch model already exists as the
fallback for ADP-less players on any board, and a hybrid would add a second
moving part to a one-shot test. The eval pool stays ADP top-180 (consistent
with phase0), which by construction CANNOT detect the undrafted-breakout blind
spot; if we ever want that measured, it needs its own pre-registered test with
a different pool. Recorded now so the limitation is on the claim, not
discovered after it.

**3. Residual target (frozen): points-space vs a walk-forward ADP curve.**
For eval season t, fit per position a monotone-decreasing curve (isotonic
regression) of actual season half-PPR points on within-position ADP rank using
ONLY seasons < t; implied_pts = curve(adp_pos_rank); residual target =
actual_pts − implied_pts (zero-game seasons keep their real, near-zero
actuals). Reason for points-space over rank-space: the output remains a real
point projection (compatible with the harness's VOR/MAE metrics and any board),
and the positional draft-value curve is the natural, standard prior. This is
the only mapping that will be tried.

**4. Shrinkage and tuning policy (frozen).** Correction applied as
final = implied + λ·residual_pred, λ ∈ {0, 0.25, 0.5, 0.75, 1.0} selected PER
POSITION by walk-forward CV strictly inside the training window (for eval
season t, inner folds only use seasons < t). Model = the frozen A1/A3 LightGBM
config and feature set, unchanged — no new hyperparameter search, no feature
selection, nothing chosen on the evaluation panel. Note λ=0 recovers raw ADP
by construction, so the inner CV is free to conclude the correction is
worthless; that is the honest path to the negative in (6).

**5. Decision rule (exact, one test).** Primary panel 2020–2025, ADP-top-180
pool, harness metrics, positions RB/WR/TE, pooled = unweighted mean of
per-position ρ (matching A4's D2 definitions). ADOPT iff ALL of:
  (a) pooled Δρ (residual model − raw ADP) ≥ **+0.020**;
  (b) the pooled season-level Δ is positive in **≥ 4 of 6** seasons;
  (c) no position's Δρ vs raw ADP below **−0.010**;
  (d) consistency: pooled top-12 hit rate and bust rate are not BOTH worse
      than raw ADP.
2016–2019 is reported as context only (FFC format proxies make it a noisier
ADP null; it does not gate). Numbers at 3 decimals. Rejection is final: no
metric shopping, no alternative residual mappings, no λ-grid extensions.

**6. The negative is pre-committed as acceptable.** If the inner CV collapses
λ to ~0 or the gate fails, the finding is: the market already contains what our
prior-stats features know, and the honest product is ADP plus a calibrated
uncertainty band (Phase 4 direction: distributions and bust probabilities on
top of market rank). That outcome will be reported as-is and not iterated
around; it would close the "beat ADP with prior-stats features" question for
this feature set, leaving offseason/competition features (Step 3) as the
remaining pre-registerable angle.

---

## OUTCOMES ADDENDUM — benchmark provenance audit (2026-07-10, Sub-steps H+J+K)

**Verdicts: Sleeper 2020 projections VOID; ADP CLEAN (all seasons); ffc_adp /
ECR / naive_pts CLEAN. A4, H4, and the Step 2 FAIL all stand — their null
(raw ADP) and the top-180 pool were never contaminated.**

- *Sleeper `sleeper_pts_half_ppr`*: fetched live-for-completed-seasons
  (`fetch_adp.py`), but Sleeper's backend serves a frozen artifact (0 changed
  values across three git pulls spanning a month). **2020's stored values are
  near-actuals**: `gp` varies per player and correlates **+0.908** with actual
  games played; Mixon "projection" 88.0 / gp 6 vs actual 89 pts / 6 games;
  Barkley 35.1 / gp 2 (week-2 ACL); corr(proj, actual) 0.968 vs 0.81–0.86 in
  every other season. **2021–2025 pass every probe** (constant full-slate gp;
  injury busts keep high projections — Henry-21 270, Kupp-22, Burrow-23,
  CMC-24 250; unknowns stay tiny — Purdy-22 49.7). 2020 quarantined at source
  (`fetch_adp.py`), in the cache, and in the rebuilt dataset.
- *ADP — the null in A4/H4 and the pool definition*: **CLEAN.** The same
  players that convicted the projection column acquit ADP (2020 Barkley ADP
  rank 4, Mixon rank 6); no 2020 outlier in corr(ADP, actual) (.720 vs
  .711/.724 neighbors); the aggregate is late-frozen preseason (Dobbins, ACL
  Aug 28, stored at rank 268 — repriced) with no detectable post-week-1 bleed
  (Puka-23 at 248 despite a top-30 week-2 value). ffc_adp: clean on
  inspectable panels (Luck absent from 2019 post-retirement); **2008–2015
  assessed at provenance level only — outcome correlations were deliberately
  NOT computed there** (preserved unseen slice). ECR: timestamped scrape
  archive. naive_pts: internal, snapshot-pinned.
- **Recorded BEFORE the ex-2020 numbers existed** (Joseph's condition):
  excluding 2020 LOWERS Sleeper's measured skill and therefore FLATTERS our
  models. The exclusion rests solely on provenance evidence about the
  artifact, not on any property of the comparison.
- *Ex-2020 restatement* (`recompute_sleeper_ex2020.py`; footnote for every
  figure: n=5 seasons 2021–2025, 2020 excluded for provenance): Sleeper ρ
  QB .578 / RB .711 / WR .659 / TE .544 (was .636/.754/.707/.609) vs ADP
  .420/.585/.571/.454. **"We lost to Sleeper" survives at n=5, margin
  reduced.** The three-way-blend claim does NOT survive: harness restatement
  (frozen 0.2/0.3/0.5 weights, 2021–2024) gives blend .685 vs Sleeper alone
  .711 — the blend is no longer shown to beat Sleeper alone, and the original
  weights were tuned on data including the voided season (doubly affected).
  README claims struck through, not edited. eval_totals: unaffected (its eval
  window was already 2021–2025).

**Named confound (recorded blind, before any test using it is designed):
SLEEPER FRESHNESS ASYMMETRY.** Sleeper's projection is a week-1-eve snapshot
(Puka-23: projection 186 vs ADP 248, dated by Kupp's Aug 31 IR); ADP is an
aggregate of drafts across the summer — late-frozen and largely repriced
(Dobbins), but still an average including pre-news drafts. An unknown share of
Sleeper's remaining ρ edge over ADP is therefore not forecasting skill but
information that did not exist when part of the market drafted (last-days camp
injuries, depth-chart decisions). This confound attaches to EVERY
Sleeper-vs-ADP comparison in this repo, including the surviving 2021–2025
numbers. Any future value-signal test built on projection-rank minus ADP-rank
disagreement risks measuring nothing but post-ADP news — actionable only for a
drafter using a same-day snapshot in a late draft. Stated now, blind; any such
test's pre-registration must confront this in its claim.

---

## H5 — The value-signal hypothesis: Sleeper-vs-ADP disagreement predicts ADP error
## (pre-registered 2026-07-10, BEFORE any code or metric for it exists)

**Blindness disclosure (required reading before accepting this prereg).** No
systematic disagreement list has ever been printed in this project. However,
during the provenance audits (Sub-steps H+J) ~a dozen individual rows showing
both a player's ADP and Sleeper projection were examined, several selected
BECAUSE they were famous breakouts/busts (Puka-23, Deebo-21, Conner-21,
Patterson-21, M.Williams-23, the injury quartet, Purdy-22), and the
disagreement direction was explicitly reasoned about for some. That is an
outcome-selected anecdote sample — nearly uninformative about aggregate signal
skill, but a possible anchor on design choices. Mitigation: every numeric
choice below is inherited from a pre-existing repo convention or an
already-frozen H4 mechanism, none is newly invented. The prereg is therefore
PARTIALLY blind, declared as such; Joseph rules on acceptability before firing.

**L1 — Amendment 4 ruling (written first).** H4 asked whether OUR prior-stats
FEATURES carry information beyond ADP; answer: no. H5 asks whether SLEEPER'S
projection, through its disagreement with ADP, carries information beyond ADP.
Different signal source (an external vendor snapshot vs our feature set), same
null. The claim also differs in kind: an H5 positive is explicitly NOT alpha —
it is a measurement claim about a public source (see L5). Honest reading: a
genuinely different hypothesis, not a variant of H4 tuned to pass; NOT
Amendment-4 gate-shopping. One Amendment-4-adjacent burden is acknowledged:
this is the SECOND hypothesis tested against the raw-ADP null, and serial
testing against one null inflates family-wise error — per H3 the
multiple-comparisons burden sits on the claim, so the decision thresholds
below are set at H4's severity, not relaxed.

**L2 — Signal, one definition, frozen.**
value_signal_i = adp_pos_rank_i − sleeper_pos_rank_i, computed within position
and season on the ADP-top-180 pool (phase0 convention), where sleeper_pos_rank
ranks `sleeper_pts_half_ppr` descending within position. Positive = Sleeper
ranks the player materially better than the market (undervalued candidate).
Rows with no Sleeper projection (≤3% of pool) cannot express disagreement:
excluded from signal buckets, retained in all outcome-rank denominators.
**Panel: 2021–2025 only** — 2020 is excluded because its stored projections
are near-actuals (H2/J finding, quarantined at source). **QB is IN SCOPE:**
Amendment 2 dropped the QB MODEL (our model lost to its own null); this signal
uses no model of ours, Sleeper's QB edge is the largest on the corrected board
(.578 vs .420), and excluding the strongest a-priori slice from a signal test
would be unprincipled. Positions = QB/RB/WR/TE; pooled = unweighted mean over
the four (A4/H4 pooling convention, extended to include QB for this test).

**L3 — Hypothesis, test, decision rule.**
- *Materiality threshold (one value, inherited):* |value_signal| ≥ **8**
  within-position ranks — the shipped value board's HIGH-confidence gap
  (`build_value_board.py`, HIGH = gap ≥ 8), a convention that predates this
  test. Undervalued bucket: signal ≥ +8. Overvalued bucket: signal ≤ −8.
- *Outcome measure (inherited from H4's frozen mapping):* per player,
  perf_i = actual_pts_i − implied_pts_i, where implied_pts is the per-position
  isotonic curve of actual points on adp_pos_rank fit walk-forward on ADP
  seasons < t (same machinery as `step2_residual_model.py`; ADP is audited
  clean, so curve-fit seasons include 2020).
- *Statistic:* Spread(s,p) = mean(perf, undervalued) − mean(perf, overvalued),
  per season and position; a position-season contributes only if BOTH buckets
  have ≥ 3 players. Pooled spread = unweighted mean over contributing
  positions, then seasons.
- *Decision rule — PASS iff ALL of:*
  (a) pooled Spread ≥ **+15 points** (~0.9 PPG bucket separation; ≈3 SE at the
      expected pooled bucket sizes);
  (b) the season-level pooled Spread is positive in **≥ 4 of 5** seasons;
  (c) per-position floor: no position's pooled Spread below **−10 points**;
  (d) sanity: a pre-declared permutation placebo (signal shuffled within
      position-season, 1,000 draws) puts the observed pooled Spread above the
      95th percentile. (a)–(d) all required. One shot. Rejection final: no
      threshold changes, no alternative outcome measures, no panel swaps.
- *Null:* raw ADP unchanged — under it, both buckets have expected perf ≈ 0
  and Spread ≈ 0. Buy-side (U) and fade-side (O) contributions are reported
  separately but do NOT gate (prior repo knowledge that fade-side signals have
  been weaker is disclosed here and priced into the choice to gate on the
  combined spread only).

**L4 — The freshness confound rides on the claim (per the K4 named confound).**
A PASS licenses ONLY: "late-window Sleeper-vs-ADP disagreement predicts ADP
error — actionable for a drafter holding a same-day projection snapshot in a
late draft." It does NOT license a standing market-inefficiency claim, because
Sleeper's snapshot postdates part of the drafting window (Puka-23). *Pre-declared
SECONDARY analysis (gates nothing):* the same Spread computed on the
STABLE-ROLE subset — veterans (is_rookie == 0) on the same team as the prior
season with prior_games ≥ 14 — players whose late-August news exposure is
mechanically smallest. Reported with the same statistic and no threshold: if
the spread survives there, the news-only explanation weakens; if it vanishes,
the confound likely explains the primary result. Defined blind from existing
dataset columns; not a gate; may not be promoted to one after the fact.

**L5 — Both outcomes pre-committed.**
- *Negative:* Sleeper's disagreement with ADP carries nothing beyond ADP once
  bucketed at the shipped threshold. The point-estimate question is then
  closed for PUBLIC sources too (our features: closed by H4; the sharpest
  public projection's disagreement: closed by H5) — the product is a
  projection (Sleeper's or ADP) plus OUR calibrated uncertainty band, and the
  band is the whole contribution.
- *Positive:* we are reselling Sleeper's self-disagreement. The contribution
  is measurement and calibration — verifying, sizing, and bounding a public
  signal — not alpha, and any product surface built on it must say so
  explicitly ("powered by Sleeper's projections vs the draft market", not "our
  model finds value").

**L6 — What this does not test.** Undrafted players (outside the ADP pool, as
in H4 — the discovery blind spot remains unmeasured). Any other signal
definition: ECR-vs-ADP, our-model-vs-anything, magnitude-weighted or
continuous variants, other thresholds, other panels. Transfer to 2026 drafts.
Cross-vendor generality (this is a claim about one vendor's snapshot). Each of
those would need its own pre-registration.

*Locked 2026-07-10, before any H5 code exists. Fires exactly once, next
session, conditional on Joseph accepting the blindness disclosure above.*

---

## H5 Amendment 1 (2026-07-10, Sub-step M) — units fix + primary/secondary swap
## Amended BLIND: no H5 metric of any kind exists at commit time.

**Hardness assertion (checked change-by-change before writing):** every
amendment below either makes the test strictly HARDER or scale-corrects an
incoherent unit — none loosens a gate by choice. The two disclosures required
by that assertion: (1) converting the invented +15-point bar to a uniform
effect size makes the bar nominally softer at TE than the OLD BAR'S ACCIDENTAL
implication there (old +15pts ≈ 0.33σ at TE vs 0.20σ at QB — the incoherence
being corrected); it is strictly harder at QB and RB, where the old bar was
weakest and where scope was newest. (2) The per-position floor on the new
primary is unassessable at QB/TE for feasibility reasons measured blind (bucket
counts below), not by preference. Everything else is unchanged or harder.

**M1 — Units fix (the pooling bug).** The original H5 statistic pooled raw
points across positions whose season-total scales differ ~3× (QB vs TE), so
"+15 points" meant different severities per position and QB would have carried
the pool. Restated scale-free, adopting Joseph's proposal: per position-season,
effect size d = [mean(perf, undervalued) − mean(perf, overvalued)] / SD(perf),
where perf = actual − ADP-implied (unchanged) and SD(perf) is taken over ALL
pool rows of that position-season (more stable than tiny-bucket SDs and not
gameable). Standardizing perf within position-season to z-scores makes d
identical to the bucket-mean difference of z — used below for cross-position
pooling. **Re-pinned thresholds, with provenance:**
- PASS effect size: **d ≥ 0.25** — proposed by Joseph in the M2 instruction
  before any H5 number existed; coincides with Cohen's small-to-medium
  convention (external, pre-dating this project). NOT invented post-Puka.
- Per-position floor: **d ≥ −0.10** — strictly harder than the old −10-point
  floor at every position (old implied tolerances 0.13–0.22σ).
- ≥ 4 of 5 seasons positive: UNCHANGED. 95th-percentile permutation placebo
  (1,000 draws, signal shuffled within position-season): UNCHANGED.

**M2 — Threshold provenance, answered honestly.** |gap| ≥ 8 is verifiably
inherited (shipped board HIGH tier, predates this test). **+15 and −10 were
INVENTED by the author of this prereg after seeing the Puka row**; the
"≈0.9 PPG / ~3 SE" framing was written after the number was chosen and does
not constitute inheritance. Both numbers are dead. Their replacements (d ≥
0.25, floor −0.10) derive from Joseph's blind proposal and from the
strict-dominance argument above, respectively.

**M3 — Primary/secondary swap (the gate moves to the informative question).**
Argued before amending: a globally better ordering does not LOGICALLY entail
informative tail disagreements (the ρ edge could live in ubiquitous small
adjustments while |gap|≥8 rows are algorithmic-quirk noise), but it makes a
full-pool PASS largely EXPECTED given the measured +0.09–0.16 ρ edge — high
prior probability, low likelihood ratio, weak evidence. The asymmetry is
recorded: a full-pool FAIL would be surprising and strongly informative. The
gated question becomes the one that separates "Sleeper forecasts better" from
"Sleeper's snapshot postdates the market":

- **PRIMARY (gates the headline claim): the STABLE-ROLE subset spread.**
  Subset pinned exactly: is_rookie == 0 AND context_team(season N) ==
  team(season N−1), both non-null, AND prior_games ≥ 14. Computed on the
  ADP-top-180 pool, 2021–2025, |gap| ≥ 8 buckets, missing-projection rows
  excluded from buckets as before.
  *Blind feasibility check (counts only, no outcomes, no names), as ordered:*
  per-position-season both-buckets-≥3 holds in WR 4/5, RB 1/5, QB 0/5, TE 0/5
  — the original per-position pooling is INFEASIBLE on this subset. **Minimal
  relaxation, chosen now:** buckets pool ACROSS POSITIONS within each season
  on within-position-season z-scored perf (the M1 units make rows
  comparable); season-level bucket sizes are then +5/−8, +14/−14, +7/−3,
  +18/−6, +5/−6 — all five seasons feasible with the ≥3 rule intact. The
  subset definition itself is NOT relaxed (the confound control is the point
  and is untouched). Consequence, disclosed: the primary's per-position floor
  is only assessable at RB and WR (reported per-position d; neither may fall
  below −0.10); QB/TE cannot form buckets at this threshold on this subset
  and are reported descriptively only.
  *Primary decision rule — PASS iff ALL of:* (a) 5-season mean z-spread
  ≥ **0.25**; (b) season-level z-spread positive in **≥ 4 of 5**; (c) neither
  RB nor WR subset-d below **−0.10**; (d) observed 5-season mean above the
  **95th percentile** of the within-position-season permutation placebo.
  One shot. Rejection final.
- **SECONDARY (descriptive, gates nothing): the full-pool spread** — the
  former primary, in M1 units, per-position pooling with the four-position
  −0.10 floor reported. Pre-stated: a PASS here is largely expected from the
  corrected ladder and is therefore WEAK evidence; it may not be cited as
  confirmation of anything beyond itself.
- **Four-way reading, pre-committed verbatim:** full-pool passes + stable-role
  passes = real forecasting edge, actionable in a normal draft. Full-pool
  passes + stable-role fails = the freshness confound explains the signal;
  post-ADP news only, usable solely with a same-day snapshot. Full-pool fails
  = disagreement carries nothing; H5 negative; product = projection + our
  calibrated band. Stable-role passes while full-pool fails = incoherent;
  reported as such and not rescued.

**M4 — Carried over unchanged.** Buy/fade sides reported separately, gating
nothing. L5's pre-committed outcomes stand verbatim with "the spread" now
meaning the PRIMARY (stable-role) spread; L4's licensing language tightens
accordingly: even a full four-way positive licenses "verified, sized public
signal," never alpha. L6 unchanged.

*Amended 2026-07-10 before any H5 code exists. Sub-step N (build + structural
asserts, F/G split) awaits Joseph's approval of this amendment; the shot
itself gets a fresh session.*

---

## H5 Amendment 2 (2026-07-10, Sub-step M2) — power, the five-way reading,
## signal-units disclosure, pins. Amended BLIND: no H5 outcome metric exists.

**Hardness assertion:** every change below weakens a CLAIM we are licensed to
make, adds a disclosure, or pins an underspecified rule more strictly. No gate
is loosened. The one feasibility-forced pin (the floor's pooling, P4) is the
only precise definition the measured bucket counts permit and is disclosed as
such.

**P1 — Power, computed blind (bucket sizes + unit variance only, zero
outcomes; simulation of the exact joint rule, 20,000 trials, per-trial
1,000-draw placebo).** SE of the 5-season mean z-spread at the real bucket
sizes (+5/−8, +14/−14, +7/−3, +18/−6, +5/−6): **0.248**. Null placebo 95th
percentile: **0.406** — **criterion (a) at d ≥ 0.25 is DECORATIVE; the
permutation placebo binds.** Joint false-positive rate under the null: 4.1%
(controlled). Joint power: **13.2% at true d=0.15, 24.4% at d=0.25, 45.7% at
d=0.40, 75.2% at d=0.60. MDE at 80% power ≈ d 0.65.** Joseph's pre-stated
estimates (power 15–25% at the PASS bar, placebo ≈ 0.41, MDE near 0.60) are
confirmed, with the MDE slightly worse than estimated.

**P2 — The five-way reading (replaces the four-way; claims weakened, gates
unchanged).**
- A primary FAIL is reported, in the headline, as: **"FAIL (underpowered:
  MDE = 0.65; true effects up to d ≈ 0.65 are not excluded)."**
- "Full-pool passes + stable-role fails" now reads: **the freshness confound
  is NOT EXCLUDED and the signal is NOT ESTABLISHED** — inconclusive on the
  confound question, not a verdict against the signal.
- INCONCLUSIVE and NEGATIVE have the same product consequence (Phase 4:
  projection + our calibrated uncertainty band). The decision does not hang
  on the underpowered test.
- The asymmetry is recorded: the placebo controls the false-positive rate
  regardless of power, so **a PASS remains meaningful and trustworthy; low
  power inflates false negatives only.**
- **Is firing worth it? Plainly: NO, not as a gate.** With ~24% power at a
  true d=0.25, the modal outcome of firing against a genuinely moderate
  signal is an uninformative FAIL; the only decision-changing outcome is a
  ~24%-probability (FPR-controlled) PASS; and both non-PASS outcomes lead to
  the same Phase-4 product anyway. The descriptive quantities Phase 4
  actually needs (full-pool spread, buy/fade asymmetry, calibration inputs)
  can be produced under Phase 4's own measurement pre-registration without
  spending a one-shot on an underpowered gate. **Recommendation: do not fire;
  record H5 as DESIGNED-BUT-NOT-FIRED (an underpowered-design finding, not a
  negative); the properly powered instrument for the confound question is the
  dated-ADP design (P5).** Joseph rules; if he orders the shot anyway, this
  amendment's expectations govern the reading.

**P3 — The signal threshold has M1's bug on the other axis (disclosed, number
unchanged).** |gap| ≥ 8 position ranks is not scale-free: it is ~1/3 of a
~24-player QB/TE drafted pool and ~1/9 of a ~72-player WR pool, so the signal
bar is far more severe in small pools — very likely why QB/TE produce 0/5
feasible bucket-seasons. **The number is NOT changed**: it is the only
threshold with clean provenance (shipped board HIGH tier), and changing it
after seeing feasibility counts would be threshold-shopping with counts as
the data. Consequences, disclosed: (1) the primary is **effectively an RB/WR
test** — of the 86 pooled stable-role bucket rows, WR contributes 52 (60%),
RB 27 (31%), QB 4 and TE 3 (~8% combined); the four-position label is
retired from the primary's description. (2) The earlier "free observation"
(that large disagreements "barely exist among stable-role veterans and
concentrate in unstable situations") is **RETIRED AS STATED and requalified**:
it is partly an artifact of a fixed rank threshold meeting pools of different
sizes, it fed the pooling relaxation, and it may not be read as evidence for
the confound story.

**P4 — Three pins, blind.**
- *Per-position floor (RB/WR, d ≥ −0.10):* computed **pooled across all five
  seasons** (all subset bucket rows of the position pooled in z units, one d
  per position; RB pooled buckets +14/−13, WR +29/−23 — both assessable). A
  per-season-averaged floor is infeasible (RB has both-buckets-≥3 in 1 of 5
  seasons); the pooled rule is the only precise definition available and is
  pinned now.
- *Primary placebo:* the signal is shuffled among **STABLE-ROLE rows only**,
  within position-season. Confirmed and pinned — shuffling among all pool
  rows would test the wrong null (exchangeability must be conditional on the
  subset).
- *`team` provenance (J-class check, proved from code):* the feasibility
  script and the subset definition read `team` from `season_dataset_2014_2025
  .csv`, whose output team is `context_team.fillna(team)` — the WEEK-1 roster
  team from the snapshot-pinned `rosters_weekly_w1` (build_season_dataset.py
  fix (c), line 461); prior-season team is the dataset's own (player, N−1)
  row. The Sleeper join contributes only ADP/projection fields (keep-list,
  line 465) — no Sleeper roster/team field touches the subset. NOT leaky;
  P1's counts stand. Residual, disclosed: context_team coverage is 95%
  (Step 1a), so ~5% of rows fall back to last-stats-team and could be
  misclassified into/out of the subset; bounded, not voiding.

**P5 — Design cost, for the record.** The J audit established ADP is ALSO
late-frozen (it repriced Dobbins on Aug 28 and Akers on Jul 19), so the
freshness confound is narrow — last-days news, the Kupp-IR→Puka class, a
handful of rows per season. To control for that narrow confound, the
stable-role subset strips every rookie, team-changer, and low-prior-games
player (~40–60% of the pool) and thereby spends nearly all the statistical
power (P1). A properly powered test of the confound would use a **DATED ADP
series** (e.g. FFC publishes ADP by draft-date window) to measure the
freshness effect directly instead of proxying it by subset exclusion. That is
a future pre-registration with a fresh data pull; nothing about it may be
attempted now.

*Amended 2026-07-10, blind. Sub-step N remains unwritten; whether the shot is
fired at all now awaits Joseph's ruling on P2's recommendation.*

---

## H5 Amendment 3 (2026-07-10, Sub-step Q) — laundering ruling + design ruling.
## Amended BLIND: no outcome metric on the disagreement axis has ever been computed.

**Q1 — Ruling: (a). H5 stays FULLY unfired.** Nothing on the disagreement axis
— no full-pool spread, no buy/fade asymmetry, no bucket means, no
disagreement-conditioned statistic of any kind — may be computed in Phase 4 or
anywhere else without a fresh pre-registration. Phase 4's scope is pinned to
functions of (point estimate, actuals) only: residual distributions, quantile
coverage/pinball, P(top-12 | rank), bust probability. **Confession, on the
record:** the not-fired recommendation in Amendment 2 named "full-pool spread,
buy/fade asymmetry" as Phase-4 deliverables — that WAS the laundering pattern
(H5's secondary renamed), caught by Joseph, struck here. Option (b) is refused
because firing the secondary alone harvests a pre-declared-weak number AND
leaks full-pool outcome structure that would unblind any better-instrument
test on the same rows. **Product-surface confession:** the shipped board
already displays a cousin of the signal (the Sleeper-rank comparison column,
the `sleeper_agrees` flag, and the "Consensus values" box gated on it) — the
product ships a form of the H5 claim today, unvalidated. Labeling duty,
pre-committed: until a pre-registered test on this axis PASSES, any surface
displaying Sleeper-vs-ADP agreement must carry "sized but unvalidated;
freshness confound not excluded"; if H6 (below) passes, the label may soften
only to "signal validated in aggregate; threshold tiers unvalidated" — because
H6 does not test the tier convention.

**Q2 — Ruling: the continuous statistic is legitimate design, not
gate-shopping — under three conditions, all adopted.** The case FOR: zero
outcomes on this axis exist (only bucket counts and power simulations);
changing statistic before any outcome look is design iteration; subset,
confound control, conditional placebo, seasons rule, and pooling convention
all survive; it uses the 473 stable-role rows instead of 86. The case
AGAINST, stated fairly: it raises P(PASS) — resolved by the distinction that
the permutation placebo pins P(PASS | null) at 5% while only P(PASS | real
effect) rises, which is instrument quality, not gate softness; it abandons
|gap| ≥ 8, the only clean-provenance threshold — true, unfixable, and
therefore the continuous test DOES NOT test the board's convention; and it is
a different hypothesis (magnitude tracks error monotonically vs large
disagreements predict) — resolved by giving it a different name. Conditions:
(1) fresh prereg H6, hypothesis relabeled; (2) H5's bucket design recorded as
ABANDONED ON POWER GROUNDS BEFORE ANY OUTCOME EXISTED — retired unfired, not
partially fired; (3) H6's non-licenses explicit. **Design cap, adopted from
Joseph's Q3 clause: two designs is the limit. Had the continuous design also
been underpowered, H5/H6 would have closed unfired — no third statistic.**
Statistic pinned: **Spearman** (repo-wide convention; robust at n=13–43;
invariant to monotone transforms of the signal, which dissolves P3's
pool-size severity bug — a rank correlation cannot be distorted by the rank-
gap bar meaning different severities in different pool sizes).

---

## H6 — Continuous value-signal test (fresh pre-registration, 2026-07-10;
## committed BEFORE any H6 code or outcome metric exists)

**Opening statement.** H5's bucket design was abandoned on power grounds
(MDE d ≈ 0.65 at 24% power at its own bar; Amendment 2, P1) before any
outcome existed. H6 is a first look with a better instrument, not a second
look at an answered question: no statistic on the disagreement axis has ever
been evaluated against outcomes in this project. The H5 partial-blindness
disclosure carries over verbatim: ~a dozen outcome-selected disagreement rows
were seen during the provenance audits (Puka-23 the one genuinely
contaminating row — projection >> ADP with huge outperformance, a confirming
point seen in advance); one row of ~473 cannot move a permutation-tested rank
correlation, and every numeric choice below is derived, not invented.

**Hypothesis.** Among stable-role players (the news-insulated subset),
Sleeper-vs-ADP disagreement MAGNITUDE tracks ADP error monotonically:
corr(signal, perf) > 0, where signal = adp_pos_rank − sleeper_pos_rank and
perf = z-scored (actual − ADP-implied points), both as previously frozen.

**Test, frozen.** Per position-season on the stable-role subset (definition
unchanged from H5 Amendment 1: is_rookie == 0, week-1 team == prior-season
team, prior_games ≥ 14; row counts QB 15/14/13/14/16, RB 23/23/25/24/34,
TE 14/14/15/18/16, WR 43/36/34/41/41): Spearman r between signal and perf.
Pooled = unweighted mean over the four positions of per-position 5-season
means (A4/H4/M1 convention; QB/TE re-enter — the continuous statistic needs
no bucket feasibility). Panel 2021–2025. Walk-forward implied-points curve
unchanged. Placebo: signal permuted within position-season among STABLE-ROLE
rows only, 1,000 draws.

**Power (computed blind, Q3, row counts + unit variance only):** pooled null
SE 0.0517; placebo 95th pctile ≈ 0.086; joint FPR 3.7%. Joint power 23% at
true r=0.05, 54% at 0.10, 84% at 0.15, 99% at 0.25. **MDE(80%) = r ≈ 0.144.**
Scale translation via the signal-only bucket separation (k = 3.37 z-signal
units): r 0.144 ≈ d 0.49; the abandoned bucket design's d 0.65 ≈ r 0.193.
Stated plainly: powered against moderate effects, a coin flip at r = 0.10.

**Decision rule — PASS iff ALL of (derived blind from the Q3 null):**
  (a) pooled 5-season mean r above the fire-time permutation placebo's 95th
      percentile (expected ≈ 0.086 from Q3; the placebo BINDS — no decorative
      fixed threshold is added, per the P1 lesson);
  (b) season-level pooled r positive in ≥ 4 of 5 seasons;
  (c) per-position floor: no position's 5-season mean r below **−0.03**
      (Amendment 1's d ≥ −0.10 floor scale-corrected through k = 3.37;
      assessable at all four positions);
  (d) one shot, rejection final — no threshold changes, no third statistic
      (the Q2 design cap), no panel swaps.

**Five-way reading, carried over with H6's power figures.** A FAIL headlines
as "FAIL (true r up to ≈ 0.144 not excluded at 80% power)". Full-pool
continuous Spearman is the descriptive SECONDARY, gating nothing, pre-stated
as weak evidence (largely expected from the corrected ladder, M3). Full-pool
passes + stable-role fails = confound NOT excluded, signal NOT established.
Both non-PASS outcomes have the same product consequence (Phase 4 as scoped
in Q1). A PASS is meaningful regardless of power (placebo-controlled FPR).

**What a PASS licenses (L4/L5 carried, tightened).** "Among stable-role
veterans, Sleeper's disagreement with ADP carries aggregate information about
ADP error not explained by last-days news exposure" — a verified, sized
public signal; measurement, not alpha. It does NOT license: the |gap| ≥ 8
tier, the board's HIGH/`sleeper_agrees` surfaces (label duty per Q1 stands),
any tail-specific claim, undrafted players, other vendors, other panels, or
transfer to 2026. Negative/inconclusive: product is projection + our
calibrated band, and the point-estimate + disagreement questions are both
closed for public sources under this program.

*Locked 2026-07-10. Sub-step N (build + structural asserts, F/G split) awaits
Joseph's approval; the shot gets a fresh session. I commit nothing.*
