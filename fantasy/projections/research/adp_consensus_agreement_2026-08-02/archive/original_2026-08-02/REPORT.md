# Current model + Sleeper agreeing against ADP — does the player finish on the predicted side?

**Descriptive post-hoc research, run 2026-08-02. NOT pre-registered. NOT live-validated.**
No threshold was selected after seeing results — the grid `{0, >5, >7.5, >10}` was fixed by the
request and every cell at every threshold is reported, including the ones that fail.

Reproduce with `adp_consensus_experiment.ipynb`. Inputs, hashes and diagnostics: `manifest.json`.

---

## Verdict

**Three findings, in descending order of confidence.**

1. **The headline number is an artifact and must not be quoted.** Over the full ADP-bearing model
   population the agreement cell hits 79.9% at threshold 0 and 92.3% at `>10` (2024–2025). That
   population's agreement rows have a **median overall ADP of 634** — players nobody drafts. The
   effect is both projections correctly ordering the noise floor below the draftable range, not
   beating a market price. The largest "hits" are Tai Felton (4.0 half-PPR points), David Moore
   (2.2), DeAndre Carter (0.0), Jason Brownlee (0.0).

2. **On the actually-drafted board the pattern survives, but much smaller and on few calls.**
   Restricted to `adp_overall_rank <= 180` (the repo's `phase0_benchmark.POOL_SIZE` draftable
   universe), pooled 2024–2025: **66.1%** at threshold 0 (n=162) rising to **85.0%** (n=40),
   **93.1%** (n=29) and **100%** (n=15) at `>5`, `>7.5`, `>10`. The empirical permutation null sits
   at 48–50% at every threshold and p = 0.0001 throughout. The high-threshold cells are ~20 and ~7
   calls per season respectively.

3. **The incremental claim over Sleeper alone is NOT established.** This is the claim that matters —
   whether our model's agreement adds anything to a projection Sleeper already publishes. On the
   drafted board over the full **2021–2025** panel the lift over Sleeper-calls-where-the-model-does-
   not-agree is **+0.068 [−0.028, +0.162]** at `>5`, **+0.073 [−0.028, +0.172]** at `>7.5` and
   **+0.035 [−0.095, +0.156]** at `>10` — every interval crosses zero. The shorter 2023–2025 and
   2024–2025 panels do show a positive lift, but they are subsets of the panel that does not.

**Read plainly: the agreement cell picks the right side of ADP well above chance, but on the drafted
board we cannot show that our model's agreement adds anything to Sleeper's projection on its own.**
The lift over *our model alone* is large and stable (+0.21 to +0.48) — that is the weak direction of
the claim, and it is what you would expect given the model does not beat Sleeper at any position.

---

## Primary table — pooled 2024–2025, both rank universes

Universe **A** = board analogue (rank over the ADP-bearing model population; a missing Sleeper
projection keeps a missing Sleeper rank). Universe **B** = common universe (restrict to complete rows
first, then re-rank). `>7.5` means at least 8 rank spots, since ranks are integers.

### Full ADP-bearing population — inflated, do not quote

| Threshold | Universe | n | hits | misses | ties | hit rate | Wilson 95% | median ADP |
|---|---|---|---|---|---|---|---|---|
| 0 | A | 512 | 409 | 97 | 6 | **79.9%** | 76.2–83.1% | 459.6 |
| >5 | A | 338 | 300 | 37 | 1 | **88.8%** | 84.9–91.7% | 634.3 |
| >7.5 | A | 307 | 277 | 29 | 1 | **90.2%** | 86.4–93.1% | 640.7 |
| >10 | A | 259 | 239 | 19 | 1 | **92.3%** | 88.4–95.0% | 652.0 |
| 0 | B | 509 | 395 | 108 | 6 | **77.6%** | 73.8–81.0% | 451.1 |
| >5 | B | 321 | 274 | 46 | 1 | **85.4%** | 81.1–88.8% | 617.4 |
| >7.5 | B | 276 | 240 | 35 | 1 | **87.0%** | 82.5–90.4% | 624.3 |
| >10 | B | 231 | 205 | 25 | 1 | **88.7%** | 84.0–92.2% | 640.7 |

### Drafted board (`adp_overall_rank <= 180`) — the decision-relevant panel

