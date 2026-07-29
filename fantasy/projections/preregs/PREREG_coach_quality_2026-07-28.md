# PRE-REGISTRATION — Coach-Quality Quantification for Season-Total Projections

**Date frozen:** 2026-07-28
**Revision:** **v3.2** — supersedes v1, v2, v3 and v3.1 in full.
**Statistical design:** **RATIFIED by Joseph 2026-07-28**, subject to the v3 amendments below.
**Execution status:** **RATIFIED AND T0 PASSED — 2026-07-28.**
**Frozen source table:** `coaching/data/actual_play_caller.csv`, md5 `391be44c4e4205ceea6456ea935794c0` (v3.2; supersedes `ac9883e98cdb1bd04a1c0978746cc023`)
**FITTING STATUS (corrected 2026-07-28, end of session):** No player-projection arm (0-5) has been
fit and no outer projection result has been examined. **Preliminary Arm 3 nuisance and coach-effect
models WERE fit** — `RidgeCV` expectation models (one per season) and `RidgeCV`+`Ridge`
cross-classified coach-effect models — and their alpha choices and effect magnitudes were observed
before audit. An earlier claim that "nothing has been fit" was inaccurate and is withdrawn.
Five confirmed defects gate the next step; see `coaching/AUDIT_TODO.md`. **The observed effect
magnitudes must not be interpreted** — Stage-2 tuning did not resolve (9 of 10 target-season
fits selected the grid-maximum alpha; 1,194/1,292 rows = 92.4% row-weighted) and defects 1-4
remain. The corrected values could increase, decrease, change sign, or converge to zero.
**Subproject:** `fantasy/projections/coaching/`

> **T0 FINAL 2026-07-28 — BOTH GATES PASS.**
> Outer 2018-2025: **95.3% row / 95.4% game** (244/256 team-seasons; 4,058/4,254 games) vs a 95% gate.
> Prior-building 2014-2017: **90.6% row / 90.6% game** (116/128; 1,856/2,048 games) vs a 90% gate.
> 410 resolved rows, all `high` confidence, 108 distinct persons, **18 dated midseason splits,
> 0 overlapping week ranges, 0 duplicate attributions**. The outer window was NOT narrowed and
> nominal OC was NOT substituted at any point.
> Table frozen at md5 `391be44c4e4205ceea6456ea935794c0` (v3.2; the T0 numbers above were RECOMPUTED from the corrected table and are unchanged).

### Amendment record (v3.1 -> v3.2, Joseph 2026-07-28, PREFIT)

**`n_games_attributed` corrected in the canonical table; table re-frozen under a new md5.**

- **Superseded md5:** `ac9883e98cdb1bd04a1c0978746cc023`
- **New canonical md5:** `391be44c4e4205ceea6456ea935794c0`
- Superseded copy retained on disk as `actual_play_caller.SUPERSEDED_ac9883e9.csv`.

**Reason.** The column was originally derived by WEEK ARITHMETIC
(`min(week_end, team_games) - week_start + 1`), which over-counts any segment spanning a bye week.
GB 2015 weeks 1-14 span 14 WEEKS but only 13 GAMES (bye in wk 7). The column feeds exposure weights
and the frozen `g/(g+32)` reliability directly, so a known-wrong canonical value is not worth
preserving to retain a checksum. **The checksum is an integrity tripwire, not the scientific object.**

**Exact diff — 14 rows, 7 team-seasons, 2015-2017 only, every one a clean +1/-1 pair:**

| season | team | person_id | weeks | old | new |
|---|---|---|---|---|---|
| 2015 | GB | tom_clements | 1-14 | 14 | **13** |
| 2015 | GB | mike_mccarthy | 15-99 | 2 | **3** |
| 2015 | LA | frank_cignetti | 1-13 | 13 | **12** |
| 2015 | LA | rob_boras | 14-99 | 3 | **4** |
| 2015 | MIA | bill_lazor | 1-12 | 12 | **11** |
| 2015 | MIA | zac_taylor | 13-99 | 4 | **5** |
| 2015 | TEN | ken_whisenhunt | 1-8 | 8 | **7** |
| 2015 | TEN | jason_michael | 9-99 | 8 | **9** |
| 2016 | JAX | greg_olson | 1-8 | 8 | **7** |
| 2016 | JAX | nathaniel_hackett | 9-99 | 8 | **9** |
| 2016 | MIN | norv_turner | 1-8 | 8 | **7** |
| 2016 | MIN | pat_shurmur | 9-99 | 8 | **9** |
| 2017 | KC | andy_reid | 1-12 | 12 | **11** |
| 2017 | KC | matt_nagy | 13-99 | 4 | **5** |

