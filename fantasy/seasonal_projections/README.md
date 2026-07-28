# Seasonal Projections

A pre-season fantasy projection system, separate from the in-season weekly
model in `fantasy/`. The goal: project each player's upcoming season and compare
to the market (ADP) to surface over/undervalued players. It is the fantasy analog
of the betting side's "model vs the Vegas line" thesis (here the market line is ADP).

## What ships today: the 2026 Draft Board (2026-07-12)

> **Update 2026-07-22 — the Draft Board page was REBUILT and no longer renders the band.**
> It is now a season-projection comparison table: 245 rows, 13 columns — Sleeper ADP and
> Position Rank beside Sleeper's and my own from-scratch season projections, the positional-rank
> gap for each, and two descriptive talent columns from `fantasy/talent/`. A detail toggle (on by
> default) can collapse it to a compact 9-column comparison view. There is no Floor/Expected/
> Ceiling, no Top-12 chance and no bust risk on the page. `phase4_band_2026.csv` and
> `talent_index_2026.csv` stay FROZEN on disk for this closed campaign only — **neither is an
> input to the daily ADP refresh** (its one frozen input is `season_dataset_2014_2026.csv`), and
> the page reads the band nowhere. **The description below documents the RETIRED band product,
> for history.**

The band product paired the market's point estimate — powered by Sleeper's projections versus
the draft market — with a calibrated range I built around it: a Floor, Expected, and Ceiling for
the season, a Top-12 chance, and a bust risk. When I drew those ranges for the 2021 through 2025
seasons, about 8 in 10 players finished inside their 80% range.

The board also shows the gap between projection and draft price. That gap has a tested
track record as a group pattern — validated in aggregate across five past seasons,
including a check that it wasn't just the projections being fresher than the prices — for
established players and for running backs and receivers in changing situations; it is not
yet tested for quarterbacks and tight ends in changing situations, and those rows are
marked. It describes patterns across many players, never a call about any one player. The
full story is in `GUIDE.md`, the file-by-file status is in `ARTIFACTS.md`, and the
pre-registered research campaign behind the signal is in `PREREGISTRATION.md`.

The Seasonal Value Finder described below was the earlier shipped tab; I retired it on
2026-07-12 and keep it here as history.

## ~~What ships today:~~ the Seasonal Value Finder (2026-06-08) — **RETIRED 2026-07-12**

**[RETIRED 2026-07-12 — replaced by the 2026 Draft Board (see the section above and
`draft_board_2026.py`). The BUY/FADE tab described in this section no longer ships. The
text below is kept verbatim as history and is not rewritten.]**

The live dashboard tab is the **Seasonal Value Finder** — **our independent model's
calls vs the draft room's ADP**. `train_model_a.py` (per-position **LightGBM**, injury
features removed) projects each player; `build_value_board.py` ranks the drafted pool,
computes `value = adp_rank − our_rank`, and emits **BUY** (undervalued) / **FADE**
(overvalued) calls with confidence tiers → `value_board_{season}.csv` → the app tab.