| Threshold | Universe | n | hits | misses | ties | hit rate | Wilson 95% | median ADP |
|---|---|---|---|---|---|---|---|---|
| 0 | A | 162 | 107 | 48 | 7 | **66.1%** | 58.5–72.9% | 97.5 |
| >5 | A | 40 | 34 | 5 | 1 | **85.0%** | 70.9–92.9% | 122.7 |
| >7.5 | A | 29 | 27 | 2 | 0 | **93.1%** | 78.0–98.1% | 130.6 |
| >10 | A | 15 | 15 | 0 | 0 | **100%** | 79.6–100% | 130.6 |
| 0 | B | 161 | 106 | 49 | 6 | **65.8%** | 58.2–72.7% | 97.4 |
| >5 | B | 39 | 34 | 4 | 1 | **87.2%** | 73.3–94.4% | 120.0 |
| >7.5 | B | 28 | 26 | 2 | 0 | **92.9%** | 77.4–98.0% | 128.0 |
| >10 | B | 14 | 14 | 0 | 0 | **100%** | 78.5–100% | 128.0 |

**No conclusion changes between universe A and universe B.** The result is not population-sensitive
along that axis. It *is* violently sensitive along the drafted/undrafted axis, which is why both
populations are carried through every table in `threshold_summary.csv`.

---

## Stability panels

Universe A, agreement cell hit rate. `n<10` cells are flagged in the CSV and carry no conclusion.

| Panel | Population | t=0 | t>5 | t>7.5 | t>10 |
|---|---|---|---|---|---|
| 2024–2025 | all ADP | 79.9% (512) | 88.8% (338) | 90.2% (307) | 92.3% (259) |
| 2023–2025 | all ADP | 78.0% (655) | 88.0% (392) | 90.2% (338) | 92.5% (281) |
| 2021–2025 | all ADP | 76.8% (940) | 85.7% (516) | 88.2% (422) | 91.2% (331) |
| 2024–2025 | drafted 180 | 66.1% (162) | 85.0% (40) | 93.1% (29) | 100% (15) |
| 2023–2025 | drafted 180 | 67.2% (241) | 86.4% (59) | 92.5% (40) | 100% (19) |
| 2021–2025 | drafted 180 | 72.2% (410) | 83.8% (105) | 88.6% (70) | 89.2% (37) |

**Per season, drafted board, t=0:** 2021 83.5% (79), 2022 75.6% (90), 2023 69.6% (79), 2024 74.4%
(86), **2025 56.6% (76), Wilson 45.4–67.1% — includes 50%.** The threshold-0 signal is not stable
season to season, and the most recent season is its weakest. Higher thresholds are 3–13 calls per
season on this population: too small to read individually.

---

## Incremental comparisons

### Against the empirical permutation null

`actual_gap` permuted within season-position 10,000 times, signals/thresholds/cell sizes held fixed.
The null mean lands at **0.48–0.51** and its 95th percentile at 0.52–0.73 in every cell — so the 50%
visual reference is approximately right, and it is not an artifact of ties or direction imbalance.
**p = 0.0001 (the resolution floor of 10,000 draws) at every threshold in every panel and
population**, including the drafted board.

### Against non-agreement — the comparison that decides the claim

Stratified bootstrap (season-position), 10,000 resamples, universe A.

**Drafted board:**

| Panel | t | agree | model calls w/o agreement | lift vs model-alone [95%] | Sleeper calls w/o agreement | lift vs Sleeper-alone [95%] |
|---|---|---|---|---|---|---|
| 2024–2025 | 0 | 66.1% | 44.6% (168) | +0.214 [+0.111, +0.316] | 58.3% (151) | +0.078 [**−0.027**, +0.187] |
| 2024–2025 | >5 | 85.0% | 51.8% (141) | +0.332 [+0.192, +0.467] | 69.7% (66) | +0.153 [**−0.004**, +0.311] |
| 2024–2025 | >7.5 | 93.1% | 50.5% (109) | +0.426 [+0.287, +0.552] | 75.0% (48) | +0.181 [+0.026, +0.333] |
| 2024–2025 | >10 | 100% | 52.0% (75) | +0.480 [+0.367, +0.590] | 73.1% (26) | +0.269 [+0.107, +0.450] |
| 2021–2025 | 0 | 72.2% | 43.9% (408) | +0.283 [+0.219, +0.346] | 59.5% (358) | +0.127 [+0.061, +0.193] |
| 2021–2025 | >5 | 83.8% | 55.7% (354) | +0.282 [+0.194, +0.366] | 77.0% (161) | +0.068 [**−0.028**, +0.162] |
| 2021–2025 | >7.5 | 88.6% | 55.1% (285) | +0.335 [+0.237, +0.425] | 81.3% (128) | +0.073 [**−0.028**, +0.172] |
| 2021–2025 | >10 | 89.2% | 58.6% (191) | +0.306 [+0.177, +0.419] | 85.7% (77) | +0.035 [**−0.095**, +0.156] |

