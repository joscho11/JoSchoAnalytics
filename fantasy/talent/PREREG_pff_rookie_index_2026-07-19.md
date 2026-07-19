# PRE-REGISTRATION — PFF college talent index vs the NFL talent construct
**Date:** 2026-07-19 · **Status at commit: BLIND** (no college value has been related to any
NFL value; alpha-hat values are UNREAD until the fire). One-shot. Joseph reviews this prereg;
firing is a later session.

This is a **fresh pre-registration**, not a re-run. It registers a NEW instrument built from the
newly licensed PFF college CSV library (2019–2025), measured against the same NFL talent construct
(alpha-hat) and on the SAME frozen rookie panel used by `PREREG_pbp_index_2026-07-17.md`, so the
two instruments are directly comparable. It also re-measures the PBP index on a **position-pure**
cut of that panel — which puts the shipping RB PBP pipe (disatt .474, `PREREG_pbp_index` OUTCOMES)
at risk. That is the point: measure honestly.

## HYPOTHESIS
A PFF college talent index — grade + yardage/target market share + age, EQUAL-weighted within
position — tracks the NFL talent construct (alpha-hat) at a band-relevant level for RB, WR, TE,
and (its FIRST instrument) QB.

## INSTRUMENT (frozen)
Per position, one index over each player's **final + best college season** (2019–2023 finals; no
λ decay — college ages are close), z-scored within the scoped qualifying population, EQUAL-weighted
across facets:
- **RB** = z(`grades_run`) + z(rushing-yards team share) + AGE. Table `college_rushing_summary`.
- **WR / TE** = z(`grades_pass_route`) + z(receiving-yards team share) + AGE. Table
  `college_receiving_summary`.
- **QB** = z(`grades_pass`) + AGE only. Table `college_passing_summary`. Team share is meaningless
  at one QB per team (declared); QB carries grade + age alone.
