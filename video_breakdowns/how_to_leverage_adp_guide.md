# How to Leverage ADP: The Guide

*Series opener · what happens when two projections both disagree with the market*

**The one-liner:** Across drafted players in 2021 to 2025, when my season-projection model and Sleeper's projections both put a player on the same side of his ADP, that pair picked the correct side **72.2%** of the time. The wider the disagreement, the better it did: 75.0% at three positional spots, 83.2% at five, 88.6% at eight. This write-up gives the exact panel, every denominator, and the two places where the result does **not** support the stronger reading.

---

## 1. The rule, stated precisely

Everything below runs on one definition. Ranks are computed within `(season, position)` using `method='min'`.

| Term | Definition |
|---|---|
| `model_gap` | `adp_rank − model_rank` (positive means my model ranks him **above** his draft price) |
| `sleeper_gap` | `adp_rank − sleeper_rank` |
| `actual_gap` | `adp_rank − actual_rank` (his real finish) |
| **agreement at t** | `sign(model_gap) == sign(sleeper_gap)` AND both gaps exceed `t` |
| **consensus** | `sign(model_gap) × min(|model_gap|, |sleeper_gap|)`. The **weaker** of the two gaps governs. |
| **hit** | `sign(actual_gap) == sign(consensus)` and `actual_gap ≠ 0`. **An exact tie counts as a miss.** |

Two consequences worth holding onto. First, the weaker gap governing means a headline number is always the conservative one: if my model says a player is nine spots underpriced and Sleeper says three, the filter records three. Second, ties are graded as failures rather than dropped, which costs the rate rather than flattering it.

## 2. The panel

Every historical figure on this page comes from one frozen panel, no exceptions:

> **Drafted top-180 players, universe A, complete rows, seasons 2021 to 2025.** Row-level artifact: 5,315 player-seasons.

"Drafted" is load-bearing. These rates describe players who carried a real draft price, not the whole player pool. Read as a claim about the entire board they would be wrong.

The study's thresholds are **strict `>`** on integer ranks, so its own published `>5` cell actually means *six or more spots*. The 3+ and 5+ bars used in the video are the **inclusive** bars (`>2.5` and `>4.5`), recomputed with the study's own estimator. Both versions exist and they are not interchangeable.

## 3. The ladder

| Bar | Hit rate | Calls |
|---|---:|---:|
| Any gap | **72.2%** | 296 / 410 |
| 3+ spots | **75.0%** | 162 / 216 |
| 5+ spots | **83.2%** | 104 / 125 |
| 8+ spots | **88.6%** | 62 / 70 |

The chance benchmark is **about 48%**, established by 10,000 within-`(season, position)` permutations. On the four cells for this exact panel the null landed at 0.4835 to 0.4889 with `p = 0.0001`. Two things to be precise about: **across all 48 permutation cells the study ran, the null spans 0.483 to 0.505** and one cell reads `p = 0.0002`, so 48% is this panel's number rather than a universal one. And **every permutation cell is all-position.** There is no per-position null, which matters for the positional instalments in this series.

These are **historical group rates on a fixed panel, not odds for any current player**. Nothing on this page attaches a percentage to a name.

## 4. What my side of the consensus actually is

Seven models ship, not eight: **RB, WR, TE and QB veterans, plus RB, WR and TE rookies**. There is no quarterback rookie model. It was fitted and walk-forward evaluated, then held back from the shipped surface, so rookie quarterbacks carry no projection at all.

The family is **LightGBM**, one model per position per experience class, targeting full-season half-PPR points.

Feature importance is **held-out permutation importance**, grouped into readable families, normalized within each position model, then averaged with equal weight across positions. These are the figures the video puts on screen:

| Veterans (4 models) | Share | In that model's top 3 |
|---|---:|---:|
| Prior NFL production | 71.6% | 4/4 |
| Usage / role | 13.3% | 3/4 |
| Age / experience | 4.5% | 2/4 |

