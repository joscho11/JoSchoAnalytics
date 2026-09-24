# RB Advanced Stat Leaders, Weeks 1-2: Part 1

*2026 · Weeks 1-2 · running backs, 5 of 8 advanced stats*

**The one-liner:** The top 10 running backs through two weeks on five advanced stats. These are two-game numbers built from public data, and three of the five boards (yards after contact, yards before contact, and "vs. 8+ in the box") are the same ranking in different units. Read them as a snapshot of two weeks, not a verdict on anyone.

Part 2 covers the other three stats (route share, target share, yards before contact). The badge in Part 2 continues this numbering, so this part is RB 1/8 to RB 5/8.

---

## 1. How the boards are built

- **Source:** nflverse 2026 play-by-play through Week 2 (all 32 games: 16 in Week 1, 16 in Week 2), plus public snap counts. Snapshot taken 2026-09-22.
- **Garbage time:** every play is dropped when either team's win probability is above 90% before the snap. The same rule applies to every stat.
- **Rates come from summed counts.** I add each player's numerators and denominators across both weeks, then divide. I do not average the two weekly rates.
- **Sorting** uses the unrounded value. Ties go to the larger sample, then to the name.
- **Minimums:** 8 rush attempts for the four rushing boards, 20 route-proxy snaps for the receiving one.

Most of these are public approximations of stats that normally need tracking data. Each one is labeled on screen as a public approximation.

---

## 2. Yards after contact per attempt

Proxy yards after contact is set to 60% of a player's rushing yards, divided by rush attempts. The public feed has no tackle-point data, so this is not true yards after contact.

| Rank | Player | Team | Yards After Contact / Attempt | Sample |
|---|---|---|---|---|
| 1 | Kyle Monangai | CHI | **4.80** | 14 rush attempts |
| 2 | Kenneth Walker III | KC | **3.86** | 42 rush attempts |
| 3 | TreVeyon Henderson | NE | **3.65** | 12 rush attempts |
| 4 | Bucky Irving | TB | **3.32** | 24 rush attempts |
| 5 | Blake Corum | LA | **3.32** | 13 rush attempts |
| 6 | Jahmyr Gibbs | DET | **3.30** | 34 rush attempts |
| 7 | Christian McCaffrey | SF | **3.21** | 14 rush attempts |
| 8 | Tyjae Spears | TEN | **3.15** | 8 rush attempts |
| 9 | James Cook | BUF | **3.13** | 23 rush attempts |
| 10 | Bhayshul Tuten | JAX | **2.96** | 15 rush attempts |

---

## 3. Missed tackles forced per attempt

The proxy counts rushes of 10 or more yards and divides by attempts. It is a big-play rate, not a count of missed tackles.

| Rank | Player | Team | Missed Tackles Forced / Attempt | Sample |
|---|---|---|---|---|
| 1 | Kaleb Johnson | GB | **0.25** | 2 MTF proxy / 8 attempts |
| 2 | Jahmyr Gibbs | DET | **0.24** | 8 MTF proxy / 34 attempts |
| 3 | Blake Corum | LA | **0.23** | 3 MTF proxy / 13 attempts |
| 4 | James Cook | BUF | **0.22** | 5 MTF proxy / 23 attempts |
| 5 | Kyle Monangai | CHI | **0.21** | 3 MTF proxy / 14 attempts |
| 6 | Jadarian Price | SEA | **0.17** | 4 MTF proxy / 23 attempts |
| 7 | TreVeyon Henderson | NE | **0.17** | 2 MTF proxy / 12 attempts |
| 8 | Kenneth Walker III | KC | **0.14** | 6 MTF proxy / 42 attempts |
| 9 | Christian McCaffrey | SF | **0.14** | 2 MTF proxy / 14 attempts |
| 10 | Bhayshul Tuten | JAX | **0.13** | 2 MTF proxy / 15 attempts |

---

## 4. Rushing success rate

A rush is a success if it gains 40% of the yards to go on first down, 60% on second down, or all of it on third and fourth down.

