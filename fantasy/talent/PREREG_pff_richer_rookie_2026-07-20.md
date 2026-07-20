# PREREG — PFF RICHER COLLEGE ROOKIE INDEX vs FULL R29 NFL-TALENT TARGET (RB/WR/TE/QB)

**Registered 2026-07-20. Author: Claude (Opus 4.8) at Joseph's direction. All constructs RULED and
FROZEN by Joseph 2026-07-20 before any rho was computed on any data. ONE SHOT per position at fire.**

Supersedes nothing. Companion to the FIRED grade+share+age instrument (RB/WR/TE dead all three,
2026-07-19) and the FIRED QB grade+age instrument (CLEAN +0.685, PREREG_pff_qb_index_2026-07-19).

---

## HYPOTHESIS

A **richer, pre-specified** PFF college index — efficiency/ball-skill facets, not just the base
grade — ranks NFL talent (the full R29 alpha-hat) better than the dead grade+share+age index did.
MECHANISM: the dead index used one grade + raw yard share (opportunity) + age; the richer index
adds per-opportunity efficiency and ball-skill facets (yards-after-contact, elusiveness, YPRR,
contested-catch, YAC, hands grade, accuracy, big-time/turnover-worthy rates, pressure grade) that
measure what the PLAYER does independent of scheme/volume. NO age term; NO draft capital (these
are SCORES). This is a NEW instrument, motivated by — not selected on — the prior null.

## THE FOUR FROZEN INDICES (weights on root facets, each sums to 1.00; NEVER fitted)

Index_p = z-composite of the player's **volume-weighted career-pooled** facet values (z-scored across
the panel participants, ddof=1), combined per the WEIGHT-BLOCK missing-data rule below. Higher=better
for every facet; ONLY QB twp_rate is negated (z(−twp_rate)). All facets from PFF **college** tables.

**Career pooling:** per facet, value = Σ(season_value · vol)/Σ(vol) over the player's college
seasons (vol = block opportunity: RB rush block = attempts, all receiving facets = routes, QB block
= dropbacks); the two avoided-tackle RATE facets use season_value = avoided_tackles÷(attempts | receptions).

**Missing-data handling — WEIGHT-BLOCKS (revised 2026-07-20, pre-fire, blind intact; supersedes the
prior "missing facet → population mean, z=0").** Blocks: **RB** = rush {grades_run/yco_attempt/
rush_avt/breakaway, weight .65} + receive {grades_pass_route/yac_per_rec/yprr/rec_avt, weight .35};
**WR/TE/QB** = one block (all facets, 1.0).
- **(1) NON-PARTICIPATION PENALTY** — a player with NO data for an ENTIRE block gets, for each facet
  in that block, the **10th-percentile** value of that facet's panel distribution (a real bottom-tier
  penalty — NOT a neutral mean-fill), the block weight is KEPT (so it drags the score down), and a
  per-player flag is emitted for display. Only reachable for RB's receive block (a rusher with no
  receiving row; z=0 would have wrongly treated him as league-average pass-catcher). The percentile is
  Joseph's dial — default 10th.
- **(2) OMIT-AND-REDISTRIBUTE** — within a block the player DOES participate in, any individually
  missing facet is DROPPED and the player's present-facet weights rescaled **proportionally** (not
  evenly — preserves the intended anchor emphasis) to sum to the block weight (WR/TE → 1.0). This is
  the ~contested_catch_rate gap for WR/TE; a high performer previously compressed toward 0 by mean-fill
  now scores on his present facets.
z-scores are computed over the panel participants as before. QB has full coverage → neither branch
fires; QB index is UNCHANGED by this revision.