- **AGE** = a frozen declared linear term `z(−age_at_final_college_season)` (younger = higher),
  age from `players.parquet` birth_date via gsis. NO TD-share components; NO draft capital; NO
  combine / pro-day / athletic-testing features (standing talent-side exclusion — those measure
  traits or the market's opinion, not college football performance).
- **Team share** = player yards ÷ Σ same-file, same-`franchise_id` yards in that season (frozen
  approximation; declared). **EQUAL weights within position** — not fitted against alpha-hat
  (circular) and not fitted against anchors (anti-tuning). Owner may later ratify a different
  vector via a delegated one-shot (the R31 pattern), never by eyeballing this run.

## PANEL (frozen — position-pure, identity-only recon 2026-07-19)
From `panel_fire.pkl` md5 `0c6f1e15a7bd534fa25c0bd10ab21c3e`, true-final college season 2016–2023,
then restricted to **2019–2023 finals ∧ position-pure ∧ PFF-covered**. Frozen n (identity/coverage
recon, NO value read):

**BLIND COUNT CORRECTION (2026-07-19, F-step roster reconstruction) — STRIKE-DON'T-REPLACE, per the
H6-Amendment-2 precedent.** Membership metadata only; no alpha/outcome value was read; it loosens no
gate and the blind is intact. The three per-cell counts first frozen below were the raw
`norm_name`+final join totals; the three registered adjudications in THIS prereg (Gore-by-gsis,
Roberts exclusion, the alias table) were not folded into them. Corrected frozen n, each cell moving
exactly one player TOWARD this prereg's own rulings: **~~RB 121~~ → 120 · ~~WR 176~~ → 178 ·
~~TE 81~~ → 80** (QB unchanged, F-step-pinned). Per-cell reasons in the struck bullets + the ALIAS
TABLE fix below.

- ~~**RB = 121.**~~ → **RB = 120.** Raw RB cell 300 − 56 confirmed non-RB (44 NFL-QB, 10 gadget-WR,
  1 CB Marcus Jones, 1 TE Connor Heyward, matched to their PFF final-season `position`) −
  ~~123~~ → **124** uncoverable = ~~121~~ → **120**. **Correction (gsis-key ruling): Frank Gore Sr
  `00-0023500` moves kept→uncoverable** — the raw name-join wrongly attached Frank Gore Jr's Southern
  Miss HB row to Sr under the collapsed nn `frank gore`; gsis-keyed, Sr's final-season match is 0 rows.
  This is now ~~6~~ → **7** below the ~127 estimate: 6 genuine RBs in the documented BYU/Liberty/NMSU
  2019–22 data hole (e.g. Allgeier, BYU '21) + the 1 Gore-Sr collision; the contaminant split is
  exactly as predicted (44+10+1+1=56). The number wins: ~~121~~ → **120**.
- ~~**WR = 176.**~~ → **WR = 178.** Raw 308 − 2 flips (De'Michael Harris→HB, Lynn Bowden→QB) −
  ~~130~~ → **128** uncoverable = ~~176~~ → **178**. **Correction (alias ruling): the alias recovers
  BOTH Josh Palmer and Mike Woods** (final 2020, WR) — the raw 176 applied no alias; both have a PFF
  final-season WR row under a name `norm_name` can't bridge unaided (PFF "Joshua Palmer", Tennessee;
  "Michael Woods II", Arkansas). See the ALIAS TABLE key fix below (the `michael woods` key was dead
  as first written).
- ~~**TE = 81 scorable**~~ → **TE = 80 scorable** (roster 133 kept whole — estimand is NFL-TE, so the
  college-WR converts stay; 133 − ~~52~~ → **53** uncoverable = ~~81~~ → **80**). **Correction
  (collision ruling): Michael Roberts `00-0033559` EXCLUDED** — his only PFF match is a
  school-disconfirmed Army WR 2021 (a name collision, not a genuine convert), moving scorable
  81→80; the 7 genuine WR-converts still remain.
- **QB = the FIRST QB talent instrument, panel assembled value-free at F-step** (membership only,
  the `PREREG_pbp_index` precedent: index membership + `ne` read, no alpha value): NFL QBs holding
  an alpha-hat entry ∩ true-final college 2019–2023 ∩ ≥ 150 career college dropbacks. Expected
  n ≈ 40–70; the exact value is pinned at F-step. College QB supply clears the floor easily
  (~108–150 QBs/year ≥ 150 dropbacks, 2019–2025).

**Adjudications, frozen (identity recon):** RB college rows for `frank gore` key to **Jr.
`00-0039471`** (Southern Miss 2020–23); **Frank Gore Sr. `00-0023500` is UNCOVERABLE** (his college
predates PFF) and must NOT inherit the son's rows. Alias table (2 entries, applied before matching;
keys are the POST-`norm_name` form): ~~`{joshua palmer ↔ josh palmer, michael woods ii ↔ mike woods}`~~
→ **`{joshua palmer ↔ josh palmer, michael woods ↔ mike woods}`**. **Key fix (2026-07-19):** the
struck `michael woods ii` was a DEAD key — `norm_name` strips the trailing " ii" suffix before the
alias lookup, so it never fired; the operative key is `michael woods` (PFF source lists "Michael
Woods II", Arkansas WR 2020). `joshua palmer → josh palmer` is unchanged and fires as written (PFF
"Joshua Palmer", Tennessee WR 2020). Both recoveries land in the corrected WR count (176 → 178).

## ALPHA-HAT ARTIFACT (values UNREAD until the fire)
`C:/tmp/S2.pkl` md5 `9b3d9df67ae88272f4eab0a0ae1cbb21` (== SPEC.md Class-B pin). Key: `gsis_id`.
alpha-hat = unshrunk composite `aw = Σ_f W[P][f]·zmed_f`; reliability `wt = Σ_f W[P][f]·wn_f / Σ W`,
`wn = ne/(ne+knew)`, `knew = kold·(sam/sad)²` — reproduced verbatim from the `PREREG_pbp_index`
frozen definition. Membership (index + `ne`) is read to build the QB panel; **no alpha value is
read at T-step.** The blind is spent by the fire only.

## SCOPE RULES (registered)
- FBS-school players only, mirroring `PREREG_pbp_index`'s frozen scope; FCS-school EXCLUDED.
- 2020 included as-is (career pooling absorbs the short season). 2024/2025 finals excluded from the
  panel (thin/no NFL season) — panel is 2019–2023 finals.
- Position purity is by PFF `position` in the player's FINAL college season (recon above). The
  RB/WR cuts are frozen rosters; the TE cell keeps its converts; QB is a new value-free panel.

## Z-RULE (registered)
Pooled career z over the scoped qualifying population (FBS, true-final ≤ 2023, ≥ MINV), one z per
career per facet; EQUAL-weight composite over the position's facet set (RB grade+share+age,
WR/TE grade+share+age, QB grade+age). Volume floors inherited from `PREREG_pbp_index`
(RB ≥ 40 carries, WR/TE ≥ 30 targets); QB ≥ 150 dropbacks.