**Sourced evidence did NOT change.** A strict diff allowlist asserts that `n_games_attributed` is the
ONLY column with any changed cell, and that row count and row order are identical. Unchanged:
season, team, person_id, actual_play_caller, play_caller_role, week_start, week_end, nominal_oc,
head_coach, source_url, source_date, source_publisher, confidence, ambiguity_status,
pc_is_head_coach, pc_is_nominal_oc, note.

**Counting rules.**
- *Historical (season <= 2025):* distinct actual REG games inside `[week_start, week_end]`, from the
  PBP-derived weekly components using the same normalised team identifiers as
  `build_segment_offense.py`. Weeks spanning a bye are not games.
- *Prospective (2026):* games have not occurred, so the count is REG games **scheduled** for that team
  in the week range, from the nflverse schedule. Explicitly a scheduled count, **not** set to zero
  because PBP is unavailable. Zero 2026 rows changed (already 17).

**Reconciliation tests now enforced** (`fix_games_attributed.py`, re-checked in
`build_segment_offense.py`): canonical count == independently computed `pbp_games` on every
historical segment (0 of 378 disagree); every counted game inside the sourced week range; segment
sums == team distinct REG games for all 360 resolved historical team-seasons; no overlapping ranges;
no played game inside a resolved range left unassigned.

**T0 RECOMPUTED, not assumed.** Outer 2018-2025 **244/256 rows, 4,058/4,254 games**; prior-building
2014-2017 **116/128 rows, 1,856/2,048 games**. Identical to the pre-correction values, as expected
from paired +1/-1 corrections that leave every team-season total unchanged. Both gates still PASS.

**No player-projection arm was fit and no outer projection outcome was examined** at any point in
this correction.

### Amendment record (v3 → v3.1, Joseph 2026-07-28, PREFIT)

**Phase 1 audit required before any player-projection arm is fit.** Five defects confirmed against
the preliminary Arm 3 implementation, all recorded with their pre-audit observations in
`coaching/AUDIT_TODO.md` so no later choice can be justified by which option yields larger effects:

1. **Segment attribution** — play-caller segments currently inherit FULL team-season offense values;
   both callers in a split receive identical metrics. Must be rebuilt from PBP inside each sourced
   `week_start:week_end`, placed against the frozen within-season league distribution.
2. **Arm 3 exposure** — only the primary caller enters the design matrix, discarding all 18 splits'
   secondary callers. Replace with game-share exposure weights (HC changes too), preserving the
   HC==PC collapse without duplication.
3. **Reliability** — coded as `n_seasons/(n_seasons + 32/16)`; the frozen formula is
   `prior_games/(prior_games + 32)` on attributed games, emitted separately for HC and PC.
4. **Expectation controls** — `prior_qb_id` absent; no season indicators despite a code comment
   claiming them. Add the categorical with unknown handling and implement training-season effects,
   or file a prefit amendment for an identifiable alternative for an unseen season.
5. **Regularisation** — `RidgeCV` uses row-level CV, not season-blocked. Stage-2 tuning did NOT
   resolve: **9 of 10 target-season fits selected the grid-maximum alpha of 1000** (primary
   diagnostic), emitting **1,194 of 1,292 effect rows = 92.4% row-weighted**. Stage-1 alpha was
   never persisted, so 92.4% describes **Stage 2 only**.
   **Interpretation (corrected).** Ridge minimises `||y-Xb||^2 + alpha*||b||^2`, so an optimum at
   the grid maximum means the validation wanted **at least** that much shrinkage — widening the
   grid can only select a LARGER alpha and shrink coefficients FURTHER. A ceiling on alpha is a
   floor on effect size, not a cause of over-shrinkage. An earlier claim that the boundary
   'mechanically crushed' the effects was backwards and is withdrawn. **A persistent preference
   for very large alpha may itself be a genuine finding** that coach identities add little after
   controls; that possibility is NOT ruled out.
   **Fix + frozen boundary protocol:** season-blocked inner validation in both stages, with
   preprocessing fit inside each inner-training split; a preregistered broad log-spaced grid; on a
   boundary optimum, expand in that direction by a preregistered number of decades for a
   preregistered maximum number of iterations; if the upper boundary is still preferred at the
   frozen maximum, RECORD IT as evidence favouring effective complete pooling rather than forcing
   an interior solution; persist and report Stage-1 and Stage-2 diagnostics separately, at both
   fit level and row level. Never enlarge the grid until a coach effect becomes non-zero.

### Amendment record (v2 → v3, Joseph 2026-07-28)

