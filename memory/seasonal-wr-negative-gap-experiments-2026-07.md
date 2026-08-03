---
name: seasonal-wr-negative-gap-experiments-2026-07
description: Rejected 2026-07 WR point rescues and the depth-chart follow-up. Depth tier is historically informative beyond roster presence, but the only current-schema fold regressed, so it does not enter the July model.
metadata:
  type: project
---

Rejected experiments from the 2026-07-25/26 investigation into why several 2026 WR
projections sit far below Sleeper's. All ran on the WR **non-rookie** path (the term
"veteran" is retired in user-facing copy), fixed LightGBM at the deployed config
(`objective="mae"`, `num_leaves=15`, `learning_rate=0.03`, `n_estimators=400`,
`random_state=42`), 2021-2025 walk-forward, no nested model selection, no artifact
writes. Protected MD5s asserted unchanged at the start and end of every run
(`wr_veteran_model.pkl` = `17dfbcf01054bdd5ce032f2b55df9ad2`, `wr_rookie_model.pkl` =
`6c9a3f3ed02ce32c53594f383aade882`).

Two walk-forward row counts are in play and are **not comparable**: n=1006 (assembled
via the full `--assemble` pipeline including the frozen rookie matrices; baseline MAE
31.170) and n=955 (built from `season_dataset` directly; baseline MAE 32.213). Never
compare a number from one against the other.

## The framing result: the gap is mostly not ours

On the 546 out-of-fold 2021-2025 rows where Sleeper published a projection:

| | Mean projection | Bias vs actual |
|---|---|---|
| Actual outcome | 97.6 | — |
| Model | 91.4 | **−6.2** |
| Sleeper | 118.2 | **+20.6** |

`mean(model − sleeper)` = −26.76, and it decomposes exactly as −6.17 − 20.59, so **77%
of the gap is Sleeper being too high**. Sleeper is above the actual result on 68% of
rows. The mechanism is full-health projection — split by games actually played, Sleeper's
bias is +4.1 on 16-17 game seasons and +46.6 on 0-12 game seasons, while the model's runs
−27.6 and +30.3. The two sources answer different questions; a ~27-point standing gap is
the translation between them, not a defect.

Head-to-head on those rows: model MAE **39.05** vs Sleeper **39.99** (paired Wilcoxon
p=0.30, model better on only 51.3% of rows, sign flips if 2021 is dropped — **not a real
edge**). Rank correlation: model **0.745** vs Sleeper **0.794**, and Sleeper wins rho in
**4 of 5 seasons** — that one IS robust. After removing each source's own mean bias
Sleeper's MAE beats the model's (37.44 vs 39.19), so the model's entire MAE edge is level
calibration, not discrimination. **Sleeper has better signal; we have better calibration.**

Consequence: closing the point gap is not a goal. Closing the **ranking** gap is.

## The structural defect

Bias by ACTUAL outcome decile (n=1006): bottom **+18.2**, d3 +16.1, middle **0.0**,
d8 −24.8, top **−56.6**. Prediction SD 58.7 against an actual SD of 69.9. The model
overpays busts and underpays stars, and every other measured bias in this campaign is
single-digit by comparison.

## Rejected — do not re-run

**1. Feature-representation variants on the season total** (`PREREG_ppg_vs_total_2026-07-25.md`).
Drop `prior_half_ppr`; down-weight it via LightGBM `feature_contri`; replace it with a
recency-weighted PPG composite; drop it plus `prior_games`. Baseline MAE 31.170 →
31.391 / 31.391 / 31.394 / 31.389. All worse, all ≤2 of 5 seasons improved, rho fell in
every case, and the shortened-prior-season subgroup (n=430) did not improve either
(22.279 → 22.335+). Two mechanical findings that kill the whole family:
`prior_half_ppr == prior_ppg * prior_games` **exactly** (max abs diff 0.0), so "dropping
the total" removes no information from a tree that still holds both factors; and
`feature_contri=0.25` does not down-weight, it **deletes** — the feature's SHAP share went
33.9% → 0.0% with 0 splits, making that variant identical to the drop. **Verdict: REJECT.**

