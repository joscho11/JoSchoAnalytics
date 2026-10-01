# NFL Week 4 2026: Model Gaps

*2026 · Week 4 · four HIGH flags vs Tuesday median*

**The one-liner:** Four of sixteen Week 4 games clear a 3-point gap between my model's fair margin and the frozen Tuesday US median. Atlanta is the largest disagreement. Chicago is the home HIGH flag and needs the uncertain-QB caveat on screen. This is a thresholded screen, not four identical cover probabilities.

Every number below comes from the active Week 4 release build `predictions-2026w04-f3e67139da16` (produced 2026-09-29) and the Tuesday snapshot captured 2026-09-29. Live lines can remove a HIGH flag; they cannot mint one after the Tuesday freeze.

---

## 1. What HIGH means this week

A HIGH MODEL FLAG means the absolute gap between the model predicted home margin and the Tuesday US median spread is at least **3.0** points. It is a disagreement flag, not a win probability and not a bet slip.

Through Week 3 of live 2026 grading the video cites: **25-21-2** overall (**54.3%**) and **6 of 10** HIGH. Historical walk-forward HIGH context on the screen: **261/449 (58.13%)**, Wilson lower 95% **54.26%**. Neither sample is a promise about Week 4.

---

## 2. The four HIGH flags

| Matchup | Tuesday median | Model fair | Gap | Model side |
|---|---|---|---|---|
| ATL @ NO | ATL +2.5 | ATL −2.0 | **4.5** | ATL |
| NYJ @ CHI | CHI −3.5 | CHI −7.6 | **4.1** | CHI |
| DEN @ SF | DEN +3.0 | DEN −0.5 | **3.5** | DEN |
| DAL @ HOU | DAL +2.5 | DAL −0.6 | **3.1** | DAL |

Near misses left muted on the slate: KC @ LV (2.9) and ARI @ NYG (2.7).

---

## 3. Atlanta: largest gap, price skew on both plates

Absolute top input: **spread price skew** (uneven juice on each side of the same line), about **−1.17** toward Atlanta. Versus the Week 4 slate median, that same feature is also the most unusual input for this game.

Extra rest for Atlanta (Thursday Week 3 into Monday Night Week 4) shows up as `rest_off_bye_away` in the model. That flag is a **10+ day rest proxy**, not a scheduled bye week. No team has had a real bye yet.

---

## 4. Chicago: home HIGH with an uncertain-QB caveat

Model side is **CHI**. Tuesday CHI −3.5 versus model fair about CHI −7.6.

The largest absolute contribution is the disclosed **home QB uncertain** flag (**+1.53**). That is a fixed model weight for an unsettled situation, not a claim that uncertainty makes Chicago better. Without the prior-build context the video notes, this game stayed under HIGH; the stronger separate point is that listed QB paths (Bagent, Keenum, Caleb) still clear.

---

## 5. Denver: IR moves the number; slate-relative top fights it

Absolute top: **IR starters gap**, about **−1.48** toward Denver (San Francisco carrying more projected starters on IR).

Slate-relative top is different: **home QB downgrade** for San Francisco, which pushes toward the 49ers. So the number is mostly IR; what stands out on the slate is the QB bar fighting it. Classification used the frozen Tuesday file.

---

## 6. Dallas: top bar against the model side

Model side is **DAL** with a **3.1** gap. The single largest absolute input fights that side: **rush defense EPA**, about **+0.90** toward Houston. The largest input in Dallas's favor is **spread price skew**, about **−0.84**. Net of everything, Dallas still clears HIGH.

---

## 7. What this does not prove

- HIGH is a **gap threshold**, not four identical cover chances. Gaps run **3.1 to 4.5**.
- Feature bars **explain the output**; they are not causal claims.
- Live line movement after Tuesday can change whether a game still looks HIGH on render day.
- Live 2026 and the historical HIGH walk-forward are context, not a Week 4 guarantee.

---

*TikTok id `7691810928202894623`. Educational model analysis, not betting advice.*
