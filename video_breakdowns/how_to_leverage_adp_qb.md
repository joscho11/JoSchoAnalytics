# How to Leverage ADP: QB Edition

*2026 · the five quarterbacks with a gap between the market and both projections*

**The one-liner:** At quarterback the filter barely fires. **No 2026 quarterback clears even three positional spots**, the largest consensus gap in the whole pool is two, and the five names below are the entire board worth discussing. That absence is the finding.

If you have not read the series opener, the rule and its limitations are laid out in the Guide write-up. Short version: `consensus = sign(model_gap) × min(|model_gap|, |sleeper_gap|)`, so the **weaker** of the two disagreements governs, and a tie against the market counts as a miss.

---

## 1. The five

Snapshot capture `2026-08-04T143835Z`, 27 eligible quarterbacks in the formal top-245 ADP range. Model values are joined to the **frozen raw** `qb_projection_2026.csv`, never to the 45-row analyst display overlay that the Draft Board renders.

| Player | Team | ADP | Sleeper | My model | Sleeper proj | Model proj | Talent |
|---|---|---|---|---|---:|---:|---:|
| Joe Burrow | CIN | QB4 | QB6 | QB8 | 306 | 257 | **94.7** |
| Jaxson Dart | NYG | QB9 | QB11 | QB11 | 297 | 234 | 77.5 |
| Bo Nix | DEN | QB14 | QB12 | **QB3** | 296 | 277 | 75.4 |
| Baker Mayfield | TB | QB20 | QB18 | QB10 | 275 | 238 | 75.3 |
| Bryce Young | CAR | QB26 | QB24 | QB22 | 236 | 149 | 73.9 |

Projections are full-season half-PPR points. **Talent Score is my own composite index, not a PFF product and not a projection.** It grades how a quarterback actually played in the previous window. The quarterback talent instrument fired dead as a predictor when it was tested, so it is descriptive context only and is never an input to any projection.

## 2. Joe Burrow, and why the model marks him down

Both projections sit below his QB4 price. The mechanism is not a judgment about Burrow, it is the shape of the model.

| Season | Games |
|---|---:|
| 2020 | **10** |
| 2021 | 16 |
| 2022 | 16 |
| 2023 | **10** |
| 2024 | 17 |
| 2025 | **8** |

**One correction to the video.** The on-screen strip shows 17 games in 2022. It was **16**: Cincinnati had a bye and their week-17 game was cancelled. The spoken claim that survives it is the one that matters, and it is still true. Ten or fewer games in three of six seasons, in 2020, 2023 and 2025. Now pair that with what the model weights: prior NFL production is **71.6%** of veteran feature importance, and on Burrow's own prediction the single largest contribution is prior half-PPR points at **+56.85** against a base of 99.88.

**The availability features do not rescue him. They make it worse.** On eight games played and nine missed, Burrow's availability features net **−8.13**. They penalise a short season rather than correcting a partial-season total back up to a full one. That is a real limitation of the model, not a considered stance on injury risk, and it is worth knowing before you read QB8 as an opinion about him.

Against that, my talent score has Burrow **second among all quarterbacks at 94.7**, behind only Josh Allen. The honest framing is the one the video uses: QB4 is a fair price for a healthy Burrow, and "healthy" is the assumption doing the work.

## 3. Jaxson Dart, and the second-year effect

Both projections land on **QB11** against a QB9 price, and talent agrees rather than arguing: Dart is **14th** among the 26 quarterbacks carrying a 2026 draft price.

There is a mechanical reason to be cautious about how confident that number looks. Dart has exactly one NFL season, and the model reads it four separate times: `prior_ppg`, `ppg_2yr`, `ppg_3yr` and `career_high_ppg` are **all 17.256** for him. Four features, one season of evidence.

The counterweight is a real, measured effect. Paired within-player change in realized points per game, quarterback seasons 2014 to 2025, with a starter floor of eight games (n = 428 seasons over 117 players):

| Transition | Mean change in PPG |
|---|---:|
| **Year 1 to year 2** | **+2.591** |
| Year 2 to 3 | −0.717 |
| Year 3 to 4 | −0.981 |
| Year 4 to 5 | +0.113 |
| Year 5 to 6 | −0.415 |
| Year 6 to 7 | +1.234 |

The year-1-to-2 cell is n = 33, median +0.797, **t = +2.89, 95% CI [+0.84, +4.35]**, and 61% of those quarterbacks improved. Every other transition averages **−0.153**. So the jump is specific to the second year rather than a general upward drift.

**Two caveats that matter.** It is measured **paired**, on purpose: only about 66% of year-one starters start again in year two, so a naive cross-section would be reading survivorship. And it is **exploratory, not pre-registered**. It is a reason to hold the projection loosely, not a validated adjustment.