**2. Prorating the season-total features to a 17-game footing**
(`PREREG_prorate_totals_2026-07-25.md`). Exactly three features scale with games played
(`prior_half_ppr`, `prior_rec_epa`, `prior_rush_epa`); everything else in the 32-feature
pool is already a rate or context. Naive prorate, all-three prorate, empirical-Bayes
shrunk prorate (k=4 pseudo-games, anchor computed on the training fold only), and shrunk
prorate with the injury features removed: MAE +0.356 / +0.422 / +0.209 / +0.782 vs
baseline. Only the last is significant (CI [+0.135, +1.423]); the first three straddle
zero. The decisive finding: **prorating does not raise short-season players.** On the 240
deploy rows the mean change for `prior_games <= 12` was −0.49 / −0.63, because the injury
features absorb the lift — and it is `prior_games_missed` doing 1.6-1.9× more of the
absorbing than `prior_games`; dropping either alone leaves the sign negative. The bump
only lands when **both** are removed, which is the one variant that is measurably worse.
The over-projection guardrail moved the wrong way in every variant (+19.2 → +25 to +38).
**Verdict: REJECT.** Note the k grid is noise (k=6 sits at parity, +0.006), so H's small
penalty is partly an artifact of the pre-specified k=4.

**3. Within-season role trajectory.** Second-half vs first-half target share; last-4-games
share ramp; both plus air-yards and scoring trends; and a `years_exp == 2` interaction.
MAE +0.178 / −0.017 / +0.127 / +0.204, every CI straddling zero, rho down in all four,
2-3 of 5 seasons better. It also **failed at the job it was built for**: the third-season
cohort under-projection went 17.47 → 19.67 / 16.67 / 18.31 and cohort MAE rose from 52.00
in every variant. Coverage is 79% on training rows but **72%** on the 2026 deploy rows —
the same drift class that hit the rookie profile matrix in July. **Verdict: REJECT.**

**4. Loss functions.** L2, Poisson, Tweedie at variance power 1.1/1.3/1.5/1.7/1.9, and
LambdaRank, all against MAE's 31.170. Nothing beat it: 32.68 / 31.87 / 31.76 / 31.82 /
31.39 / 31.36 / 31.56, and LambdaRank — trained on pure ranking — was the **worst** ranker
at rho 0.7129 vs MAE's 0.7452. Poisson buys +0.003 rho for +0.70 MAE. Critically, the
top-decile under-projection is **not** a loss artifact: it stays at −55 to −66 under every
objective (L2 −55, Poisson −59, Tweedie 1.5 −63) while the bottom deciles inflate from
+18 to +24. Mean-targeting losses raise the floor, not the ceiling. The target is
right-skewed (mean 67.4 vs median 43.4, skew +1.12, 12% exact zeros, variance/mean 73.8),
so the median-targeting objective does cost ~24 points of level — but fixing that is
global inflation, not discrimination. **Verdict: REJECT. Keep `objective="mae"`.**

## The one live candidate

Third-season WRs (`years_exp == 2`) are under-projected by **+6.8** pooled (n=168,
positive in 5 of 5 seasons, player-clustered bootstrap CI [−0.64, +13.75]) and **+17.5**
for the subset with `prior_target_share >= 0.15` (n=47, 5 of 5 seasons, CI [−1.40,
+36.59]). Within that cohort only, within-season target-share trend correlates with
under-projection at rho **+0.357** (5 of 5 seasons, CI [+0.196, +0.497]); every other
career stage is ~0 or negative (2nd −0.105, 4th −0.059, 5th-6th −0.038, 7th+ −0.087).
Split by direction: third-year players whose role rose are under-projected **+22.4**
(n=73, 5/5 seasons); those whose role fell are over-projected −7.1 (n=58, 1/5).
The misses are the canonical breakouts — Deebo Samuel +242, Nico Collins +167,
Smith-Njigba +124, Puka Nacua +114, St. Brown +104.

**Caveats that travel with this claim:** found by slicing (~10 cuts examined), the CI on
+17.5 straddles zero, and experiment 3 above shows the raw feature — and the years_exp
interaction — do not capture it. This is a **candidate, not a result**. The working
explanation is that the signal lives entirely in the right tail while the MAE objective
optimizes the median.

## Counter-cohort — do not raise these players

WRs coming off a short prior season (1-12 games) at a top-quartile prior per-game rate are
**already over-projected by +19.2** (n=39; direction consistent 5/5, but the pooled CI is
[−3.21, +39.59] and one row — Will Fuller 2021, projected 170.7, scored 6.6 — supplies a
fifth of it, so treat the direction as established and the magnitude as not). Other
blowups in the class: Calvin Ridley 115.0 → 0.0, Julio Jones 159.0 → 64.9, Chris Godwin
142.1 → 66.5. **Mike Evans, Terry McLaurin and Rome Odunze are all in this cohort.**
By draft capital, Round-1 WRs carry a model bias of **+0.9** against Sleeper's **+33.5**;
by age, 29+ is model **+2.4** against Sleeper **+27.1**. Moving those players toward
Sleeper imports a known 27-33 point error.

