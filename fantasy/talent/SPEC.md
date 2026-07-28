# Talent Score — Architecture Spec

Status: RATIFIED (R19, 2026-07-16) with the "k derivation of record" amendment below, then
**SUPERSEDED IN PART by the per-position migration R34–R41 (2026-07-27).**

> ## READ THIS FIRST — how to navigate this file (added 2026-07-27)
>
> This file has two layers, and they do not describe the same product.
>
> **Sections (a)–(f) below are the ORIGINAL Phase-1 spec of 2026-07-16.** They describe a
> two-artifact build (`talent_score_2026.csv` + `rookie_score_2026.csv`) feeding two board
> columns joined exactly on `gsis_id`. **That is no longer what ships.** They are retained as the
> ratification record of that phase; where they conflict with an R-numbered section, **the
> R-numbered section wins.**
>
> **Sections R34–R41 are the CURRENT formulas of record** — eight dedicated per-position builds,
> all shipped 2026-07-27:
>
> | Build | SPEC | Artifact | γ |
> |---|---|---|---|
> | NFL QB | **R34** | `nfl_qb_score_2026.csv` | 0.55 |
> | College QB | **R35** | `college_qb_score_2026.csv` | 0.40 |
> | College RB | **R36** | `college_rb_score_2026.csv` | 0.60 |
> | NFL RB | **R37** | `nfl_rb_score_2026.csv` | 0.55 |
> | College WR | **R38** | `college_wr_score_2026.csv` | 0.50 |
> | NFL WR | **R39** | `nfl_wr_score_2026.csv` | 0.55 |
> | College TE | **R40** | `college_te_score_2026.csv` | 0.60 |
> | NFL TE | **R41** | `nfl_te_score_2026.csv` | 0.55 |
>
> Each build ships alongside a `*.provenance.json` recording its spec, γ, weights, the per-facet
> method-of-moments k vector, the effective (post-shrinkage) weights, the anchor pool, and the
> md5 of its own CSV. Each is `fantasy/talent/build_{nfl,college}_{pos}_score.py`, and each puts
> its work behind `if __name__ == "__main__":` so **importing a build must never run it** —
> pinned by `tests/test_nfl_qb_score.py::test_importing_a_build_never_runs_it`.
>
> **What changed that sections (a)–(f) get wrong:**
> - **Artifacts:** eleven now, not three. `talent_score_2026.csv` is **superseded at every
>   position and feeds no rendered board column**; it stays on disk unregenerated at pinned md5
>   `d7c1a57547be4ab8060c053de02aaead`. `rookie_score_2026.csv`
>   (`57b5b6c51637f11a2067bb7249ac7805`) survives only as the College-Talent fallback where a
>   college build has no coverage.
> - **Board wiring:** NFL Talent Score is fed by R34/R37/R39/R41 and College Talent Score by
>   R35/R36/R38/R40, disjoint by position. College RB/WR/TE **REPLACE** the box-score value where
>   they cover a player; college QB **FILLS BLANKS ONLY**.
> - **Joins:** NFL joins are exact on `gsis_id`. The four **college joins are guarded NAME
>   joins, by necessity** — brand-new rookies carry placeholder ids and no id namespace is shared
>   with PFF college. A name ambiguous on **either** side is refused, never guessed.
> - **Scale:** every build clips to **[50, 99]** except college QB at **[40, 99]** (a recorded,
>   unresolved inconsistency). **50 is a display floor, not a league-average player.**
> - **College blend:** WR and TE are **no longer NFL-only** — both blend a college prior gated on
>   ≤3 NFL seasons. Every college instrument fired **DEAD** against NFL outcomes, so the blend is
>   descriptive and empirical-Bayes drives its median contribution to ~0.06–0.07.
> - **College limits:** no strength-of-schedule adjustment anywhere, and PFF college is **FBS
>   only** — FCS prospects can never be scored.
>
> **Open, deliberately not applied:** winsorization at ±3 in Stage 1 of the college builds; the
> college-QB 40 clip floor against the other three at 50; and the measured-but-unapplied
> alternatives recorded in the R-sections (RB "P1", WR "P3", TE "P3", `k_blend` units).

## k derivation of record (R19 amendment)

The DERIVED k values (R1: sigma^2_eps = E[n_ptw*eps_ptw^2] from week-grain weighted
residuals; k = sigma^2_eps / sigma^2_alpha_median, per (position, facet), NS=60 seed
20260716) are CANONICAL. The literals 52/560/143/319/110/173/516/58 (+ QB MoM
285/399/12/24) are RETIRED, preserved as history:

| pos/facet | retired literal | derived (canonical) | ratio |
|---|---|---|---|
| RB YACcon | 52 | 50.4 | 0.97 |
| RB brkTkl_ru | 560 | 226.3 | 0.40 |
| RB success | 143 | 142.9 | 1.00 |
| RB explosive | 319 | 293.1 | 0.92 |
| RB yac_oe_rec | 110 | 91.0 | 0.83 |
| RB brkTkl_rec | 173 | 78.9 | 0.46 |
| WR cp | 516 | 441.7 | 0.86 |
| WR yac_oe | 110 | 76.7 | 0.70 |
| WR brkTkl_rec | 173 | 125.4 | 0.72 |
| TE yac_oe | 58 | 39.0 | 0.67 |
| TE brkTkl_rec | 173 | 1057.9 | 6.11 |
| QB cpoe | 285 | 367.0 | 1.29 |
| QB bad | 399 | 585.5 | 1.47 |
| QB qsucc | 12 | 32.4 | 2.70 |
| QB q10 | 24 | 50.2 | 2.09 |
| QB deep | — | 176.7 | — |

(brkTkl rows fold in the delta-drop as well as the sigma^2_eps definition.)
NS=60 + seed 20260716: RATIFIED. Null-last sort: RATIFIED. Gate-4 indeterminates:
ALL KEPT, disclosed (R17). TE brkTkl_rec: KEPT, hard-flagged fragile (R18). Nothing in this directory ships until he
ratifies this spec and commits. The prototype (instrument snapshot
`cowork_OS/_instrument_snapshot_20260715/`, byte-identical to the 05f61ef9 session
scratchpad) is SUPERSEDED by this build, never patched.

## (a) New artifacts

> **SUPERSEDED 2026-07-27 (R34–R41).** The table below lists the three Phase-1 artifacts. Eleven
> exist now: the eight `{nfl,college}_{qb,rb,wr,te}_score_2026.csv` (each with a
> `.provenance.json`) plus `rb_pbp_facets_2026.csv`. `talent_score_2026.csv` feeds no board
> column any more. See the navigation banner at the top of this file.

| Artifact | Written by | Schema |
|---|---|---|
| `fantasy/talent/talent_score_2026.csv` | `build_talent_score.py` (Phase 2 emit) | `gsis_id, display_name, position, score, ci_lo, ci_hi, w (composite reliability), rank_pos, college_share, flag ("†" w<0.40, "‡" w<0.30), per-facet z + w columns` |
| `fantasy/talent/rookie_score_2026.csv` | `build_rookie_score.py` (Phase 2) | `gsis_id (or draft-id), display_name, position, rookie_score, rank_pos, games, per-facet z (box-score index: dominator/recshare/ypc/ypr per position)` |
| `fantasy/talent/rho_provenance.json` | `archive_rho.py` (this session) | The registered rho outputs: PBP rho (all four registered estimators, per position + pooled, n, target label) + box-score test #2 values from RHO2.res, target-labeled. Append-only once written. |

These artifacts JOIN the frozen-artifact fence (MD5-pinned, never mutated) only AFTER
Joseph ratifies and commits. `talent_index_2026.csv` (the single-metric H7 provenance
record) is NOT modified, NOT superseded in place — the Talent Score is a NEW artifact with
a NEW name. `refresh_board_adp.py` never touches any of the three new artifacts.

### Frozen fence — THREE classes (R30, amended 2026-07-16 after committing the build)

The fence does two separate jobs; conflating them tripped a false red-alert (a scheduled
ADP refresh moved `board_adp_live_2026.csv` and halted a deploy session). It is now split:

- **CLASS A — cross-session pinned, BLOB basis** (`git show HEAD:<path> | md5`, which is
  checkout-invariant; the working-tree hash is NOT the pin because autocrlf makes it
  checkout-dependent). Print BOTH blob and working-tree hashes every session, labeled.
  - `talent_index_2026.csv` — blob `391b4381cbadbde8adfb46a03f2b48ab` (also: special —
    preserves the single-metric H7 provenance record; NEVER modified)
  - `phase4_band_2026.csv` — blob `776a861e377ac4928a95934b140f6793`
  - `talent_score_2026.csv` — blob `d7c1a57547be4ab8060c053de02aaead`
  - `rookie_score_2026.csv` — blob `57b5b6c51637f11a2067bb7249ac7805` (R32/R33, 2026-07-18;
    was `ee0d9c4d…` R31, was `2040df2e…` pre-R31. RB now scored on the frozen PBP instrument;
    WR reverted to equal thirds. Proven blob-basis: `git hash-object <path>` == `git hash-object
    --stdin` this session (filter no-op), so the worktree md5 shown IS the blob pin.)
  - `rb_pbp_facets_2026.csv` — blob `29de781601adc58e7bf9a941cde8e3b8` (R32, 2026-07-18; the
    8 RB rookies' frozen PBP career facets + the scoped-pool z/anchor constants in its
    provenance sidecar. cfbfastR 2.0.0, version-pinned cache. This provenance is the
    methodological upgrade the cfbfastR parquet mirror never carried.)
  (talent_score/rookie_score match on both bases today only because Python wrote them LF and
  they have not been re-checked-out; a fresh clone flips them to CRLF — the blob is the pin.)
