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

*Locked 2026-07-09. Harness of record: `phase0_benchmark.py` (+
`phase0_benchmark_results.json` for the Phase 0 numbers this file cites).*