1. **Play-caller research standard.** Sources ranked: contemporaneous team announcements /
   press conferences → contemporaneous ESPN, AP, CBS, NFL Network, local beat or established
   football publications → season previews and archived articles → coach biographies or
   retrospectives naming role and season → Wikipedia only where its cited source supports the
   claim. **The article itself must be read.** Search-result snippets, AI summaries, forum posts
   and fan sites do not qualify.
2. **Complement-inference is FORBIDDEN.** A source naming only the head-coach callers does not
   establish the caller for the remaining teams. The `medium`-confidence complement rows used in
   v2 were **removed**; 2018 is now covered by a direct 32-team source instead.
3. **Coverage gates apply to BOTH row and game-weighted coverage** (v2 assessed row primarily).
   Split rows may not inflate the numerator: a team-season with two resolved segments counts
   **once** for row coverage and **by attributed games** for game coverage.
4. **PFF-enhanced personnel sensitivity added** as a diagnostic-only arm (§11). It cannot enter
   nested selection and cannot rescue a failed primary result.
5. **Assertions extended** to T8 (PFF target-season leakage), T9 (PFF raw files stay ignored and
   uncommitted) and T10 (artifact hashes, row counts, feature order, prediction joins stable).

### Amendment record (v1 → v2)

v1 proposed sourcing the `pc_*` feature family from the **nominal offensive coordinator** because no
machine-readable actual-play-caller dataset exists. **That substitution is withdrawn.** It replaced
the variable the experiment is about with a different variable, which would have invalidated the
central question — whether demonstrated offensive-lead quality *travels between teams* — precisely
at the cases that motivate it.

v2 replaces it with a **citation-backed actual-play-caller table**, keyed on a **stable person
identity that survives job titles and teams**, plus **pre-registered minimum coverage gates that
block model fitting** when evidence is insufficient.

The substitution was not merely inelegant, it was measurably wrong: **13 team-seasons in the
assembled table have a play-caller who is neither the head coach nor the nominal OC** (e.g. 2021 LV
= Jon Gruden with Greg Olson as nominal OC; 2023 LV = Josh McDaniels with Mick Lombardi as nominal
OC). A nominal-OC rule mis-attributes every one.

---

## §0. THE QUESTION

Whether the incoming or incumbent offensive leadership has a **demonstrated, portable** track record
that improves player-level season-total half-PPR projections — and if so, *which quantification* of
coach quality does the work. Six competing quantifications are frozen as Arms 0–5 and chosen among
by nested walk-forward selection using training seasons only.

1. Does head-coach win percentage add signal?
2. Do offenses' annual rankings under a play-caller add signal?
3. Are continuous offensive-efficiency measurements better than ordinal rankings?
4. Does coach performance survive controls for team, quarterback and roster quality?
5. Are scheme and positional-allocation tendencies more useful than generic coach quality?
6. Does a combined quality-plus-scheme representation improve the website's projections?

---

## §1. IDENTITY AND ROLE ATTRIBUTION

### §1.1 Four separate identities

| Identity | Source | Grain | Coverage (2014–2026) |
|---|---|---|---|
| `head_coach` | nflverse `load_schedules` | **game** | 100% |
| `actual_play_caller` | citation-backed table, `playcaller_sources.py` | game-range | **56.7%** (see §1.6) |
| `nominal_oc` | Wikipedia season articles + cited current-OC list | season | 90.8% — **metadata only** |
| `pc_is_head_coach` | derived: play-caller vs head coach | game-range | wherever the play-caller is known |

### §1.2 Attribution rule (frozen)

**Offensive results are attributed to the ACTUAL PLAY-CALLER.** Historical performance belongs to
**the function the person actually performed, not the title he held.**

- A **nominal-OC season is never credited as a play-calling season** without evidence that the
  nominal OC actually called plays.
- **Nominal OC is staff-continuity metadata only.** It is never promoted to play-caller, and it
  never overrides a play-caller determination. A change of nominal OC **does not** set
  `pc_changed = 1` when the evidenced play-caller is unchanged.
- Where no reliable play-caller can be established, the observation routes to **UNKNOWN** → league
  prior, `reliability = 0`, `no_prior_history = 1`. It is **never** backfilled with the nominal OC.

### §1.3 Stable person identity

`person_id` is a normalized-name key that is **constant across every team and every job title** the
person ever holds, with generational suffixes folded (sources write both "Pete Carmichael" and
"Pete Carmichael Jr." for one man). This is what makes a record portable: Mike McDaniel's four
Miami seasons — held under a **head-coach** title — carry the same `person_id` as his 2026 Chargers
**coordinator** season, so his play-calling record follows him. Verified: no two distinct NFL
play-callers in 2014–2026 collide on a normalized name.

### §1.4 Role derivation — sources are not trusted

