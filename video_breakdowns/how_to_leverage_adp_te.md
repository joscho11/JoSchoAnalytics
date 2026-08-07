# How to Leverage ADP: TE Edition

*2026 · the seven tight ends with a gap between the market and both projections*

**The one-liner:** Seven tight ends clear a two-spot disagreement. **Five of the seven say the same thing, which is that the market is too high.** Only two go the other way, and the larger of those two is a 37-year-old. This write-up carries the evidence the video had to compress, including the two exhibits that argue against its own calls.

*One correction up front: the video's Kelce segment calls him "the only one consensus says is undervalued." That is wrong by one. Eli Stowers is +2 and appears in the same tables. Kelce is the **larger** of two positive calls, not the only one.*

The rule is the one from the series opener: `consensus = sign(model_gap) × min(|model_gap|, |sleeper_gap|)`, so the **weaker** of the two disagreements is what gets reported.

---

## 1. The seven

Snapshot capture `2026-08-05T143724Z`, 31 eligible tight ends. Model values joined to the **frozen raw** `te_projection_2026.csv`, never the analyst display overlay. Talent ranks are within the **29 tight ends carrying a 2026 draft price**; college ranks are within that player's own final-season cohort.

| Player | Team | ADP | Sleeper | My model | Call | NFL talent | College talent |
|---|---|---|---|---|---:|---|---|
| Dalton Kincaid | BUF | TE9 | TE12 | TE18 | **−3** | 88.6 (7th) | 95.2 (1st of 92) |
| Oronde Gadsden II | LAC | TE11 | TE18 | TE20 | **−7** | 78.3 (13th) | 83.9 (6th of 127) |
| Jake Ferguson | DAL | TE12 | TE15 | TE15 | **−3** | 68.8 (26th) | 80.3 (8th of 92) |
| Travis Kelce | KC | TE13 | TE10 | TE7 | **+3** | 78.5 (12th) | n/a |
| Kenyon Sadiq | NYJ | TE19 | TE24 | TE27 | **−5** | none | 74.3 (26th of 208) |
| Terrance Ferguson | LAR | TE24 | TE27 | TE31 | **−3** | 64.5 (27th) | 78.6 (7th of 127) |
| Eli Stowers | PHI | TE30 | TE28 | TE22 | **+2** | none | 92.0 (3rd of 208) |

Sadiq and Stowers have **no NFL talent row at all**. Both are true rookies and the index needs a professional record to score anyone. That is a limitation of the instrument, not a statement about them.

**How the bar changes the board**, over the 31 eligible tight ends:

| Bar | Qualifying | Market too low | Market too high |
|---|---:|---:|---:|
| 1+ spot | 13 | 5 | 8 |
| **2+ spots** | **7** | **2** | **5** |
| 3+ spots | 6 | 1 | 5 |
| 5+ spots | 2 | 0 | 2 |
| 8+ spots | 0 | 0 | 0 |

The weaker-gap rule is doing visible work here. Kincaid's raw model gap is **−9** and Tucker Kraft's is **−13**, but Sleeper only has them at −3 and −1, so the filter reports the small numbers. Gadsden is the largest call precisely because **both** instruments agree deep, at −9 and −7.

## 2. Dalton Kincaid: the ability is real, the volume is the question

Talent has Kincaid **7th of the 29** at 88.6, and his college score of 95.2 was **first in his entire 2022 cohort of 92**. So this is not a talent objection. Both projections are betting against his target share.

**Buffalo, 2025 actual targets** (all pass catchers, running backs included, team total 479 over 17 games):

| Player | Pos | Games | Targets | Per game | Share |
|---|---|---:|---:|---:|---:|
| Khalil Shakir | WR | 16 | 95 | 5.9 | 19.8% |
| Keon Coleman | WR | 12 | 59 | 4.9 | 12.3% |
| **Dalton Kincaid** | TE | **12** | **49** | **4.1** | 10.2% |
| Dawson Knox | TE | 16 | 49 | 3.1 | 10.2% |
| James Cook | RB | 17 | 40 | 2.4 | 8.4% |
| Ty Johnson | RB | 17 | 33 | 1.9 | 6.9% |