**Honest verdict (and why it's framed the way it is):**
- Our calls **beat the casual ADP line**: ~**68% on confident (HIGH) buys**, stable every
  season (canonical eval `surprise_eval.py`: ADP-mispricing skill +0.20 vs a ~0 placebo).
- The edge is **buy-side**; raw fades are a coin flip, so **fades are gated** to players
  with a real decline catalyst (aging or declining) and never young — that subset clears
  50%. The eval **excludes mid-season-injury seasons** (unpredictable noise).
- We do **NOT** beat the sharpest public projection. ~~**Sleeper's projection alone vs ADP
  is ~84-90%** (verified not leakage)~~ **[STRUCK 2026-07-10 — provenance audit:** Sleeper's
  stored **2020 "projections" are near-actuals** (gp correlates +0.91 with actual games;
  Mixon proj 88.0/gp 6 = his real 89 pts/6 games), so every Sleeper number computed on
  2020 was inflated; see `PREREGISTRATION.md` Outcomes + the quarantine in `fetch_adp.py`.
  The 84-90% figure's source computation was deleted in the 2026-06-12 scratch cleanup and
  cannot be recomputed as-was. Ex-2020 restatement (2021-2025, `recompute_sleeper_ex2020.py`):
  Sleeper ρ QB .578 / RB .711 / WR .659 / TE .544 vs ADP .420/.585/.571/.454 — still the
  sharpest public source, by a reduced margin. 2021-2025 projections passed every
  contamination probe.**] Combining our model with Sleeper does not beat
  Sleeper alone. So Sleeper is shown on the board **as a comparison column only** — we
  deliberately do **not** ship Sleeper-as-our-edge (that would be repackaging, not an edge
  we own). The tab's claim is "beats your draft room," not "beats Sleeper."

Everything below (the A×B VOR board, the three-way blend, the rookie model) is the **earlier
research arc** — kept on disk for reference, but it is **not** what the tab serves.

## Why this is a different model than the weekly one

The weekly model leans on *in-season* rolling features (recent EPA, recent
target share). None of those exist before Week 1. So this is a distinct problem:
a season-long projection built only from information known at draft time
(prior-season aggregates, multi-year trend, age, draft capital, team context).

## Pipeline (run in order) — **RETIRED ARC, kept for history**

> **Do not run these to produce anything shipped.** Every "SHIPPED" / "CANONICAL" tag below dates
> from the Model-A / value-board era, which was retired on 2026-07-12. `train_model_a.py`,
> `build_value_board.py` and `surprise_eval.py` are all marked RETIRED in `ARTIFACTS.md`; the
> Seasonal Value tab they fed no longer exists (the site is a multipage app with no such page), and
> `value_board_*.csv` was deliberately removed from git. **`build_value_board.py` emits BUY/FADE
> verdict language that the current licensing fence forbids on any live surface.**
>
> **The one command that is live today** is the daily ADP refresh:
> `python fantasy/seasonal_projections/refresh_board_adp.py` — see "Daily ADP refresh" below.

| Step | File | Output | Notes |
|------|------|--------|-------|
| 1 | `fetch_adp.py` | `sleeper_adp_2020_2026.csv` | Caches Sleeper preseason ADP (`adp_half_ppr`) + Sleeper's own season projection. ADP exists 2020+; 2026 already has ~245 players and grows toward late-August. |
| 2 | `build_season_dataset.py` | `season_dataset_2014_2025.csv` | One row per (player, season): prior-only features, two targets, ADP/Sleeper joined for 2020+. |
| 3 | `train_model_a.py` | `models/{pos}_ppg_model.pkl` | **SHIPPED model.** Model A (PPG), one **LightGBM** per position, games-weighted, **injury features removed**, 2014-2024 train / 2025 holdout. (Bakeoff: LightGBM/tree-ensemble beat CatBoost ~0.15 PPG MAE; CatBoost hyperparam tuning did nothing.) |
| 4 | `build_value_board.py` | `value_board_{season}.csv` | **SHIPPED tab data.** Loads Model A pkls, ranks the drafted pool vs ADP, emits BUY/FADE calls + tiers (fades gated to decline-catalyst, not young), adds Sleeper rank as a comparison column, and runs the **incoming-competition guard** (`incoming_competition.py`) that turns a BUY into **⚠️ Contested** when a real new threat joined the player's room (round≤2 rookie, free-agent/trade arrival, returning-from-injury starter, or a crowded backfield) — fixing the "our model over-likes James Conner / Trey Benson" problem the prior-stats model can't see. Elite-gated + conservative so it never fades a clear starter. Feeds the app's Seasonal Value tab. |
| 5 | `surprise_eval.py` | (stdout) | **CANONICAL eval.** ADP-mispricing skill = corr(our deviation from ADP, actual deviation), conditional on ADP, injury-filtered. Measures the shipped per-position config. ~+0.20 skill, +10pp bold calls. |
| - | `train_rookie_model.py` | `models/rookie_ppg_model.pkl` | Rookie PPG model (draft capital + combine + landing spot, via `rookie_features.py`). **Used by `build_value_board.py`** to project rookies (Model A has no prior stats for them). Rookies show on the board but get no buy/fade call — our rookie ranking loses to ADP, so we don't pretend a rookie edge. |
| - | `build_2026_board.py` | `season_dataset_2014_2026.csv` | Seeds upcoming-season (2026) rows from rosters **+ every drafted rookie pulled straight from `load_draft_picks`** (the roster feed lags the draft, so even top picks like Jeremiyah Love were missing — draft team is normalized to the roster convention via `DRAFT_TEAM_MAP`) + 2025 priors; keeps 2014-2025 verbatim. Run before building the 2026 value board. (Rookie ADP fills in over the summer, so the rest enter the pool as ADP populates.) |
| - | `train_model_b.py`, `build_draft_board.py` | — | **Earlier arc (retained, not shipped):** Model B (availability) + the A×B VOR + three-way-blend board. Kept for reference; the tab no longer uses them. |
| - | `rookie_features.py` | - | Shared rookie-model features (combine join + ROOKIE_FEATS). Source of truth for the trainer, board, and experiments. |
| - | `three_way_blend_test.py` | - | Sweeps the our/ADP/Sleeper blend weights (simplex grid + LOSO). Confirmed 0.2/0.3/0.5 beats the 2-way 5/5 seasons. |
| - | `blend_experiment.py` | - | The original our/ADP two-way weight sweep (found 0.30). Superseded by the three-way blend. |
| - | `diagnose_vet_rookie.py`, `rookie_model_experiment.py`, `rookie_blend_test.py` | - | Diagnostics behind the rookie model (vet/rookie split, standalone bakeoff, A/B/C blend test). |

`_utils.py` holds shared helpers (`norm_name`, constants). `test_seasonal_projections.py`
is a hermetic test suite (no network) for the transformation logic.
`model_a_compare.ipynb` is the original 3-way bakeoff (CatBoost vs XGBoost vs LightGBM),
kept for reference. CatBoost won *that* pass, but the later, sharper bakeoff in
`model_bakeoff.py` found **LightGBM** beats it by ~0.15 PPG MAE at every position — so the
shipped `train_model_a.py` uses LightGBM, with injury features dropped.

**Completed-season grading and injuries.** For a finished season the board shows where each
player actually finished and a ✅ hit / ❌ miss on the call — *except* players who missed
more than 6 games, who show **🏥 injured** and aren't graded either way. This matches the
canonical eval, which excludes mid-season-injury seasons because injury timing is
unpredictable noise (and our BUYs aren't more injury-prone than the field — ~14% vs ~18%).

```bash
python fantasy/seasonal_projections/fetch_adp.py
python fantasy/seasonal_projections/build_season_dataset.py
python fantasy/seasonal_projections/test_seasonal_projections.py   # dataset transform tests
python fantasy/seasonal_projections/train_model_a.py               # SHIPPED model (LightGBM, no injury feats)
python fantasy/seasonal_projections/build_value_board.py           # SHIPPED tab data: value_board_{season}.csv
python fantasy/seasonal_projections/surprise_eval.py               # CANONICAL eval: ADP-mispricing skill
# --- earlier arc (retained, not shipped) ---
python fantasy/seasonal_projections/build_2026_board.py            # seed 2026 rows (needed by build_value_board for 2026)
python fantasy/seasonal_projections/build_draft_board.py           # old three-way-blend board
```

## What the models do, and the honest verdict

**Model A (PPG)** is per-position CatBoost, games-weighted. 2025 holdout, matched-row
MAE (rookies excluded so the naive baseline can compete): QB 2.78, RB 2.41, WR 1.84,
TE 1.36, and it beats a 3-year-average baseline at all four spots. **Model B (games)**
is one pooled CatBoost trained on every player-season including the reconstructed
full-miss years. 2025 holdout MAE 3.73 games, beating "repeat last year" (4.11) and
"predict the mean" (5.34). It does what we wanted: separate durable from fragile
tiers, not nail exact games (most injury variance is a freak hit no feature sees).

Combined into a board, value = PPG x games, then value-over-replacement (VOR) so the
cross-position ranking is sane (raw points would stack every QB at the top).

**Does our model beat the market on its own? No.** Walk-forward backtest 2020-2024
(retrain on seasons before each year, drafted pool only, judged on actual VOR): our
ranking ρ averages 0.488 vs ADP's 0.552, and ADP wins every single year. The players we
would "value pick" (rank well above ADP) finished with a 125-point mean vs 160 for
players we are neutral on and 157 for players we would fade. When our model disagrees
with ADP, ADP is usually right. Same lesson as the spread and totals models: a market
consensus already prices in offseason news, camp reports, and depth-chart moves a
prior-season-stats model cannot see. So we do not ship the standalone model as an edge.

**What we do ship is the blend** (see below), ~~which out-ranks any single source~~
**[STRUCK 2026-07-10: ex-2020 the blend no longer beats Sleeper alone — see the
three-way section below]**. The
honest framing: our model is not draft-board alpha on its own, but as one ingredient in
a market blend it earns a real, small contribution. We present the board as a
sanity-checked consensus, not a secret edge.

`diagnose_vet_rookie.py` splits that backtest by rookie status to see where the gap
comes from. Veterans (86% of the drafted pool): our ρ 0.506 vs ADP 0.544, basically
parity (we even edged ADP in 2022 and 2024). Rookies (14%): our ρ 0.172 vs ADP 0.462,
a wipeout. The model has no prior-season data on rookies, so it clumps them all at the
bottom.

### Rookie model (shipped into the blend)

We built a dedicated rookie model on draft capital, combine measurables (forty, bench,
vertical, broad jump, cone, shuttle, height, weight, joined to our player id through
the draft-picks pfr bridge, about 93 percent coverage on drafted rookies), and
landing-spot features. College production is not in nflreadpy, so we do not have it.
The feature engineering is in `rookie_features.py` and the trained model is
`models/rookie_ppg_model.pkl` (`train_rookie_model.py`).

Standalone it does not beat ADP (rookie ranking rho 0.26 vs 0.46) so it is not an edge
on its own. But the right question is not whether it beats ADP alone, it is whether it
helps inside the blend, and it does. `rookie_blend_test.py` compared three ways to
handle rookies' projection in the blend: the veteran model (the old behavior), the rookie
model, and pure ADP. Walk-forward mean rookie-slice rho came out veteran 0.457, rookie
model 0.488, pure ADP 0.457. The rookie model is the only option that clears pure ADP
on rookies (its errors are independent of the market's, so the ensemble lifts it), and
it does not cost anything on the overall board. So `build_draft_board.py` uses the
rookie model for rookies' projection inside the blend. Shipping it improved the board's
2025 PPG accuracy (2.06 vs 2.01) and nudged the season-total projection closer to
Sleeper's. The standalone edge backtest deliberately does not use it, so the "we lose
to ADP standalone" result is unchanged.

### The blend (shipped into the board)

This is where our work pays off. Our standalone projection loses to the market, but it
carries independent signal, so blending it with market signals out-ranks any single
source. We never feed a market signal into the model itself (that would be circular,
the tree would just copy it); we combine rankings after the fact.

Two steps got us here. First the two-way (`blend_experiment.py`): `0.3*our + 0.7*ADP`
beats pure ADP in 5 of 5 seasons, but only by about 0.012 to 0.015 Spearman rho, inside
the noise band. Then the big one (`three_way_blend_test.py`): Sleeper also publishes its
own season point projection, which alone already beats ADP, so we added it as a third
ranker. The best mix, confirmed by a simplex weight sweep plus leave-one-season-out, is
**our 20 percent, ADP 30 percent, Sleeper 50 percent**. ~~That lifts the board to rho
0.637 versus 0.567 for the old two-way, a plus 0.07 gain (about two standard errors)
that holds out of sample in 5 of 5 seasons. Our model still earns its 20 percent: the
full three-way beats ADP-plus-Sleeper-without-us, so the projection is not redundant.~~
**[STRUCK 2026-07-10 — doubly affected by the 2020 provenance finding: the weights were
TUNED on and the gain was EVALUATED on 2020-2024, and 2020's Sleeper column is
near-actuals (see PREREGISTRATION.md Outcomes). Harness restatement ex-2020
(`recompute_sleeper_ex2020.py`, frozen weights, 2021-2024): three-way ρ .685, two-way
.564, ADP .489 — but Sleeper ALONE .711, i.e. the blend is no longer shown to beat
Sleeper alone. The "our model earns its 20%" claim does not survive the corrected
record (restated with different model machinery — LightGBM points vs the original
CatBoost VOR — so it is a restatement, not an exact rerun; a faithful rerun would also
require re-tuning the weights ex-2020, which has not been done).]**
The board uses this three-way blend as the headline recommended draft order
(`blend_rank` / `blend_pos_rank`); the raw projection is kept for the value and reach
view. It is a real ranking improvement, but it is a blended consensus, not a secret edge.

### 2026 pre-draft board (built)

A real pre-draft board for the upcoming season is built, not just a future idea. Sleeper
ADP for 2026 already exists (early best-ball drafts have run; about 245 players now,
growing toward the late-August consensus), the 2026 draft happened in April so rookie
draft and combine data exist, and 2026 rosters give the player population. The only thing
missing is 2026 stats (the season has not been played), which a pre-draft board does not
need. `build_2026_board.py` seeds a row for every 2026 rostered skill player plus the
rookies, attaches their 2025-derived priors through the same prior-join the training data
uses, and appends those rows to the dataset (the trained 2014-2025 rows are kept verbatim,
since nflreadpy data drifts and the models were trained on them). Then
`BOARD_SEASON=2026 python build_draft_board.py` builds `draft_board_2026.csv`, and the
dashboard season selector shows it. The 2026 board correctly ranks rookies like Ashton
Jeanty and Omarion Hampton via the rookie model plus their ADP.

## Daily ADP refresh — the live one

The board's draft prices are re-pulled from Sleeper daily by
`.github/workflows/board_refresh.yml`, which runs `refresh_board_adp.py` and writes the
regenerable overlay `board_adp_live_2026.csv` (all 245 board rows, with a `refreshed_at` stamp the
page's "latest pull" caption reads).

```powershell
python fantasy/seasonal_projections/refresh_board_adp.py
```

**The freeze boundary is the point of it:** the refresh pulls **live ADP only** and recomputes the
price-derived rank and gap columns against a FROZEN projection side. It never writes
`phase4_band_2026.csv`, `talent_index_2026.csv`, the season dataset, or the ADP cache — and
(verified 2026-07-27) it does not even *read* the first two; its one frozen input is
`season_dataset_2014_2026.csv`. If a row is missing from the overlay, the page falls back to the
frozen dataset snapshot, so a fresh clone still renders.

## Annual refresh — **RETIRED ARC**

> **Superseded.** The section below describes regenerating the retired Model-A blend board via
> `build_draft_board.py`. That is not what ships; use the daily ADP refresh above. Kept because the
> annual data steps (extending `fetch_adp.py`, re-running `build_season_dataset.py` once actuals
> are final) are still the right offseason sequence for the dataset itself.

The board is kept as a projection and cross-check tool, so it is worth regenerating
each offseason. `build_draft_board.py` is season-parameterized: by default it builds
the latest season in the dataset and backtests the ADP-era seasons before it. Override
the season with the `BOARD_SEASON` env var:

```powershell
$env:BOARD_SEASON=2026; python fantasy/seasonal_projections/build_draft_board.py
```

It degrades gracefully: a season with no rows prints a rebuild hint, a season with no
ADP yet prints projections only, and an empty backtest is skipped. Output is written to
`draft_board_{season}.csv`. To refresh for a new season: (1) extend `fetch_adp.py` to
that season once Sleeper ADP lands, around late August; (2) re-run
`build_season_dataset.py` after the prior season's actuals are final; (3) optionally
fold the prior holdout season into training and re-run `train_model_a.py` and
`train_model_b.py`; (4) run `build_draft_board.py` with the new `BOARD_SEASON`.

~~One limitation to know: a true pre-draft board for a season with zero games played
needs the player list seeded from rosters and depth charts joined to prior-year stats,
because dataset rows come from `load_player_stats`, which is empty until games are
played. That seeding is not built, so the pipeline today produces a board for the
current or just-completed season.~~

**[RESOLVED — the seeding was built.]** `build_2026_board.py` seeds every 2026 rostered skill
player plus every drafted rookie from `load_draft_picks`, which is exactly the zero-games-played
case described above. `season_dataset_2014_2026.csv` exists on disk and the shipped 2026 board is
a genuine pre-draft board over 245 players. The limitation as written is no longer true.

## Two targets (two-model design)

- **`target_ppg`** — half-PPR points per game (Model A, production). NaN when the
  player played 0 games or fewer than 3 (a tiny sample is a noisy label).
- **`target_games`** — games played (Model B, availability). Present for every
  row, including reconstructed full-miss seasons.
- **`sample_weight`** — games played, so Model A trusts a 2-game season far less
  than a 16-game one.

Final draft value = projected PPG × projected games, ranked against ADP.

## Key design decisions (intentional, not bugs)

- **ADP is a benchmark, never a feature.** It only constrains evaluation (2020+),
  not the training window. The model trains on 2014+ from nflreadpy.
- **Full-miss seasons are reconstructed.** A season a player skipped entirely
  leaves no stats row, so Model B would never see a 0-game outcome. We synthesize
  a `games=0` row for every gap *between* a player's first and last active season.
  This leans toward injury/IR (the player returned) rather than left-the-league.
- **`is_rookie` vs `missed_prior_season`.** Both produce a NaN-ish prior, but mean
  opposite things (no NFL history vs a veteran who sat out hurt). Both are flags.
- **Prior features use an explicit season-(N-1) join, not `shift(1)`,** so a
  missed season correctly yields NaN priors instead of pulling 2-year-stale data.
- **Missing priors are NaN, never 0** (zero is a real value to a tree; NaN gets
  routed natively by XGBoost). Same lesson as the spread side's time-decay bug.
- **Low-snap player-seasons are kept, not filtered.** Usage drives points, so a
  17-game / 15%-snap line is real signal; `snap_share_pg` lets the model learn it.
  The ADP join means low-relevance players never reach the board anyway.

## Known caveats (honest)

- **`qb_changed` and `vacated_target_share` / `vacated_rush_share`** use season-N
  primary-passer / roster info. At a real late-August draft this is ~known, but
  it is mild hindsight in a strict backtest. `coach_changed` is fully clean.
- **Reconstructed gaps** capture injury plus some non-injury cases (a backup who
  sat a year). The ADP join ignores them, so they only inform Model B's
  durability gradient, not the board.
- **`games_played`** is snap-based where snaps exist (2013+), else stat-line
  weeks. It can still blur a true injury absence vs a healthy inactive.
- **Sleeper data floors:** ADP 2020+, Sleeper point projections 2018+. Neither
  limits the model (both are benchmarks).