Dart's situation also changed around him: new head coach, new coordinator, new personnel. Those are reasons for variance in both directions, which is where the video lands on him.

## 4. Bo Nix, the one the video argues against

This is the largest disagreement on the board, and it is the one call where Joseph takes the market's side over his own model.

My model has Nix **QB3**, six spots above his QB12 Sleeper rank and eleven above his QB14 price. The mechanism is volume: he threw more passes than anyone in football last season, and a points model reading raw production picks that up directly.

The rate underneath the volume is the problem. **6.4 yards per attempt** means most of those attempts were short, and a projection built on prior totals does not distinguish between 600 efficient attempts and 600 inefficient ones. Talent has him **75.4**, which is a long way from the top of the position and sits much closer to where ADP has him.

Reported separately, and not something computed from any artifact here: he is coming off an ankle injury.

The conclusion in the video is deliberately split. The consensus and the talent number together still point slightly above his ADP, but QB3 is the model latching onto the one thing it weights most heavily.

## 5. Baker Mayfield, the same story quieter

ADP QB20. Sleeper QB18. My model **QB10**. Talent 75.3.

The video describes it as a big total with an ugly rate: completion percentage down from 71 to 63, yards per attempt down from 7.9 to 6.8. Same failure mode as Nix, at a lower price and with a smaller gap.

Because the price is already QB20, the practical read is narrower than the model's number suggests. QB10 would be a surprise; finishing above QB20 would not be.

## 6. Bryce Young, recorded and cut

Young was written, recorded and then cut for runtime. He still appears in the video's hook and summary tables, and he belongs here because the board is only five names deep:

**ADP QB26 · Sleeper QB24 · my model QB22 · talent 73.9.** A two-spot disagreement, the kind that only becomes interesting in superflex or two-quarterback formats.

## 7. A correction the video could not make

The talent board in the video **shows no rank numerals**, and there is a specific reason.

The talent file ranks **49 quarterbacks**. Only **26 carry a 2026 ADP**, and the 26 are the population the video is actually about. Dart's spoken "14th" is correct in the 26-quarterback pool. But the recorded audio says Nix is **17th** and Mayfield **18th**, which are 49-pool ranks. In the 26-quarterback pool they are **16th and 17th**.

Rather than print a numeral on screen that contradicted the narration, the board was built to show order, score and each subject's neighbours with no ranks at all. Fixing it properly needs two short re-records. **The correct ranks in the population the video discusses are 16th for Nix and 17th for Mayfield.**

Same class of error as any denominator mismatch: the number was not wrong so much as computed against the wrong population.

## 8. History at quarterback

On the same historical panel as the Guide (drafted top-180, universe A, 2021 to 2025), the agreement filter at quarterback, at the one-or-more-spots bar:

> **33 of 45 correct, 73.3%.** Wilson 95% interval **[59, 84]**.

n = 45 clears the sample floor used for quoting a cell. Cells with fewer than 11 calls are not quoted anywhere in this series, however flattering they look, and there is at least one such cell at quarterback.

**On the chance line, one thing the video does not say.** The ~48% benchmark shown beside that rate comes from permutation tests that are **all-position**. The study ran 48 permutation cells and not one of them is quarterback-only, so there is no null computed for these 45 calls specifically. Treat 48% as the study-wide reference point it is, not as a quarterback-specific baseline.

## 9. What this does not prove

- **The 73% is historical and positional, not a per-player probability.** It describes 45 quarterback calls over five seasons. It is not the chance that any of these five works out.
- **Talent Score is descriptive.** The quarterback instrument fired dead as a predictor. It is context beside a projection, never an input to one, and never a forecast.
- **The second-year finding is exploratory.** It was not pre-registered and should not be treated as a validated adjustment to any projection.
- **The model penalises missed games rather than adjusting for them.** Burrow's availability features net negative on a short season. Read QB8 with that in mind.
- **Nothing here is live-validated.** 2026 is the first live test of the filter, and there is no outcome for any 2026 name.
- **The chance benchmark is not a quarterback number.** No permutation null was computed for any single position.

## 10. About the video

The short walks the five in ADP order, spends the most time on Burrow and Nix, and closes on the honest headline for this position: the quarterback board barely disagrees with itself at all. The tight end instalment is where the filter actually has something to say.

---

*Sources: a dated Sleeper retrieval for ADP and Sleeper's projections; the frozen raw `qb_projection_2026.csv` in `fantasy/projections/results/`; per-prediction feature contributions from the shipped `qb_veteran_model.pkl` (re-prediction reproduces the shipped projections on all 93 veteran quarterbacks to a maximum absolute difference of 0.05); `fantasy/talent/nfl_qb_score_2026.csv` for the talent index; nflverse-derived season data for the games and second-year tables. The ankle injury reference is external reporting and is not computed from any artifact here. This is football analysis, not betting advice.*