On the largest, longest drafted panel the lift over Sleeper alone is indistinguishable from zero at
every threshold above 0. On the full ADP-bearing population the same lift is positive with intervals
clear of zero (+0.099 to +0.216) — but that population is the one contaminated by undrafted rows.

**No independence between the two systems is claimed anywhere.** Sleeper's projection is public and
our model trains on overlapping information; the comparators above are descriptive contrasts, not a
test of two independent signals.

### Descriptive logistic

Outcome = the model's directional call is correct; predictors `agree`, `|model_gap|`,
`|sleeper_gap|`, position, season. Universe B, 2024–2025. Converged, no separation.

| Population | n | pseudo-R² | `agree` coef | SE | p | `abs_model_gap` | `abs_sleeper_gap` |
|---|---|---|---|---|---|---|---|
| all ADP | 783 | 0.134 | **+1.432** | 0.171 | <1e-15 | +0.025 (p=0.0003) | +0.007 (p=0.35) |
| drafted 180 | 289 | 0.074 | **+1.128** | 0.253 | <1e-5 | +0.040 (p=0.041) | −0.014 (p=0.60) |

Agreement carries information beyond gap magnitude, on both populations. Note what this does and
does not say: the outcome is *our model's* call being right, so it confirms that Sleeper's agreement
improves our model — the same weak direction as the model-alone comparator. It is not evidence that
our model improves Sleeper.

---

## Freshness confound — and the dated-market check

`PREREGISTRATION.md`, *SLEEPER FRESHNESS ASYMMETRY*: the stored Sleeper projection is a week-1-eve
snapshot; Sleeper ADP is a late-frozen summer aggregate with no timestamp. An unknown share of any
positive result is late news (camp injuries, depth-chart decisions) that entered the projection after
part of the ADP sample had already drafted.

**The primary result above is therefore a late-draft, board-analogue signal, not pure forecast
skill.** It describes what a drafter holding a same-day projection snapshot could have seen against a
summer-average price — not a forecast made at the time the market formed.

**Secondary check — final dated Underdog window.** Reconstructed offline from the sha256-manifested
Underdog best-ball dumps `h11_freshness_signal.py` already stages (W10, or W9 for 2024), joined by
normalized name + position at **99.5% coverage on the drafted range**. Nothing was written back to
any research artifact and no network was used. Kept separate: **Underdog best ball is a different
format from Sleeper half-PPR redraft**, so this is a directional robustness reading, not a
substitute result.

| Population | t | vs Sleeper ADP | vs dated Underdog | n (UD) |
|---|---|---|---|---|
| all ADP | 0 | 79.9% | 73.2% | 451 |
| all ADP | >5 | 88.8% | 81.2% | 245 |
| all ADP | >7.5 | 90.2% | 84.3% | 204 |
| all ADP | >10 | 92.3% | 86.5% | 163 |
| drafted 180 | 0 | 66.1% | 62.8% | 172 |
| drafted 180 | >5 | 85.0% | 75.5% | 49 |
| drafted 180 | >7.5 | 93.1% | 86.7% | 30 |
| drafted 180 | >10 | 100% | 76.9% (n=13) | 13 |

The signal **attenuates against the contemporaneous market at every threshold but does not vanish**.
That is consistent with freshness contributing part — not all — of the measured edge. The cells are
too small to size the freshness share, and no attempt is made to.

---

## Audit rows — drafted board, 2024–2025, `>5` (usable examples)

Read these, not the `all_adp` table, for any content use.

**Hits, buy side:** Chuba Hubbard (ADP RB43 → finished RB15, 220.1), Jakobi Meyers (WR55 → WR23,
174.5), Josh Downs (WR66 → WR34, 147.5), Rico Dowdle (RB58 → RB17, 196.8), Bucky Irving (RB59 →
RB14, 220.9), Tyler Allgeier (RB53 → RB35, 116.0), Michael Wilson (WR73 → WR49, 101.0).

**Hits, fade side:** Marquise Brown (WR41 → WR73, 13.6), Zamir White (RB24 → RB55, 26.3), Deebo
Samuel Sr. (WR14 → WR40, 130.1), Christian Kirk (WR31 → WR62, 57.4), Anthony Richardson (QB6 → QB17,
162.9), Rome Odunze (WR33 → WR43, 117.9).

