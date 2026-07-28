# PREREG — Rookie Score facet weights (one-shot), 2026-07-17

**Status:** REGISTERED before any metric was computed. Rules below are frozen; results
append under OUTCOMES without modifying them.

**Commissioned and pre-ratified by Joseph (2026-07-17 session order):** the owner
delegated final design authority for this one experiment to decide the rookie box-score
facet weights, whose shipped state is "EQUAL WEIGHT (owner sets weights later)"
(`build_rookie_score.py:5-6`; `rookie_score_2026.provenance.json`). The session order IS
the ratification signature for the decision rule below; the rule fires mechanically.

## Authority seam (R13/R14) — declared, not dodged

- R13 (`SPEC.md:137`): weights are OWNER CONFIG. This experiment IS the owner setting the
  rookie weights — via a decision rule he pre-authorized, not by agent taste.
- R14 (`SPEC.md:139`): "no vector is chosen, named, or recommended by the agent —
  permanently." R14's scope (per `GUIDE.md:168-171`) is benchmark/named-player-driven
  selection ("no weight or parameter is ever chosen to move a named player"). This
  experiment optimizes NOTHING against named players or benchmark lists; the selection is
  a pre-registered out-of-fold gate against the project's own talent construct, and the
  owner pre-committed to accept its output either way. Precedent that owner-authorized,
  pre-registered, one-shot college→NFL measurement is NOT fenced:
  `talent-score-design.md:245-247` (the ρ measurement, "NOT fenced: α_NFL is the
  project's own estimand").
- R9 (`SPEC.md:127`): NOT violated — no re-execution of `cfb_rho.py`, no regeneration of
  the four registered PBP estimators. New quantities only.
- "No college→NFL fit" fence (`talent-score-design.md:270-271`): NOT crossed — that fence
  forbids fitting a college→NFL SCALE rescaling (inflating the prior on the NFL scale).
  This experiment fits RELATIVE weights among college facets; the anchor family, clip,
  and scale disclosure are untouched.
- H7 fence: untouched — no ADP, no price, no market-error target anywhere in this file.
- Sealed slices: untouched — panel is college 2014-2025 vs 2018+ NFL vets; seasonal
  2008-2015 model-vs-ADP territory is never contacted.

## Hypothesis + mechanism

Some non-negative weighting of the live box-score facets tracks the NFL talent construct
better out-of-fold than equal weights, per position. Mechanism: the facets measure
different constructs (usage/share vs per-play efficiency) with different reliabilities
and different construct overlap with the NFL latent-effect composite; equal weight is a
default, not an optimum. Origin of the idea: the owner's commission — not a data peek.

## Panel (frozen; mirrors the registered box_score_test2 assembly, step2.py)

- College side: `seasonal_projections/college_production_2014_2024.csv` + the frozen
  `talent/college_production_2025_cache.csv` (substituting the cache for step2.py's live
  `fc.aggregate_season(2025)` call — the freeze-plan equivalent; deterministic).
  Career summary per normalized name (step2.py `summ`, verbatim): dom_best =
  dominator.max, recshare = last-season rec_yds_share, ypc = nanmean, ypr = nanmean,
  games = sum. ALIAS map from step2.py:12 applied.
- Membership: inner join to `nfl.load_draft_picks()` RB/WR/TE (HB/FB→RB), games ≥ 8
  (step2.py:21-22; position = first-duplicate rule, verbatim).
- NFL target: **the SAME target as box_score_test2** — unshrunk composite
  Σ_f W_f·zmed_f from frozen `C:/tmp/S2.pkl` (Class B pin `9b3d9df67ae88272f4eab0a0ae1cbb21`,
  verified before every run), with the PROTOTYPE weight vector `S2["W"]` and
  `knew = kold·(sam/sad)²` from `S2["QU"]` (step2.py:8-10 verbatim). **Declared:**
  `S2["W"]` ≠ config.py's later-ratified vectors (e.g. RB .25/.25/.20/.15/.10/.05 vs
  ratified .22/.28/.14/.16/.12/.08) — identity with the registered target requires the
  prototype vector; this is a feature of the frozen target, not an error.
- Join + filter: gsis→names→nn, mask `(wt>0) & college-composite-available & aw.notna()`
  (step2.py:62-63 verbatim). Expected n (structural check before firing, counts only):
  RB 195 / WR 278 / TE 120 (`rho_provenance.json` box_score_test2). If the rebuilt panel
  n differs, STOP and report before firing.
- 2026 class: has no NFL facet data → excluded from the correlation sample by the mask
  (as in the registered run). Its college rows DO participate in the z-pool moments,
  exactly as they did in step2.py — mirrored, disclosed.
- Draft class per player (fold key; new, registered here): draft `season` from
  `load_draft_picks`, max per normalized name. Classes with < 5 panel rows for a
  position are excluded from the fold mean (count reported).

