# PREREGISTRATION — NFL Team Season Win Totals (`futures/`)

**Status:** OPEN — written before any model was fitted. Nothing in this directory has been
fitted, tuned, or evaluated at the time this document was committed.
**Author:** Joseph Schoenbaum · **Written:** 2026-08-02
**Governs:** every notebook in `futures/season_team_totals/`, the artifact `futures/futures_predictions.csv`, and
the live page `site_pages/page_futures.py`.

This document is the constitution for the subproject. Where it and a notebook disagree, this
document wins. Amendments are numbered, dated, and appended to §10 — never edited in place, and
never written after seeing the number they would change.

---

## 1. The question

For each NFL team and each regular season, the sportsbook posts a **preseason season win total**
— a number of wins with an OVER and an UNDER price, published before Week 1 and settled on the
team's regular-season win count. The question:

> Can a model built only from information available before Week 1 predict a team's
> regular-season win count **more accurately than the preseason sportsbook win-total line**?

The market line is the benchmark, not a feature to be beaten in the abstract. A model that
predicts wins well but no better than the line has produced a *descriptive* projection, not an
edge, and must be labelled that way.

**Secondary question (only if §7 gates open):** does the model's simulated win *distribution*
produce calibrated OVER/UNDER probabilities against the posted line and price?

---

## 2. Data contract

### 2.1 Outcome (the target)

`wins` — regular-season wins for one team in one season.

* Source: `nflreadpy.load_schedules()`, `game_type == "REG"`, games with a non-null `result`.
* A game counts for the home team if `result > 0`, for the away team if `result < 0`.
* **Ties.** Books settle NFL season win totals with a tie counting as **half a win**
  (the near-universal convention; a 9-6-1 team grades as 9.5). The canonical target is therefore
  `wins_half_ties = wins + 0.5 * ties`. A strict `wins` column is carried alongside so any book
  whose rules differ can be re-graded without rebuilding the dataset. **Every headline metric in
  this preregistration is computed on `wins_half_ties`.**
* **Season length is not constant.** 2002–2020 are 16-game seasons; 2021+ are 17. 2022 BUF/CIN
  played 16 (cancelled game, never made up). The dataset carries `games_played` per team-season
  and no metric may assume a fixed denominator.
* **Cancelled/forfeited games are counted as played only if `result` is non-null.** No
  reconstruction, no forfeited-win imputation.

### 2.2 Market line (the benchmark)

Required schema for any win-total line file (`futures/data/win_totals.csv`, or the path in
`FUTURES_LINES_PATH`):

| column | type | meaning |
|---|---|---|
| `season` | int | season the total settles on |
| `team` | str | nflverse team abbreviation (post-relocation, e.g. `LV`, `LAC`, `LA`) |
| `win_total_line` | float | the posted number (halves and integers both legal) |
| `price_over` | int | American odds on OVER (e.g. `-115`) |
| `price_under` | int | American odds on UNDER |
| `book` | str | the sportsbook the number came from |
| `as_of_date` | date | when the number was observed |
| `source` | str | where the row came from (provider, scrape, manual) |

**Point-in-time requirement.** `as_of_date` must be strictly earlier than the first kickoff of
that season. A row without an `as_of_date`, or with one on/after Week 1, is **not** a preseason
line and is excluded from the benchmark. Closing/in-season numbers are not substitutes.

**No reconstruction.** If a season's lines are missing, that season is dropped. It is explicitly
forbidden to (a) substitute a current-year line for a historical one, (b) reconstruct a
historical line from game-level spreads, ratings, or any model, or (c) fill from a secondary
source that does not carry its own `as_of_date` and `book`. A reconstructed line is a model, and
benchmarking a model against a model answers nothing.

### 2.3 Features

Any feature used for season *S* must be computable from information dated strictly before the
first kickoff of season *S*. That means prior-season results, prior-season play-by-play
aggregates, roster/coach identity as of the preseason, and (once §5 verifies availability)
offseason transactions. It does **not** include anything that reads season-*S* game outcomes,
season-*S* play-by-play, or an end-of-season roster snapshot backfilled to the preseason.

`futures/season_team_totals/00_data_audit.ipynb` §7 classifies each candidate feature family as AVAILABLE,
CONDITIONAL, or UNAVAILABLE before it may be used. `01_build_dataset.ipynb` re-asserts the rule
per column and fails the build on any violation.

### 2.4 Provenance

Every artifact records: source library + version, the as-of date of the pull, the season range,
a content hash of each input, the feature list in order, the random seed, and the notebook that
wrote it. An artifact without provenance is not a result.