| Pos | facet (weight) → table.column [direction] |
|---|---|
| **RB** (rush .65 / receive .35) | grades_run .35 → rushing_summary.grades_run [+] · yco_attempt .10 → rushing_summary.yco_attempt [+] · rush_avoided_tkl_rate .10 → rushing_summary.avoided_tackles÷attempts [+] · explosive .10 → rushing_summary.**breakaway_percent** [+] (substituted: `explosive` is an integer COUNT; breakaway_percent is the rate — the one pre-specified data-nature conditional) · grades_pass_route .20 → receiving_summary.grades_pass_route [+] · yac_per_reception .05 → receiving_summary.yards_after_catch_per_reception [+] · yprr .05 → receiving_summary.yprr [+] · rec_avoided_tkl_rate .05 → receiving_summary.avoided_tackles÷receptions [+] |
| **WR** | grades_pass_route .40 · yprr .25 · contested_catch_rate .10 · rec_avoided_tkl_rate .10 (avoided_tackles÷receptions) · grades_hands_drop .075 (the GRADE, higher=better — NOT the drop rate) · yac_per_reception .075 — all receiving_summary, all [+] |
| **TE** | grades_pass_route .435 · yprr .25 · contested_catch_rate .065 · rec_avoided_tkl_rate .10 · grades_hands_drop .075 · yac_per_reception .075 — all receiving_summary, all [+] |
| **QB** | grades_pass .35 → passing_summary.grades_pass [+] · accuracy_percent .15 → passing_summary.accuracy_percent [+] (NOT completion_percent) · btt_rate .125 → passing_summary.btt_rate [+] · twp_rate .10 → passing_summary.twp_rate [**NEGATED**, z(−twp_rate)] · grades_run .15 → passing_summary.grades_run [+] (designed-run/scramble grade) · pressure_grades_pass .125 → passing_pressure.pressure_grades_pass [+] |

## PANELS — Option A (validate vs the FULL R29 target, players active 2018+)

College finals 2014–2023, floored (RB attempts≥40, WR/TE targets≥30), position-pure (PFF final
`position`), pff_id→gsis via snapshots/players.parquet, ∩ has a full R29 target (PFR-facet member in
S2). **ASSERTED COUNTS: RB 261 · WR 358 · TE 150.** QB panel = the frozen n=103 (finals 2014–2023,
career dropbacks≥150, gsis-resolved==178, ∩ the 4-facet S2 QB alpha member). **ASSERTED: QB 103.**

## TARGET (answer key — assembled/read ONLY at --fire)

- **RB/WR/TE:** the FULL R29 alpha-hat, assembled EXACTLY as `fire_pff_rho.assemble_alpha`
  (aw = Σ W_pos[f]·zmed_f over ALL S2 facets, S2 weights; wt = Σ W·wn_f/ΣW, wn = ne/(ne+knew),
  knew = kold·(sam/sad)²) from C:/tmp/S2.pkl (md5 9b3d9df6…).
- **QB:** the frozen 4-facet S2 QB alpha (cpoe/bad/qsucc/q10, W = .35/.25/.25/.15), assembled exactly
  as `fire_pff_qb_rho` (aw = Σ W·zmed, wt = Σ W·w). This is the SAME target the +0.685 was measured on.

## STATISTIC + BANDS

Per position, on the panel (mask wt>0 ∧ index & aw non-null): rawPearson, Spearman, w-wt Pearson
(reported); **banded on the disattenuated rc = rawPearson / √mean(wt)**. Bands: **≥.50 CLEAN /
.35–.50 WEAK-DISCLOSED / <.35 DEAD.** ONE SHOT per position; rejection final — no metric substitution,
no panel re-cut, no re-weight.

## SHIP-REGARDLESS CLAUSE

Each position's richer score ships as a DESCRIPTIVE college composite regardless of band; the band
selects the disclosure wording (CLEAN = validated-in-aggregate / WEAK = sized-weak-signal / DEAD =
descriptive-only). talent_score_2026.csv is untouched by this test.

## BLINDNESS DECLARATION