- **CLASS B — cross-session pinned, FILE basis** (outside git, no line-ending conversion):
  `S2.pkl` `9b3d9df67ae88272f4eab0a0ae1cbb21` · snapshot aggregate (PowerShell method)
  `208fde4ee59b79a13eff0e23d0f7694c`.
- **CLASS C — WITHIN-session integrity only, never cross-session pinned:**
  `board_adp_live_2026.csv`. Verify before==after WITHIN a session (proves Fable did not
  mutate it); its hash moving BETWEEN sessions is never a finding — `board_refresh.yml` is
  designed to rewrite it daily. Do NOT re-pin it. Within-session movement IS a red alert.

Legitimate regeneration of any Class A/B artifact happens ONLY via an owner-ruled rebuild
(a new R-numbered ratification) with old and new hashes both reported and the delta attributed.

**R31 (RATIFIED-2026-07-17) — rookie box-score facet weights installed; equal-weight-pending
RESOLVED.** The Rookie Score's "EQUAL WEIGHT — owner sets weights later" state is closed by the
one-shot `PREREG_rookie_weights_2026-07-17.md`: **WR = {dom_best .80, recshare .00, ypr .20}**
(fitted — leave-one-draft-class-out out-of-fold Spearman IC equal −.021 → fitted .106, gate
+.05/+.10 passed at Δ+.127; the rec-share facet graded backwards, corner IC −.094), **RB =
{dom_best .50, ypc .50}** and **TE = {dom_best, recshare, ypr equal}** = equal weights RATIFIED
(Δ +.024 / +.038, below gate). `rookie_score_2026.csv` regenerated via
`schemas.write_artifact`: **old blob `2040df2e7e8ca80adcb67552edb14cd1` → new
`ee0d9c4d32b6f59a6d118ebbba65f5c7`** (worktree md5, LF; equals the blob pin once committed).
Delta attributed ENTIRELY to the WR weight change — RB + TE rows are byte-identical to the old
file (verified line-by-line); only the 16 WR rows moved (Tyson 87.0→93.4, rank 1 unchanged;
Bernard 79.8→86.4; Bell 71.9→58.0). **Not done here (flagged):** `build_rookie_score.py` still
hardcodes an equal-weight nanmean, so it no longer regenerates this artifact — it must be wired
to the ratified WR vector (or a config ROOKIE_WEIGHTS block) before the next rebuild, and the
golden hash in `tests/golden/golden_weighted.json` must move to the new pin in the same commit.

## (b) Build scripts

> **SUPERSEDED 2026-07-27 (R34–R41).** The eight entry points that actually ship are
> `build_nfl_{qb,rb,wr,te}_score.py` and `build_college_{qb,rb,wr,te}_score.py`. Each exposes
> `build()` behind an `if __name__ == "__main__":` guard — importing one must never run it.
> The scripts named below built the retired R29 artifacts.

| Script | Reads | Writes |
|---|---|---|
| `config.py` | — | — (OWNER CONFIG block: 4 weight vectors PROVISIONAL-UNRATIFIED + deepCPOE 0.00 UNSET; stack constants; mode switches). No code path may alter the vectors. |
| `facets.py` | nflreadpy (player_stats, PBP, PFR advstats, NGS *numerators only*, ff_playerids identity crosswalk), `../seasonal_projections/phase4_band_2026.csv` + `season_dataset_2014_2026.csv` (read-only universe inputs) | checkpoint pickles under `C:/tmp/talent_build/` (scratch, not repo) |
| `model.py` | facet checkpoints | — (fit, sigma_alpha at NS splits, R1 k derivation, residual sigma^2_eps) |
| `composite.py` | model outputs | — (z, w, ONE composite branch, CB anchor, boards, RB pipe) |
| `build_talent_score.py` | all above | Phase 1: measurement checkpoints only. Phase 2 (post-ratification): `talent_score_2026.csv` |
| `build_rookie_score.py` | college_production CSVs + `rb_pbp_facets_2026.csv` (frozen) | Phase 2b: `rookie_score_2026.csv` — RB scored on the frozen PBP instrument (R32, weak-disclosed .474); WR/TE box-score DESCRIPTIVE-ONLY, equal weights (R33 reverted WR; TE equal). Old note "PBP not deployable — cfbfastR lacks 2020/2023-25" is SUPERSEDED: CFBD carries 2016-2025, version-pinned via cfbfastR 2.0.0 (2025 receiver/passer parse still degraded → WR/QB class-scoring blocked; RB rusher parse clean) |
| `archive_rho.py` | frozen `C:/tmp/S2.pkl`, `C:/tmp/CFBFAC.pkl`, `C:/tmp/RHO2.pkl`, prototype `cfb_rho.py` stdout | `rho_provenance.json` (once) |
| `tests/test_talent_build.py` | checkpoints + accepted-table constants | — |

NOTHING here writes to any existing frozen artifact, tracker, or forward log.

## (c) The ruled stack (verbatim, with owner rulings R1–R14 folded in)

Mixed model `y_{p,t,w} = mu + alpha_p + gamma_teamseason + delta_opponent + eps` at WEEK
grain; weights = opportunities × exp(−0.20·(2025−season)) (λ=0.20 DECLARED, NOT DERIVED —
never re-derived); lookback 2018+; weighted sparse crossed FE solve (lsqr);
player_stats/PFR-own denominators — NGS is NEVER a denominator; gsis↔pfr_id crosswalk is
IDENTITY ONLY; exact gsis IDs everywhere (R11 — college joins are exact normalized-name
with a printed collision audit); PERCENTILE NOWHERE in the pipeline (report-rendering only).

- **R1 — k is DERIVED, per (position, facet), no shared literals:**
  `sigma^2_eps(per-opportunity) = E[n_ptw · eps_ptw^2]` over the model's week-grain
  residuals (n_ptw = the week's raw opportunity count, eps from the full weighted fit);
  `k_{P,f} = sigma^2_eps / sigma^2_alpha_median{P,f}`. QB facets (MoM, no model): the same
  recipe with sigma^2_eps = pooled within-player per-opportunity variance from the row-level
  feed and sigma^2_alpha via split-half at NS splits. Derived k printed next to the retired
  literal with the ratio, every facet.
- **R2 — NS = 60 splits**, seed `default_rng(20260716)` (documented here). Gate-6 quartet
  per facet: sigma_alpha median, mean (SD scale), cs.std() (sigma^2 scale, stated), CV
  (= cs.std/|cs.mean| on the sigma^2 scale, denominator = mean, stated), %<=0 with binomial
  SE, split count.
- **R3 — NO floor, NO clip.** If median sigma^2_alpha <= 0: facet flagged UNIDENTIFIABLE
  at that position, excluded from scoring, reported loudly. The prototype's `max(., 1e-4)`
  is deleted.
- **R4 — QB universe = the COMPLETE-CASE INTERSECTION** of all five QB facets. Every QB
  facet's standardization moments (mean, SD) are computed on that ONE population.
- **R5 — QB shrinkage ALIGNED:** QB routes through the SAME composite branch as model
  positions — contribution = w_f · z_f, z_f = zstd (unit-SD on the R4 universe), no baked-in
  sqrt(w). Verified by decile test: SD(w·z) rises with w for QB as for RB.
- **R6 — deepCPOE wired in** as QB facet #5 (air_yards ≥ 20 per-attempt CPOE-style feed;
  own split-half k at NS=60). Config weight 0.00 marked UNSET — owner assigns later.
- **R7 — Gate 4 universe = SCORED, raw facet values, Pearson, n + 95% CI per cell.**
  Breaches reported, never acted on; CI straddling 0.70 = "indeterminate at this n."
