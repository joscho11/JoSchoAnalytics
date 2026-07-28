# PRE-REGISTRATION — PFF college QB passing index vs the NFL QB talent construct
**Date:** 2026-07-19 · **Status at commit: BLIND** (no QB college value has been related to any NFL
value; QB alpha-hat VALUES are UNREAD until the fire — only the alpha-hat membership INDEX and the
estimator STRUCTURE/constants were read). One-shot. Joseph reviews this prereg; firing is a later
session.

Sibling to `PREREG_pff_rookie_index_2026-07-19.md` (RB/WR/TE, FIRED 2026-07-19 — the fresh college
index came up DEAD at all three; RB's PBP index shipped CLEAN at +0.501 post-supersession). QB was
held out of that fire (SIZED-NOT-SHIPPED, shot preserved) for two reasons this prereg resolves: the
RB/WR/TE `alpha_w` k-recipe does not cover QB's distinct estimator, and the panel needed the
2014-2018 college passing upload. Both are now in hand.

## HYPOTHESIS
A PFF college passing index — passing grade + age, EQUAL-weighted — tracks the NFL QB talent
construct (alpha-hat) at a band-relevant level.

## INSTRUMENT (frozen)
QB college index over each player's **final + best college season** (2014-2023 finals; no λ decay):
**z(`grades_pass`) + z(−age_at_final_college_season)**, EQUAL weight (½/½), z within the scored
panel. `grades_pass` = mean of the player's final-season and best-season (max-grade) values from
`passing_summary`; age from `players.parquet` birth_date via gsis (≈ Sept 1 of the final season).
NO team-share (meaningless at one QB per team — declared). NO draft capital, NO combine/pro-day
(standing talent-side exclusion). Weights EQUAL (unfitted — not against alpha-hat, not against
anchors).

## PANEL (frozen — membership/counts recon 2026-07-19, NO alpha value read)
Distinct college QBs with **true-final college season 2014-2023, ≥ 150 career dropbacks**, resolving
to an NFL gsis AND **holding a QB alpha-hat entry** (gsis ∈ the S2 `F['QB']` index).
- **Fireable panel n = 103** (the alpha-hat-member intersection — the rows that can enter the rho).
- **gsis-resolved = 178** is the UPPER BOUND only (the 2026-07-19 audit's figure); **75 of the 178
  resolve to a gsis but have NO NFL QB alpha-hat entry** (backups/washouts who never logged enough
  NFL QB snaps to earn a talent-score) and therefore cannot enter the correlation. The panel is the
  103, not the 178 — recorded so the power is honest.

n per true-final year (alpha-hat-member / gsis-resolved):

| final | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | TOTAL |
|---|---|---|---|---|---|---|---|---|---|---|---|
| member | 6 | 8 | 13 | 13 | 13 | 11 | 10 | 7 | 13 | 9 | **103** |
| resolved | 13 | 20 | 17 | 21 | 22 | 20 | 10 | 16 | 19 | 20 | 178 |

Notable finals-2014-2018 additions in the member panel: Mariota, Winston, Goff, Prescott, Mahomes,
Watson, Mayfield, Lamar Jackson, Darnold, Josh Allen, Kyler Murray, Daniel Jones.
- **Ryan Willis promotion recorded:** final 2019, career dropbacks **1063** (Kansas 2015/16 + Virginia
  Tech 2018/19 pooled); under 2019-only data his 141 dropbacks were below the floor. He enters via
  the pooled pre-2019 seasons — the 2014-2018 upload adds one finals-2019 QB, not only 2014-2018 finals.
- **Nick Patti resolution: EXCLUDE (moot).** pff_id 46582 (UCF 2014-16, 47 db) and 77614 (Pittsburgh
  2019-22, 146 db) — neither is in the gsis crosswalk and both are sub-150-db, so Patti is out of the
  panel under either the one-person or two-person reading. Zero effect on the count.
- **Ingestion naming rule (both eras, season = directory year, no in-file year column):** 2014-2018 =
  `pff/college_<YYYY>/passing_summary.csv`; 2019-2025 = `pff/college_<YYYY>/college_passing_summary_<YYYY>.csv`.
  The join is by PFF `player_id` (int, one continuous id universe across the 2018/2019 seam — 249 QBs
  span it under a single id; zero id-collisions), NOT by team_name; team labels are PFF abbreviations.

## ALPHA-HAT ARTIFACT (QB values UNREAD until the fire)
`C:/tmp/S2.pkl` (SPEC.md Class-B pin, md5 `9b3d9df67ae88272f4eab0a0ae1cbb21`; F-step re-verifies md5
before firing). Key: `gsis_id`. The QB alpha-hat is built by `s2.py` from **FOUR** facets —
`cpoe, bad, qsucc, q10`, weights **W["QB"] = {cpoe .35, bad .25, qsucc .25, q10 .15}** — and is stored
as `S["F"]["QB"][facet]` frames with columns `[w, zmed, zmean, a]`, indexed by gsis.
- ~~**Discrepancy flagged for Joseph (NOT resolved here):** this S2.pkl QB alpha-hat is the **4-facet**
  build; the later-ratified **R29** QB vector is 5-facet (`cpoe .33 / bad .22 / deepCPOE .22 /
  qsucc .16 / q10 .07`). **deepCPOE is absent from `s2.py`/this artifact** (it lived only in `qb2.py`).
  This prereg measures the college index against the **4-facet S2.pkl QB alpha-hat** (the artifact the
  RB/WR/TE fire also used). If Joseph wants the R29 5-facet QB target, that is a different artifact and
  a different prereg. Only the alpha-hat membership index was read here; no value.~~
  **[RESOLVED 2026-07-19 — Joseph's ruling (A), folded before any harness exists:]**
- **TARGET RULED (A): the frozen S2 4-facet QB alpha-hat** (`cpoe/bad/qsucc/q10`,
  W["QB"] = {.35/.25/.25/.15}) — the SAME artifact and pin the RB/WR/TE fires measured against;
  cross-position comparability is the point. **Registered footnote (carried onto every claim and
  into the board disclosure):** this target construct differs slightly from the shipped R29
  5-facet QB talent score (deepCPOE, weight .22 in R29, is absent from this artifact) — the board
  copy will state that the college index was validated against the 4-facet construct, not the
  shipped 5-facet score. No re-target after results; a 5-facet re-measure would be a NEW prereg on
  a NEW artifact, openly a second look. Only the alpha-hat membership index was read pre-fire; no
  value.

## ESTIMATOR (registered — QB MoM-k / √w recipe, verbatim from `s2.py`)
Per facet f ∈ {cpoe, bad, qsucc, q10} (from `s2.py`, weighted-attempt aggregates with recency weight
`exp(−LAM·(2025−season))`):
- reliability `w_f = n_f / (n_f + QK[f])`, **QK = {cpoe: 285, bad: 399, qsucc: 12, q10: 24}** (the MoM
  k constants, hardcoded `s2.py:78`);
- `zstd_f = (v_f − mean(v_f)) / std(v_f)`; stored `zmed_f = zmean_f = √(w_f)·zstd_f` (the **√w
  shrinkage** — QB is shrunk at √w, unlike RB/WR/TE which shrink at w; `s2.py:81`).
QB alpha-hat and reliability (`s2.py:94,97`, ΣW["QB"] = 1.0):
`aw = Σ_f W["QB"][f]·zmed_f` ; `wt = Σ_f W["QB"][f]·w_f`.
MEASUREMENT: per the panel, rho = corr(QB college index, `aw`) over members with `wt > 0` and both
non-null, **R8-disattenuated** `rc = raw_Pearson / √(mean(wt))`. Raw Pearson and Spearman reported
alongside, **NON-GATING**. (Note: the QB assembly reads the STORED `w`/`zmed` columns directly — there
is no `knew = kold·(sam/sad)²` step and no `ne` column, unlike the RB/WR/TE `alpha_w`; the QB fire
needs its own assembler.)

## POWER (blind; at the fireable n = 103; CORRECTS the audit's n=178 sketch)
Disattenuated SE ≈ (1/√(n−3))·(disatt factor); disatt ∈ {2.0, 2.5}× (unknown mean-wt, as for
RB/WR/TE); MDE(80%) = 2.80·SE (two-sided α = .05).
- **n = 103 (fireable):** SE ≈ 0.201–0.251 → **MDE(80%) ≈ 0.56–0.70**.
- (For reference, the audit's n=178 upper bound gave ≈ 0.43–0.53 — but 178 is not the measurable
  panel; **103 is**, so QB remains UNDERPOWERED against a moderate effect: MDE sits ABOVE the .50
  band.) A placebo/disattenuation-controlled result stays meaningful regardless of power; low power
  inflates false negatives only. Exact SE/MDE pinned at the F-step under the frozen panel.

## BANDS
`≥ .50 ships clean / .35–.50 ships weak-disclosed / < .35 dead` (this instrument family).

## SHIP RULE (Joseph's ruling — the QB rookie score ships REGARDLESS of band)
The QB college index **SHIPS to the public board regardless of its measured band**, framed as a
**DESCRIPTIVE college passing composite** — the on-board disclosure states the measured
disattenuated rho, its wide confidence interval, and a prominent **small-sample caveat**
(n = 103, underpowered). It is **NOT presented as a validated talent ranking**. The band is still
recorded honestly and **governs the disclosure wording** (clean → "validated in aggregate";
weak-disclosed → "sized, weak signal disclosed"; dead → "descriptive only, not shown to track NFL
talent at this sample"), **not whether it ships**. Draft capital never enters this score (it may
enter a separate projection engine — different question).

## ONE SHOT
One run. No metric substitutions, no panel re-cuts, no subgroup rescues, no second estimator promoted
after results. A crash is not a result; a completed run's numbers are final. The fire script and its
sha256 are recorded here at the F-step (harness built in a separate session, no metric printed — it
must implement the QB MoM-k/√w assembler above), run exactly once.

**F-step build recorded 2026-07-19 — CODE IS FROZEN.** Fire script:
`scratchpad/fire_pff_qb_rho.py` sha256
`d21e82e710479787dff9bbd8332997372d8a1aa725c45c2c7548accee21ae6ee`, run exactly once. The build
read NO QB alpha-hat VALUE (S2 opened for membership indexes + structure only; value-read counter
= 0) and printed no outcome statistic. Structural asserts all PASSED: S2 md5 `9b3d9df6…` verified;
both filename patterns load (anchors Mariota '14, Goff '14–15); S2 `F['QB']` structure =
{cpoe, bad, qsucc, q10} × [w, zmed] as registered; panel stages 650 → 178 gsis-resolved → **103
alpha-members EXACT** with the per-final-year table matching the frozen PANEL row
(6/8/13/13/13/11/10/7/13/9); Patti pids (46582, 77614) excluded; QB index finite for all 103;
**end-to-end synthetic fire** drove the REAL fire path against a FAKE S2-shaped QB artifact and
reproduced the hand answers (+2.000 CLEAN / −2.000 DEAD / mixed-weight disatt = 1/√0.15); NO stub
tokens in any fire code path. Power pinned at the F-step: n = 103, raw-SE 0.100, disatt-SE ≈
0.200–0.250, **MDE(80 %) ≈ 0.56–0.70** — above the .50 band; the ship-regardless rule governs.
**Membership clarification (metadata, counts unchanged):** Ryan Willis is gsis-RESOLVED (in the
178) but holds NO alpha-hat entry — he is one of the 75 resolved-without-alpha QBs, NOT one of the
103; the frozen counts already reflect this. The shot is the next session; the fire path (real
w/zmed read + assembler + band + ship-regardless wording) is fully implemented and was not entered.

## BLINDNESS DISCLOSURE
Everything seen, none of which related a QB college value to an NFL value: the session-1/9 PFF audits
(schemas, counts, coverage); the 2026-07-19 QB recon that froze this panel (college dropback counts,
gsis resolution, and the S2 `F['QB']` **index** = alpha-hat membership — the frames' `w/zmed/zmean/a`
VALUES were never read); the `s2.py` SOURCE for the estimator formula + QK constants + W["QB"] (code,
not values). No QB alpha-hat VALUE was read. Components are RULED (grade + age), weights EQUAL
(unfitted), bands INHERITED from the fired instrument family. PARTIALLY blind, declared; Joseph rules
before the F-step. The blind is spent only by the fire.

## Amendment 1 (2026-07-20) — full 2008+ PFF upload audited; panel n=103 UNCHANGED; fire RATIFIED
**Amended BLIND: no QB metric of any kind exists at commit time** — this amendment records a
read-only coverage audit and a ratification, computes nothing. Hardness: it adds a disclosure and
PINS that the panel is unchanged; it loosens no gate and alters no frozen section above.
- The 2026-07-20 "data back to 2008" upload was audited (identity/coverage only): college full 11
  tables 2014–2025 + `time_in_pocket`-only 2008/2010–2013 (2009 empty); NFL full 11 tables 2006–2025.
  The bare-named 2014–2018 college files were renamed to the `college_<table>_<YYYY>.csv` convention
  (pff repo commit `b70f291`); the harness `passing_path` dual-pattern loader resolves the renamed
  files transparently, and the fire's own `assert len(panel) == 103` is the backstop.
- **Panel n = 103 UNCHANGED.** The target is the frozen 4-facet S2 QB alpha-hat, built from nflverse
  feeds (PF = 2018–2025), which the new PFF files do not feed; pre-2014 college is `time_in_pocket`-only
  (no `grades_pass`), adding no scorable QB; the QB college index still reads college `passing_summary`
  2014–2023 only. Nothing in the upload perturbs the panel or the alpha-hat.
- **Fire RATIFIED by Joseph 2026-07-20.** The earlier "hold for supersession on the expanded panel"
  is dissolved — this prereg already incorporated the 2014–2018 college passing data at n=103. One
  shot, this session, on the frozen harness (sha `d21e82e7…21ae6ee`), under the ONE SHOT and
  SHIP-REGARDLESS rules above (unmodified).

## OUTCOMES (recorded after the fact; rules above were not modified)
**FIRED 2026-07-20 — ONE SHOT, run exactly once.** Script `scratchpad/fire_pff_qb_rho.py`
sha256 `d21e82e710479787dff9bbd8332997372d8a1aa725c45c2c7548accee21ae6ee` (== frozen sha; S2 md5
`9b3d9df6…` re-verified at fire). Interpreter: AI_hedge_fund venv. Panel reproduced n=103 EXACT.

**RESULT (n = 103):** rawPearson **+0.459** | Spearman **+0.464** | w-wt Pearson **+0.426** |
mean-wt **0.449** | **DISATT rc = +0.685** → **BAND: CLEAN (≥ .50).**
- The reliability-disattenuated rho (rc = rawPearson / √mean-wt = 0.459 / √0.449) = **+0.685**, above
  the .50 clean band. Raw and Spearman (+0.46) are the pre-registered non-gating companions.
- **VERDICT: the PFF college passing index (z(grades_pass) + z(−age), equal-weight) TRACKS the
  4-facet S2 QB talent construct — CLEAN.** Rejection/acceptance is final: no metric substitution,
  no panel re-cut, no second estimator.
- **POWER CAVEAT (carried onto every claim):** MDE(80%) ≈ .56–.70 at n=103 — the point estimate sits
  near the MDE and the CI is wide (small sample); a placebo/disattenuation-controlled PASS stays
  meaningful regardless of power (low power inflates false negatives only, not false positives).
- **TARGET FOOTNOTE (registered):** validated against the **4-facet** S2 QB alpha-hat
  (cpoe/bad/qsucc/q10, W = .35/.25/.25/.15), NOT the shipped **R29 5-facet** QB score (deepCPOE,
  weight .22, is absent from this artifact). A 5-facet re-measure would be a NEW prereg on a NEW
  artifact.
- Fire wrote exactly one artifact: `fire_pff_qb_results.pkl` (cd8c93d8 scratchpad). No repo write;
  `talent_score_2026.csv` untouched.

**BOARD DISCLOSURE COPY (ship-regardless rule; band = CLEAN selects the wording):**
> QB college passing score — a **descriptive** composite of PFF college passing grade and age
> (younger = higher), equal-weighted. In aggregate it tracks our NFL QB-talent measure
> (reliability-corrected rank correlation ≈ 0.69; raw ≈ 0.46) over 103 QBs with 2014–2023 final
> college seasons. **Small sample — treat individual rankings with caution.** Validated against a
> 4-facet talent construct, which differs slightly from the shipped 5-facet QB talent score. It is
> **not** a projection and does not use draft capital.