**Read the per-game column, not the share.** Kincaid missed five games, so his season-total share reads 10.2% while his per-game rate is about 14.5%. Quoting the season total would understate his role by roughly a third.

On those 49 targets he averaged **11.65 yards per target**, the best raw mark of anyone in this video. It is quoted as a rate and never as a rank, because the ranked population in this series is tight ends with 50 or more targets and he finished one short of the bar.

**Buffalo, 2026 projected.** Two things have to be said before the table. My model **does not project targets**. It projects season points. So the share column below is a transparent estimate built for this video only: projected half-PPR points, converted to a receiving portion, divided by Buffalo's 2025 receiving points per target for that position, then normalised across the room.

| Player | Pos | Projected pts | Implied share |
|---|---|---:|---:|
| DJ Moore *(new)* | WR | 109.9 | 17.4% |
| Khalil Shakir | WR | 94.0 | 14.8% |
| **Dalton Kincaid** | TE | **86.9** | 9.4% |
| Keon Coleman | WR | 75.1 | 11.9% |
| Dawson Knox | TE | 45.2 | 4.9% |
| James Cook | RB | 213.6 | 5.9% |

**"Third on that offense" needs its population stated, and the video does not state it.** Among the **pass catchers** (the receivers and tight ends), Kincaid is third on projected points behind Moore and Shakir, which is the claim the narration is making. Count James Cook, who is in the table above at 213.6, and Kincaid is **fourth**. On implied targets he is fourth either way, because a tight end converts a target into more points than a receiver does and therefore needs fewer of them to reach the same total.

Three different orderings, all defensible, and the video quotes one without naming which. Third among the receiving corps is the honest version.

DJ Moore arriving is the whole mechanism behind the TE18. It is stated in the model's own numbers rather than asserted.

## 3. Oronde Gadsden II: the biggest call, and the least comfortable

This is the largest disagreement on the board at −7, and **the per-snap evidence points the other way.** Leaving that out would be the dishonest version, so it is here in full.

**Rookie tight end seasons with 50 or more targets, ranked by yards per target.** Window is 2019 to 2025 (seven classes, **19 qualifying seasons**). Source data begins in 2018, and a player first appearing in 2018 cannot be confirmed as a rookie, so 2019 is the clean start. This is **not** "the last decade".

| Rank | Player | Rookie year | Targets | Yards | Y/T |
|---:|---|---:|---:|---:|---:|
| **1** | **Oronde Gadsden II** | **2025** | 69 | 664 | **9.62** |
| 2 | Kyle Pitts | 2021 | 110 | 1,026 | 9.33 |
| 3 | Colston Loveland | 2025 | 82 | 713 | 8.70 |
| 4 | Hunter Henry\* | 2019 | 76 | 652 | 8.58 |
| 5 | Noah Fant | 2019 | 66 | 562 | 8.52 |
| 6 | Brock Bowers | 2024 | 153 | 1,194 | 7.80 |

He is **1st of the 19 in yards per target and 8th in total yards**: elite rate, modest volume, the same shape as Kincaid.

**\* Two of the 19 are not actually rookies, and the video's plate does not say so.** "Rookie season" here is implemented as *a player's first season present in the source file*, and that file begins in 2018. Anyone who missed all of 2018 and returned in 2019 gets labelled a 2019 rookie. **Hunter Henry was drafted in 2016** and missed 2018 injured; **Jason Witten**, drafted in 2003, is in the same pool off-screen at 6.37. On a plate whose entire point is a carefully defined population, that is a real defect.

It does not move the finding. Drop both and the pool is **17 true rookie seasons**, Gadsden is still 1st in yards per target, and he is still 8th in total yards, because both misclassified seasons sit below his 664. The rank survives; the label on the Henry row does not.

