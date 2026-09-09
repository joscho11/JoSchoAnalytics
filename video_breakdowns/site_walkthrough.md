# A walk through the JoScho Analytics site

*2026 · page-by-page tour of joschoanalytics.streamlit.app*

**The one-liner:** Each tab has one job. Draft Board compares Model Proj to ADP. Weekly Fantasy is player-week projections. Weekly Predictions is the betting page, and HIGH is a 2.5-point disagreement with the Tuesday 9am line that still holds. Track Record and Season Totals post the sample and the confidence-interval floor next to the headline. Film Room, League History, and Help sit under More.

Live-page updates since this recording: Draft Board can toggle Sleeper ADP or ESPN ADP. League History loads public and private ESPN leagues, and Yahoo on the live page. Yahoo is not in this video. Weekly Fantasy holdout is now MAE 4.999 vs Sleeper 5.188, rank 0.395 vs 0.402. Starting in 2026, the Tuesday US median drives the pick, edge, and 2.5-point HIGH cut; the best US Tuesday quote is displayed separately and used for grading.

---

## 1. Draft Board and Rookie Board

The 2026 Draft Board stacks Model Proj against published projections and ADP, plus an optional Talent Score that tries to describe talent after stripping opportunity and environment. Talent Score is context, not a ranking input.

On 2021 to 2025, Model Proj beat ADP ordering in **5 of 6** seasons. That is an ordering result, not a guarantee that any one 2026 name is cheap.

Rookie Board shows this year's class plus prior years.

---

## 2. Weekly Fantasy

The 2026 weekly model was scored on a 2025 holdout of **3,060** player-weeks. MAE **4.999** vs Sleeper **5.188**. Rank **0.395** vs Sleeper **0.402**. Point error is a bit better. Ordering is a bit worse. That is a scoring-error comparison, not a start/sit oracle.

---

## 3. Weekly Predictions and Track Record

Every game gets a pick. HIGH means the model disagrees with the Tuesday 9:00 AM EST line by **2.5 or more** points, and the live line still holds that gap. If the gap falls under 2.5, HIGH comes off. Picks freeze Tuesday 9:00 AM EST.

Frozen Tuesday HIGH benchmark, 2021-2025, injury reports as-of Tuesday 9:00 ET, median-triggered and scored at the best US Tuesday number: **302/535**, 56.45% ATS. The conservative end of a 95% interval on that sample is **52.90%**, above the **52.4%** break-even at -110. Starting in 2026, the same median-triggered, shop-graded contract applies. That is Tuesday line value, not closing-line value.

The video may still say an older HIGH sample. The live pages are the book.

---

## 4. Season Totals

HIGH here is **1 or more** wins off the posted number. Historical HIGH: **64/108**, 59.3%. The 95% interval floor is **51.35%**, which is under 52.4%. The page does not claim an edge on posted season win totals.

---

## 5. Film Room, League History, Help

Film Room is the posted shorts plus written breakdowns. League History is a separate walkthrough: load a Sleeper or ESPN league and read its drafts, standings, and luck. Help & Guide answers page questions.

The site URL in the video is joschoanalytics.streamlit.app. Code is on GitHub.

---

## 6. What this does not prove

- **That Model Proj will beat ADP in 2026.** Five of six is the historical ordering record.
- **That HIGH is a lock.** 302/535 is the sample. The floor is 52.90%, above 52.4%. No 2026 games are graded yet.
- **That Season Totals HIGH beats the posted number.** The interval floor is 51.35%.
- **Closing-line value.** Track Record is the Tuesday freeze.
- **Yahoo League History.** That importer is on the live page and is not in this video.

---

*TikTok id `7676601401342037279`. Live Help and Weekly Predictions are the book. This is football analysis, not betting advice.*