`play_caller_role` is **derived** by comparing the play-caller against the authoritative nflverse
head-coach table, never taken from a source's label. Published tables mislabel roles routinely
(Fantasy Index 2026 lists Sean McVay as an "offensive coordinator"; Yardbarker 2022 lists Luke
Getsy as a "head coach"). Every source/derived disagreement is reported.

### §1.5 Effective dates, midseason changes, ambiguity

- Head coach is attributed **game-by-game** (43 of 893 team-seasons had a midseason HC change).
- A midseason play-calling change is **split by games** where a defensible effective week exists
  (e.g. 2015 GB — McCarthy reclaimed play-calling, NFL.com dated 2015-12-13, week 15; 2020 CHI —
  Nagy relinquished after nine games, week 11). Otherwise the team-season is marked
  **ambiguous** and excluded from that coach's quality history — never split by guesswork.
- Co-play-callers with no single attributable person → **ambiguous** (2021 MIA, 2022 NE).
- Sources in direct conflict → **unresolved**, never silently reconciled (2022 PHI: Yardbarker
  names Sirianni, CBS reports Steichen took full-time play-calling).

### §1.6 PRE-REGISTERED MINIMUM COVERAGE GATES — these block model fitting

Assessed on **both** row and game-weighted coverage; **both** must clear the threshold.

| Scope | Gate | **Measured 2026-07-28** | Status |
|---|---|---|---|
| Outer-test team-seasons 2018–2025 | **≥ 95% row AND game** | **95.3% row / 95.4% game** (244/256; 4,058/4,254 games) | **PASS** |
| Historical team-seasons building their priors (2014–2017) | **≥ 90% row AND game** | **90.6% row / 90.6% game** (116/128; 1,856/2,048 games) | **PASS** |
| Deploy season 2026 | — | 100% row / 100% game | ok |

**Row coverage counts each (season, team) once** regardless of how many caller segments it carries,
so a midseason split cannot inflate the numerator. **Game coverage** is attributed games over
actual team games, capped per team-season at the real schedule length.

**No model may be fit while either gate is failing.** On failure the required output is the
unresolved rows, the search avenues attempted, the best available evidence and the exact coverage —
**not** a narrowed outer window and **not** nominal-OC attribution.

**Blocking seasons: 2014, 2015, 2016, 2019** — 127 of the 131 unresolved team-seasons. No
qualifying 32-team play-caller source exists for any of them; see
`coaching/data/RESEARCH_LOG.md` for the eleven search avenues attempted and their outcomes.

### §1.7 Table schema — `data/actual_play_caller.csv`

`season, team, person_id, actual_play_caller, play_caller_role, week_start, week_end,
n_games_attributed, nominal_oc, head_coach, source_url, source_date, source_publisher, confidence,
ambiguity_status, pc_is_head_coach, pc_is_nominal_oc, note`

**Confidence levels.** `high` — the source names this person as the team's play-caller.
`medium` — the source establishes the play-caller is *not* the head coach and the complement is
taken (documented inference, disclosed; **excluded from the primary coverage number**).
`conflict` — sources disagree → UNKNOWN. Absent → UNKNOWN.

All 238 currently resolved rows are `high`. No `medium` rows are admitted under v2.

### §1.8 Sources of record