Widening the population to **all tight end seasons with 50+ targets since 2018 (214 seasons)**, his rookie 9.62 ranks **16th**. George Kittle owns the top two at 11.77 in 2024 and 11.33 in 2023. That figure did not make the video because a third leaderboard in one beat would have been a wall, and the rookie population makes the point more cleanly.

**College.** Gadsden graded **83.9, 6th of 127** in his 2024 final-season cohort, which places him at the **89th percentile** of the 318 drafted tight ends in the college file.

**The competition, and a coincidence worth the space.** The Chargers brought in David Njoku and Charlie Kolar. On college grades:

| Rank | Tight end | College | Year | Score | |
|---:|---|---|---:|---:|---|
| 29 | Charlie Kolar | Iowa State | 2021 | **85.4** | 2026 Charger |
| 32 | Cole Hikutini | Louisville | 2016 | 84.6 | |
| 33 | David Njoku | Miami (FL) | 2016 | **83.9** | 2026 Charger |
| **33** | **Oronde Gadsden II** | **Syracuse** | 2024 | **83.9** | 2026 Charger |
| 35 | David Morgan | UTSA | 2015 | 83.6 | |

Njoku graded **exactly** where Gadsden did, tied at 33rd, and Kolar graded higher. All three are on the 2026 Chargers.

**But the pro grades say the opposite, and that changed the video's closing line.** On NFL talent Gadsden is far ahead of Njoku, 78.3 to 69.1, and 13th of the 29 draftable against Njoku's 25th. So "they graded right there with him" is true of college and false of the professional grades. The narration says the roster fact instead, which needs no grade claim.

**On Charlie Kolar having "no score".** That is a sample-size exclusion, not missing data, and the distinction matters. He has receiving rows in all three window seasons: 65 routes in 2023, 49 in 2024, 102 in 2025. The build sets a **100-route per-season floor and a 150-route three-year window minimum**. Only his 2025 clears the per-season floor, and 102 routes alone misses the window minimum. He is excluded by design.

It is computable, though. Re-running the real build with the floors dropped to 40 and 100 admits him at **77.7, 22nd of a 117-tight-end pool**, with Gadsden at 80.9 and Njoku at 69.9 in that same run.

**Those three numbers are comparable only to each other.** Widening the pool from 92 to 117 re-fits every reference and the anchor, which moved all 92 shipped players by a median +1.25 (range −10.3 to +5.5). Printing 77.7 beside the shipped 78.3 would mix two populations. The ratified artifact was not touched by that sensitivity run.

Kolar landing just behind Gadsden on the re-fit scale is the target-competition argument in one line. And the reason the floor exists is visible in his 2025: 13 targets and 10 receptions, which is not enough to score a contested-catch or deep facet with any confidence.

## 4. Jake Ferguson: the cleanest call, and the counter it does not survive cleanly

TE12 in ADP, and Sleeper and my model land on the **exact same number, TE15**. Talent has him **26th of 29**.

**A correction to the video's gloss on that.** The screen calls 68.8 the lowest talent score of anyone in the video. It is not: Terrance Ferguson is **64.5, 27th of 29**, and both numbers sit side by side in the video's own summary table. Jake Ferguson is the lowest of the four players given a dedicated segment, which is what the narration means, but the on-screen wording overstates it.

The mechanism is the cleanest illustration in the video of what the two lenses measure:

| 2025 | Value | Rank |
|---|---:|---|
| Targets | 102 | **7th at the position** |
| Yards per target | 5.88 | **27th of 29** (50+ targets) |

The projection reads the volume. The talent score reads the efficiency. Both are right about different things.

**Where he sits on yards per target, with his neighbours:**

| Rank | Player | Team | Y/T |
|---:|---|---|---:|
| 25 | Evan Engram | DEN | 6.07 |
| 26 | Mark Andrews | BAL | 6.03 |
| **27** | **Jake Ferguson** | **DAL** | **5.88** |
| 28 | Mason Taylor | NYJ | 5.68 |
| 29 | Jonnu Smith | PIT | 4.11 |