| Rank | Player | Team | Rushing Success Rate | Sample |
|---|---|---|---|---|
| 1 | Christian McCaffrey | SF | **78.6%** | 11 successful rushes / 14 attempts |
| 2 | Kaelon Black | SF | **75.0%** | 9 successful rushes / 12 attempts |
| 3 | Derrick Henry | BAL | **72.0%** | 18 successful rushes / 25 attempts |
| 4 | Rachaad White | WAS | **64.3%** | 9 successful rushes / 14 attempts |
| 5 | Braelon Allen | NYJ | **63.6%** | 7 successful rushes / 11 attempts |
| 6 | Bucky Irving | TB | **62.5%** | 15 successful rushes / 24 attempts |
| 7 | Jahmyr Gibbs | DET | **61.8%** | 21 successful rushes / 34 attempts |
| 8 | Blake Corum | LA | **61.5%** | 8 successful rushes / 13 attempts |
| 9 | Kyren Williams | LA | **61.5%** | 8 successful rushes / 13 attempts |
| 10 | Chuba Hubbard | CAR | **60.0%** | 9 successful rushes / 15 attempts |

---

## 5. Yards per carry against 8+ in the box

Defender box counts are not in the public play-by-play, so this board is **all-carry yards per carry**. It does not isolate carries against stacked boxes.

| Rank | Player | Team | YPC vs. 8+ in the box | Sample |
|---|---|---|---|---|
| 1 | Kyle Monangai | CHI | **8.00** | 14 carries · all-carry box proxy |
| 2 | Kenneth Walker III | KC | **6.43** | 42 carries · all-carry box proxy |
| 3 | TreVeyon Henderson | NE | **6.08** | 12 carries · all-carry box proxy |
| 4 | Bucky Irving | TB | **5.54** | 24 carries · all-carry box proxy |
| 5 | Blake Corum | LA | **5.54** | 13 carries · all-carry box proxy |
| 6 | Jahmyr Gibbs | DET | **5.50** | 34 carries · all-carry box proxy |
| 7 | Christian McCaffrey | SF | **5.36** | 14 carries · all-carry box proxy |
| 8 | Tyjae Spears | TEN | **5.25** | 8 carries · all-carry box proxy |
| 9 | James Cook | BUF | **5.22** | 23 carries · all-carry box proxy |
| 10 | Bhayshul Tuten | JAX | **4.93** | 15 carries · all-carry box proxy |

---

## 6. Yards per route run

Receiving yards divided by a route proxy: a player's offensive snaps, scaled to the team's pass plays that survived the garbage-time filter. Public snap counts are weekly totals, not play-level route data.

| Rank | Player | Team | YPRR | Sample |
|---|---|---|---|---|
| 1 | Bijan Robinson | ATL | **3.59** | 27.5 route-proxy snaps |
| 2 | Christian McCaffrey | SF | **2.52** | 21.8 route-proxy snaps |
| 3 | Breece Hall | NYJ | **2.06** | 38.4 route-proxy snaps |
| 4 | Derrick Henry | BAL | **1.68** | 22.6 route-proxy snaps |
| 5 | De'Von Achane | MIA | **1.59** | 25.2 route-proxy snaps |
| 6 | D'Andre Swift | CHI | **1.55** | 41.3 route-proxy snaps |
| 7 | Kyren Williams | LA | **1.55** | 20.6 route-proxy snaps |
| 8 | Kyle Monangai | CHI | **1.44** | 24.3 route-proxy snaps |
| 9 | Kenneth Walker III | KC | **1.42** | 54.0 route-proxy snaps |
| 10 | Jahmyr Gibbs | DET | **1.32** | 31.1 route-proxy snaps |

---

## 7. Three boards are one list

Boards 2, 5 and (in Part 2) yards before contact use the same ingredient. Proxy yards after contact is 60% of rushing yards per carry, and proxy yards before contact is the other 40%. So those boards rank the same ten backs in the same order, and only the unit changes. That is why Kyle Monangai, Kenneth Walker and TreVeyon Henderson lead all three. Of the five boards in this part, that leaves four distinct signals: yards per carry, big-play rate, success rate and yards per route.

---

## 8. What this does not prove

- **That any of these backs is good or bad.** Two games is a small sample. The top of several boards sits on 8 to 14 carries.
- **That the proxies match the real stats.** Yards after contact, missed tackles forced and box counts are approximated from public data. Tracking-based versions would rank some of these backs differently.
- **That the list carries forward.** These are cumulative through Week 2. They are not projections.
- **That the garbage-time filter is neutral for every back.** It removes plays from lopsided games, which can help or hurt a given player.

---

*TikTok id `7688512676288318750`. This is football analysis, not betting advice.*