## Features

Live facet z per position (`build_rookie_score.py:33` / step2.py:23):
RB {dom_best, ypc} · WR {dom_best, recshare, ypr} · TE {dom_best, recshare, ypr}.
z-scored over the position's ref pool (step2.py:27 moments), **unshrunk** — no
games-shrink in evaluation (owner's spec).

**Pipeline-difference flags (required disclosure):**
1. The registered box_score_test2 college composite WAS games-shrunk (`×g/(g+6)`,
   step2.py:28); this experiment evaluates UNSHRUNK facet z per the owner's spec. The
   equal-weight arm here is therefore NOT numerically identical to the registered R_z.
2. The 2026 shipping build z-scores over a pooled historical+class pool and applies wg
   shrinkage at score time (`build_rookie_score.py:151-156`); the experiment's z is over
   the historical ref pool only. Any shipped-weights consequence keeps the shipping
   build's own z/shrink/anchor machinery and swaps ONLY the facet weights.
3. Missing-facet rule (registered): per-player weighted nanmean — renormalize the weight
   vector over that player's available facets (reduces to step2's nanmean under equal
   weights, keeping the panel identical). Count of affected rows reported.

## Method

Grid over the weight simplex, step 0.05, weights ≥ 0 summing to 1, per position.
RB: 21 vectors. WR/TE: 231 vectors (includes all single-facet corners). Composite =
renormalized Σ w·z as above. Tie-break on the gate metric: lexicographically smallest
vector (deterministic). Equal weights (RB ½/½; WR/TE ⅓/⅓/⅓ — not a grid point for 3
facets) is evaluated as its own vector: same folds, same metric.

## Evaluation + decision rule (ONE SHOT)

- Leave-one-draft-class-out folds (per position; ≥5-row classes).
- **Primary metric:** mean out-of-fold Spearman IC between composite and the target,
  numbers at 3 decimals.
- Report alongside (never gates): full-sample disattenuated Pearson
  (r/√(mean wt), step2.py:66) for the equal and best vectors — for comparability with the
  .385/.000/.254 record, expected to drift from those numbers because of flag 1 above.
- Per-fold argmax vector reported (stability read).
- **SHIP GATE, per position, decided now:** fitted weights replace equal ONLY IF
  (mean OOF IC_fitted − IC_equal) ≥ +0.05 AND IC_fitted ≥ +0.10. Otherwise **EQUAL
  WEIGHTS ARE RATIFIED** for that position as the deliberate default, this experiment as
  the evidence.
- **Secondary (report-only, never gates, never re-optimized):** Spearman of the
  gate-winning composite vs best-season half-PPR PPG in NFL seasons 1-3 (min 6 games,
  REG only, half-PPR = (std + PPR)/2 from nflverse weekly player stats), per position.
- One shot. No metric substitutions, no grid changes, no fold re-cuts, no subgroup
  rescues after seeing results. Corner solutions are legal outcomes and get reported
  plainly. A crash is not a result (fix and rerun); a completed run's numbers are final.

## Blind power note (structure-only, computed before firing)

Single-fold Spearman SE ≈ 1/√(n_fold−1): WR folds ≈ 25 rows → fold SE ≈ .20, SE of the
~11-fold mean ≈ .06; TE fold SE ≈ .30, mean SE ≈ .10. The +0.05 gate margin is therefore
≈ 1 SE — the gate is deliberately conservative: it also has to absorb the selection
optimism of a 231-point grid argmax. Asymmetry accepted and pre-committed: low power
inflates false negatives only, and the negative outcome (equal ratified on evidence) is
itself the deliverable that resolves the pending stamp. A pass under this gate is a
decisive weighting, not a marginal one.

## Pre-committed outcomes

- FAIL (either gate clause, any position): equal weights RATIFIED for that position —
  the pending-owner-weights stamp is resolved to "equal, ratified by pre-registered
  test 2026-07-17"; no re-runs, no alternative metrics; the question "do fitted
  box-score facet weights beat equal OOF" is CLOSED for this facet set and panel.
- PASS (both clauses): the fitted vector is reported with full diff consequences to a
  TEMP-path rebuild only; the shipped `rookie_score_2026.csv` (Class A blob pin
  2040df2e…) is NOT touched this session; Joseph commits any artifact change under a
  new R-numbered ratification per SPEC's frozen-fence rules.
- Either way, no rho record is superseded; R10 disclosure language unchanged.

## Blindness disclosure (required reading)