- **R8 — the rho consequence bands are carried by the DISATTENUATED estimator**
  (the pre-registration's own baseline .385 is disattenuated); Spearman and raw Pearson are
  registered-descriptive.
- **R9 — one sanctioned archival execution** of the prototype `cfb_rho.py`, byte-identical,
  frozen pickles, to persist the four registered estimators. No other rho execution, ever.
- **R10 — rho disclosure:** no rho describes the shipped board; copy states rho was measured
  against the unshrunk composite and the shipped score applies per-facet reliability
  shrinkage on top. ~~Pipe ships RB-only at the box-score disattenuated rho (.385,
  weak-disclosed)~~ **[SUPERSEDED 2026-07-18 by R32/R33 — see below]**; WR/TE pipe DEAD per bands.
- **R32/R33 — rookie pipe re-measured on a clean panel (2026-07-18, PREREG_pbp_index_2026-07-17
  OUTCOMES).** The .385 box-score RB figure came from the DEFECTIVE step2 panel (cfb_screen
  `career()` enforced no final-season condition → ~38% of the registered WRs, and RBs likewise,
  scored on wrong-window truncated careers). On the clean true-final / full-career / FBS panel
  (version-pinned cfbfastR 2.0.0), same R8 disattenuated estimator: **box RB .298 (DEAD)**; the
  RB **PBP** instrument (EPA/rush + explosive, z over the scoped pool) measures **.474 raw .215,
  n=300 → WEAK-DISCLOSED**, so **R32: RB ships on the PBP instrument** (`rb_pbp_facets_2026.csv`),
  replacing the box pipe. Same-panel WR box .028 / PBP .086, TE box .295 / PBP .312 — all DEAD,
  so WR/TE stay box-score DESCRIPTIVE-ONLY. **R33: WR reverted to equal thirds** — R31's fitted
  vector (OOF Spearman +.106) did not replicate on the clean panel (−.009) and was fitted on the
  defective step2 panel. No rho_provenance record is superseded; those are the archived
  defective-panel estimators and stay verbatim.
- **R12 — two-cell display:** zero NFL regular-season snaps → Rookie Score populated /
  Talent Score dashed; inverse otherwise. Sorting a score column sinks the dashed group
  (null-last), never filters. Scale-disclosure line beside the columns. (Sort behavior
  adopted by the intermediary — flagged for owner sign-off.)
- **R13 — weights are OWNER CONFIG**, single declared block, every line
  PROVISIONAL-UNRATIFIED, no code path alters them.
- **R14 — benchmarks are READ-ONLY report cards.** Feasibility geometry/certificates only;
  no vector is chosen, named, or recommended by the agent — permanently.
- Facet sets (SETTLED): RB brkTkl_ru/yac_oe_rec/explosive/YACcon/brkTkl_rec/success ·
  WR cp/yac_oe_per_rec/brkTkl_rec · TE yac_oe_per_rec/brkTkl_rec · QB CPOE/badthrow%(inv)/
  deepCPOE/QBrush success/QBrush 10+. gamma dropped from brkTkl facets (delta_brk noise,
  −0.06 on record). QB has NO gamma/delta — structurally unidentifiable (one starter per
  team); ships UNADJUSTED, a different estimand under the same header.
- Display estimator: constrained Bayes (Louis 1984) — per-facet Fork-3 shrink → composite →
  per-position unit-SD → anchor p5→52 / p98→95 on the w≥0.30 slice, clip [40,99]. NO
  confidence floor. Display 3c: interval primary, † w<0.40, ‡ w<0.30, near-ties sorted by
  confidence.

## (d) Dashboard integration plan (NO dashboard code this session)

> **SUPERSEDED 2026-07-27 (R34–R41).** The two board columns are fed by **eight** artifacts, not
> two. NFL Talent Score reads R34/R37/R39/R41 (exact `gsis_id` joins); College Talent Score reads
> R35/R36/R38/R40 (**guarded normalized-name joins**, ambiguity refused — the "joined on gsis_id
> (exact)" claim below does not hold on the college side). College RB/WR/TE replace the box-score
> value where covered; college QB fills blanks only.
>
> **The two display bullets below did NOT ship.** No shipped artifact carries `ci_lo`/`ci_hi` or a
> flag column (only the retired `talent_score_2026.csv` does), so there is **no interval as the
> primary visual and no † / ‡ flags** — a player below his position's volume floor is left blank
> instead. And there is **no advanced view exposing per-facet z + w**: `draft_board_2026.py` has one
> expander ("How to read this board") and one toggle ("Show projection and talent detail",
> default ON) whose compact mode simply *hides four whole columns* (Sleeper Proj, Model Proj, NFL
> Talent Score, College Talent Score) rather than revealing facet internals. The per-facet
> `z_*` / `neff_*` / `r_*` values live only inside the CSVs, unrendered. The CSV download always
> carries all 13 columns.

- Display slot: `draft_board_2026.py::_load_board_2026` — the current single-metric
  `eff_disp` column is replaced by TWO columns (Talent Score, Rookie Score) fed from the two
  new CSVs, joined on gsis_id (exact).
- Two-cell rules per R12 (dash rule, null-last sort, scale-disclosure line).
- Display 3c: interval as the primary visual; † / ‡ flags; near-ties sorted by confidence.
- Advanced view: per-facet z + w exposure behind an expander; report-only percentiles may
  render THERE only (never in the pipeline).
- Tests retargeted: `tests/test_app_draft_board.py` (AppTest all-tabs), `test_draft_board.py`
  (column contract), plus new `tests/test_talent_build.py`. Compliance scan on all new copy.

## (e) Missing-facet policy

The prototype imputes a missing facet to z=0, w=0 (union universe + fillna(0)). This build
keeps that ONLY:
- at QB inside the R4 complete-case universe, where by construction it cannot bind
  (every scored QB has all five facets);
- at model positions, where it binds for players missing a feed entirely — documented at
  build time: the build prints, per position, every SCORED player with any all-missing facet
  (who, which facet). A missing facet contributes nothing (w=0 zeroes it) and drags the
  composite reliability w down, which is the honest treatment: absence of evidence enters as
  zero-confidence, never as an imputed skill level.

## (f) Disclosure-copy skeleton (content law: first-person singular; no forbidden words)

> **SUPERSEDED IN TWO PLACES 2026-07-27 (R34–R41).** (i) Item 6's score range: every build clips
> to **[50, 99]** (college QB [40, 99]), and **50 is a display floor, not "the worst draftable
> player"**. (ii) Item 8: WR and TE are **no longer NFL-only** — both blend a college prior gated
> on ≤3 NFL seasons; every college instrument fired DEAD, so the blend is descriptive and
> empirical-Bayes drives its median contribution to ~0.06–0.07. The live copy that reflects this
> is `reports/disclosure_final.md` (revised 2026-07-27).

1. "My Talent Score is a model-based estimate of what a player does per opportunity, net of
   situation — not a summary of his production. Models can be wrong."
2. "The score applies reliability shrinkage on top of the underlying composite; the college
   agreement (rho) behind the rookie pipe was measured against the unshrunk composite, not
   the displayed score." (R10)
3. Constrained-Bayes cost: "Scores rank players correctly and the distribution is honest,
   but an individual score is not each player's best point estimate."
4. Honesty line: "Situation adjustment (team + opponent) explains roughly 8% of
   week-to-week variance; most of what you see week to week is noise."
5. QB note: "QB scores are unadjusted for situation — one starter per team makes his
   situation inseparable from him. A different estimand under the same header."
6. Score range: "Elite is 85+, good 70–85, below-average 50–70. A 50 means the worst
   draftable player, NOT a league-average one." It is NEVER called a Madden rating.
7. Rookie cell: "A rookie's score is a college-production talent read on its own scale —
   it does not claim to predict NFL performance or fantasy value."
8. Pipe: "For early-career RBs I blend in a college prior at its measured (weak) agreement;
   at WR and TE the measured agreement was zero-to-weak, so their scores are NFL-only."

---

## R34 (RATIFIED-2026-07-27 by Joseph) — QB TALENT SCORE, FORMULA OF RECORD

Joseph's ratified QB specification. SUPERSEDES the R29 5-facet PBP vector
(`cpoe .33 / bad .22 / deep .22 / qsucc .16 / q10 .07`) as the formula of record.
Directed; recorded verbatim to his ratification.

**Revised same-day** to add the 3-season temporal window (Stages 0-2) and the career-stage
gate on the blend. The 9-facet composite weights are unchanged from the first ratification.

### Stage 0 — temporal window

Seasons `s in {T-2, T-1, T}`. Per-season decay weight multiplied by that season's volume:

```
w_s = n_s * gamma^(T - s)          gamma = 0.55   (RATIFIED-2026-07-27)
```

Normalized across a full 3-season sample that is approximately
**54% / 30% / 16%** for current / prior / two-back.

### Stage 1 — per-season standardization

Z-score each facet **within position, within season**, against the frozen reference pool.
Per-season rather than pooled washes out league-wide drift, so a 2023 z and a 2025 z carry
the same meaning:

```
z_{i,s} = (x_{i,s} - mu_{i,s}) / sigma_{i,s}
twp_rate enters as -z
```

### Stage 2 — temporal aggregation

```
zbar_i  = SUM_s w_{i,s} * z_{i,s} / SUM_s w_{i,s}
N_eff,i = SUM_s w_{i,s}
```

`w` is indexed by **facet as well as season** — `n_s` for `grades_run` is designed-run count,
for `CPOE` it is dropbacks. That indexing is the point of Stage 3.

### Stage 3 — per-facet reliability shrinkage

```
z_tilde_i = sqrt(r_i) * zbar_i          r_i = N_eff,i / (N_eff,i + k_i)
```

### Stage 4 — NFL composite (weights /100, sum = 1.00)

```
NFL_QB = 0.20 * z_tilde_grades_pass
       + 0.10 * z_tilde_CPOE
       + 0.10 * z_tilde_btt_rate
       - 0.10 * z_tilde_twp_rate
       + 0.10 * z_tilde_pressure_grades_pass
       + 0.05 * z_tilde_accuracy_pct
       + 0.05 * z_tilde_EPA_dropback
       + 0.05 * z_tilde_deep_CPOE
       + 0.25 * z_tilde_grades_run
```

### Facet sourcing — R34 IS A HYBRID (verified on disk 2026-07-27)

`cpoe` and `deep_CPOE` do NOT exist in PFF — no NFL PFF file contains the string `cpoe`.
They come from the nflverse feeds the shipped talent build already uses. Sourcing of record:

| Facet | W | Feed | Column / derivation | `n_s` (volume) |
|---|---:|---|---|---|
| `grades_pass` | .20 | PFF | `nfl_passing_summary.grades_pass` | dropbacks |
| `CPOE` | .10 | **nflverse NextGen** | attempt-weighted `completion_percentage_above_expectation` (REG, `week != 0`) — `facets.py:147-156` | attempts |
| `btt_rate` | .10 | PFF | `nfl_passing_summary.btt_rate` | dropbacks |
| `twp_rate` | .10 | PFF | `nfl_passing_summary.twp_rate` (enters `-z`) | dropbacks |
| `pressure_grades_pass` | .10 | PFF | `nfl_passing_pressure.pressure_grades_pass` | dropbacks |
| `accuracy_pct` | .05 | PFF | `nfl_passing_summary.accuracy_percent` | dropbacks |
| `EPA_dropback` | .05 | PFF | `nfl_passing_summary.epa / dropbacks` | dropbacks |
| `deep_CPOE` | .05 | **nflverse PBP** | mean `cpoe` over pass attempts with `air_yards >= 20` — `facets.py:176-181` | deep attempts |
| `grades_run` | .25 | PFF | `nfl_rushing_summary.grades_run` | designed-run attempts |

**Join key:** PFF `player_id` -> `gsis_id` via `snapshots/players.parquet` (`pff_id`). NEVER by
name — the repo has been burned by name joins.

**Four distinct volume denominators are live in one player.** Worked example, Drake Maye
2024-2025: dropbacks 1029 / attempts 702 / designed runs 167 / deep attempts 112. This is why
the facet-indexed `w_{i,s}` in Stage 2 is load-bearing, not cosmetic.

**Worked example of record (Maye, gamma=0.55 RATIFIED, QB pool >= 150 dropbacks, k illustrative):**
zbar by facet = grades_run +0.941, grades_pass +0.325, **CPOE +2.116**, btt_rate +0.348,
pressure_grades_pass -0.275, twp_rate -0.050, EPA_dropback +0.563, accuracy_pct +0.638,
deep_CPOE +0.964. N_eff = 987 dropbacks / 670 attempts / 162 designed runs / 109 deep attempts.
NFL_QB = **+0.402** at k=0.5*N_max, **+0.328** at k=1.0*N_max. Omitting the two nflverse facets
(15% of weight) roughly HALVES the result — they are not optional.

### Stage 5 — early-career blend (GATED on career stage)

```
lambda    = N_eff / (N_eff + k)        N_eff = SUM_s w_s  (aggregate, 3-season)
Talent_QB = lambda * NFL_QB + (1 - lambda) * College_QB
```

**Gate:** the `(1 - lambda) * College_QB` term applies **only when NFL seasons played <= 3**.
Beyond that, shrink toward the **position mean** instead of toward college — same shrinkage
logic, correct prior.

### Stage 6 — display

Map to 0-100 (percentile, or fixed z->100 anchoring, whichever the board uses).
Current board: two-point anchor, p5 -> 52 and p98 -> 95, clipped to [40, 99].

### Two things the 3-season window breaks — RULED FIXES, write into the prereg

1. **`k` must be recalibrated against the 3-season maximum, or lambda never reaches 1.**
   `k` was conceived against career-length sample. Capping the window at three seasons caps
   everyone's `N_eff`, so a career-scale `k` leaves even Burrow at `lambda ~ 0.8` carrying
   permanent college weight. Estimate `k` against the 3-season maximum so a healthy full-time
   starter with three complete seasons sits at `lambda >= 0.95`.

2. **Low `N_eff` re-activates the college blend for veterans — the real bug.** A 30-year-old
   who missed two of the last three seasons has a small `N_eff`, and Stage 5 as literally
   specified mixes in his decade-old college talent score. Not an edge case: it is Burrow's
   2023-2024 and every post-injury veteran on the board. **Fix = the Stage 5 career-stage gate
   above.** Must be explicit in the prereg — it will NOT surface in a face-validity pass unless
   an injured veteran is deliberately checked.

### Knock-on for the benchmarks

The 3-season window pins anchors to **2023-2025 football specifically**. **Justin Fields is the
case to re-examine** — his heaviest rushing and weakest passing seasons are 2021-2022, now out
of window, so he may no longer be the clean discriminator for the `grades_run` 25% he was
pitched as. Re-check that cell against who actually looks like that in the current window
BEFORE the anchor list is frozen.

### Still open (owner's call)

- **Which college index feeds `College_QB`.** Lean of record: **grade+age**, the +0.685
  validation of record, over the richer 6-facet (+0.609, descriptive re-measure).

### Build conditions (carried)

1. **Double-shrink disclosure.** Facet shrinkage pulls a thin player toward the position mean
   and lambda then pulls him toward college — an early-career composite moves twice. Disclose
   it rather than discover it in a face-validity check.
2. **Estimate the k's separately and once.** Per-facet `k_i` from that facet's own variance
   decomposition; the blend's `k` from the NFL-vs-college decomposition. Sharing or re-fitting
   them turns this into tuning.
3. **lambda's `n` must be the EFFECTIVE sample** (`N_eff`), not raw seasons.
4. **Sign convention.** Stage 1 flips `twp_rate` to `-z` and Stage 4 carries a `-0.10` weight;
   applied literally the two cancel. The build must apply the flip exactly once.

### Open blockers to a build (status verified on disk 2026-07-27)

- **Stage 5 has no input.** `rookie_score_2026.csv` contains ZERO QB rows (WR 16 / RB 8 / TE 4)
  and `college_share` is 0.0 for all 31 QBs in `talent_score_2026.csv`. No `College_QB` artifact
  exists; the 2025 passer parse is degraded, so QB class-scoring is blocked.
- **Six of nine facets are PFF NFL columns** (`grades_pass`, `btt_rate`, `twp_rate`,
  `pressure_grades_pass`, `accuracy_pct`, `grades_run`) and PFF has no ingestion path in the
  talent build today. Distinct from the FIRED PFF *college* instrument campaign, which tested
  college indices against NFL alpha-hat and does not bear on NFL PFF facets.

### Status — SHIPPED 2026-07-27

**BUILT AND SHIPPED.** `build_nfl_qb_score.py` -> `nfl_qb_score_2026.csv` (md5 `47f8ea81...`,
**49 qualified starters**) + provenance JSON. `talent_score_2026.csv` was **NOT regenerated**
(Joseph's call) — it keeps md5 `d7c1a575...` and its R29 QB values; the board simply PREFERS the
R34 artifact for QB rows. Additive, so nothing else moved.

**POOL (the R35 lesson, carried).** Scored/displayed pool = qualified starters, **>= 300
dropbacks across the window**; per-season z uses a >= 150-dropback reference. Display ranked
WITHIN that pool. This is why 3 of 7 facet anchors land in band vs 0 of 8 on the first college
attempt.

**Anchor fitted within the pool:** p5 = -0.4119 -> 52, p98 = +0.6834 -> 95, clip **[50, 99]**
(50 is the floor for any scored player). MoM k, each in its OWN denominator:
grades_pass 738 / CPOE 451 / btt 1269 / twp 844 / pressure 2184 / accuracy 1415 /
EPA 607 / deep_CPOE 155 / **grades_run 31**. `k_blend` 53.8, **13 of 49 blended**.

### Anchor validation, 2026-07-27

FACET anchors (lambda = 1 — these test the weights): **Burrow 94.7 PASS**, **Lamar 91.8 PASS**,
**Mahomes 86.4 PASS**; Fields 71.5 HIGH, Tua 50.7 LOW, Purdy 91.0 HIGH, Bryce Young 73.9 HIGH
(note Young was drafted 2023 -> 3 NFL seasons -> lambda 0.95, so he is NOT a clean lambda=1 cell).
BLEND anchors (reported separately, they test the college mix and NOT the weights):
Maye 88.9 / Daniels 87.6 / Dart 77.5 / Caleb Williams 75.0, lambda 0.89-0.95.

**Weight sensitivity, measured:** cutting `grades_run` to .20 / .15 / .10 drops the passing count
from **3 to 1** every time — Lamar and Mahomes fall out of band immediately while Tua gains only
+1.7 / +4.4 / +8.3 and never reaches his floor. **Baseline is the best set tested.** Shipped as
ratified.

**Two anchor cells are unfalsifiable-by-construction and should be retired, not chased:**
- **Purdy** ("isolate the player from the scheme") — SPEC states QB carries NO situation
  adjustment because one starter per team makes scheme inseparable from the player. He is rank
  3-4 under every weighting tested.
- **Tua** at 50.7 is a genuine DISCLOSED LIMITATION, not a defect: with a quarter of the weight on
  rushing, a genuinely immobile QB cannot score well. Same for Stafford (passing grade +1.32,
  4th best in the pool, ranks 27th) and Derek Carr.

### Carried open (NOT blockers, recorded so they are not lost)

- **`k_blend` is in DROPBACK units**, reverse-calibrated so a median 3-season starter sits at
  lambda 0.95. The principled construction is an NFL-vs-college variance decomposition in
  **season-equivalents**. It is a DIFFERENT object from the per-facet k vector and must never be
  merged with it.
- Fields / Bryce Young read average because they ARE average on these facets in this window.
  Reaching a 25-40 band needs a **percentile display map or less shrinkage**, not weights — the
  same conclusion R35 reached.

**Validation:** `tests/test_nfl_qb_score.py` 5/5; full suite 207/207; AppTest 10/10. All 7 pkls, 4 raw
projection CSVs, `talent_score_2026.csv`, `rookie_score_2026.csv` and `college_qb_score_2026.csv`
byte-identical.

---

## R35 (RATIFIED-2026-07-27 by Joseph) — COLLEGE TALENT SCORE, QB

Feeds `College_QB` in R34 Stage 5. Directed; recorded verbatim to his ratification.

### Stage 0 — window and per-season weights

**POOL (RATIFIED-2026-07-27): qualified starters only — every FBS QB season with `dropbacks >= 200`,
one row per player-season** (max-dropback row kept where a player has multiple team rows).

ALL available qualifying college seasons, anchored on the player's **final college season F**, not a
calendar year — so a 2023 declare and a 2025 declare are each scored on their own last-three-back.

```
w_{i,s} = n_{i,s} * gamma^(F - s)          gamma = 0.4   (RATIFIED-2026-07-27)
```

`n_{i,s}` is facet-indexed, as on the NFL side:

| Facet | `n` |
|---|---|
| `grades_pass`, `accuracy_pct`, `btt_rate`, `twp_rate` | dropbacks |
| `pressure_grade` | pressured dropbacks |
| `grades_run` | designed rush attempts |

At gamma = 0.4 with equal volume a three-year starter splits **64 / 26 / 10**; a two-year, **71 / 29**.

### Stage 1 — per-season standardization

Z-score each facet **within position, within season**, against the college pool.
`twp_rate` sign-flips **here and only here**.

```
z_{i,s}   = (x_{i,s} - mu_{i,s}) / sigma_{i,s}
z_twp,s   = -(twp_rate_s - mu) / sigma
```

### Stage 2 — temporal aggregation

```
zbar_i  = SUM_s w_{i,s} * z_{i,s} / SUM_s w_{i,s}
N_eff,i = SUM_s w_{i,s}
```

### Stage 3 — per-facet reliability shrinkage

```
z_tilde_i = sqrt(r_i) * zbar_i          r_i = N_eff,i / (N_eff,i + k_i)
```

`k_i` estimated **on the college pool, per facet, in that facet's own units**. **DO NOT reuse the
NFL `k_i`** — different pools, different reliabilities, and the dropback-vs-designed-run unit
mismatch is exactly the bug that wrecked the first Maye run.

### Stage 4 — composite (weights sum = 1.000)

```
College_QB = 0.250 * z_tilde_grades_pass
           + 0.200 * z_tilde_accuracy_pct
           + 0.175 * z_tilde_btt_rate
           + 0.100 * z_tilde_twp_rate        (PRE-FLIPPED in Stage 1 -> POSITIVE weight)
           + 0.250 * z_tilde_grades_run
           + 0.025 * z_tilde_pressure_grade

FINAL weights RATIFIED-2026-07-27 (third revision; .350/.150/.125/.100/.150/.125 ->
.300/.150/.125/.100/.200/.125 -> the above). `grades_run` and `grades_pass` now carry EQUAL
weight at .250. `pressure_grade` cut to .025 — it is 0.68-correlated with `grades_pass` and
contributes no independent information (see the correlation note below); retained at token
weight rather than dropped.
```

### Stage 5 — display

0-100, **same mapping as the NFL side** so both sit on one scale before lambda mixes them.
Two-point anchor p5 -> 52, p98 -> 95, clip [40, 99].

**REFERENCE POOL RATIFIED-2026-07-27: the anchor is fitted on NFL-REACHING QBs only**
(`pff_id` present in the `players.parquet` crosswalk; n=179 at rel >= 0.30), NOT the full
college pool. This mirrors the NFL score, which anchors on the board universe (ADP <= 250)
rather than all NFL players, and is what puts the two scales on comparable footing before
lambda mixes them. Fitted constants at ratification: p5 = -0.2261, p98 = +1.0714.
The composite is unchanged by this — it is a relabeling, monotone, and preserves every rank.

### Facet redundancy — measured 2026-07-27, n=742

`grades_pass` correlates **0.70 / 0.65 / 0.68** with `accuracy_pct` / `twp_rate` /
`pressure_grade`. PCA on the weighted composite puts **64.6% of variance on PC1** — five of the
six facets are largely one passing-grade factor. **`grades_run` is the only orthogonal facet**
(0.09-0.25 against all others) and carries nearly all of PC2. Consequence of record: reweighting
INSIDE the passing block moves scores by <1.5 points and cannot change the composite's character;
only `grades_run`, the display map, or the shrinkage level are real levers.

### Sourcing — VERIFIED ON DISK 2026-07-27, all six facets present 2014-2025

| Facet | W (SHIPPED) | File | Column | `n_s` column |
|---|---:|---|---|---|
| `grades_pass` | .250 | `college_passing_summary_{y}` | `grades_pass` | `dropbacks` |
| `accuracy_pct` | .200 | `college_passing_summary_{y}` | `accuracy_percent` | `dropbacks` |
| `btt_rate` | .175 | `college_passing_summary_{y}` | `btt_rate` | `dropbacks` |
| `twp_rate` | .100 | `college_passing_summary_{y}` | `twp_rate` (flip in Stage 1) | `dropbacks` |
| `grades_run` | .250 | `college_rushing_summary_{y}` | `grades_run` | `attempts` |
| `pressure_grade` | .025 | `college_passing_pressure_{y}` | `pressure_grades_pass` | `pressure_dropbacks` |

*(**W column corrected 2026-07-27** to the FINAL ratified vector — the one in the Stage-4 section
above, and the one `build_college_qb_score.py:46` actually ships. The
`.350/.150/.125/.100/.150/.125` shown here originally was the FIRST revision, left behind when the
third was ratified; reading it would have given `grades_run` .150 instead of the ratified .250 that
makes it co-equal with `grades_pass`. The revision history itself is unchanged above.)*

**Unlike R34, College_QB needs NO hybrid** — every facet is in college PFF. Filename patterns:
`college_{kind}_{y}.csv` for 2019-2025, bare `{kind}.csv` for 2014-2018 (see
`fire_pff_qb_rho.passing_path`).

**Identity — CORRECTED 2026-07-27.** The "join to NFL via the `players.parquet` crosswalk, never
by name" instruction holds only for resolving *which college QBs reached the NFL*. It does **not**
hold for flagging the 2026 rookie class: a brand-new rookie has no `gsis_id`, carries a placeholder
in the deploy builder (`MEN516487`, `SIM639376`, `ALL015451`, `pfr_BeckCa01`), and the rookie board
carries its own placeholders that differ from the season dataset's. **That join is a guarded
normalized-name join** — names ambiguous on either side are refused, never guessed. The first
attempt to force an id join there silently produced a confident wrong answer (it flagged four old
UDFAs as the 2026 class and matched zero of the actual players).

### OPEN — zero designed runs is NOT missing data (rule REQUIRED before build)

A pocket QB with 4 designed carries has a **real, informative near-zero** on a 15%-weighted
facet. Both existing missing-data rules mishandle it: omit-and-rescale **rewards** him by
redistributing that .150 onto his passing facets; the 10th-percentile penalty invents a value.
A rule is required that distinguishes:

- **ABSENT DATA** (table coverage gap — no row for that player-season) -> omit and rescale;
- **LOW ACTIVITY** (row exists, `attempts` is small or zero) -> **keep the z**, let Stage 3
  shrinkage handle it via a small `N_eff`.

PROPOSED discriminator, NOT YET RATIFIED: presence of a row for that (player, season) in
`college_rushing_summary_{y}` is the test. Row present -> low activity, keep. No row -> absent,
rescale. Owner to ratify or replace.

### Still open (owner's call)

- **The zero-designed-runs rule** above.

### Note back to R34

R35 Stage 4 resolves the sign convention explicitly ("pre-flipped in Stage 1 -> positive
weight"). R34 Stage 1/Stage 4 still carry both a `-z` flip AND a `-0.10` weight, which cancel if
applied literally. R34 should be brought to the R35 convention at build.

### Status — SHIPPED 2026-07-27

**BUILT AND SHIPPED.** `build_college_qb_score.py` -> `college_qb_score_2026.csv`
(md5 `ffa9f0da...`, 742 QBs, 186 reached the NFL, 24 are 2026 rookies) + provenance JSON.
Panel 1,437 qualifying player-seasons 2014-2025. MoM k on the college pool:
grades_pass 699 / accuracy 550 / btt 979 / twp 691 / **grades_run 86** / pressure 679.
Anchor fitted on 179 NFL-reaching QBs: p5 = -0.2261 -> 52, p98 = +1.0714 -> 95.

`rookie_score_2026.csv` is UNCHANGED (md5 `57b5b6c5...`, still zero QB rows by design) — the QB
score is a SEPARATE artifact, disjoint by position, so the two can never collide.

**Board integration.** Draft Board fills College Talent for rookie QBs (Mendoza 81.1,
Simpson 75.6); Rookie Board fills 8 of 9 QB rows and adds a collapsed
"college QBs not in this rookie class" view. Both are read-only joins that feed no other column.

**IDENTITY — both joins are guarded NAME joins, by necessity.** A brand-new rookie QB has no
gsis_id and carries a placeholder in the deploy builder (`MEN516487`, `SIM639376`, `ALL015451`,
`pfr_BeckCa01`); the rookie board carries its OWN placeholders which do not always match the
season dataset's (Taylen Green is `GRE361852` there vs `00-0041092` in the dataset). No id
namespace is shared with PFF college, so `norm_name` is the only key available — the same
reason `assemble_features.py` uses it. Names ambiguous on EITHER side are refused, not guessed.

**STANDING LIMITATION — FCS prospects can never be scored.** PFF college covers 136 teams (FBS
only; James Madison appears post-2022 reclassification). Cole Payton (North Dakota State) and
Jack Strand (South Dakota State) are the 2 of 26 rookie QBs with no row at all — verified absent
from every college passing summary 2021-2025, not a join failure. A blank is the honest output.

**Validation:** `tests/test_college_qb_score.py` 7/7; full suite 202/202; AppTest 10/10.
`tests/test_fantasy_league_pages.py` updated (the rookie board now renders TWO tables; the
direct-PFF-exclusion assertion was EXTENDED to both, not loosened).

---

## R36 (RATIFIED-2026-07-27 by Joseph) — COLLEGE RB TALENT SCORE — SHIPPED

`build_college_rb_score.py` -> `college_rb_score_2026.csv` (md5 `faaa5239...`), **1,395 RBs**;
396 reached the NFL; 46 of 65 2026 rookie RBs scored. Provenance JSON alongside.

**gamma = 0.6** — NOTE the deliberate difference from college QB (R35), which uses **0.4**.
Pool: FBS RB seasons with **>= 75 rush attempts**, one row per player-season, 2014-2025.
Anchor fitted on **RBs who reached the NFL** (n=396): p5 = -0.2752 -> 52, p98 = +1.1628 -> 95,
clip **[50, 99]**.

Weights (locked 65 rush / 35 receive, age excluded):
`grades_run .35 · yco_attempt .10 · avoided_tackles_rush .10 · explosive .10` (falls back to
`breakaway_percent`) `| grades_pass_route .20 · yprr .05 · yac_per_reception .05 ·
avoided_tackles_rec .05`. **`yardshare` and `elusive_rating` DELIBERATELY ABSENT** (opportunity
confound; double-counts yco + avoided).

Per-facet MoM k, own denominators (rush attempts / routes / receptions):
grades_run 260 · yco 324 · avoided_rush 182 · explosive 292 · route 410 · yprr 313 ·
yac_per_rec **85** · avoided_rec **39**.

### Effective vs nominal weights — nominal is NOT what ships

`nominal x sqrt(median r)`, renormalised: **nominal 65/35 lands at EFFECTIVE 69/31.** The
receiving block LOSES ~4 points, driven by `yac_per_reception` (median r **0.175**, least
reliable facet in the set — delivers .035 effective for .050 nominal). Read any anchor with
this in hand.

### Anchors — 3 of 8

McCaffrey 2016 **91.4 PASS** · Barkley 2017 **91.7 PASS** · Gibbs 2022 **82.8 PASS** ·
Henry 2015 81.0 HIGH · J.Taylor 2019 95.1 HIGH · Bijan 2022 95.8 HIGH ·
Sermon 2020 80.0 HIGH · Davis-Price 2021 56.4 HIGH.

**Henry — the load-bearing 65/35 cell — CANNOT be reached by reweighting.** Measured:
65/35 -> 80.8, 65/35 realloc -> 78.9, 60/40 -> 78.6, 55/45 -> 76.6. Even at an effective 58/42
he stays above band; his rush z's (+1.33 run, +0.89 yco) carry him. The receiving block IS
biting (route -0.70, yprr -0.47) — just not far enough. **Ratified weights shipped unchanged;**
the only defensible tweak found was zeroing `yac_per_reception`, a tidiness gain that changes no
verdict.

**Barkley is scoreable now.** The 2026-07-19 rookie-index prereg recorded him UNTESTABLE
("final 2017, pre-PFF") and substituted Breece Hall. `college_rushing_summary_2017.csv` was
written **2026-07-20**, the day AFTER — the call was correct when made and the pre-2019 PFF
expansion superseded it. No substitution needed here.

### HONEST LABEL — do not cite either number as validation

This is the 8-facet PFF index that fired **rc +0.329 = DEAD (< .35)** in
`PREREG_pff_richer_rookie_2026-07-20`. The shipped RB rookie instrument is the **PBP index,
rc +0.501 CLEAN**, and DOES-PFF-ADD was a **FAIL**. Ships DESCRIPTIVELY at Joseph's direction.

**Board policy — DIRECTED, against the recommendation.** I recommended FILL-BLANKS-ONLY so a
DEAD instrument would never overwrite a CLEAN one. Joseph directed **"replace with pff in all
places"** (2026-07-27), and R36 now REPLACES the box-score RB value on every row it covers, on
both the Draft Board and the Rookie Board. Rows R36 does not cover keep the box-score value.
Recorded as a directed decision, not a measured one.

Displayed movement on the 2026 rookie board: **Love 78.6 -> 95.6**, Coleman 73.0 -> 82.2,
Johnson 66.5 -> 75.5, Allen 67.2 -> 72.9, **Price 79.1 -> 67.4**, **Claiborne 67.5 -> 52.8**;
newly covered — Black 62.2, Randall 59.8, McGowan 57.6, Washington 57.3, Miller 50.0.
`rookie_score_2026.csv` itself is UNCHANGED on disk (md5 `57b5b6c5...`) — this is a display-layer
preference, not a rewrite of the artifact.

### KNOWN LIMITATION — no strength-of-schedule adjustment

Facets are z-scored within position within season across ALL FBS players; a carry against
Alabama and a carry against a Group of Five defence count identically. PFF college carries no
conference field. Visible consequence in the 2026 class: **nine of the top ten are UDFA or Day
3** — Frank Gore Jr. (So Miss) 2nd, Coleman Bennett (Kennesaw) 4th, Kentrel Bullock (S Alabama)
5th — while Price (pick 32) lands 13th and Jam Miller (pick 245) sits on the floor. Joseph
accepted this knowingly ("its fine, ship it as is"). Descriptive only.

**Where the two RB instruments disagree, the measured evidence favours PBP:** Price PFF 67.4
(13th) vs PBP 79.1 (1st); Claiborne PFF 52.8 (41st) vs PBP 67.5 (5th); Singleton PFF 62.7 (22nd)
vs PBP 71.1 (4th).

**Validation:** full suite 207/207; AppTest 10/10. All protected artifacts byte-identical
(`talent_score_2026.csv` `d7c1a575...`, `rookie_score_2026.csv` `57b5b6c5...`,
`college_qb_score_2026.csv` `ffa9f0da...`, `nfl_qb_score_2026.csv` `47f8ea81...`, 7 pkls, 4 raw
projection CSVs). `tests/test_college_qb_score.py` strengthened: the fill test now proves NO existing
talent score is ever overwritten, rather than counting non-QB rows.

### Carried open

- **Floor inconsistency between the two college scores:** college QB clips at **40** (160 below
  50), college RB at **50** (248 clipped). Both defensible, but they should probably match.
- Low anchors (Sermon, Davis-Price) do not respond to weights at ANY split — the same conclusion
  R34/R35 reached. The lever is a percentile display map or less shrinkage, not weights.

---

## R37 (RATIFIED-2026-07-27 by Joseph) - NFL RB TALENT SCORE - SHIPPED

`build_nfl_rb_score.py` -> `nfl_rb_score_2026.csv` (md5 `71973d38...`), **85 qualified RBs**
(>= 100 carries across 2023-2025; per-season z on a >= 40-carry reference). gamma **0.55**.
Anchored WITHIN the qualified pool, clip **[50, 99]**. 12 facets, **ratified 60 rush / 40 receive
SHIPPED UNCHANGED** - a reliability-driven alternative is recorded below but NOT applied.

`talent_score_2026.csv` NOT regenerated (md5 `d7c1a575...`). The board prefers R37 for **RB rows
only**; QB reads R34, WR/TE still read R29 - three sources, disjoint by position.

### k vector (printed before the anchors, per Joseph's check)

grades_run 1170 - **RYOE 3172** - yco_attempt 452 - MTF_rush 271 - success_rate 588 -
breakaway_pct 236 - EPA_rush 688 - grades_pass_route 531 - yprr 753 - receiving_EPA_target 85 -
YAC_reception 65 - drop_rate 34.

**Joseph predicted `breakaway_pct` would blow up; it did NOT** - r = 0.452, second-most reliable.
**The blowup is `RYOE`: k = 3172, r = 0.067**, a .100 nominal weight delivering .026 effective.
`grades_run` is second-worst at r = 0.143.

### Effective vs nominal - the prediction inverted

**Nominal 60/40 lands at EFFECTIVE 56/44.** Joseph predicted ~65/35 (thin receiving denominators
shrinking harder). They ARE thin (40 targets, 33 receptions) but their k values are correspondingly
tiny (85/65/34) because those facets are stable year to year, while the rush block's two heaviest
facets are the least reliable in the set. **The receiving block GAINED weight.**

### Anchors - 4 of 7

Bijan **99.0 PASS** - Gibbs **97.2 PASS** - Achane **93.9 PASS** - Zack Moss **60.8 PASS** -
Henry 85.6 (HIGH by 0.6) - Kyren Williams 66.8 LOW - Josh Jacobs 81.9 HIGH.

- **Kyren 66.8 answers his own cell.** Excluding yards-before-contact DID isolate him from the
  blocking - run +1.11 against route -0.32 / yprr -0.59, more completely than the band assumed.
- **Jacobs is unreachable:** route grade **+1.56**, genuinely elite.

### Measured alternatives - recorded, NOT applied

**"P1" (reliability-driven):** RYOE .100->.040, grades_run .100->.080, into MTF_rush .130 /
yco_attempt .120 / breakaway .095. Nominal stays 60/40; **effective moves 56/44 -> 58/42**;
anchors go **4 -> 5** (Henry enters band at 84.2). P2/P3 also reach 5 but distort the ratified
split for nothing - Jacobs only moves 81.9 -> 80.0.

**gamma sweep 0.55 / 0.65 / 0.75:** CMC 79.3/80.8/82.3, Barkley 66.9/68.0/68.8,
**Taylor 70.2/69.3/68.6 - moves the WRONG way**. No single gamma helps all three; Gibbs drops
97.3 -> 95.9 and Bijan 99.0 -> 97.9 as the cost. **gamma is not the lever.**

### VOLUME DISCIPLINE - where it is and is not in the score

Every facet is a rate or a grade; touches, snap share, red-zone share, total yards/TDs,
yards-before-contact and top speed are excluded by design. Volume still enters through two
deliberate channels: the within-player season weight, and Stage-3 reliability -
**corr(carries, sqrt(r)) = +0.91**. Net **corr(carries, final score) = +0.15**. Quartile medians:
Q1 68.7 / Q2 62.3 / Q3 67.2 / Q4 70.0.

**ONE facet carries a genuine volume signature: `grades_run`, corr +0.47 with carries** (PFF run
grades rise with workload) vs +0.15/+0.13/+0.16 for the other rush facets. It **INFLATES**
high-volume backs - so CMC, Barkley and Taylor are currently scored slightly HIGH, not low.

**Route grade was tested for the same defect and CLEARED:** corr(routes run, route grade) = +0.244,
and four backs with near-identical heavy route volume span -0.48 (Barkley, 650 routes) to +2.05
(McCaffrey, 776). It measures technique, not usage - so Taylor's -0.88 and Barkley's -0.48 are
honest reads.

### SUBSTITUTION and blend label

`success_over_expected` has NO source (NGS carries RYOE and `efficiency`, no expected-success
model) - **PBP rush SUCCESS RATE** is used in its place. The Stage-5 college input is the R36
index, which fired **rc +0.329 DEAD**; the blend is DESCRIPTIVE, not validated. Stage 5 is gated
on **CAREER NFL seasons <= 3**, never window volume.

### Board effect

57 of 76 board RBs scored; 19 below the volume floor are BLANK, never backfilled from R29.
Largest moves vs R29: Gibbs 69.4 -> 97.2, Jacobs 55.7 -> 81.9, Skattebo 68.4 -> 85.8,
Walker 74.7 -> 91.8, Hampton 73.3 -> 84.6, Conner 76.6 -> 86.9.
`nfl_talent` coverage now WR 85 / RB 57 / TE 31 / QB 28.

**Validation:** full suite 208/208; AppTest 10/10; all protected artifacts byte-identical.
The QB test's "non-QB reads R29" assertion was correctly tripped by this ship and **narrowed to
WR/TE** rather than loosened.

---

## R38 (RATIFIED-2026-07-27 by Joseph) - COLLEGE WR TALENT SCORE - SHIPPED

`build_college_wr_score.py` -> `college_wr_score_2026.csv` (md5 `6e55edf5...`), **2,872 WRs**;
755 reached the NFL; **122 of 149 2026 rookie WRs scored**. gamma **0.5** (57/29/14), 150-route
season floor, clip [50, 99]. Weights: route .400 / yprr .250 / contested .100 / avoided_rec .100 /
hands_drop .075 / yac_rec .075. `yardshare`, `dominator` and target share DELIBERATELY ABSENT.

**FRAMING:** WR is DEAD across six instrument classes. These anchors test only whether the score
DESCRIBES college WR talent. A high score for a future bust is the construct working.

**Pool RULED FOR WR on its own terms** (not inherited): drafted-only puts **4 of 7** anchors in
band vs **3 of 7** for the all-WR pool. The QB small-pool objection does not apply - 755 resolved
vs QB's 178.

### k vector and effective weights

route 418 (r .543) - yprr 420 (r .542) - **contested 95 (r .152)** - avoided_rec 70 (r .449) -
hands_drop 221 (r .300) - yac_rec 60 (r .488).

| facet | nominal | effective |
|---|---:|---:|
| grades_pass_route | .400 | **.437** |
| yprr | .250 | **.273** |
| **contested_catch_rate** | .100 | **.055** |
| avoided_tackles_rec | .100 | .099 |
| grades_hands_drop | .075 | .059 |
| yac_per_reception | .075 | .077 |

**Route-craft block runs 71% effective against 65% nominal.**

### Anchors - 4 of 7 (drafted-only)

DeVonta Smith 2020 **99.0 PASS** - Nabers 2023 **94.6 PASS** - **Drake London 2021 85.1 PASS** -
Deebo 2018 **85.3 PASS**; Treadwell 2015 83.8 LOW, JSN 2021 99.0 (clipped) HIGH,
Velus Jones 2021 75.1 HIGH.

### TWO DISCLOSED DEFECTS - shipped knowingly

1. **`contested_catch_rate` delivers .055 effective vs .100 nominal** (r = 0.152, median 17
   contested targets). **Raising it to .180 fixes the mechanics (.104 effective) and KNOCKS
   DRAKE LONDON OUT OF BAND** (85.1 -> 84.6) - the archetype the facet exists for. His contested
   z is only +0.94; he passes on route +1.66 / yprr +1.65. Measured and REJECTED; anchors 4 -> 3.
2. **The omit-and-rescale path affects 709 of 2,872 players - 228 of 755 drafted (~30%)**, not
   the ~87 the spec anticipated. Roughly a third of the drafted pool is scored on FIVE facets
   rather than six, so the composite's facet set varies by row. Treadwell is one of them (his
   contested z is NaN) and he misses his band. **Open question left with Joseph:** drop contested
   entirely and redistribute across the five that always exist, vs keep the per-row rescale.

### Other findings

- **Travis Hunter is UNSCORABLE** at the 150-route floor - two-way snaps, worse than the
  shrinkage Joseph predicted.
- **Ja'Marr Chase is NOT a forcing case** for the absent-season rule: his final season is 2019, so
  the 2020 opt-out falls OUTSIDE his window. Scores 94.7 on 588 effective routes. De facto rule
  remains: a zero-volume season contributes no weight, so the player shrinks toward the mean.
- **Tyson consistency check: 82.4 vs the board's 87.0** - same direction, 4.6 lower, different
  instrument. Not counted in the tally.
- **JSN clips at 99.0** with route +2.66 / yprr +3.55 / contested +2.43 - the best profile in the
  panel. A ceiling problem, not a weights problem; he and DeVonta Smith cannot be separated.
- **Velus Jones 75.1 vs 58-68** - the same low-anchor pattern as Sermon, Davis-Price and Fields:
  productive in college, and the band encodes an NFL outcome the facets do not carry.
- SUBSTITUTION: no `catchable_targets` column; `grades_hands_drop` uses `targets`.

### Board effect

WR college talent REPLACES the box-score value wherever R38 covers a player (matching the RB
policy). Rookie Board WR coverage **14/33 -> 31/33**. Draft Board college_talent WR 16 / RB 8 /
TE 4 / QB 2. A third returning-player expander ("College WRs who are not in the 2026 rookie
class") joins the QB and RB ones.

**Validation:** suite 208/208; AppTest 10/10; `talent_score_2026.csv` `d7c1a575...` and
`rookie_score_2026.csv` `57b5b6c5...` byte-identical.

---

## R39 (RATIFIED-2026-07-27 by Joseph) - NFL WR TALENT SCORE - SHIPPED

`build_nfl_wr_score.py` -> `nfl_wr_score_2026.csv` (md5 `ca1e6b79...`), **164 qualified WRs**
(>= 250 routes across 2023-2025; per-season z on a >= 150-route reference). gamma 0.55,
clip [50, 99]. **Ratified weights SHIPPED UNCHANGED.** Board: R39 owns WR rows; QB reads R34,
RB R37, TE still R29 - four sources, disjoint by position.

### k vector (printed before the anchors, per Joseph's flag 1)

yprr 293 (r .645) - grades_pass_route 236 (r **.693**) - **deep_explosive 37 (r .296, med N_eff
15.6)** - receiving_EPA_target 131 (r .400) - avg_separation 51 (r .664) -
**contested_catch_rate 59 (r .219, med N_eff 16.5)** - drop_rate 215 (r .289) -
YAC_over_expected 86 (r .417) - MTF_rec 43 (r .565).

**Joseph's flag 1 CONFIRMED and quantified.** contested r = 0.219 is the WR analog of the QB
side's pressure_grades_pass at 0.231, exactly as predicted. **Archetype block (contested + deep)
delivers 12.6% EFFECTIVE against 17.5% nominal** - he predicted "closer to 10%".
**Route block runs 46.5% effective against 40% nominal.**

### Anchors - 4 of 7

St. Brown **95.2 PASS** - Deebo **86.0 PASS** - **Drake London 85.5 PASS** -
Tolbert **58.7 PASS**; Chase 94.5 (LOW by 0.5), Jefferson 85.5 LOW, **Mike Evans 76.9 LOW**.

- **London PASSED** - the score DOES isolate a good receiver from unstable quarterbacking
  (route +1.87, yprr +1.42). That load-bearing cell holds.
- **Evans FAILED, and it is the denominator, not the weights.** His contested z is +0.47, the
  best in the anchor set, but 16.5 contested targets a season cannot carry a player at any weight.

### Weight alternatives - MEASURED and REJECTED

| variant | archetype effective | Evans | anchors |
|---|---:|---:|---:|
| **current** | .126 | **76.9** | **4** |
| P1 contested x2 (.170) | .190 | **76.5** | 3 |
| P2 both archetypes | .238 | **75.8** | 3 |
| P3 drop confounded facets | .103 | 80.3 | 4 |

**DOUBLING contested weight moves Evans the WRONG way** (76.9 -> 76.5): the weight comes out of
route facets he is above average on (+1.21 yprr, +1.22 route), so he loses more than he gains.
P2 drops him to 75.8 and pushes Deebo out of band. **P3 - dropping the two situation-confounded
facets - is the only principled alternative** (Evans 80.3, London 88.0) and ties at 4; recorded,
not applied. **Jefferson is untouched by every variant** (85.5/85.2/84.5/85.6) - his window z's
simply do not separate him from London. A football claim, not a calibration error.

### TWO DISCLOSED CONFOUNDS (Joseph's flags 2 and 3)

Two of nine facets measure situation as much as player: **`deep_explosive`** (mean EPA on targets
with air_yards >= 20) carries the QB confound - deep production depends on who is throwing; and
**`avg_separation`** carries the slot/scheme confound - alignment buys separation, not skill.

### Stage 5 - the blend behaved as hoped, no defect to catch

College_WR is dead across six instrument classes. **EB drove its median contribution among the 50
blended players to 0.070 on its own** - no k_lambda estimation problem. Nabers lambda .913,
Odunze .955, Worthy .952. Guarded by a test asserting it stays < 0.15.

### Board effect

Top of pool: Puka Nacua 99.0, JSN 97.3, Nico Collins 95.5, St. Brown 95.2, Chase 94.5,
Zay Flowers 92.7.

**Validation:** suite 209/209; AppTest 10/10; `talent_score_2026.csv` `d7c1a575...` and
`rookie_score_2026.csv` `57b5b6c5...` byte-identical.

---

## R40 (RATIFIED-2026-07-27 by Joseph) - COLLEGE TE TALENT SCORE - SHIPPED

`build_college_te_score.py` -> `college_te_score_2026.csv` (md5 `36727e60...`), **1,101 TEs**;
318 reached the NFL; **56 of the 2026 rookie TEs scored**. gamma **0.6** (51/31/18) - the flattest
of the four college indices, ruled on the thin-panel argument. Route floor lowered to **100**.
Weights RATIFIED and SHIPPED UNCHANGED: route .435 / yprr .250 / avoided_rec .100 /
hands_drop .075 / yac_rec .075 / contested .065. Blocking excluded (fantasy-irrelevant).

**FRAMING:** TE fired at **+0.294** (grade+share+age) and **+0.326** (richer) - both DEAD, and the
bar does not move for a near-miss. These anchors test DESCRIPTION only.

**gamma of record across the four college indices: QB 0.4 / WR 0.5 / RB 0.6 / TE 0.6.**
RB was ruled and shipped at 0.6 earlier the same day - it was NOT left unset.

### Flag 1 CONFIRMED TO THE DECIMAL

| facet | nominal | effective | r | med N_eff |
|---|---:|---:|---:|---:|
| grades_pass_route | .435 | **.481** | .530 | 309 |
| yprr | .250 | **.288** | .571 | 309 |
| avoided_tackles_rec | .100 | .086 | .337 | 29 |
| grades_hands_drop | .075 | .048 | .190 | 43 |
| yac_per_reception | .075 | .066 | .351 | 29 |
| **contested_catch_rate** | **.065** | **.030** | **.100** | **7.0** |

Joseph predicted contested "comes out near 3%" - **it is 3.0%**; and that route+yprr would climb
"well above 68.5%" - **it is 77.0%**. **The trim did not reduce the facet, it deleted it.**
r = 0.100 on a median of SEVEN contested targets is the lowest reliability of any facet in any of
the five builds.

### Anchors - 2 of 6, the weakest of the program

Bowers 2023 **99.0 PASS** - McBride 2021 **91.7 PASS**; Pitts 2020 89.7 LOW,
**Gesicki 2017 77.9 LOW**, Hunter Henry 2015 94.8 HIGH, Jacob Harris 69.9 HIGH.

- **Gesicki is the diagnosis he set up.** His contested z is **+1.50, the strongest single facet
  reading anywhere in the five builds**, and he still lands 77.9.
- **Hunter Henry 94.8 is the same coin.** Route grade +2.56 with route-craft at 77% effective
  carries him past the ceiling. His cell asked whether 68.5% route dominance is too much; it is
  not 68.5%, it is 77%, and yes.
- **Jacob Harris resolved to final season 2025, not 2020** - different player or a re-entry. Cell
  UNVERIFIED.
- **Loveland scores 87.6** but is NOT in `rookie_score_2026.csv`, so that consistency cell has no
  board reference.

### Weight alternatives - MEASURED and REJECTED (all three)

| variant | contested eff | route-craft eff | Gesicki | Hunter Henry | in band |
|---|---:|---:|---:|---:|---:|
| **current** | .030 | .770 | 77.9 | 94.8 | **2** |
| P1 contested .20 | .101 | .678 | 79.1 | **97.5** | 2 |
| P2 contested .27 | .144 | .622 | 79.5 | **99.0** | 2 |
| P3 drop contested | .000 | .798 | 77.7 | 93.7 | 1 |

**The non-obvious result: raising contested makes Hunter Henry WORSE.** He is on the
omit-and-rescale path (contested NaN), so pulling weight out of route renormalises his REMAINING
facets over a smaller base and route dominates harder - 94.8 -> 97.5 -> 99.0. **The 268 rescaled
players are structurally immune to contested reweighting.** Gesicki moves only 77.9 -> 79.5 even
at 27% nominal. P3 is the cleanest object (every TE on the same five facets) but loses McBride.

### Disclosed, not fixed

Contested is functionally absent (3.0% effective); route-craft runs 77.0% against 68.5% nominal;
**268 of 1,101 players are scored on five facets rather than six**. Thinnest and least
well-behaved of the four college indices, on an instrument that already fired dead.

### Board effect

TE college talent REPLACES the box-score value wherever R40 covers a player. Rookie Board TE
coverage **3/20 -> 19/20**. Draft Board TE rows: Stowers 92.0, Trigg 81.5, Klare 76.3, Sadiq 74.3.
A fourth returning-player expander completes the QB/RB/WR/TE set.
2026 class top: Rohan Jones (Arkansas) 99.0 on a **yprr z of +6.56 - an extreme outlier worth a
look before trusting**; Stowers 92.0, Koziol 84.7, Trigg 81.5. **Sadiq is 13th at 74.3** despite
being the pick-16 TE carried in the analyst overlay.

**Validation:** suite 209/209; AppTest 10/10; `talent_score_2026.csv` `d7c1a575...` and
`rookie_score_2026.csv` `57b5b6c5...` byte-identical.

---

## R41 (RATIFIED-2026-07-27 by Joseph) - NFL TE TALENT SCORE - SHIPPED. PROGRAM COMPLETE.

`build_nfl_te_score.py` -> `nfl_te_score_2026.csv` (md5 `50bfdab7...`), **92 qualified TEs**
(>= 150 routes across 2023-2025; per-season z on a >= 100-route reference). gamma 0.55,
clip [50, 99]. Ratified weights SHIPPED UNCHANGED - route block 43% nominal, tilted to route
grade (.240) over yprr (.190).

### THE HEADLINE - flag 2 answered, the rebuild fixes the known TE defect

**Brock Bowers was TE26 of 31 at 62.9 in the shipped R29 artifact**, arithmetically locked out of
the top 12. Under R41 he is **TE6 of 92 at 88.8**, on route grade +1.75 and yprr +1.31. The old
facet set was simply blind to him. He still misses 95-99 because MTF is -0.67 and separation
-0.54 - elite route craft, ordinary athletic-archetype facets.

### k vector (printed before the anchors)

grades_pass_route 320 (r .530) - yprr 417 (r .464) - **receiving_EPA_target 529 (r .092)** -
avg_separation 362 (r .215) - contested_catch_rate 34 (r .183, med N_eff 7.5) - drop_rate 154
(r .257) - YAC_over_expected 85 (r .451) - MTF_rec 30 (r .578) -
**deep_explosive 26 (r .129, med N_eff 3.9)**.

**TE is the worst position in the program for thin denominators.** `deep_explosive` sits on a
median of **3.9 deep targets a season** and `receiving_EPA_target` on 53.5 targets at r = 0.092 -
both effectively broken. Route block runs **51.4% effective against 43% nominal** (Joseph
predicted "well above 43%"); contested landed at 6.1% against his predicted 3-4%.

### Anchors - 2 of 7

McBride **95.8 PASS** - Cade Otton **63.5 PASS**; Bowers 88.8 LOW, Gesicki 66.6 LOW,
LaPorta 94.8 HIGH, **Kelce 78.5 LOW**, Kincaid 88.6 HIGH.

**Kelce answers his cell, but not as assumed.** The tilt was supposed to carry an aging elite on
route craft. It cannot: his **route z is only +1.04 and yprr +0.79**. The 43% block did all it
could - there is no elite route craft left to amplify. **Gesicki is unreachable** (route +0.43,
yprr +0.11, contested +0.06 - league-average everywhere).

### Weight alternatives - MEASURED and REJECTED

| variant | route block eff | Bowers | McBride | in band |
|---|---:|---:|---:|---:|
| **current** | .514 | 88.8 (rk 6) | **95.8** | **2** |
| P1 route .30 | .516 | 89.2 (rk 6) | 95.9 | 2 |
| P2 route .34 | .518 | 89.4 (rk 6) | 96.0 | 2 |
| P3 drop 2 weakest | .559 | **91.1** | 97.5 (out) | 1 |

**Pushing route .240 -> .340 (a 42% increase) moves Bowers 0.6 points** and leaves him rank 6 in
every variant - the block is already past its effective ceiling, so nominal weight barely reaches
the mix. **P3 (drop `receiving_EPA_target` and `deep_explosive`) is the principled alternative on
reliability grounds** and is the only one that helps Bowers materially, but it pushes McBride out
of band. Recorded, not applied.

### Blend

College_TE fired dead (+0.294 / +0.326). EB drove its median contribution among the 24 blended
players to **0.061** on its own. Loveland lambda .940 (score 92.6, rank 4), Tyler Warren .945
(76.7, rank 19).

### MIGRATION COMPLETE

Every board position now reads a dedicated per-position build: **QB R34 / RB R37 / WR R39 /
TE R41**. `talent_score_2026.csv` now feeds **NO** board column. It stays on disk unregenerated
(md5 `d7c1a575...`) for the closed campaign, and a test asserts it never moves.

Board TE movement vs R29: Kittle 78.8 -> 99.0, **Bowers 62.9 -> 88.8**, Loveland 71.3 -> 92.6,
Kincaid 68.3 -> 88.6, Fannin 72.1 -> 87.7; down: Kraft 99.0 -> 92.1, Likely 85.4 -> 79.7.

**Validation:** suite 209/209; AppTest 10/10; `talent_score_2026.csv` and `rookie_score_2026.csv`
byte-identical.
