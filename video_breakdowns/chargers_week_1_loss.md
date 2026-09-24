# Why the Chargers Struggled in Week 1

*2026 · Week 1, Cardinals 26, Chargers 14*

**The one-liner:** The Chargers were not outplayed on early downs. They kept reaching third down needing double-digit yards, and that is where the game got away from them. One game tells you what happened here. It does not tell you what this team is.

Every number below comes from nflverse 2026 play-by-play for game `2026_01_ARI_LAC`, using run and pass plays that carry an EPA value (120 plays: Arizona 69, Chargers 51). "Garbage time" means win probability under 10% or over 90%, cut the same way for every team. League ranks use all 16 Week 1 games. EPA (expected points added) and win probability are model outputs, not measurements.

---

## 1. The hook: favorites this big rarely lose

Week 1 regular-season games from 1999 to 2025 where the favorite was laid 8.5 points or more (nflverse schedules): **45 games**. The favorite lost outright in **9** of them, exactly **20.0%**. The Chargers opened -8.5 and lost 26-14, so they became the 10th.

| Lost outright as Week 1 favorite | Made the playoffs that year |
|---|---|
| 1999 Seahawks, 2008 Chargers, 2008 Colts, 2018 Saints | Yes (**4 of 9**) |
| 2001 Vikings, 2002 Cowboys, 2003 Dolphins, 2012 Saints, 2016 Cardinals | No |

---

## 2. The number nobody put on the timeline

Average yards to go on third down, Week 1:

| | Avg yards to go | Third downs |
|---|---|---|
| **Chargers** | **12.4** (median 10.5) | 8 |
| Cardinals | 5.5 (median 4) | 13 |

The Chargers' 12.4 is the **longest of any team-game in Week 1** (1st of 32 with at least 5 third downs; league average 7.0; Baltimore is second at 11.6).

Two of those eight third downs came in the fourth quarter with the game already decided (3rd-and-30 at 4.5% win probability, 3rd-and-18 at 0.7%). Take them out and the Chargers averaged **8.5 yards on 6 third downs**. That is still the **5th longest of 29** team-games (Green Bay is longest at 10.7; league average 6.8) and worse than the Chargers' own 2025 season average under the same filter, 6.6.

---

## 3. Early downs were fine

First and second down dropbacks, win probability between 10% and 90%:

| | Dropbacks | EPA per dropback | Success rate |
|---|---|---|---|
| **Chargers** | 20 | **+0.22** | **55.0%** |
| Cardinals | 29 | +0.38 | 62.1% |

The Chargers rank **9th in EPA and 6th in success rate** among teams with at least 10 early-down dropbacks, both above the league average (+0.04 EPA, 47% success). One note on the video: it says "27 teams" and shows a league average of +0.10 and 49%, because the play-by-play file held 15 games when I pulled it. With all 16 games the pool is 29 teams, the average is lower, and the Chargers' ranks (9th and 6th) do not change.

---

## 4. Third and fourth down is where it broke

Same filter, third-down dropbacks and fourth-down dropbacks (going for it):

| | Dropbacks | EPA per dropback | Success rate |
|---|---|---|---|
| **Chargers** | **6** | **-0.85** | **16.7%** |
| Cardinals | 8 | +0.09 | 37.5% |

From early downs (+0.22) to late downs (-0.85) is a **-1.07 swing**, the 4th largest of 26 qualifying teams: Green Bay -1.55, Carolina -1.45, Los Angeles Rams -1.34, Chargers -1.07. Six dropbacks is a small number. Read the rank as a description of this week, not a measure of skill.

---

## 5. What long third downs cost: possessions, not yards

| | Drives | How they ended |
|---|---|---|
| **Chargers** | 10 | 2 touchdowns, 3 punts, **2 turnovers, 3 turnovers on downs** |
| Cardinals | 11 | 2 touchdowns, 4 field goals, 1 missed field goal, 3 punts, 1 end of half |

Five of the Chargers' ten drives ended with Arizona getting the ball back. Arizona had no turnovers and never went for it on fourth down. Time of possession: **Arizona 37:31, Chargers 22:29**. Third-down conversions: Arizona 6 of 13, Chargers 2 of 8, plus 0 of 3 on fourth down.

---

## 6. The blocked punt was the symptom

At 12:28 of the fourth quarter, on 4th-and-11 from their own 19, the Chargers' punt was blocked. Arizona took over at the Chargers' 3 and scored two plays later. Win probability dropped **14.6 percentage points** on that snap, the largest single swing of the game. The play before it was 3rd-and-11, an incomplete pass. The punt was the end of a drive that had already failed on third down.

---

## 7. What the video could not fit: the game-script test

The obvious objection is that the Chargers only looked bad because they were chasing. I tested that four ways, on all run and pass plays (not just dropbacks), EPA per play with the number of plays in parentheses:

| Cut | Cardinals | Chargers |
|---|---|---|
| Win probability 20% to 80% | +0.230 (55) | **-0.142 (38)** |
| Score within 8 points | +0.202 (58) | **-0.199 (35)** |
| First half only | +0.303 (36) | **-0.044 (22)** |
| Through the third quarter | +0.221 (54) | **-0.072 (35)** |

The Chargers are negative in every cut, so "they were just chasing" does not explain it.

---

## 8. Why the McConkey split is not in the video

Ladd McConkey left the game in the third quarter. Chargers dropbacks before that: 19 at +0.22 EPA, 52.6% success. After: 16 at -0.68, 25.0%. It looks like a clean before and after, but the average third-down distance was **6.0 before and 18.8 after**. That split measures down and distance at least as much as it measures his absence, so I did not use it.

---

## 9. What this does not prove

- **That third-and-long caused the loss.** It shows where the offense failed. I did not test what put them into those third downs.
- **That any single play, player or call decided it.** EPA and win probability are model estimates of how the game moved.
- **That the Chargers' offense is broken.** It is 120 plays in one game, and the late-down numbers rest on 6 Chargers dropbacks.
- **That the league ranks are stable.** They are Week 1 superlatives and will move.

---

*TikTok id `7685576445548154142`. This is football analysis, not betting advice.*