| Rookies (3 models) | Share | In that model's top 3 |
|---|---:|---:|
| Draft capital | 65.7% | 3/3 |
| PFF college grades | 13.0% | 3/3 |
| Size / athletic testing | 8.8% | 1/3 |

**A disclosure that belongs with those percentages.** The importance run was never written to a persisted artifact, and neither was the map from raw features to the family names above. Re-deriving it later turned out to be only partly possible: the quarterback veteran feature matrix no longer exists on disk, so the four-position veteran average cannot be recomputed at all. On the three rookie models, which do survive, a fresh permutation run reproduces the **ordering of the top two families and all three top-three counts**, but not the exact shares, and it puts college production third where the video puts athletic testing third.

So read the **ordering and the top-three counts as solid, and the specific percentages as a single unreproduced run.** The correct fix is to persist the importance artifact and the family map alongside the models, and that has not been done yet.

**Inputs and importance are also different lists**, and the video keeps them separate for a reason: the spoken rookie input list is in narrative order, not importance order, and should not be read as a ranking.

What does survive every version of that calculation is the shape: **prior NFL production dominates the veteran models**. That is the single most useful thing to know about the model's behaviour, and it is why the model marks down players coming off short seasons.

## 5. The limitation, stated plainly

**Sleeper is the stronger single instrument at every position.** On the same rows, ranked against realized season totals (Spearman):

| Position | n | JoScho | Sleeper |
|---|---:|---:|---:|
| RB | 486 | .671 | **.799** |
| WR | 657 | .738 | **.797** |
| TE | 304 | .741 | **.798** |
| QB | 262 | .731 | **.849** |

My model alone on that panel picks the correct side of ADP **58.1%** of the time (475/818) at any gap and 61.9% (322/520) at five or more spots. Sleeper alone beats it at every bar.

Adding the agreement requirement raises the observed rate:

| Bar | Sleeper alone | Both agree | Observed difference |
|---|---|---|---:|
| 3+ | 70.4% · 340/483 | 75.0% · 162/216 | +4.6 pts |
| 5+ | 77.1% · 246/319 | 83.2% · 104/125 | +6.1 pts |
| 8+ | 83.8% · 166/198 | 88.6% · 62/70 | +4.7 pts |

**Those are descriptive comparisons across different denominators, not incremental-lift estimates.** The study's own pre-declared incremental comparisons read **+0.068 [−0.028, +0.161]**, **+0.073 [−0.031, +0.169]** and **+0.035 [−0.098, +0.156]**. Every interval crosses zero.

So the honest statement is: **the study does not establish that my model adds value beyond Sleeper alone.** What it establishes is that the two-instrument filter beat chance on this panel, and that the intervals are too wide to separate the pair from Sleeper by itself.

One arithmetic note, because it is the kind of thing that quietly inflates a chart. The 8+ difference is **+4.7**, not +4.8. Subtracting the two displayed rates gives 88.6 − 83.8 = 4.8, but the exact difference is 88.5714 − 83.8384 = **+4.733**. Rounding twice overstated the gap.

## 6. Recent seasons

The video shows ten correct calls from each of the last two seasons at the inclusive 5+ bar. Those are **selected examples**, so the full season rates stay attached to them:

- **2024: 29 of 34 correct (85.3%).** Five misses.
- **2025: 11 of 14 correct (78.6%).** Two misses and one exact tie, which counts as a non-hit.

Every displayed number in those tables is a **positional rank**, not a projected point total, and all 80 cells were checked against the row-level artifact.

## 7. The 2026 board

Point-in-time snapshot, ADP retrieved **2026-08-03 at 15:32 ET** from Sleeper. This list is not maintained; ADP moves daily and later videos in the series re-pull it.

The eligible population reconciles like this:

```
245 players in the formal top-245 ADP range
 −35 kicker and defense rows (no position model covers them)
 − 1 rookie QB with no frozen projection (no rookie-QB model ships)
=209 eligible
```

