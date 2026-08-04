# Preseason feature feasibility — QB, All-Pro, injury and roster families

Written 2026-08-03, **before** `02_model_comparison.ipynb` existed and before any model result was
observed. Governed by `PREREGISTRATION.md` §2.3 and §10 Amendment 2 (A2.4).
Machine-readable twin: `futures/artifacts/preseason_feature_feasibility.json`, written by
`01_build_dataset.ipynb` from the same frozen table.

**Outcome: no family in this audit was added to `FEATURE_COLS`.** This is a feasibility record.

---

## 0. Why the spread model's feature ranking is not evidence here

It is tempting to import the betting model's high-importance features. That ranking cannot support
a claim in this project, and its own project history is the reason:

* **`spread_line` dominates it**, and `spread_line` is ≈ the closing line (corr **0.994** to
  `spread_close`; the only line-derived feature in `PROD_FEATURES_35`). A model whose top feature is
  the market is not evidence that its *other* features carry independent information.
* **Closing-line / CLV interpretation problem** — picks made at the open were graded against the
  close, so "beating the close" was partly mechanical. Predicted-margin MAE beat the closing line by
  **0.14 pt**, far too little for the claimed edge.
* **Sack-feature leak** — the sack history was built only from sack-positive team-game rows, so a
  zero-sack game had *no* row; presence encoded the current game's outcome and `fillna(0)` wrote
  zeros onto exactly those rows. `sack_diff` / `sack_diff_reverse` were `PROD_FEATURES_35` #2 and #3.
* **All-Pro identity collision** — the roster CSV has no player ID, and two distinct players named
  C.J. Mosley (BAL ILB / DET MLB, both 2014) merged under a name key, with the survivor chosen by an
  unstable sort. Four production features moved between pandas versions.
* **Corrected result:** in a pinned environment, **HIGH 129/238 = 54.2017%, Wilson lower bound
  47.8551% — below the 52.4% break-even. No tier clears.**
  (`betting/experiments/audit_2026-08-03c_final/PROVENANCE.md`.)

So: importance there is not evidence of usefulness here. Each family below is judged **only** on
whether it can be built point-in-time and honestly, for both history and 2026.

---

## 1. Verdicts

| # | family | verdict | binding reason |
|---|---|---|---|
| 1 | Expected preseason starting QB | **UNAVAILABLE** | schedule QB fields are post-game; **272/272 null for 2026** |
| 2 | Starting-QB change | **UNAVAILABLE** | derived from (1) |
| 3 | Prior QB passing EPA/play | **CONDITIONAL** | prior-season EPA is settled, but attaching it to the *2026 starter* needs a dated preseason depth snapshot |
| 4 | Prior passer rating | **CONDITIONAL** | same identity blocker; NGS also starts **2016**, so 2002–2015 lack coverage |
| 5 | Prior CPOE | **CONDITIONAL** | same identity blocker; NGS 2016+ |
| 6 | Current-roster weighted All-Pro talent | **UNAVAILABLE** | All-Pro CSV has **no player ID** and its `Team` is the *honoring* team, not the current one |
| 7 | Current-roster off/def All-Pro split | **UNAVAILABLE** | same |
| 8 | Roster continuity / returning snaps | **CONDITIONAL** | roster tables are revised in place; no dated preseason snapshot is owned |
| 9 | Preseason IR/PUP/NFI status | **UNAVAILABLE** | the injury feed is a weekly in-season report; no preseason status snapshot exists |
| 10 | Expected games lost / injured-player value | **UNAVAILABLE** | depends on (9) |
| 11 | Offensive-line continuity | **UNAVAILABLE** | depth charts end at **2024** in this stack — absent for the 2026 deploy season |
| 12 | Previous-season turnover rate | **AVAILABLE** (not included) | settled prior-season play-by-play, no identity join |
| 13 | Previous-season special-teams EPA | **AVAILABLE** (not included) | settled prior-season play-by-play, no identity join |

---

## 2. The three blockers, stated once

**Blocker A — post-game population.** The schedule's `home_qb_id` / `away_qb_id` are filled in after
games are played. Measured on the pinned snapshot: **0 null for 2019 and 2025, 272/272 null for
2026.** Everyone knew each team's Week 1 starter in August; the archive cannot *prove* what was
known then, and for 2026 the field is simply empty. Using it would be both a leak in history and a
train-present/deploy-absent collapse in 2026 — the same failure that projected a running back at 4
points against an actual 331 in `fantasy/projections`.

**Blocker B — no identity spine.** `betting/nfl_allpro_1997_2025.csv` carries
`Pos, Player, Team, Year, Side` over 2,047 rows and **no player ID**. `Team` is the team the player
was honored with. "Current-roster All-Pro talent" therefore requires a dated preseason roster mapping
each historically honored player to the team he is on *now* — a mapping this repository does not own.
Substituting an end-of-season roster revised in place would answer a different, contaminated
question. Note also that prior-team All-Pro counts must never be *described* as current-roster
talent; that conflation is what the `allpro_identity` work had to unpick.

**Blocker C — in-season-only feeds.** Injury status comes from a weekly in-season report
(`load_injuries(seasons=[S])`, consumed at a target week). There is no preseason IR/PUP/NFI snapshot,
and a Week 1 injury report is published in game week, not in the preseason. Weekly injury counts are
therefore not preseason features and are excluded by §2.3.

---

## 3. The two AVAILABLE families, and why they are still not in the panel

Prior-season **turnover rate** and **special-teams EPA** are honestly buildable: they are settled
before the target season starts, need no identity join, and would exist for 2026 from 2025 data.

They are **not added**, for one reason: the pinned play-by-play aggregate
(`futures/data/pbp_team_season_epa.parquet`) carries offensive/defensive EPA per snap and offensive
success rate only. Adding either family means re-pinning that snapshot and changing `FEATURE_COLS`.
Amendment 2 (A2.4) states that no family is added by this amendment, and adding one after `02`
produces numbers would be a feature choice informed by results.

**Exact unlock:** a further amendment declaring the definitions, followed by re-pinning the PBP
aggregate with turnover and special-teams columns and rebuilding `01`. Both must happen before `02`
is executed.

---

## 4. What would unlock the blocked families

| family | exact source needed |
|---|---|
| Preseason starting QB, QB change, and the three prior-QB metrics | a **dated** preseason depth chart or starter list per team-season (published before Week 1, archived with its capture date) |
| Current-roster All-Pro talent (both variants) | a **dated preseason roster** with stable player IDs, plus an ID-bearing All-Pro source or a reviewed crosswalk into `allpro_identity` |
| Roster continuity / returning snaps | the same dated preseason roster, plus prior-season snap counts |
| Preseason IR/PUP/NFI and expected games lost | a **dated preseason transaction/status feed** (not the weekly in-season injury report) |
| Offensive-line continuity | depth-chart coverage extending through the deploy season, plus the dated roster above |

None of these is fetched in this task. This is a feasibility audit, not authorization for a new
acquisition pipeline.

---

## 5. Standing rules this audit enforces

* A **CONDITIONAL** or **UNAVAILABLE** family may not enter `FEATURE_COLS` (A2.4).
* Prior-team All-Pro counts are never described as current-roster talent.
* Weekly injury counts are never used as preseason features.
* End-of-season rosters revised in place are never substituted for preseason snapshots.
* When an honest preseason snapshot is absent, the feature is left out and the exact missing source
  is named — as above.
