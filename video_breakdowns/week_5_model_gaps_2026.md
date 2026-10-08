# NFL Week 5 2026: Model Gaps

*2026 · Week 5 · five HIGH flags vs Tuesday median*

**The one-liner:** Five of fifteen Week 5 games clear a 3-point gap between my model's fair margin and the frozen Tuesday US median. Indianapolis is the largest disagreement. Atlanta clears HIGH only under a Tyler Huntley input; with Lamar Jackson the gap falls below the bar. This is a thresholded screen, not five identical cover probabilities.

Every number below comes from the active Week 5 release build `predictions-2026w05-e6902ce4fb32` (produced 2026-10-06) and the Tuesday snapshot captured 2026-10-06 at 08:55 ET. Live lines can remove a HIGH flag; they cannot mint one after the Tuesday freeze.

---

## 1. What HIGH means this week

A HIGH MODEL FLAG means the absolute gap between the model predicted home margin and the Tuesday US median spread is at least **3.0** points. It is a disagreement flag, not a win probability and not a bet slip.

The video's Week 4 HIGH recap is **3 of 4**, with a 95% Wilson interval of **30%–95%**. Four games from one week is highly uncertain and is not a stable rate.

---

## 2. The five HIGH flags

| Matchup | Tuesday median | Model fair | Gap | Model side |
|---|---|---|---|---|
| IND @ PIT | IND +2.5 | IND −2.2 | **4.7** | IND |
| BUF @ LAR | BUF +2.75 | BUF −1.3 | **4.1** | BUF |
| BAL @ ATL | ATL +2.5 | ATL −1.4 | **3.9** | ATL |
| DEN @ LAC | DEN −3.5 | DEN −7.0 | **3.5** | DEN |
| CIN @ MIA | CIN −7.0 | CIN −10.1 | **3.1** | CIN |

Atlanta's 3.9 gap is the Huntley scenario. With Lamar Jackson the gap is **2.50**, Atlanta remains the model side, and the game falls below HIGH.

---

## 3. Indianapolis: largest gap

Model side is **IND**. Tuesday IND +2.5 versus model fair about IND −2.2.

Absolute top inputs: **new-coach gap** (about **−0.89**) and **moneyline vs spread** (about **−0.86**). Both also stand out against the 15-game Week 5 median.

---

## 4. Buffalo at the Rams

Model side is **BUF**. Tuesday BUF +2.75 versus model fair about BUF −1.3. Gap **4.1**.

Absolute top inputs: **rating history** (about **−1.18**) and **IR starters** (about **−0.99**). Those same features sit unusually high versus the rest of the slate.

---

## 5. Atlanta: HIGH only if Huntley is the input

Model side is **ATL** in both quarterback scenarios. The HIGH label is not.

| Baltimore QB input | Gap | Qualification |
|---|---|---|
| Tyler Huntley | **3.92** | HIGH |
| Lamar Jackson | **2.50** | Atlanta side, below HIGH |

This is a user-set quarterback input, not a confirmed starter. If the number you can get is not the Tuesday median shown here, leave the flag alone.

Under the Huntley run, the largest absolute inputs are **away QB uncertain** (about **+1.61**) and **away QB downgrade** (about **+1.52**).

---

## 6. Denver: current spread fights the model side

Model side is **DEN**. Tuesday DEN −3.5 versus model fair about DEN −7.0. Gap **3.5**.

The largest absolute input fights that side: **current spread**, about **+1.58** toward Los Angeles. **Moneyline vs spread** (about **−1.15**) and **combined pass protection** (about **−1.01**) pull toward Denver. Net of everything, Denver still clears HIGH.

---

## 7. Cincinnati: moneyline vs spread dominates

Model side is **CIN**. Tuesday CIN −7.0 versus model fair about CIN −10.1. Gap **3.1**.

The single largest absolute input on the slate is here: **moneyline vs spread**, about **−3.35** toward Cincinnati. Win odds imply a different spread than the posted line. **Current spread** (about **+2.69**) offsets part of that move. Net still clears HIGH.

---

## 8. What this does not prove

- HIGH is a **gap threshold**, not five identical cover chances. Gaps run **3.1 to 4.7**.
- Feature bars **explain the output**; they are not causal claims.
- Atlanta's HIGH flag depends on the Huntley input. Lamar starting drops it below the bar.
- Live line movement after Tuesday can change whether a game still looks HIGH on render day.
- The Week 4 3-of-4 recap is a four-game sample with a wide interval, not a Week 5 guarantee.

---

*TikTok id `7694038078754671902`. Educational model analysis, not betting advice.*