**As shown in the video: 46 of the 209 cleared three or more spots.** One was set aside editorially, because he was injured and not on a roster at the time, leaving **45 tracked**: 20 above ADP, 25 below, and by position WR 23 · RB 16 · TE 6 · QB 0. Saying "45 cleared" alone would misreport the filter's own output, which is why both numbers are on screen.

**That board does not reproduce today, and the reason is worth stating plainly.**

The board was built at 17:23 on 2026-08-03. The four frozen projection files it joined against were **rewritten at 20:36 to 20:38 the same evening**, three hours later, in an inference refresh that added a feature join without retraining any model. The refresh log records the replaced file hashes, and the old quarterback hash it lists is the exact hash the video cites as its source. So the on-screen counts and the on-screen name list are correct for the artifacts that existed when the board was built, and they are joined to projection files that no longer exist in that form.

Recomputing the same filter from the manifest definition against the current snapshot in the video's own package (ADP captured 2026-08-06, joined to the frozen projections as they now stand, all 209 model values matching the frozen artifacts exactly) gives:

> **42 of 209 clear three or more spots. 16 above ADP, 26 below. WR 22 · RB 14 · TE 6 · QB 0.**

The stable parts across both versions are the ones the video actually argues: **six tight ends, no quarterbacks at all**, and a receiver-heavy board. The exact count and the membership near the three-spot line move with every ADP pull.

**So the 45 names are deliberately not republished here.** A name list that cannot be regenerated is not evidence, and reprinting it on a page that outlives the snapshot would present a superseded board as a current one. If you want a live view of where the market and the projections disagree, the Draft Board tab is refreshed daily and is the maintained surface.

Two things that are true of either version. **Every row is a current disagreement with no outcome**, carrying none of the historical rate. And at least one name on the below-ADP side reflects an injury-year projection collapse rather than a read on the market, which is a reason it belongs in a complete list and nowhere else.

**The lesson for the series is the operational one.** The video file's own instruction was to re-verify the market snapshot on the day of render, and the render happened the following evening. What actually moved underneath it was not the ADP but the projection artifacts. The later instalments pin a frozen copy of their snapshot beside the video for exactly this reason.

## 8. What this does not prove

- **It does not prove my model adds anything to Sleeper.** Every pre-declared incremental interval crosses zero. Sleeper alone ranks finishes better at all four positions.
- **It is not pre-registered and it is not live-validated.** This is descriptive post-hoc research on a stored panel. 2026 is the first season with a real timestamp on both sides.
- **It says nothing about undrafted players.** The panel is drafted top-180 only.
- **A group rate is not a per-player probability.** 88.6% describes 70 historical calls at that bar. It is not the chance that any 2026 name works out.
- **The display bars are not the pre-declared bars.** The 3+ and 5+ tiers were added for presentation in 2026-08 and recomputed with the study's estimator; they were not part of the original declared set.
- **The chance benchmark is all-position.** No permutation null was computed for any single position, so the ~48% line should not be read as the chance rate for a quarterback-only or tight-end-only cell.
- **The feature-importance percentages are a single unpersisted run.** The ordering and top-three counts survive recomputation; the exact shares have not been reproduced, and the veteran average cannot be reproduced at all until the missing feature matrix is rebuilt.
- **The 2026 board on screen is joined to superseded projection files.** See section 7. The direction of the finding holds; the exact membership does not.

## 9. About the video

The short walks the ladder, names the model, concedes that Sleeper is the better standalone instrument, then puts the 2026 board up with no result attached. The position-by-position instalments that follow (quarterback, tight end, and the rest) apply the same filter one position at a time.

---

*Sources: the ADP-consensus agreement study under `fantasy/projections/research/`, panel `drafted_top180 / universe A / complete / 2021-2025`, with all rates recomputed from its row-level artifact; the frozen raw 2026 projections in `fantasy/projections/results/` (never the analyst display overlay used on the Draft Board); and a single dated Sleeper retrieval for ADP and Sleeper's projections. Rank correlations were reproduced independently from the stored walk-forward files. This is football analysis, not betting advice.*