Separately, on the young / high-draft-capital / not-yet-featured profile — the exact story
told about Pearsall and Odunze — **the model already out-ranks Sleeper** (rho 0.607 vs
0.531). Sleeper's ranking edge lives in mid-career, mid-capital, age 25-28 players.

## Method notes worth keeping

- Every result above was re-derived by an independent adversarial subagent working from
  the raw parquet/CSV. Verification **cut nearly every finding down** — one claimed 532
  corrupted rows where 162 was the truth. Budget for the verify pass; the finders
  systematically overstate.
- Do not mutate the dataset while a review is running. On 2026-07-26 the corrected
  `season_dataset_2014_2026.csv` was written mid-run, and two verifiers then "refuted"
  postseason findings that were real and already fixed.

Related: [[joschoanalytics-model-experiments-2026-05]], [[experiment-rejection-criteria]],
[[daily/2026-07-26]].

## 2026-07-26 correction — the third-year effect is a tail, not a point lift

The July 26 data fix materially changes the live candidate's interpretation. Under the
same fixed LightGBM and the production-shaped n=1,006 panel, corrected-data MAE is
**31.071** and Spearman is **0.7534**. The broad third-season group remains underprojected
on the mean by **+8.79** (n=168, 5/5 seasons, player-clustered 95% interval
[+1.83, +16.07]), stronger than the pre-fix +6.79. But the old
`prior_target_share >= 0.15` refinement is not durable: 47 rows shrink to 37,
mean bias falls from +17.48 to **+12.25**, consistency falls from 5/5 to 4/5, and the
interval remains wide at [-7.51, +31.58]. Eleven old members, including Deebo Samuel and
Nico Collins, cleared 15% only because the prior target-share calculation was wrong.
Hunter Renfrow is the one new entrant. **The threshold story is retired.**

More importantly, the broad +8.79 is not a median-calibration error. In those 168
third-season rows:

- actual mean 66.14 versus prediction mean 57.35, but actual median **31.74** versus
  prediction median **39.29**;
- median residual `actual - prediction` is **-2.30**, and only **45.2%** of rows are
  underprojected;
- the top 10 residuals supply **35.4%** of all positive residual mass; removing them
  reduces mean bias to +1.47, and removing the top 17 makes it -2.43;
- the largest misses are true breakout-tail events: Deebo +217.6, Nico Collins +170.5,
  Jaxon Smith-Njigba +129.9, Hunter Renfrow +117.9, and Jameson Williams +113.9.

The fixed MAE learner estimates a median-like point forecast. Its cohort median is already
slightly high while a minority of breakouts pulls the mean residual positive. A blanket
third-year uplift would therefore worsen more player point forecasts than it fixes. Treat
this as **breakout uncertainty**, not permission to raise the point estimate.

## Rejected — cross-season role state

`PREREG_wr_cross_season_role_2026-07-26.md` froze one genuinely new challenger for every
non-rookie WR: corrected `target_share_lag2` plus
`prior_target_share - target_share_lag2`, with both new fields missing whenever either
source season had multiple teams. The script loaded no Sleeper/ADP data and left every
model/result artifact unchanged.

Primary 2018-2020 (n=566): baseline MAE 35.393 / rho 0.6858 versus challenger
35.336 / 0.6835. The 0.057-point MAE gain missed the frozen 0.25 bar, rank fell 0.0023,
and the player-clustered paired interval was [-0.439, +0.547]. Compatibility 2021-2025
(n=1,006): baseline 31.071 / 0.75341 versus challenger 31.082 / 0.75355, with both
metrics better in only 2/5 seasons and top-tail underprojection worsening
54.59 to 55.50. **Verdict: REJECT.** No alternate lag, threshold, interaction,
career-stage slice, or tail rescue using these role-state fields.

A post-hoc diagnostic reinforces the rejection: among the 142 corrected third-season rows
with clean cross-season role change, its Spearman correlation with residual is only
**+0.080**, with fold values +0.049, -0.126, -0.159, +0.212, +0.390. The rising-role
story does not replicate as a stable cross-season mechanism.

## Pearsall sensitivity — college talent dead, depth tier is a live candidate