The author of this prereg has seen: the registered composite-level correlations
(box rc RB .385 / WR .000 / TE .254; PBP disatt .376 WR), the shipped 2026 rookie CSV
(including per-facet z of the 2026 class, who are NOT in the evaluation sample), and
Tyson-related recon from a prior video session. The author has NOT seen: any per-facet
vs target correlation, any weighted-composite metric on the historical panel, any
fold-level quantity. Grid step, gate thresholds, metric, folds, and the secondary all
come verbatim from the owner's commissioning order, not from the author post-peek.
Partially blind, declared as such; the owner pre-accepted this disclosure in the
commissioning order. Deviation from house step-8 (fresh-session fire) is owner-ordered:
this session builds AND fires, main thread, once.

## Run provenance (appended at fire time)

- Harness: `_rookie_weight_experiment.py` (session scratchpad; sha256 + full stdout
  appended below).

---

# OUTCOMES (recorded after the fact; rules above were not modified)

**Fired 2026-07-17, main thread, AI_hedge_fund venv.** Harness
`_rookie_weight_experiment.py` (session scratchpad).

**Run provenance — two executions, one defect, fully disclosed:**
- Run 1 (sha256 `97dfdbaf8ed2a8ee6913d7eb46a971909e3a45df0384d1377e5d565c2f2bc7ad`)
  completed but carried a NaN-propagation defect: the single RB row with a missing
  facet (ypc) produced an undefined composite under any vector with zero weight on
  his available facet; scipy propagated NaN through that fold's Spearman, and the RB
  grid argmax was selected on NaN comparisons (printed best "(0,1) IC=nan"). Treated
  as crash-class per the registered rule ("a crash is not a result"), NOT as a number.
- Run 2 (sha256 `c8bc0883d0900bf7fd51e40110642a25930befdaff935716e80dc43077120e21`)
  fixed only that: a player with no available facet under a vector is
  pairwise-excluded from that fold (the registered missing-facet rule's honest
  implication). **WR and TE outputs are numerically identical across both runs**
  (zero missing-facet rows there — deterministic), verified line-by-line; only the
  RB search path changed. Run 2's numbers are final.

**Structural verification before fire:** panel n reproduced the registered
box_score_test2 exactly — RB 195 / WR 278 / TE 120; 11 usable folds (draft classes
2015–2025) per position; sub-5 classes excluded: RB {1982:1, 1985:1, 2005:2, 2014:1},
WR {2006:1, 2007:1, 2011:1, 2014:2}, TE {2013:1} (nn-collision strays, as accepted by
the prototype). Missing-facet rows: RB 1, WR 0, TE 0. S2.pkl pin verified both runs.

## Per-position results (mean out-of-fold Spearman IC, 3 decimals)

| Position | n | Equal IC | Corners | Best vector | Best IC | Δ vs equal | Gate |
|---|---|---|---|---|---|---|---|
| RB | 195 | .205 | dom .097 / ypc .133 | (.30 dom, .70 ypc) | .228 | +.024 | **EQUAL RATIFIED** (Δ < +.05) |
| WR | 278 | **−.021** | dom .102 / recshare **−.094** / ypr −.050 | **(.80 dom, .00 recshare, .20 ypr)** | .106 | **+.127** | **FITTED SHIPS** (both clauses pass) |
| TE | 120 | .129 | dom −.025 / recshare .154 / ypr −.037 | (.05 dom, .50 recshare, .45 ypr) | .167 | +.038 | **EQUAL RATIFIED** (Δ < +.05) |

Per-fold argmax (stability): RB mixed dom/ypc (equal is competitive everywhere).
WR: dom-dominant vectors win 6 of 11 folds (incl. pure-dom in 2023/2024/2025);
recshare near-zero weight in 10 of 11 fold winners — the fitted vector is stable in
direction, not just on average. TE scattered (hence the gate fail despite IC .167).

Disattenuated Pearson alongside (report-only, full-sample; expected to drift from the
.385/.000/.254 record per pipeline flag 1): RB equal .362 / best .331; WR equal
**−.001** (independently reproduces the registered ~.000 WR null) / best **.227**;
TE equal .248 / best .245.

Secondary (report-only, gate winners): best-season half-PPR PPG (seasons 1–3, ≥6
games) Spearman — RB .283 (n=166), WR .086 (n=244), TE .261 (n=107). Reported, not
interpreted; never gates.

## Pre-committed consequences now in force

- **RB: equal weights (.50 dom_best, .50 ypc) RATIFIED** — pending-owner-weights
  stamp resolved by this test; fitted-vs-equal for this facet set/panel is CLOSED.
- **TE: equal weights (⅓/⅓/⅓) RATIFIED** — same closure.
- **WR: fitted vector (.80 dom_best, .00 recshare, .20 ypr) passes the ship gate.**
  Candidate rebuild goes to TEMP only this session; the shipped
  `rookie_score_2026.csv` (Class A blob 2040df2e…) is untouched. Joseph commits the
  artifact swap under a new R-numbered ratification, or declines it — either way this
  file records the evidence.
- No rho record superseded; R10 language unchanged; no second run of the search.
