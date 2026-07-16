# Talent Score / Rookie Score — Architecture Spec (Phase 1 build, 2026-07-16)

Status: RATIFIED (R19, 2026-07-16) with the "k derivation of record" amendment below.

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

| Artifact | Written by | Schema |
|---|---|---|
| `fantasy/talent/talent_score_2026.csv` | `build_talent_score.py` (Phase 2 emit) | `gsis_id, display_name, position, score, ci_lo, ci_hi, w (composite reliability), rank_pos, college_share, flag ("†" w<0.40, "‡" w<0.30), per-facet z + w columns` |
| `fantasy/talent/rookie_score_2026.csv` | `build_rookie_score.py` (Phase 2) | `gsis_id (or draft-id), display_name, position, rookie_score, rank_pos, games, per-facet z (box-score index: dominator/recshare/ypc/ypr per position)` |
| `fantasy/talent/rho_provenance.json` | `archive_rho.py` (this session) | The registered rho outputs: PBP rho (all four registered estimators, per position + pooled, n, target label) + box-score test #2 values from RHO2.res, target-labeled. Append-only once written. |

These artifacts JOIN the frozen-artifact fence (MD5-pinned, never mutated) only AFTER
Joseph ratifies and commits. `talent_index_2026.csv` (the single-metric H7 provenance
record) is NOT modified, NOT superseded in place — the Talent Score is a NEW artifact with
a NEW name. `refresh_board_adp.py` never touches any of the three new artifacts.

## (b) Build scripts

| Script | Reads | Writes |
|---|---|---|
| `config.py` | — | — (OWNER CONFIG block: 4 weight vectors PROVISIONAL-UNRATIFIED + deepCPOE 0.00 UNSET; stack constants; mode switches). No code path may alter the vectors. |
| `facets.py` | nflreadpy (player_stats, PBP, PFR advstats, NGS *numerators only*, ff_playerids identity crosswalk), `../seasonal_projections/phase4_band_2026.csv` + `season_dataset_2014_2026.csv` (read-only universe inputs) | checkpoint pickles under `C:/tmp/talent_build/` (scratch, not repo) |
| `model.py` | facet checkpoints | — (fit, sigma_alpha at NS splits, R1 k derivation, residual sigma^2_eps) |
| `composite.py` | model outputs | — (z, w, ONE composite branch, CB anchor, boards, RB pipe) |
| `build_talent_score.py` | all above | Phase 1: measurement checkpoints only. Phase 2 (post-ratification): `talent_score_2026.csv` |
| `build_rookie_score.py` | college_production CSVs (frozen college snapshot per the freeze plan) | Phase 2: `rookie_score_2026.csv` — box-score index per the standing outcome (WR rookie prior is a validated null; PBP index not deployable — cfbfastR lacks 2020/2023-25, CFBD ruled NO) |
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
  shrinkage on top. Pipe ships RB-only at the box-score disattenuated rho (.385,
  weak-disclosed), w and rho from the SAME new median-k build; WR/TE pipe DEAD per bands.
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

- Display slot: `draft_board_2026.py::_load_board_2026` — the current single-metric
  `eff_disp` column is replaced by TWO columns (Talent Score, Rookie Score) fed from the two
  new CSVs, joined on gsis_id (exact).
- Two-cell rules per R12 (dash rule, null-last sort, scale-disclosure line).
- Display 3c: interval as the primary visual; † / ‡ flags; near-ties sorted by confidence.
- Advanced view: per-facet z + w exposure behind an expander; report-only percentiles may
  render THERE only (never in the pipeline).
- Tests retargeted: `test_app_draft_board.py` (AppTest all-tabs), `test_draft_board.py`
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