On 2026-07-26, a new player-specific sensitivity test compared the corrected 32-feature
refit with (a) the already-frozen richer PFF college WR composite, decayed 1.0/0.5/0.25
over the first three NFL seasons, (b) nflverse preseason depth tier, and (c) both.
The test used the same fixed LightGBM and 2021–2025 expanding walk-forward (n=1,006);
no market number entered a feature, fit, or gate.

The college feature failed: MAE 31.071 to 30.943 (-0.128, short of the frozen -0.25
threshold), rho .75341 to .75192, with 3/5 MAE-winning seasons. Pearsall's composite was
only +0.115 SD and decayed to +0.029 in Year 3, moving his corrected-panel projection
76.06 to 76.10. **Do not use college talent to rescue Pearsall.**

Depth tier was the first point-forecast challenger in this campaign to clear its frozen
sensitivity gate: MAE **31.071 to 29.053**, rho **.75341 to .80523**, 3/5 MAE-winning
seasons. The third-year slice (n=168) improved from MAE 33.033 / rho .7714 / bias +8.79
to 30.729 / .8157 / +5.14. The new ESPN depth schema must be translated by ranking within
`(team, pos_slot)`; raw `pos_rank` is not comparable to legacy `depth_team`. Under that
translation, Mike Evans, Ricky Pearsall, and Christian Kirk are all tier 1; De'Zhaun
Stribling is tier 2. New-feed tiers are capped at 1–2 to prevent deep July camp rosters
from creating a 96%-versus-70% coverage shift.

Pearsall: shipped 63.9 (protected pre-correction model), corrected-panel refit 76.1,
depth tier 1 **89.4**, college+depth 91.0. A tier-2 counterfactual falls to 79.2 / 79.0.
Therefore the lift is a role scenario, not an injury correction or college-pedigree
effect. The combined model adds no historical support beyond depth alone (MAE is 0.005
worse); treat **depth only** as the developmental candidate. It still needs a separate
production-wide preregistration, and July depth status can change before Week 1.

Artifacts:
`fantasy/projections/PREREG_wr_pearsall_sensitivity_2026-07-26.md` and
`fantasy/projections/wr_pearsall_sensitivity_harness.py`. Existing model/result artifacts
were unchanged.

## Depth falsification — real historical ordering, failed current-source transport

A frozen follow-up separated roster presence from ordinal tier and aligned both legacy and
new feeds to tiers 1–2. On the same 2021–2025 panel (n=1,006), a binary listed flag improved
MAE 31.071 to 29.712 and rho .75341 to .79261, recovering **67.3%** of the originally fired
depth MAE gain. Presence is the majority mechanism, but it missed the predeclared 75%
threshold for calling the result only a listing proxy.

Ordinal tier survived the harder test. With identical top-two support, MAE was 29.229 and
rho .80058. On listed complete cases only (n=658), refitting both models on listed players,
tier improved MAE 38.368 to **37.753** and rho .71085 to **.73213**, with MAE better in
3/5 seasons. Tier 1 outcomes averaged 122.9 (n=392) versus 40.1 for tier 2 (n=266).
Historical rank contains real information beyond active-roster presence.

Timing from the earliest dated 2025 snapshot (Aug 3) to the pre-opener snapshot (Sep 3)
was reasonably stable: 88.2% of early top-two players remained listed, and 86.6% of the
127 common players retained the same tier. This does not validate July.

The decisive deployment caveat is source transport. The only evaluated year using the
same dated ESPN schema as 2026 was **2025, and it regressed**: aligned-tier MAE 28.672 to
29.191, rho .81991 to .81571; complete-case MAE 34.468 to 34.943. The pooled positive
evidence comes from the legacy nflverse schema. **Do not add ordinal depth to the current
July model.** It remains a historically credible mechanism awaiting forward/current-schema
validation, not a production feature. Pearsall's 89.4 remains a role sensitivity output,
not a calibrated current projection.

Artifacts:
`fantasy/projections/PREREG_wr_depth_signal_falsification_2026-07-26.md` and
`fantasy/projections/wr_depth_signal_falsification_harness.py`. Protected artifacts were
unchanged.

## Pearsall player-specific 2026 range

Read-only reconstruction from the pinned weekly-stat and snap snapshots, plus current
49ers roster/injury verification on 2026-07-26, supports a wide scenario distribution
rather than a blanket injury prorate.

Pearsall's active-game role progressed from a 13.8% weighted target share in 2024
(11 games, 46 targets, 31-400-3 receiving, 78.0 half-PPR including 45 rushing yards) to
18.4% in 2025 (9 games, 53 targets, 36-528-0, 70.6 half-PPR). The path was not smooth:

- 2025 Weeks 1-4, before the PCL absence: 29 targets, 327 yards, 42.3 half-PPR,
  19.7% weighted target share.
- Weeks 11-13, first return: 9 targets, 20 yards, 4.7 half-PPR, 11.3% share.
- Weeks 15 and 17, around the PCL reaggravation/ankle issue: 15 targets, 181 yards,
  23.6 half-PPR, 24.6% share.

That sequence shows both real target-earning upside and performance impairment during
recovery. Multiplying the nine-game 2025 total by 17 would erase the most important
player-specific information.

San Francisco recorded 497, 504, 471, 513, and 550 team targets from 2021 through 2025
(mean 507). As of 2026-07-25/26, the active roster includes Pearsall, Mike Evans,
Christian Kirk, and rookie No. 33 pick De'Zhaun Stribling. Brandon Aiyuk is on
Reserve/Left Squad and outside the 90-man roster, so the current base allocation assigns
him zero targets. George Kittle opened camp on Active/PUP after an Achilles injury, making
his target claim a scenario variable. The 49ers' own depth-chart page says it will not be
updated until the start of the season. Therefore the nflverse/ESPN July tier is not an
official team hierarchy.

A transparent historical screen of Round-1 WRs since 2000 with at most 22 games and at
least 300 receiving yards over their first two seasons produced n=16: third-year median
50.0 half-PPR, IQR 9.0-120.4, and only 5/16 at 100+. The screen includes non-football
failures and is not a clean injury prior. A tighter production-matched group (700-1,200
yards, excluding Henry Ruggs) contains Kelvin Benjamin 165.6, Demaryius Thomas 246.4,
Rashod Bateman 60.5, and Corey Coleman 10.1 in Year 3: median 113.0, range 10.1-246.4.
The comparison is useful only for demonstrating variance.

Explicit 2026 scenarios:

| Scenario | Games | Team targets | Pearsall targets | Catch / yards / TD | Half-PPR |
|---|---:|---:|---:|---:|---:|
| Low: crowded room, another interruption | 13 | 493 | 55 | 35 / 451 / 2 | 75 |
| Base: active WR2/rotating WR1b | 15 | 515 | 84 | 55 / 764 / 3 | 123 |
| High: healthy breakout, 20% share | 17 | 535 | 107 | 72 / 1,049 / 5 | 173 |

The defensible range is therefore approximately **75-170 half-PPR**, with the center of
mass around **110-125**. The corrected refit 76.1 is a low-case anchor; the depth
sensitivity 89.4 is a conservative low-to-mid role scenario, not a calibrated July point
forecast. Sleeper's 139.7 sits in the upper half of the plausible range and requires
roughly 90-plus targets with 15-plus games and positive touchdown regression; it is not
ground truth. No model, dataset, board, preregistration, harness, or result artifact
changed during this follow-up.

## Pearsall protected-model target tune (exploratory)

Joseph explicitly requested a Pearsall-only, tune-to-120 diagnostic with no other player
scored. This is post-hoc target selection, not model evidence and not a shipping result.
The protected pkl scores the current corrected Pearsall row at 66.35, while the unchanged
shipped result CSV remains 63.9 because it was generated from the earlier deploy row.

The narrow sequence was:

| Step | Changed Pearsall features | Projection |
|---|---|---:|
| Current corrected row | none | 66.35 |
| Availability-neutralized | `prior_games` 9->15; `prior_games_missed` 8->2; `prior_half_ppr` 70.6->117.67 | 92.86 |
| Healthy-rate bundle | `prior_ppg` 7.84->10.575 (2025 Weeks 1-4 rate), `prior_half_ppr` ->158.625, and coherent `ppg_2yr`/`ppg_3yr`/`ppg_trend`/`career_high_ppg` updates | 108.17 |
| Air-yards threshold | `prior_air_yards_share` .186->.200 | 115.10 |
| TD-regression threshold | `prior_td_rate` 0->.020 | **120.03** |

Changing `prior_target_share` from the full-season 10.2% to his 18.4% active-week share
did not move this tree-path score. The air-yards and TD values were chosen to cross
Pearsall's fitted LightGBM thresholds after the injury-neutral bundle; they are plausible
but not independently validated. The defensible interpretation is therefore: injury
neutralization alone gets this protected model to roughly 93-108 depending on whether the
healthy Weeks 1-4 rate is adopted; 120 requires additional positive efficiency assumptions.

