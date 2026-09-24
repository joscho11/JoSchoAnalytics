# Week 1 Signal: How Much Should You Trust It?

*2026 · 2020-2025 draft-board players, split by where they were drafted*

**The one-liner:** Week 1 tells you something real about the rest of a player's season, but how much depends on where he was drafted. For an early pick you already knew most of what week 1 can tell you. For a late pick, week 1 is close to the best new information you will get. This is a study of what happened in six past seasons. It is not a projection.

---

## 1. What "signal score" means

For each player-season I took three numbers: week 1 half-PPR points, rest-of-season half-PPR points per game (weeks 2 onward, so missed time is not scored as bad play), and the prior season's points per game. I fit week 1 and rest-of-season each against the prior season, kept what was left over after that expected relationship (the residual), and correlated the two residuals. That correlation is the **signal score**.

- **0 means week 1 added nothing** beyond last season.
- **Higher means week 1 added real new information.** It is a correlation coefficient, not a percentage.
- A player needed a week 1 game and at least 4 more games that season.
- A prior season had to be a real one (at least 4 games), so I look back past an injury-shortened year to the last qualifying season. Rookies and anyone with no qualifying prior season get the 10th-percentile prior for their position, plus a rookie flag as a second control. Sweeping that fill value from 0 to the veteran median moves every position by under 0.01.

The universe is the same one as the draft board: the top 24 QBs, 60 RBs, 72 WRs and 24 TEs each season by preseason Sleeper half-PPR ADP (180 players a season), 2020-2025. Round buckets use overall pick in a 12-team snake: **R1-3** is picks 1-36, **R4-10** is picks 37-120, **R10+** is pick 121 and later.

---

## 2. The hook: early rounds versus late rounds

Pooled across all four positions:

| Bucket | Signal score | Players | 95% interval |
|---|---|---|---|
| R1-3 | **0.141** | 201 | -0.001 to 0.273 |
| R10+ | **0.305** | 312 | 0.193 to 0.404 |

That is roughly double (2.16x). The early-round interval touches zero at the low end, so that number is genuinely thin. The late-round interval sits clearly above zero. These pooled figures are not in the study's saved tier file. I recomputed them from the study's panel and they reproduce.

---

## 3. Overall, by position

| Position | Players | Signal score | 95% interval | Prior season alone | Week 1 alone |
|---|---|---|---|---|---|
| QB | 137 | **0.241** | 0.068 to 0.411 | 0.43 | 0.29 |
| RB | 304 | **0.272** | 0.155 to 0.374 | 0.57 | 0.47 |
| WR | 385 | **0.266** | 0.183 to 0.348 | 0.56 | 0.31 |
| TE | 130 | **0.289** | 0.128 to 0.444 | 0.53 | 0.32 |

The last two columns are plain correlations with rest-of-season points per game, veterans only (a slightly smaller pool), shown for scale. Two things in the video are rounded against this table. It says all four positions land between 0.26 and 0.29, but QB is 0.24. And "prior season alone about 0.55, week 1 alone about 0.30" are round summaries: by position, prior season runs 0.43 to 0.57, and week 1 alone runs 0.29 to 0.47 (RB is the high one).

---

## 4. By draft round and position

| Position | R1-3 | R4-10 | R10+ |
|---|---|---|---|
| QB | 0.14* (n=18) | **0.19** (n=62) | **0.32** (n=57) |
| RB | 0.07 (n=86) | **0.31** (n=139) | 0.15 (n=79) |
| WR | 0.12 (n=84) | **0.28** (n=181) | 0.20 (n=120) |
| TE | 0.25* (n=13) | **0.31** (n=61) | 0.14 (n=56) |

\* Below the study's own n=25 floor, so I show them as flagged, low-confidence reads. QB R1-3 has a 95% interval of -0.42 to 0.63 and TE R1-3 has -0.37 to 0.78 (only 8 different players). Neither rules out zero. Both were computed separately for the video, which is why the saved tier file leaves them blank.

The three highest cells: **QB R10+ (0.316)**, **RB R4-10 (0.310)**, **TE R4-10 (0.307)**. The weakest WR bucket is the early one, not the late one.

---

## 5. My read

- **Picked in the first three rounds and had a bad week 1:** the data says week 1 adds little on top of what you knew. A tight end is the exception to watch, but that sample is small.
- **Picked in the middle rounds:** this is where week 1 tells you the most, especially at RB, WR and TE. Pay attention to a good or bad week.
- **Picked late:** RB, WR and TE carry some signal, less than the middle rounds but not zero. A late QB carries a lot.

That read is mine. It is a reading of a descriptive study, not a Draft Board output.

---

## 6. Four real examples (illustrations, not evidence)

| Player | ADP | Week 1 | Rest of season (PPG) | Prior season (PPG) |
|---|---|---|---|---|
| Baker Mayfield, 2024 | 178.6 | 29.66 | 20.97 | 16.74 |
| Lamar Jackson, 2023 | 34.2 | 6.56 | 21.64 | 19.67 |
| Cooper Kupp, 2021 | 45.4 | 20.3 | 21.57 | 10.98 |
| Jordan Love, 2023 | 188.7 | 23.0 | 18.50 | n/a |

Love is in there on purpose. A hot week 1 from a late QB does not always turn into Mayfield's season.

---

## 7. What this does not prove

- **That week 1 predicts your player's next month.** This is a correlation across six seasons of board-caliber players, not a trained model and not a guarantee.
- **That it holds in 2026.** Every number is in-sample, 2020-2025. I have not tested how it generalizes forward.
- **That week 1 is special.** I did not compare it against week 2, week 5 or any other single week, so I cannot say it carries more signal than any other week.
- **That the small buckets are reliable.** QB R1-3 and TE R1-3 cannot be distinguished from zero.
- **That the imputed prior is a measurement.** For rookies it is a stable guess (under 0.01 across fill values), not real data.

---

*TikTok id `7686244230284545311`. This is football analysis, not betting advice.*