**The volume is the part that is squeezable.** Both CeeDee Lamb and George Pickens are Cowboys in 2026, and Lamb played 13 of 17 games last season:

| Player | Games | Targets | Per game |
|---|---:|---:|---:|
| George Pickens | 17 | 137 | 8.1 |
| **CeeDee Lamb** | **13** | 117 | **9.0** |
| Jake Ferguson | 17 | 102 | 6.0 |

Ferguson's 102 targets came with the team's WR1 missing a quarter of the season, so "if Lamb and Pickens stay healthy" is a mechanism rather than a hunch.

**Now the exhibit that argues the other way.** The instinct is that eight touchdowns on 600 yards is luck due to regress downward. The expected-touchdown data says the opposite. Among the 29 tight ends with 50+ targets in 2025:

| Player | TD | Expected TD | Over expected | Rank of 29 |
|---|---:|---:|---:|---:|
| Dallas Goedert | 11 | 5.49 | **+5.51** | 1 |
| Travis Kelce | 5 | 3.86 | +1.14 | 8 |
| Oronde Gadsden II | 3 | 4.21 | −1.21 | 26 |
| **Jake Ferguson** | **8** | **9.24** | **−1.24** | **27** |
| Tyler Warren | 4 | 7.23 | −3.23 | 29 |

He scored 8 on 9.24 expected, **27th of 29**. He was mildly unlucky, not lucky, because the volume put him in scoring position more often than the finish reflected. **A touchdown-regression argument here points up, which weakens the case for TE15 rather than strengthening it.** It was cut from the video for time and it belongs on the record.

## 5. Travis Kelce: the bigger of the two buys

Both projections have him above his TE13 price, at +3. He is the larger of the two positive calls on this board; Stowers at +2 is the other, and section 6 covers him. He finished **TE3 on season total** last year, and on points per game he still comes in at **TE9**.

**The per-game rank depends on the games minimum, so here is the cut.** At a minimum of 8 games, 87 tight ends qualify and he is 9th. Raise the bar to 12 games and he moves to **6th**, because Tucker Kraft (8 games) and Sam LaPorta (9) drop out. He gained six places on the season total purely by playing all 17.

| Rank | Player | Team | Half-PPR / game |
|---:|---|---|---:|
| 7 | Sam LaPorta | DET | 9.7 |
| 8 | Harold Fannin Jr. | CLE | 9.4 |
| **9** | **Travis Kelce** | **KC** | **9.1** |
| 10 | Dalton Kincaid | BUF | 8.9 |
| 11 | Tyler Warren | IND | 8.9 |

The 2025 profile is not a bounce-back projection. He was **4th at the position in targets (108), 4th in receiving yards (851), and 9th of 29 in yards per target (7.88)**. Still a top-four volume tight end at above-average efficiency.

**One number pair needs a gloss or it reads backwards.** My model projects Kelce for **fewer** points than Sleeper (127.0 against 136.4) while ranking him **three spots higher** (TE7 against TE10). That is because my whole tight end board is compressed, not because my model is lower on him.

**Kansas City 2025 targets, with the counter in the same table:**

| Player | Games | Targets | Per game | Share |
|---|---:|---:|---:|---:|
| **Travis Kelce** | 17 | **108** | 6.4 | 19.7% |
| Rashee Rice | **8** | 78 | **9.8** | 14.2% |
| Marquise Brown | 16 | 74 | 4.6 | 13.5% |
| Xavier Worthy | 14 | 73 | 5.2 | 13.3% |

He led Kansas City outright in total targets, which is the support. But Rice played only eight games and led the team comfortably per game, 9.8 to 6.4. **A healthy Rice is the live threat to exactly the volume this call rests on**, and quoting only the total would be picking the flattering denominator.

The rest of the case is age and quarterback health, and the video does not pretend otherwise: he is 37, decline is coming, and the question is how steep it is. The reference to Mahomes coming off an injury is external reporting, not something computed from any artifact here.

