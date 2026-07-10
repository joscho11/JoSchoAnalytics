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