- **RB/WR/TE are GENUINE BLINDS.** These richer indices' rho was NEVER computed on ANY data (this
  build proved the harness on a SYNTHETIC target only). The 2019–2023 subset was SEEN previously for
  the OLD dead grade+share+age index ONLY; these are new pre-specified instruments, motivated by (not
  selected on) that null. Bands ARE claimable.
- **QB is a RE-MEASURE, NOT a fresh validation.** The QB blind is SPENT: grade+age fired CLEAN
  **+0.685** vs this same 4-facet target (2026-07-20), and **that +0.685 remains THE pre-registered
  validation of record.** This richer QB index is grades_pass-driven → its rho is foreknown-positive;
  it ships as the richer DESCRIPTIVE QB score and makes **NO second independent validation claim and
  NO fresh band claim.** (The QB shot in this harness is reported for completeness/descriptive use only.)
- Weights are PRE-SPECIFIED and FROZEN (the R31 +.106→−.009 fitted-WR scar forbids fitting). The only
  data-based conditional is the RB explosive→breakaway substitution (column-nature, blind-safe).

## PRIORS (honest, pre-committed)

- **RB** already ships CLEAN on the PBP instrument (+.501) → the richer PFF index is a superset /
  does-PFF-add test, not a rescue.
- **TE** is the live flip candidate (old grade+share+age near-missed at .294/.316).
- **WR** PFF index is dead ×6 → low prior.
- **QB** foreknown-positive re-measure (grades_pass drives it); no fresh claim.

## POWER

Small panels (RB 261 / WR 358 / TE 150 / QB 103); a disattenuation/placebo-controlled PASS stays
meaningful regardless of power (low power inflates false negatives only). Wide-CI/small-sample caveat
rides on every shipped claim.

## ONE SHOT

Fire the frozen harness ONCE per position, in a separate session, only on Joseph's explicit "FIRE".
Fire script + sha256 recorded below at build.

---

## HARNESS (frozen at build; --fire reads the real target, --build never does)

- **Script:** `scratchpad/fire_pff_richer_rho.py` (session cd8c93d8 scratchpad, alongside the fired
  RB/WR/TE + QB harnesses; not git-committed — the sha stamp below is the integrity anchor).
- **sha256 = `4402219cf7adc039f8475d08fc45267cdd95c624b6208d7d2fe321ebdd7f72a6`. CODE IS FROZEN.**
  (Session-5b re-freeze — missing-data revision, pre-fire, blind intact; **supersedes**
  `2115d8c9883974b7801b00be0ab17512eb3695c018d593b14fc78508e5790fe6`.)
- `--fire` runs this exact code once per position. **F-step proof (re-verified 2026-07-20 --build):**
  panels asserted 261/358/150/103; end-to-end synthetic fire drives the REAL `fire_core` against a FAKE
  target and recovers the hand answer **rc = +2.000 CLEAN / −2.000 DEAD for all four positions**;
  `assemble_alpha` + `assemble_qb` parse hand-built fake S structures; NO stub tokens; **S2 value-reads
  = 0 at build** (membership/presence only). The real S2 target (md5 9b3d9df6…) is read ONLY at `--fire`.
  **Missing-data revision verified:** QB byte-identical (Δ=0); RB non-catcher (Jacardia Wright) penalized
  DOWN (−0.914→−1.303) + flagged; 87 WR / 37 TE missing-contested dropped+rescaled (DeVante Parker
  +2.360→+2.622). Synthetic proof is target-agnostic → unchanged.
- Power at the fired n (pinned): RB MDE(80%)≈.35–.44 · WR .30–.37 · TE .46–.58 · QB .56–.70.

## OUTCOMES (recorded after the fact; rules above were not modified)

*Pending fire (RB/WR/TE = one shot each; QB = descriptive re-measure, no fresh band claim). Filled at
the shot with: per-position n | rawPearson | Spearman | w-wt | DISATT rc | band; disclosure wording;
power caveat.*