## 6. The other three

**Kenyon Sadiq** had a beat written and recorded, then cut for runtime. His college score is **74.3, 26th of 208** in his 2025 cohort. Placed against the distribution of the **318 drafted** tight ends in the college file (scores 50.0 to 99.0, median 67.7), that sits at the **72nd percentile** and **would slot 87th**.

The phrasing there is deliberate. Sadiq is **not one of the 318**: that flag covers players already in the league and he is a 2026 rookie. "Would slot 87th" is honest; "ranks 87th of 318" would not be. The same applies to Stowers.

**Eli Stowers** is the standout of the group on the college instrument and the only other name the consensus likes better than his price. **92.0, 3rd of 208** in his class, and the **97th percentile** of that drafted distribution, better than anyone else in the video.

**Terrance Ferguson** is a −3, in the same direction as the majority.

A note on why the bonus beat separates them rather than grouping them: Terrance Ferguson at −3 and Stowers at +2 point in **opposite directions**. Presenting them as one group and then complimenting one of them reads as contradictory. They are two different calls.

## 7. History at tight end

Same panel as the Guide (drafted top-180, universe A, 2021 to 2025), measured at **the same 2+ bar the video draws**, so the historical rule and the 2026 filter are the same rule:

> **21 of 27 correct, 77.8%.** Wilson 95% interval **[59, 89]**.

For completeness, the neighbouring bars on the same panel: 1+ is 35/51 = 68.6% [55, 80], and 3+ is 13/15 = 86.7% [62, 96]. Cells with fewer than 11 calls are not quoted in this series, and there is such a cell at tight end that looks better than any of these. It stays unquoted for exactly that reason.

**On the chance line beside that rate.** The ~48% benchmark is real, but it is **all-position**. The study ran 48 permutation cells and every one pools all four positions at the 0, 5, 7.5 and 10-spot thresholds. **There is no tight-end cell and no 2+ cell**, so nothing was ever shuffled for the specific calls this video draws. It is a study-wide reference point, not a null computed for these 27 calls.

## 8. What this does not prove

- **A group rate is not a per-player probability.** 21 of 27 describes 27 historical calls. It is not the chance that any of these seven works out, and the interval runs from 59 to 89.
- **Talent Score is descriptive.** The tight end instrument fired dead as a predictor. It sits beside a projection as context and is never an input to one.
- **The 2026 Buffalo share column is an estimate, not a model output.** The model projects points, not targets. The chain used to derive an implied share is written out above so you can disagree with it.
- **Two of the seven have no NFL talent score at all**, so the talent column is silent on the rookies rather than low on them.
- **Two exhibits here argue against the video's own calls**: Gadsden's rookie efficiency and Ferguson's touchdowns-over-expected. Neither was hidden and neither is resolved.
- **Nothing here is live-validated.** These are current disagreements with no outcome.
- **The chance benchmark is not a tight end number.** No permutation null was computed for any single position or for the 2+ bar.
- **Four on-screen glosses are corrected above**: Kelce as "the only" undervalued call, Jake Ferguson as the lowest talent score in the video, "third on that offense" without naming its population, and two non-rookies inside the rookie table. The underlying figures hold in every case; the wording around them did not.

## 9. About the video

The short walks the seven in ADP order, spends its time on Kincaid, Gadsden, Ferguson and Kelce, and closes on the historical cell at the same bar it drew. The running back instalment is next, and by the counts it will have considerably more to work with.

---

*Sources: a dated Sleeper retrieval for ADP and Sleeper's projections, pinned beside the video's package so a daily refresh cannot silently change it; the frozen raw `te_projection_2026.csv` in `fantasy/projections/results/`; `fantasy/talent/nfl_te_score_2026.csv` and `college_te_score_2026.csv` for the talent indices; and nflverse-derived season data for every target, yardage, efficiency and expected-touchdown table. All rank populations are stated with their cohort. The Mahomes injury reference is external reporting, not computed here. This is football analysis, not betting advice.*