**Misses:** Chris Godwin Jr. (buy WR36 → WR47; season-ending ankle in week 7), Garrett Wilson (buy
WR18 → WR48), Jahmyr Gibbs (fade RB4 → RB2, 336.9), Xavier Worthy (fade WR35 → WR32), Gabe Davis
(buy WR61 → WR69).

The miss list is instructive: the two largest are availability shocks and an elite player the model
is structurally conservative on — both known limitations, not new ones.

---

## Limitations

- **Post-hoc and descriptive.** Not pre-registered, no accept/reject gate, no one-shot discipline.
  Every number here is a measurement of a fixed historical panel, not a validated product claim.
- **The drafted/undrafted split is doing most of the work.** Any figure quoted from the full
  ADP-bearing population is dominated by players at ADP 400–700 whose season totals are near zero.
- **Small cells above threshold 0 on the drafted board.** 40 calls at `>5`, 29 at `>7.5`, 15 at `>10`
  across two full seasons. The 100% cells are 15 and 14 rows.
- **Not stable across seasons.** Drafted-board t=0 runs 83.5% (2021) down to 56.6% (2025).
- **The incremental claim over Sleeper alone fails on the longest panel.** See the table above.
- **Freshness is not controlled in the primary result**, only probed by the Underdog secondary.
- **Both systems' walk-forward predictions come from models that do not beat Sleeper** at any
  position (RB ρ +0.689, WR +0.736, TE +0.734, QB +0.695; Sleeper better in every case). Nothing here
  revises that.
- **Sleeper coverage differs by vintage.** 19 rows carry a Sleeper projection in the current
  `season_dataset_2014_2025.csv` (rebuilt 2026-07-26) that was absent when the walk-forward files
  were written (2026-07-21). The walk-forward `sleeper` column is used throughout; those 19 rows
  therefore drop out of signal evaluation. Recorded in `manifest.json`.
- **Stored `adp_pos_rank` is not used.** It is joined verbatim from an external ADP source ranked
  over that source's own universe (a superset of both the season dataset and the model population),
  so it is not reconstructible here — 917 of 1,883 rows match a within-model-population
  reconstruction. Every rank in this study is rebuilt inside the stated population.

---

## Video-safe claim language

**Safe to say:**

- "Backtested over the 2021–2025 seasons, when my model and Sleeper both ranked a drafted player at
  least 8 spots away from his ADP in the same direction, he finished on that side about 89% of the
  time — on 70 calls across five years."
- "That's a late-draft signal: Sleeper's projection is a week-1-eve snapshot and ADP is a summer
  average, so part of it is news the market hadn't fully priced."
- "Against a contemporaneous dated market it's weaker but still there."
- "It's backtested, not live-validated. The first live test is the end of 2026."
- "Where the two disagree with each other, there's nothing to read."

**Not safe to say — every one of these is contradicted by the numbers above:**

- ~~"My model beats ADP"~~ / ~~"beats Sleeper"~~ — it beats neither; agreement is a joint filter, and
  the model loses to Sleeper at all four positions.
- ~~"90% hit rate"~~ without naming the drafted-board restriction and the call count. The 90%+ figures
  from the full population are an undrafted-tail artifact.
- ~~"100% at 10+ spots"~~ — that is 15 rows in two seasons.
- ~~"Adds signal on top of Sleeper"~~ — not established; the CI crosses zero on the five-season
  drafted panel.
- Any per-player buy/fade/steal/reach/bust call, tier name, or projected hit rate for a 2026 player.
  Nothing here validates a player-level call, and no 2026 outcomes exist.

---

## Files

| File | Contents |
|---|---|
| `adp_consensus_experiment.ipynb` | Full reproducible analysis with inline assertions |
| `threshold_summary.csv` | 1,346 rows — every market, population, universe, panel, threshold, and split (all / direction / position / season / veteran-rookie) |
| `player_season_results.csv` | 5,315 row-level records: every rank, gap, eligibility flag and outcome for both populations and both universes |
| `incremental_comparisons.csv` | Permutation nulls and bootstrap lifts for all comparators |
| `manifest.json` | Input paths, SHA-256 hashes, row counts, join diagnostics, definitions, logistic fits, run timestamp |

Integrity checks that would have failed the run: duplicate walk-forward keys, failed joins, position
disagreement, a test season outside 2021–2025, a surviving QB rookie row, a cross-position rank, a
summary cell not reconstructible from the row-level frame, or any source artifact changing mid-run.
All passed.