Protected model MD5s remained `wr_veteran=17dfbcf01054bdd5ce032f2b55df9ad2`
and `wr_rookie=6c9a3f3ed02ce32c53594f383aade882`; all 16 existing result CSVs were
byte-identical before and after. No other player was scored.

## Generic Pearsall sensitivity — separate PPG from availability

A follow-up replaced the post-hoc feature rewriting with transformations that could apply
to every veteran WR. Adding `prior_ppg × 16.5`, active-week target/air-yards shares, and
active-vs-full-season share gaps to the fixed season-total learner did not help:
corrected baseline 76.06, neutral-points 76.06 (zero splits; algebraically redundant),
active-role 75.19, and both 75.19. Generic feature additions are not the solution under
the total-points target.

The generic architecture change was decisive. Using the same 32 features to predict
historical WR PPG, then multiplying by the previously established fixed 16.5 games,
produced **117.71** for an unweighted PPG fit (7.134 PPG) and **119.42** when training
seasons were weighted by observed games (7.238 PPG). No player-specific constant,
healthy-week selection, target-share override, TD assumption, or tuned multiplier entered
either model.

This is a developmental architecture candidate only. Historical WR rows were used for
training, but no other player was scored and no cross-player metric was computed. The
result shows that separating scoring rate from availability resolves Pearsall's total-model
suppression; it does not show the architecture improves WR accuracy. Artifacts:
`fantasy/projections/PREREG_wr_generic_injury_role_sensitivity_2026-07-26.md`,
`wr_generic_injury_role_sensitivity_harness.py`,
`PREREG_wr_generic_ppg_total_sensitivity_2026-07-26.md`, and
`wr_generic_ppg_total_sensitivity_harness.py`. Protected model/result artifacts remained
unchanged.

## Generic PPG × 16.5 architecture — full WR validation rejected

The pre-registered production-candidate follow-up scored the games-weighted PPG
architecture on every non-rookie WR outer-fold row, including zero/very-short outcomes.
The comparison held the corrected n=1,006 panel, ordered 32 features, fixed LightGBM
configuration, and 2021–2025 folds identical; the target was the only model change.

The result was decisively negative:

- pooled MAE **31.071 → 39.679** (+8.609);
- RMSE **43.999 → 50.198** (+6.198);
- Spearman **.75341 → .72907** (-.02434);
- bias `actual - prediction` **+1.98 → -22.05**;
- challenger MAE wins **0/5 seasons**;
- paired player-cluster bootstrap interval for the MAE delta
  **[+6.919, +10.372]** (363 clusters, 2,000 draws).

All six frozen switch conditions failed. **Do not switch the non-rookie WR model from a
direct season-total target to games-weighted PPG × 16.5.** Do not rescue the result with
an unweighted fit, alternative multiplier, cap, calibration offset, healthy-player panel,
or blend.

The mechanism is clear. On players who ultimately played 13-plus games, the challenger
improved MAE 37.308 to 34.567 (n=512). On players who ultimately played 12 or fewer, it
worsened MAE 24.606 to 44.978 (n=494). That future availability split is unknowable at
draft time. On the forecast-time-known `prior_games <= 12` group, the challenger also
regressed badly: MAE 22.428 to 36.659 (n=451).

The 2026 case scores explain the temptation but cannot override the validation:
Pearsall 76.1 → 119.4, Rome Odunze 100.1 → 136.7, Luther Burden III 113.2 → 125.7
(corrected direct-total refit → PPG × 16.5; shipped context 63.9 / 94.4 / 110.4).
Treat the challenger values as healthy-season scenarios only. Artifacts:
`fantasy/projections/PREREG_wr_ppg_target_architecture_2026-07-26.md` and
`wr_ppg_target_architecture_harness.py`. Protected models/results remained unchanged.

## Analyst-overlay evidence rule

For the 2026 WR adjustment review, Joseph explicitly excluded Sleeper projections and
ADP from both candidate selection and adjustment-size decisions. A player-specific
overlay must be supported by non-market evidence such as availability, established role,
verified roster/context change, or a documented model blind spot. Market disagreement
may be displayed separately but is not evidence for moving the projection.

Malik Washington was subsequently removed from the 2026 adjustment slate because he is
outside the board's current Sleeper-ADP-245 display universe. This is an eligibility
decision, not evidence about his football projection; ADP remains excluded from the
direction and magnitude of any adjustment that is evaluated.