## MEASUREMENT (registered)
Per position, rho = corr(index, alpha-hat) over panel members with `wt > 0` and both non-null,
**disattenuated by the R8 estimator** `rc = raw_Pearson / sqrt(mean(wt))`. Raw Pearson and Spearman
reported alongside, **NON-GATING**.

## BOTH INSTRUMENTS, ONE RUN
On this SAME position-pure panel, same join, same estimator, measure BOTH in one fire:
(i) the **PFF college talent index** (above); (ii) the **PBP index** exactly as
`PREREG_pbp_index_2026-07-17.md` computes it. Both on the filtered RB 121 / WR 176 / TE 81 / QB rows.

## SUPERSESSION (registered in advance)
These position-pure numbers **REPLACE** the `PREREG_pbp_index` old-panel bands for band placement on
this instrument family. In particular the RB **PBP disatt .474** (measured on the 300-row cell that
included 44 NFL-QBs and 10 gadget-WRs) retires to its **same-panel, position-pure re-measure**. The
`PREREG_pbp_index` OUTCOMES table is append-only and is NOT edited; this supersession is recorded
here and applies from this fire forward. The shipping RB pipe stands or falls on the clean number.

## SHIP RULES (decided now, applied mechanically)
Bands (`rho_provenance.json`, this instrument family): **≥ .50 ships clean / .35–.50 ships
weak-disclosed / < .35 dead.** Applied to each position's chosen instrument:
- **RB** (pipe currently PBP .474 on the old panel): on the position-pure panel, keep whichever of
  {PFF index, PBP index} scores higher, at its band; **PFF REPLACES PBP only if
  PFF_disatt ≥ .35 AND PFF_disatt − PBP_disatt(same panel) ≥ +0.05.** If both < .35, RB is dead.
- **WR, TE** (box + prior instruments DEAD): the better of {PFF, PBP} ships at its band if ≥ .35;
  else the position stays dead.
- **QB** (first-ever instrument): ships at its band from {PFF, PBP}; a QB < .35 means no QB talent
  instrument ships this cycle.

## POWER (blind; frozen n, PBP-fire disattenuation factors as priors; re-pinned at F-step)
Disattenuated SE ≈ (1/√(n−3)) · (1/√(mean wt)); disatt factors taken from the PBP fire
(RB ≈ 2.2×, WR ≈ 2.4×, TE ≈ 1.9×). **Frozen n corrected 2026-07-19 to RB 120 / WR 178 / TE 80 (see
the PANEL blind count correction); the one-player-per-cell change moves SE/MDE below rounding — the
figures below stand, exact values re-pinned mechanically at the F-step:**
- **RB n=~~121~~ → 120:** SE_disatt ≈ .20 → MDE(80 %, one-sided vs 0) ≈ **.51**.
- **WR n=~~176~~ → 178:** SE_disatt ≈ .18 → MDE ≈ **.45**.
- **TE n=~~81~~ → 80:** SE_disatt ≈ .21 → MDE ≈ **.53**.
- **QB n≈40–70 (new instrument, no prior disatt factor):** raw-Pearson SE ≈ .13–.16; with a
  plausible 2–2.5× disattenuation, SE_disatt ≈ .28–.41 → MDE ≈ **.7–1.0**. QB band assignment is
  INDICATIVE at this power; Joseph may rule **QB SIZED-NOT-SHIPPED** after the fire. Exact QB SE/MDE
  at its F-step-pinned n is carried into the OUTCOMES record.
Band assignment is point-estimate-mechanical with wide CIs (as the PBP fire was) — stated so the
ruling is eyes-open. A placebo/disattenuation-controlled result stays meaningful regardless of
power; low power inflates false negatives only.

## ANCHORS (one-time face-validity, POST-freeze, a later session — NEVER tuning targets)
Computed once after the recipe freezes, college-profile-justified, never used to choose weights or
bands. Scorability confirmed by identity/coverage recon 2026-07-19:
- **HIGH:** Bijan Robinson, Caleb Williams, Jayden Daniels, Drake Maye, Malik Nabers, Jahmyr Gibbs,
  Justin Jefferson, Ja'Marr Chase, Brock Bowers, Trey McBride, and **Breece Hall (RB, Iowa St, final
  2021 — COVERED)** standing in for **Saquon Barkley, who is UNTESTABLE** (final 2017, pre-PFF).