| Season(s) | Source | Publisher | Date |
|---|---|---|---|
| **2017 (all 32)** | [ESPN — "The playcallers for all 32 teams and where their offenses rank"](https://www.espn.com/nfl/story/_/page/32for32x17115/nfl-2017-playcallers-all-32-nfl-teams-how-their-offense-ranks) | ESPN | 2017-11-15 |
| **2018 (all 32)** | [Fantasy Index — "Offensive coaches: Ranking the play callers 1 thru 32"](https://fantasyindex.com/2018/06/28/ian-allan/offensive-coaches) | Fantasy Index | 2018-06-28 |
| 2018 corroboration (14 HC callers) | [ESPN NFL Nation](https://www.espn.com/blog/nflnation/post/_/id/277514/finding-the-next-sean-mcvay-head-coaches-who-call-offensive-plays) | ESPN | 2018-07-12 |
| 2017 KC midseason split (wk 13) | [CBS Sports — Reid cedes play-calling to Nagy](https://www.cbssports.com/nfl/news/andy-reid-reportedly-cedes-play-calling-duties-to-offensive-coordinator-matt-nagy/) | CBS Sports | 2017-12-03 |
| 2018 CLE midseason split (wk 9) | [Newsweek — Jackson and Haley fired](https://www.newsweek.com/hue-jackson-todd-haley-fired-cleveland-browns-midway-through-season-1192594) | Newsweek | 2018-10-29 |
| 2020 | [Yardbarker](https://www.yardbarker.com/nfl/articles/ranking_the_offensive_play_callers_from_every_nfl_team/s1__32555903) | Yardbarker | 2020-10-22 |
| 2021 | [Yardbarker](https://www.yardbarker.com/nfl/articles/ranking_the_offensive_play_caller_for_each_nfl_team/s1__35857394) | Yardbarker | 2021 |
| 2022 | [Yardbarker](https://www.yardbarker.com/nfl/articles/ranking_the_offensive_play_caller_for_each_nfl_team/s1__37978942) | Yardbarker | 2022-12-05 |
| 2023 | [ESPN](https://www.espn.com/nfl/story/_/id/38108724/key-intel-all-32-nfl-playcallers-including-mike-mccarthy) | ESPN | 2023-08 |
| 2024 | [ESPN](https://www.espn.com/nfl/story/_/id/41018846/nfl-playcallers-32-teams-mike-mcdaniel-sean-mcvay-nathaniel-hackett) | ESPN | 2024-08 |
| 2025 | [ESPN](https://www.espn.com/nfl/story/_/id/46137832/nfl-playcallers-32-teams-mike-mcdaniel-sean-mcvay-brian-schottenheimer) | ESPN | 2025-08 |
| 2026 | [Fantasy Index](https://fantasyindex.com/2026/02/20/around-the-nfl/ranking-the-offensive-play-callers) | Fantasy Index | 2026-02-20 |
| midseason changes | cached Wikipedia team-season / coach articles | Wikipedia | various |

### §1.9 Strict-priority timing

Every historical quantity attached to a target-season **Y** row uses only games and seasons
**strictly before Y**. Asserted mechanically per fold (§8-T1).

---

## §2. COMMON SHRINKAGE (frozen — not tunable)

```
reliability  = prior_games / (prior_games + 32)
shrunk_value = reliability * observed_value + (1 - reliability) * league_prior
```

League priors: **0.500** for win percentage and rank percentiles; **0.000** for season-normalized
z-scores and residual effects. Also exposed per coach entity: `log1p(prior_games)`, `reliability`,
`no_prior_history`.

A coach with no qualifying history receives the league prior, `reliability = 0`,
`no_prior_history = 1`. **Unknown coaches are uncertain, not bad.**

Both windows computed: **career-to-date** through Y−1 and **rolling three-season** through Y−1.
The expanding league mean is recomputed from seasons `< Y` only.

The 32-game constant, 3-season window and league priors are **frozen** and may not be tuned against
any evaluation outcome.

---

## §3. DATA — built and validated 2026-07-28

### §3.1 Team-offense panel — `build_team_offense_panel.py` + `build_allocation_panel.py`
861 team-seasons, **1999–2025**, 33 columns.

**Frozen PBP filters:** `season_type == 'REG'`, `posteam` non-null; offensive plays =
`play_type ∈ {pass, run}`; **kneels, spikes and two-point conversions excluded** from all rate
metrics (removes 0.3% of scrimmage plays); drive metrics from `fixed_drive` / `fixed_drive_result`.

**Pace** (`seconds_per_play`) is the mean gap between consecutive snaps *within a drive* from
`game_seconds_remaining`, keeping gaps in (0, 60] s — 77% of plays qualify. This replaces v1's
all-null placeholder.

100% non-null: `epa_play`, `success_rate`, `yards_play`, `explosive_rate`, `points_per_drive`,
`redzone_td_rate`, `neutral_pass_rate`, `early_down_pass_rate`, `redzone_pass_rate`,
`seconds_per_play`, `off_points_per_game`, `rb_carry_share`, `qb_carry_share`, `rb_target_share`,
`wr_target_share`, `te_target_share`, `rz_{rb,wr,te,qb}_share`, `ol_sack_rate`.
**74.3%**: `proe` and `team_adot` — nflverse's `xpass`/air-yards models begin in **2006**; pre-2006
seasons carry native NaN, never an imputed value. Every outer test season and its training window
sit inside the covered era.

Face validity: 2024 best offenses by EPA/play = BAL, BUF, DET, WAS, TB, PHI; worst = CLE, LV, TEN.
2024 top TE target shares = ARI 34.0%, KC 33.6%, LV 33.4%. Pace: DAL fastest, GB slowest.

### §3.2 Arm 3 personnel controls — `build_personnel_controls.py`
896 team-seasons. Every column knowable **before** season S: lagged team form
(`prior_epa_play`, `prior_success_rate`, `prior_points_per_drive`, `prior_plays`,
`prior_pass_rate`, `prior_ol_sack_rate`), preseason QB identity and continuity (`prior_qb_id`,
`prior_qb_epa_play`, `prior_qb_cpoe`, `qb_returns`), returning shares
(`ret_qb_attempt_share`, `ret_rb_carry_share`, `ret_wrte_target_share`,
`ret_skill_fantasy_share`), `vacated_rush_share`, `vacated_target_share`, and `relocated`.
All 100% non-null across 2014–2026.

> Where a season's week-1 roster does not yet exist (the unplayed deploy season), returning shares
> fall back to the season roster and, failing that, emit **NaN — never 0**, which would otherwise
> read as "the entire roster departed" and hand every team a fabricated vacated share of 1.0.
> This bug was caught and fixed before freezing.

### §3.3 Player panel
`fantasy/seasonal_projections/season_dataset_2014_2026.csv` — the exact frame the four shipped
position builds consume. Target = **observed season-total half-PPR** summed from weekly REG stats,
identical to `build_rb_projection.season_total_target()`.

---

## §4. THE SIX FROZEN ARMS

**ARM 0 — CURRENT BASELINE.** The exact ordered feature columns from each position's shipped model
bundle, **including the existing `coach_changed`**. `depth_rank` stays excluded (RB prereg
Amendment 1). No coaching feature beyond the baseline.

**ARM 1 — SIMPLE COACH RÉSUMÉ.** HC: `hc_career_win_pct_shrunk`, `hc_roll3_win_pct_shrunk`,
`hc_prior_games_log`, `hc_reliability`, `hc_no_prior_history`, `hc_tenure_current_team`,
`hc_changed`. Wins/games computed game-by-game from schedules, **regular season only, no playoffs**;
a tie counts **0.5 win** and stays in the denominator.

Play-caller: for every prior qualifying season, the offense's league rank in points/game,
yards/play, EPA/play, success rate, points/drive →
`rank_percentile = 1 - (rank - 1) / (n_teams - 1)` (1.0 best);
`offense_rank_composite = mean(available rank percentiles)`, **frozen equal weight**, requiring
**≥3 of 5** components. Aggregated across prior seasons **weighted by games called**, then shrunk.
Emits `pc_career_off_rank_pct_shrunk`, `pc_roll3_off_rank_pct_shrunk`, `pc_prior_games_log`,
`pc_reliability`, `pc_no_prior_history`, `pc_tenure_current_team`, `pc_changed`, `pc_is_head_coach`.

**ARM 2 — CONTINUOUS OFFENSIVE EFFECTIVENESS.** Within each source season standardize across teams
(`z = (team − mean) / sd`); aggregate each z across the play-caller's strictly prior games/seasons;
shrink (prior 0.000). Career and rolling-3 versions of `pc_epa_play_z`, `pc_success_rate_z`,
`pc_points_drive_z`, `pc_yards_play_z`, `pc_explosive_rate_z`, `pc_redzone_td_rate_z`, plus prior
games, reliability and no-history flags. **No hand-weighted composite.**

**ARM 3 — PERSONNEL-ADJUSTED COACH EFFECT.** For every historical team-season S, fit an
**expanding** expectation model on seasons `< S` only, target = offensive EPA/play in S, using the
§3.2 controls plus season fixed effects. No season-S player performance may enter.
`team_offense_residual = actual − expected`. Using only residuals from seasons before Y, estimate
**cross-classified head-coach and play-caller effects** with partial pooling (ridge, separate HC and
PC identity blocks); regularization selected inside training data only. Emits
`hc_adjusted_offense_effect`, `hc_adjusted_effect_reliability`, `pc_adjusted_offense_effect`,
`pc_adjusted_effect_reliability`, `pc_is_head_coach`.

*Identifiability:* where one person holds both roles (113 of 238 resolved rows), attribution
collapses to a **single offensive-lead effect** and the same value is **never inserted twice** —
asserted by T4.

**ARM 4 — SCHEME AND FANTASY ALLOCATION.** Strictly prior, shrunk play-caller tendencies:
plays/game, neutral pass rate, PROE, early-down pass rate, red-zone pass rate, `seconds_per_play`,
RB/QB carry share, RB/WR/TE target share, red-zone opportunity share by position, `team_adot`.
Career and rolling-3 versions. **Only position-relevant features are appended:**

| Model | Appended |
|---|---|
| QB | plays, pass tendency, pace, red-zone pass rate, QB rush share |
| RB | plays, rush tendency, RB carry share, RB target share, RB red-zone share |
| WR | plays, pass tendency, WR target share, air-yard tendency, WR red-zone share |
| TE | plays, pass tendency, TE target share, TE red-zone share |

**ARM 5 — ADJUSTED QUALITY PLUS SCHEME.** Staff continuity/tenure + Arm 3 adjusted effects + Arm 4
position-specific features + reliability/no-history flags. **Excludes** Arm 1's win-pct/rank and
Arm 2's raw efficiency features by construction.

---

## §5. NESTED REPRESENTATION SELECTION

For each position and outer test season Y: training data = seasons `< Y`; compare Arms 0–5 by
**leave-one-season-out inner validation within training data only**; use the **exact fixed
production model family and hyperparameters** from the position's shipped bundle (the player model
is **not** retuned); rank arms by mean inner-validation MAE on the **baseline-defined draft-relevant
cohort** (QB top 12, RB top 24, WR top 24, TE top 12).

An arm is **eligible** only if inner full-panel MAE worsens by ≤ **0.25** points. If the best
coaching arm improves inner top-cohort MAE by **< 1%** vs Arm 0 → **select Arm 0**. If multiple arms
are within **0.25** top-cohort MAE points → select the arm with **fewer added features**. Fit the
selected arm on all seasons `< Y`; predict Y.

The resulting outer predictions are the **sole primary challenger**. Individual fixed arms are
diagnostic and can never be selected using outer-test results.

---

## §6. OUTER EVALUATION

Outer test seasons **2018–2025**; **2021–2025** reported separately as the recent panel. Per
position, nested-selected pipeline vs Arm 0 **on identical rows**. Report full-panel and top-cohort
MAE; RMSE; mean and median bias; mean within-season Spearman; per-season changes; player-clustered
and team-season-clustered bootstrap intervals; selection frequency for Arms 0–5; each fixed arm as
diagnostic only. Bootstrap: **20,000 draws, seed `20260728`**. Fixed arms carry **Holm correction
across Arms 1–5 within each position**.

---

## §7. PRIMARY PASS RULE

A position becomes a **developmental candidate** only if the nested-selected pipeline: (1) improves
top-cohort MAE by **≥ 3%**; (2) has **both** clustered 95% interval upper bounds **< 0**;
(3) improves top-cohort MAE in **≥ 6 of 8** outer seasons; (4) improves in **≥ 4 of 5** recent
seasons; (5) improves mean within-season top-cohort Spearman by **≥ 0.005**; (6) worsens full-panel
MAE by **≤ 0.25** points; (7) worsens full-panel RMSE by **≤ 1%**; (8) selects a non-baseline arm in
**≥ 4 of 8** folds; (9) beats the **95th percentile** of the frozen within-season coaching-feature
permutation placebo; (10) passes every timing, leakage, coverage and artifact-integrity assertion.

**No individual fixed arm can rescue a failed nested-selected result.** A result that selects Arm 0
in nearly every fold is **evidence that coaching features do not add stable signal** — a
publishable outcome, not a failure.

---

## §11. PFF-ENHANCED PERSONNEL SENSITIVITY (DIAGNOSTIC ONLY)

The public-data experiment remains the **sole primary test**. This adds one pre-registered
sensitivity. It **cannot** select a production feature representation and **cannot** rescue a
failed primary result.

**Approved files only** (regular-season scope confirmed before use): `nfl_offense_blocking_YYYY`,
`nfl_offense_pass_blocking_YYYY`, `nfl_line_pass_blocking_efficiency_YYYY`, YYYY = 2013–2025.

> **Path note.** The ratifying prompt cited these as `nfl_YYYY/offense_blocking.csv`. They were
> renamed to the repo convention on 2026-07-28 and now read `nfl_YYYY/nfl_offense_blocking_YYYY.csv`
> etc. Same 52 files, same content.

**Excluded:** the PFF passing / receiving / rushing summary exports **include postseason games**
and are barred from this regular-season experiment.

For target team-season S, features derive from **S−1 only**; no season-S PFF performance enters.
Prior-team position-group aggregates: QB snap-weighted offensive grade; RB/FB snap-weighted
offensive grade; WR/TE snap-weighted offensive grade; OL snap-weighted pass-block grade; OL
snap-weighted run-block grade; OL pressures allowed per pass-block snap; team pass-blocking
efficiency. Weights are prior-season offensive or pass-block snaps. Aggregates are standardized
within source season, carry coverage / sample-size / missing-history fields, and are shrunk toward
the expanding position-season mean. **Missing grades are never encoded as zero.**

Used **only** to build a PFF-enhanced variant of the Arm 3 expectation model. Reported: public vs
PFF-enhanced adjusted coach effects, sign agreement, rank correlation, and fixed Arm 3 / Arm 5
projection diagnostics. **Never added to primary nested arm selection.**

No raw PFF rows are copied into `coaching/` or committed; any row-level intermediate stays ignored.
Only non-licensed aggregate diagnostics are saved.

---

## §8. ASSERTIONS

- **T0 — coverage gate.** §1.6 must pass on **both** row and game coverage for every scope before
  any fit. **PASSED 2026-07-28** (95.3/95.4 outer, 90.6/90.6 prior).
- **T1 — timing.** Every coaching feature on a season-Y row derives only from games `season < Y`.
- **T2 — walk-forward.** No fold trains on its own test season.
- **T3 — shuffle-leak probe.** Coaching features carry aligned signal on a proof-model and lose it
  when the target is shuffled within season.
- **T4 — no double-counting.** Where HC and PC are one person, the effect appears exactly once.
- **T5 — unknown routing.** No qualifying history → league prior, `reliability == 0`,
  `no_prior_history == 1`; never a penalty or a bonus.
- **T6 — artifact integrity.** `rookie_ppg_model.pkl` md5 `872467b2295fce27761f9e04da01b6e8`
  unchanged; the four shipped position pkls unchanged; no parquet and no licensed PFF table written
  into the repo. **This experiment never rewrites a production artifact.**
- **T7 — routing assertions.** §8.1.
- **T8 — PFF timing.** Every PFF feature attached to season S derives from seasons `< S`; no
  season-S PFF performance enters any control.
- **T9 — PFF containment.** Raw PFF files remain gitignored and uncommitted; no row-level PFF data
  is written into `coaching/`.
- **T10 — artifact stability.** Artifact hashes, row counts, feature order and prediction joins
  unchanged end-to-end.

**Production hashes captured 2026-07-28 (T6 baseline, verified unchanged at handback):**
```
qb_veteran_model.pkl  7632549f95995b9702baefdf016d7271
rb_rookie_model.pkl   da230ee66575ca574f02cbc2139e1a80
rb_veteran_model.pkl  167aca71a8511afcced37c0abc846004
te_rookie_model.pkl   f79dad0ab26af5cb4e06a9f1723328cd
te_veteran_model.pkl  5a2f0b504d4cc6fc9a2e04453fd76a44
wr_rookie_model.pkl   6c9a3f3ed02ce32c53594f383aade882
wr_veteran_model.pkl  17dfbcf01054bdd5ce032f2b55df9ad2
rookie_ppg_model.pkl  872467b2295fce27761f9e04da01b6e8
```

### §8.1 Routing assertions — VERIFIED against the assembled table

**Los Angeles Chargers, 2026** ✅
```
head_coach         = Jim Harbaugh          hc_changed = 0
actual_play_caller = Mike McDaniel         pc_changed = 1
nominal_oc         = Mike McDaniel         [metadata only]
McDaniel prior play-calling: MIA 2022, 2023, 2024, 2025 (head-coach title) = 4 seasons / 68 games
  -> reliability = 68/(68+32) = 0.680, no_prior_history = 0
```
His Miami record follows his **person identity across the title change**, which is the whole point.

**Los Angeles Rams, 2026** ✅
```
head_coach         = Sean McVay            hc_changed = 0
actual_play_caller = Sean McVay            pc_changed = 0
nominal_oc         = Nathan Scheelhaase    [metadata only — does NOT set pc_changed]
McVay prior play-calling: 2018, 2020-2025 = 7 seasons / 117 games
  -> reliability = 117/(117+32) = 0.785, no_prior_history = 0
```
The nominal-OC change is correctly ignored. (2019 LA is absent only because 2019 is unsourced.)

**Unknown first-time play-caller** ✅ league prior, `reliability = 0`, `no_prior_history = 1`,
no subjective penalty or bonus.

---

## §9. POST-VERDICT INTERPRETATION

Report which representation — if any — was repeatedly selected: simple HC win pct + offensive ranks
/ continuous efficiency / personnel-adjusted effect / scheme-allocation / adjusted quality plus
scheme / **or no coaching information at all**.

**Only if a position passes**, run a 2026 counterfactual audit comparing actual staff assignment;
same roster and all non-coaching features; and a league-average no-history play-caller. Report
team-level and position-level movement for the Chargers and Rams. **Diagnostic only** — not
validation, not authorization to change the website.

**Never manually force McDaniel or McVay upward.** If their calculated priors are not positive after
the frozen definitions and controls, say so plainly.

---

## §10. FENCES

- This experiment **writes no production artifact**.
- A pass makes a position a **developmental candidate only**.
- "Beating Sleeper" is not a bar and is not evaluated here.
- The shrinkage constant, rolling window, league priors, cohort definitions, eligibility margins
  (0.25 / 1% / 3%), bootstrap seed, coverage gates and pass rule are frozen by this document.
  Changing any of them after seeing a result requires a written amendment stating what was known at
  the time.