---

## 3. Evaluation design

**No random cross-validation, ever.** Team-seasons within a season are not exchangeable (they
share opponents, and the league's wins are conserved), and a random split leaks the future.

**Expanding-season out-of-sample.** For test season *T*, train on every season `< T` for which
both the outcome and (where the benchmark is involved) the line exist. Evaluate on *T*. Advance
*T* by one and repeat. Every hyperparameter choice is made **inside** the training window; a
choice made by looking at any test season's score voids the fold.

Folds are fixed once §5's coverage audit reports which seasons have usable lines. They are then
frozen in `futures/artifacts/data_audit.json` and read from there — never re-chosen after seeing
a result.

**Minimum size.** A fold set with fewer than **5 test seasons** or fewer than **160 team-seasons**
of line-covered evaluation rows is declared underpowered; results may be reported descriptively
but may not open any gate in §7.

---

## 4. Metrics

Primary, on line-covered test rows only, per fold and pooled:

1. **MAE(wins)** — mean absolute error of predicted vs actual `wins_half_ties`.
2. **ΔMAE vs line** — model MAE minus the line's MAE. Negative = model closer.
3. **ATS-analog hit rate vs the line** — of team-seasons where the model takes a side (predicted
   wins above/below the posted line), how often the actual result lands on that side.
   Integer-line pushes (`wins_half_ties == win_total_line`) are excluded from **both** numerator
   and denominator, matching push-refund settlement. Push count is always reported.
4. **Break-even** — at the actual posted prices, per row; the pooled break-even is the
   price-weighted figure, not an assumed 52.4%.

Secondary (distribution quality, §3 folds, only where the model emits a distribution):

5. **CRPS** of the predicted win distribution.
6. **Log loss / Brier** of P(OVER) against the settled side, pushes excluded.
7. **Calibration**: 10-bin reliability of P(OVER) and coverage of the 50% / 80% central intervals.

Baselines every candidate is scored against, on identical rows:

* **B0 — the market line** (predict the posted total; the benchmark that matters).
* **B1 — persistence** (predict prior-season wins, rescaled for a 16→17 game change).
* **B2 — league mean** (predict `games_played / 2`).
* **B3 — shrunk persistence** (prior-season wins shrunk toward the league mean by a factor fitted
  on training seasons only).

---

## 5. Data-availability gate (fires first, in `00_data_audit.ipynb`)

The audit runs **before** any dataset is built and answers one question: do point-in-time
preseason win-total lines exist for enough seasons to make an honest backtest possible?

**GO** requires all of:

* **G1** — ≥ 8 distinct seasons carry preseason win-total lines meeting §2.2 in full.
* **G2** — within each counted season, ≥ 28 of 32 teams are covered.
* **G3** — every counted row has a non-null `as_of_date` strictly before that season's first
  kickoff, and a named `book`.
* **G4** — the outcome table passes its own integrity checks (32 teams per season, per-team
  `games_played` matching the schedule, and league-wide wins conservation:
  `Σ wins_half_ties == number of played games`, per season).

**NO-GO** if any of G1–G3 fails.

**On NO-GO the subproject stops at the audit.** `01`–`05` do not run; no model is fitted; no
predictions artifact is written; the live page states plainly that the historical line data
needed for an honest backtest does not exist, and shows nothing else. Reporting the absence *is*
the deliverable in that branch. It is specifically forbidden to respond to a NO-GO by
substituting current-season lines, reconstructing historical ones, or quietly evaluating against
a non-market baseline and presenting the result as if the market question had been answered.

*Prior expectation, recorded now:* this repository owns no win-total line data as of writing —
`betting/data/nfl.xlsx` is game-level spreads/totals only, and `nflreadpy` exposes no futures
market. NO-GO is the expected first outcome pending a line file Joseph supplies.

---

## 6. Model families (fixed before fitting)

Declared now so the list cannot grow toward whatever wins:

* **M1** — shrunk persistence + prior-season point differential (linear).
* **M2** — regularized linear model (Ridge) on the §2.3 feature set.
* **M3** — gradient-boosted trees (LightGBM), hyperparameters chosen by inner expanding-season
  selection within the training window only.
* **M4** — a team-strength + schedule Monte Carlo: fit a prior-information team rating, simulate
  every scheduled game of season *T*, and take the win distribution over simulations. This is
  the intended distribution model (`03`) because it respects the actual schedule and conserves
  league wins by construction.

Adding a fifth family after seeing any fold result requires an amendment in §10 naming the
result that motivated it, and the added family is reported as exploratory.

---

## 7. Acceptance / rejection

Judged on the pooled expanding-season out-of-sample rows defined in §3, at the fold set frozen
by §5. All thresholds fixed here, before fitting.

**A — "the model is a usable projection" (descriptive ship).**
`ΔMAE vs B1 (persistence) ≤ −0.15 wins` pooled, and MAE improves in ≥ 60% of folds.
→ Ships as a descriptive projection. Display shows projected wins and the distribution.
**No** market comparison language, no OVER/UNDER call, no probability against a posted price.

**B — "the model beats the market on accuracy."**
`ΔMAE vs B0 (the line) < 0` pooled, improving in ≥ 60% of folds, **and** a
season-block bootstrap (10,000 resamples over test seasons) whose 95% interval for ΔMAE
excludes 0.
→ May state, in aggregate only, that the projection was closer to the result than the posted
line over the backtest. Still no bet language.

**C — "the model beats the market at the posted price" (the only gate that unlocks
side-taking language).**
B passes, **and** the ATS-analog hit rate exceeds the price-implied break-even by ≥ 2.0
percentage points pooled, **and** the one-sided 95% lower bound of a season-block bootstrap on
that hit rate is above break-even, **and** P(OVER) is calibrated (ECE ≤ 0.05, 80% interval
coverage within 72–88%).
→ Only then may the page display a side, a probability against the posted line, or any
confidence tier. Even then the label is **BACKTESTED, NOT LIVE-VALIDATED** until a full forward
season is graded.

**Rejection.** If A fails, the subproject ships nothing to the site beyond the audit result. If A
passes but B fails, the honest headline is "does not beat the market" and it is stated plainly on
the page — the same standard the spread and seasonal-projection work is held to here.

**Language fence (binding regardless of outcome).** The words *bet*, *edge*, *lock*, *value*,
*play*, and any confidence tier are forbidden on the page and in the artifact unless gate C has
passed and the passing evidence is cited on the same surface. Until then the page says what the
model projects and what the backtest showed, and nothing about what to do with it.

**One-shot.** Each gate fires once, on the frozen fold set, and the result is written to
`futures/artifacts/` as JSON. Re-running to "regenerate" a number is forbidden; read the JSON.

---

## 8. Notebooks

All six live in `futures/season_team_totals/`; shared inputs (`data/`), results (`artifacts/`),
and the page artifact stay at the `futures/` root.

| Notebook | Role | Papermill |
|---|---|---|
| `00_data_audit.ipynb` | §5 gate: outcome integrity, line coverage, feature availability. Writes `artifacts/data_audit.json`. | yes |
| `01_build_dataset.ipynb` | Build the team-season panel; enforce §2.3 availability; leakage tests. | yes |
| `02_model_comparison.ipynb` | M1–M3 vs B0–B3 on the §3 folds. Research only — writes no production artifact. | yes |
| `03_distribution_model.ipynb` | M4 schedule-level Monte Carlo; CRPS/calibration; push handling. | yes |
| `04_fit_production.ipynb` | Fit the chosen model on all available seasons; pin seed, feature order, schema, metadata. | yes |
| `05_predict_futures.ipynb` | Predict the upcoming season; write `futures/futures_predictions.csv`. | yes |

`02` and `03` may not write anything the live page reads. Only `05` writes
`futures_predictions.csv`, and only if §7 gate A has passed.

**Runtime separation.** Training/simulation dependencies (LightGBM, scipy, any solver) stay out
of `requirements.txt`. The live page reads the saved CSV with pandas and Streamlit only.

---

## 9. Known limitations (stated up front)

* **Line data is the binding constraint.** Historical preseason win totals are not a free public
  dataset in the way game-level spreads are. Whatever source is used will have gaps, single-book
  coverage, and an as-of date that is somebody's snapshot, not a market consensus.
* **Settlement rules vary by book.** Tie handling, cancelled games, and relocated/renamed
  franchises are all book-specific. §2.1 states the assumption; a book with different rules
  invalidates the grading for that book's rows.
* **32 rows per season.** Even 15 seasons is ~480 team-seasons, and they are not independent —
  wins are conserved within a season, so errors are negatively correlated across teams. This is
  why §7 uses season-block bootstrap rather than row-level intervals.
* **Preseason win totals are a well-shopped market.** The base rate for beating them is low. A
  result that clears gate C on this sample size should be treated as provisional until forward
  seasons confirm it.
* **Non-stationarity.** The 17th game (2021), the 2020 season, and rule changes all shift the win
  distribution. Expanding-season evaluation absorbs some of this; nothing absorbs all of it.
* **No live validation exists.** Everything until a graded forward season is backtest.

---

## 10. Amendments

### Amendment 1 — archived market-consensus lines admitted for Tier B only

**Accepted by Joseph on 2026-08-03**, before any model was fitted and before notebooks `02`–`05`
were opened. Proposal text: `futures/PROPOSED_AMENDMENT_FREE_MARKET_ARCHIVE.md`. Acquisition run in
force at acceptance: `futures/data/win_totals.csv`, sha256
`dd6753f654dec864b7fbeb7e3e23b7a3fa2cfc41c86e1de48c66bb86742eecbe`, 352 rows, 11 seasons, recorded in
`futures/artifacts/win_totals_acquisition.json`.

Sections 1–9 above are **unchanged**. This amendment adds a second, narrower path through §5's G3
and does not touch §7's gate C, the language fence, or the one-shot rule.

**A1.1 — What is admitted.** A win-total line whose `book` is null may be counted by §5 provided it
carries a named `market_source` identifying a public archive, a published capture date per season,
and full price fields. Such a line is an **archived market consensus**, not a sportsbook line.

**A1.2 — G3 splits into two gates.**

* **G3-B (archive path, this amendment):** every counted row has a non-null `as_of_date` satisfying
  A1.3 and a named `market_source`. `book` may be null. Satisfying G3-B admits the data to §7 gates
  **A and B only**.
* **G3-C (frozen path, §5 as written):** every counted row additionally has a named `book`. **G3-C
  is required for §7 gate C and is not satisfied by any archive source.** Its text is unchanged.

The audit's verdict vocabulary gains **`GO-TIER-B`**. A plain `GO` still requires G3-C. `GO-TIER-B`
never opens gate C.

**A1.3 — Kickoff-day clause, and the timestamp that does not exist.** A capture dated *on* the
season's Week 1 date may count as preseason only because the source states its numbers are
pre-kickoff closing values. The Covers 2023 page says, verbatim:

> "Closing odds prior to each teams' first game"

**Recorded as a permanent limitation: exact closing timestamps are unavailable.** The archive
publishes a date with no clock, so strict priority to kickoff cannot be demonstrated for these
seasons — it is inferred from the source's own statement. Rows admitted this way keep
`point_in_time_status = same_day_as_week1_kickoff` and are reported separately in every result
table, never pooled silently. A season with **no** date is not admitted (2012, 2013, 2023 remain
rejected).

**A1.4 — Mandatory sensitivity.** Every headline Tier-B result is reported twice: on the
**strictly-dated** subset (2014–2018, 160 rows) and on the **full admitted** set (11 seasons, 352
rows). If they disagree in sign, the strict subset governs and the disagreement is the finding.
The strict subset yields 4 folds — **below §3's five-fold minimum** — so it is a sensitivity only
and can never be the headline. §3's minimums otherwise apply unchanged.

**A1.5 — Language.** Tier B may state, in aggregate, whether the projection was closer to the
realized win count than the archived consensus number. It must name the source as an **archived
market consensus of unattributed sportsbook origin**; the words *sportsbook line*, *Vegas*, and
*the market* as a stand-in for a book are forbidden for this data. §7's language fence stands
unchanged: *bet*, *edge*, *lock*, *value*, *play*, sides, probabilities against a posted line,
confidence tiers, EV, and profitability remain forbidden, and gate C — the only gate that could
lift them — is unreachable from this source. Over/under recommendations wait for timestamped,
named-book lines, to be collected prospectively for 2026.

**A1.6 — Disclosure (recorded at Joseph's instruction).** This amendment was drafted *after* the
acquisition run revealed which gate the free source failed. That ordering is the classic
gate-shopping hazard and is disclosed here rather than obscured. It is accepted as a **transparent
feasibility amendment** on the grounds that it (i) unlocks only descriptive/Tier-B accuracy
comparison, (ii) never treats the archive as a sportsbook, (iii) leaves every priced claim locked,
(iv) records the missing timestamps as a permanent limitation, and (v) is frozen **before** any
model is fitted and before `02`–`05` are opened. No result influenced its terms, because no result
exists.

**A1.7 — Freeze.** Effective on acceptance. The fold set it produces is frozen by the audit run of
2026-08-03 into `futures/artifacts/data_audit.json` and read from there by every downstream
notebook. Amending this amendment after a fold result is seen is forbidden by the same rule that
governs §7.