- **LOW:** Charbonnet, Dameon Pierce, plus five college-profile-justified additions, all COVERED:
  **Anthony Richardson** (Florida '22 — one-year starter, ~54 % completion, modest passing grade for
  a top pick), **Will Levis** (Kentucky '22 — declining grade, turnover-worthy-play-heavy), **Velus
  Jones Jr.** (Tennessee '21 — production at an old-for-class age; the age term's canonical test),
  **Trey Sermon** (Ohio St '20 — one-season share spike, modest grade, older), **Tyrion
  Davis-Price** (LSU '21 — low share, modest grade on a loaded offense).
- **Zach Wilson (QB, BYU, final 2020) is recorded UNTESTABLE** — BYU is entirely absent from PFF
  college files 2019–2022 (the documented data hole), not a name miss.

## ONE SHOT
One run. No metric substitutions, no panel re-cuts, no subgroup rescues, no second estimator
promoted after results. A crash is not a result; a completed run's numbers are final. The fire
script and its sha256 are recorded here at the F-step (harness built in a separate session, no
metric printed), run exactly once.

**F-step build recorded 2026-07-19 — CODE IS FROZEN.** Fire script:
`scratchpad/fire_pff_rho.py` sha256
~~`a34768d849058e92ecad7a8f536001cccb3b573c483db6bfc0611f348ce49d59`~~ →
**`773a46b8fb5d01d5aff1a392b8febde6a13ee12d3ca593ebf5f3af817a6a8e54`**, run exactly once.
**Re-frozen 2026-07-19:** the first freeze (`a34768d8…`) had a STUBBED `--fire` path
(`run_fire`/`load_alpha` raised) — it could not actually fire. The fire ORCHESTRATION is now
fully implemented (S2 `alpha_w` verbatim; PBP index = the panel's frozen `pbp_index` re-measured
on the pure rows; both instruments' raw/Spearman/disattenuated Pearson; bands; RB supersession)
and proven END-TO-END: a synthetic-fire dry run drives the real `fire_core` against a FAKE
S2-shaped alpha artifact (real `S2.pkl` never opened) and reproduces the hand-computed answer
(rc_PFF = +2.000 CLEAN, rc_PBP = −2.000 DEAD, RB → PFF REPLACES). The build printed NO outcome
statistic and read NO real alpha-hat (`S2.pkl` present, read counter = 0; panel
`pbp_index`/`box_index` dropped on load). Structural asserts all PASSED: panel md5
`0c6f1e15…`; position-pure roster counts **RB 120 / WR 178 / TE 80** exact; Gore keyed by gsis
(Sr `00-0023500` uncoverable, Jr `00-0039471` kept HB); Roberts `00-0033559` excluded; alias
recovers both Josh Palmer and Mike Woods; the 331-scar guard finds ZERO multi-matches post-alias;
378/378 roster gsis resolve in `players.parquet`; PFF index finite for every member;
estimator/band/supersession truth table; NO stub tokens in source. **QB panel (value-free):**
college QB careers with true-final ≤ 2023 and ≥ 150 dropbacks = 278, of which **84 resolve to an
NFL gsis** (upper bound on the QB panel n; fired panel = 84 ∩ alpha-hat membership). QB power:
n = 40 → MDE(80 %) ≈ 0.82–1.02; n = 55 → ≈ 0.69–0.86; n = 70 → ≈ 0.61–0.76 — thin, and the
verbatim RB/WR/TE `alpha_w` k-recipe does not cover QB's (distinct, MoM-k) estimator, so
**QB ships SIZED-NOT-SHIPPED** this cycle (sized + power only, no fabricated band). The shot is
the next session; the now-functional fire path (real alpha-hat read + PBP re-measure) is wired
but was not entered.

## BLINDNESS DISCLOSURE
Everything seen across sessions, none of which related a college value to an NFL value: the
session-1 PFF audit (schemas, counts, join/coverage rates, PFF-field-only distributions); the
2026-07-19 identity/coverage recon that froze these rosters (names, positions, gsis, final season,
row-present flags — the panel's `pbp_index`/`box_index` columns were dropped on load and never
read; `S2.pkl` never opened); the 2026-07-19 Tyson content brief (college-PFF-only WR percentile
distributions, no alpha/outcome join); anchor stat lines during acquisition. No alpha-hat VALUE was
read in any of it. Components were RULED (grade + share + age), weights are EQUAL (unfitted), bands
are INHERITED from the fired instrument family. PARTIALLY blind, declared; Joseph rules before the
F-step.

## OUTCOMES (recorded after the fact; rules above were not modified)

**PFF college talent index vs alpha-hat — RB/WR/TE FIRED (2026-07-19).** Fired once,
`fire_pff_rho.py --fire` sha256
`773a46b8fb5d01d5aff1a392b8febde6a13ee12d3ca593ebf5f3af817a6a8e54` (verified == the committed
ONE SHOT stamp before firing) → `scratchpad/fire_pff_results.pkl`. The shot read `S2.pkl`
alpha-hat + wt (`alpha_w` verbatim, `knew=kold·(sam/sad)²`) and the panel's frozen `pbp_index`
re-measured on the position-pure rows; both instruments' raw/Spearman/disattenuated Pearson
(R8, `rc = rawP/√mean-wt`) on the pure rows. QB: sized-only, NOT fired (shot preserved).

| pos | instr | n | rawPearson | Spearman | w-wt | DISATT | band |
|---|---|---|---|---|---|---|---|
| RB | PFF | 120 | −0.059 | +0.233 | +0.308 | **−0.117** | DEAD (<.35) |
| RB | PBP | 120 | +0.254 | +0.219 | +0.164 | **+0.501** | CLEAN (>=.50) |
| WR | PFF | 178 | −0.026 | +0.056 | +0.095 | **−0.062** | DEAD (<.35) |
| WR | PBP | 178 | −0.010 | +0.113 | +0.333 | **−0.024** | DEAD (<.35) |
| TE | PFF | 80 | +0.153 | +0.150 | +0.140 | **+0.294** | DEAD (<.35) |
| TE | PBP | 80 | +0.164 | +0.162 | +0.165 | **+0.316** | DEAD (<.35) |

SHIP VERDICTS (ship rules applied mechanically):
- **RB: the PFF index is DEAD (−0.117); the PBP index carries RB, and SHIPS CLEAN at +0.501.**
  PFF does NOT replace PBP (PFF −0.117 < .35, so the +.05 swap rule cannot trigger) → keep the
  higher instrument (PBP) at its band. The new grade+share+age PFF index adds nothing for RB over
  the PBP index on the clean panel.
- **WR: DEAD on both** (PFF −0.062, PBP −0.024). WR stays dead on all instruments.
- **TE: DEAD on both** (PFF +0.294, PBP +0.316) — a recorded near-miss below the .35 bar; the
  bar does not move. TE stays dead.

**SUPERSESSION (as pre-registered): the old-panel RB PBP .474 (WEAK, measured on the 300-row cell
that included 44 NFL-QBs + 10 gadget-WRs) is RETIRED for its same-panel, position-pure re-measure
= +0.501 (CLEAN).** Removing the contaminants LIFTED the RB PBP index from WEAK-DISCLOSED to CLEAN
— the shipping RB pipe stays PBP and its band upgrades .474→.501. The `PREREG_pbp_index` OUTCOMES
table is append-only and unedited; this supersession applies from this fire forward.

**QB — SIZED-NOT-SHIPPED (shot preserved for a dedicated QB cycle).** No QB rho was computed:
the verbatim RB/WR/TE `alpha_w` k-recipe does not cover QB's distinct (MoM-k / √w) estimator, and
QB power is thin. Value-free sizing at the frozen 2019-2025 college scope: **84** QBs resolve to an
NFL gsis (final ≤ 2023, ≥ 150 dropbacks); MDE(80%) ≈ 0.62–0.78 at n=84. The 2026-07-19 audit of the
newly-uploaded 2014-2018 college PASSING data projects the QB panel to **≈178** over finals
2014-2023 (+93 finals-2014-18 QBs incl. Mahomes/Watson/Mayfield/Lamar/Allen/Kyler; +1 finals-2019
via career-dropback pooling), which would tighten MDE(80%) to ≈ 0.43–0.53 (borderline vs the .50
band). QB therefore ships **SIZED-NOT-SHIPPED this cycle**, deferred to a dedicated QB prereg on the
expanded 2014-2023 panel that also sources the QB `alpha_w` spec. RB/WR/TE remain unaffected by that
data (passing-only upload). One shot spent for RB/WR/TE; QB shot unspent.

**Campaign result:** the fresh grade+share+age PFF college index is **DEAD at all of RB/WR/TE** vs
alpha-hat on the clean panel. RB continues to ship the **PBP index, now CLEAN (+0.501)** after the
position-pure supersession; WR/TE stay dead on every instrument; QB deferred. No re-slicing, no
metric substitution, no panel re-cut — rejection final per position.
