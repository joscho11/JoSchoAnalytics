# RB, WR, TE & QB Season-Total Projection — a plain-language guide

> This guide was written for the running-back model and then extended to wide receivers, tight ends,
> and quarterbacks (see "What's different for the other positions" at the end). The QB *rookie* model
> was built, judged too thin, and held back — only QB veterans are projected.

## 1. What I'm trying to do

Every summer, fantasy football managers draft players based on how many points they expect
each one to score over a whole season. The consensus of those expectations shows up in two
public numbers: **ADP** (average draft position — the average slot a player gets picked across
thousands of real drafts, i.e. the market's price on him) and a site projection like Sleeper's,
which puts an actual point total on each player. Those market numbers are hard to beat, because
they already bake in everything the crowd knows.

This subproject builds my own from-scratch projection of one thing: **how many half-PPR points
each running back will score across the entire 2026 regular season.** ("Half-PPR" is a scoring
rule — a player earns his normal points plus half a point per catch. "Season-total" means summed
over all his games, not a per-game average.) I now build it for running backs, **wide receivers, tight
ends, and quarterbacks** — with one caveat: the QB *rookie* model was held back as too unreliable (see
the end), so only QB veterans are projected.

The point of the exercise is honesty about a hard problem. A season projection has to guess two
things at once — how good a player is *per game*, and *how many games' worth of work he'll get* —
before the season has even started, when depth charts and roles are still unsettled. My baseline,
the number I hold myself against, is Sleeper's own projection. I do not assume I can beat it. I
show my projection **next to** Sleeper's, with the difference, and let the reader judge. Beating
Sleeper is explicitly not a bar this product has to clear to ship.

## 2. How it works, end to end

**The data.** I start from a season-level dataset I already maintain (`season_dataset_2014_2026.csv`),
which has one row per (player, season) for the relevant player pool from 2014 through 2026. Each row
carries "prior-season" facts — last year's points, carries, targets, efficiency — plus draft position,
age, and team-context features like how much of the backfield's touches were vacated by departed
players. For rookies, who have no prior NFL season, I additionally join a frozen college-and-combine
feature matrix (draft capital, athletic testing, college production, and college grades from PFF) that
I built and locked for an earlier project.

**The target — what the model learns to predict.** For every (player, season) I compute the *actual*
season-total half-PPR directly from weekly game logs (points + half a point per catch, summed over the
regular season). I deliberately do **not** use a pre-existing "points per game" column, because that
column throws away anyone who played fewer than 11 games — and a season projection has to include
injury-shortened and partial seasons as the low outcomes they really were. A player who was on a
roster but never played is a zero. This means the model is learning *expected season total* — rate and
availability jointly — which is exactly the quantity a manager drafts on.

**Two models, one column.** A running back either has at least one prior NFL season (a **veteran**) or
none (a **rookie**). These are genuinely different prediction problems: veterans have real NFL
production to lean on, rookies have only college and draft signals. So I train two separate models and
merge their outputs into one projection column. Every player is scored by exactly one of the two — the
split is clean and complete.

**Leakage discipline.** The cardinal sin in this kind of work is **leakage** — letting the model peek at
information it wouldn't actually have on draft day. I guard against it hard: every feature is either
prior-season (last year's stats) or knowable at draft time (draft slot, age, college, combine). The
thing being predicted — this season's total — is never itself a feature. When a player missed a season,
his "prior" fields come back blank rather than silently carrying forward two-year-old stats.

**Validation — walk-forward.** To estimate how good the projection really is, I use **walk-forward
testing**: to score the 2021 season I train only on 2014–2020; for 2022 I train on 2014–2021; and so on
through 2025. The model never sees the season it's being graded on. I test 2021–2025 because that's the
range where Sleeper's projection is available to compare against.

**How the model and its settings get chosen.** For each model I try four algorithm families (three
gradient-boosted tree methods — CatBoost, LightGBM, XGBoost — and a regularized linear model,
ElasticNet) across a fixed grid of settings that I wrote down *before* seeing any results. The choice of
which family and which settings to use is made **only** by an inner round of cross-validation on the
training seasons — never by looking at the test season. This "nested" structure is what keeps the
reported accuracy honest rather than flattered by hindsight. LightGBM won every fold.

**Missing data.** Some features are missing for some players (an old combine number, a rookie with no
prior-team context). I never invent values. The tree models handle blanks natively — they learn an
"unknown" branch. The linear baseline, which can't take blanks, gets a per-feature median fill plus a
flag marking that the value was missing.

**One feature I dropped, and why.** I originally included each back's preseason depth-chart rank
(starter vs. backup) — a genuinely powerful signal. But the depth-chart data source stops at 2024: it
has nothing for 2025 or 2026. Because that feature was well-populated in training but entirely absent for
exactly the season I need to project (2026) and my most recent test season (2025), it broke the tree
models — a back like Bijan Robinson got projected near zero. So I dropped it. That decision is recorded
as a formal amendment to the project's pre-registration, made because the data doesn't exist for the
target season, not because I was fishing for a better number.

**What ships.** The merged projection column (veteran + rookie), shown on the Rookie Board page beside
Sleeper's projection and the difference between them, replacing an older, weaker per-game surface.

## 3. A map of the key files

| File | What it is |
|---|---|
| `PREREG_rb_projection_2026-07-21.md` | The pre-registration: every choice (target, features, models, validation) frozen in writing before any model was fit, plus Amendment 1 (dropping depth rank). |
| `build_rb_projection.py` | The whole pipeline: assembles the two feature matrices, runs the walk-forward, and (in `--ship` mode) fits the final models and writes the outputs. |
| `rookie_deploy_recovery.py` | Deploy-only identity recovery: if nflverse has not assigned a new draftee's GSIS ID but the season dataset already has one, restores that player's existing college/PFF profile by normalized name. It never changes historical training rows or the frozen hit-probability harness. |
| `rb_projection_harness.py` | A synthetic-data proof that the machinery routes players correctly, detects planted signal, and screams on a deliberately leaked target — run before trusting any real number. |
| `models/rb_veteran_model.pkl`, `models/rb_rookie_model.pkl` | The two trained deploy models. |
| `results/rb_projection_2026.csv` | The full 2026 RB projection (veteran + rookie) with Sleeper and the difference. |
| `results/rb_rookie_board_projection.csv` | The rookie-only slice the Rookie Board page reads. |
| `results/walkforward_predictions.csv`, `results/sleeper_comparison.csv` | The backtest predictions and the Sleeper comparison, saved for the record. |

The raw PFF college tables are licensed and never stored in this repo; the rookie feature matrix that
uses them is regenerated in a temporary folder each run and never written here.

**Deploy refresh.** After a source-identity correction or an in-season data refresh, first run the
position's `--assemble` step, then `--refresh-deploy`. The latter re-scores only the 2026 rows with the
already-saved veteran and rookie models, rewrites the two derived projection CSVs, and asserts the model
file hashes did not change. It is deliberately not a retrain. A hard guard stops the build if a drafted
2026 RB/WR/TE would otherwise be scored with no college, combine, or PFF profile at all. QB rookie
projections remain withheld by design.

## 4. Honest results

I report every number with its sample size, its date range, and the baseline it's measured against.

**Backtest accuracy (walk-forward, 2021–2025, 802 back-seasons).** Pooled across the five test seasons,
the projection's rank correlation (Spearman — how well it orders players from best to worst, where +1 is
perfect and 0 is useless) with the actual season totals is **+0.69**; average absolute error is about 38
half-PPR points. Split out, veterans rank at +0.71 and rookies at +0.55 — rookies are harder, as
expected. The five individual seasons are stable, ranging from +0.64 to +0.74, with no collapse.

**Versus the market (Sleeper).** On the 486 back-seasons where Sleeper published a projection,
Sleeper ranks players better than I do: **Sleeper's Spearman is +0.80 against my +0.67**, and its average
error is lower (about 42 vs. 49 points on that subset). Read plainly: **my from-scratch projection does
not beat Sleeper**, and it is a little conservative on the very top players. This is the expected result —
the market is good — and it is shown, not hidden. Sleeper's number sits right next to mine on the board.

**A concrete case — the rookie fix.** The surface this replaces was a per-game model that ignored role
and playing time. It projected the 2026 rookie Jeremiyah Love, a high draft pick, at about 4.7 points per
game — the same as a late-round back — because it was nearly blind to draft capital and dominated by his
landing spot's thin vacated workload. The new model projects Love at about **153 season-total points**
(roughly 9.5 per game), the #2 rookie back and inside the top 15 overall. He still lands below Sleeper's
212 because his 2026 landing spot genuinely offers limited vacated work — but that judgment now shows up
on a real season scale instead of collapsing to a flat per-game rate.

**What's untested and provisional.** This is **backtested, not live-validated** — its first true live
test is the end of the 2026 season. The 2026 inputs are provisional: as of this writing the vacated-share
features are ~84% populated, prior-team pass rate ~60%, ADP-implied role only ~35%, and "did the team
change quarterbacks" is undeterminable before the season and reads as zero for everyone. These firm up
through August, and the 2026 projection should be re-run as they do. Wide receivers, tight ends, and
quarterbacks have no projection here yet.

## 5. The rules and fences that govern it

- **Sleeper is shown, never a gate.** The market comparison is displayed for context. "Beating Sleeper"
  is not and will never be a condition this product must satisfy to ship — the same discipline as the
  closed seasonal campaign, where beating the market was hard and the honest product shipped anyway. This
  fence exists so no future session quietly turns a context number into a success bar.
- **The old per-game model is untouched.** The prior `rookie_ppg_model.pkl` is retired from *display*
  only; its file is byte-for-byte unchanged (I assert its checksum on every build). Retiring a surface is
  not the same as retraining a model.
- **No licensed PFF data in this repo.** Raw college PFF tables stay out of the repository entirely; only
  derived projection numbers are written, and only to the `results/` folder. The feature matrix that
  touches PFF is rebuilt in a temporary folder each run.
- **Pre-registration is law.** Features, models, settings, and validation were frozen in writing before
  any model was fit, so they can't be shopped against the outcome. The one change since — dropping depth
  rank — is a written amendment justified by the data not existing for 2026, and it only *removes* a
  feature; it can't be used to fish for a better result.
- **Every projection carries its honesty label.** On the board the projection reads as backtested, not
  live-validated; the position coverage of the moment (RB and WR so far); and explicitly not a claim to
  beat Sleeper. Those labels stay until a live season earns their removal.

## What's different for the other positions

Each later position uses the **same machinery** — same target, two-model split, walk-forward, frozen
model slate, and "Sleeper shown, not gated" rule — with a position-appropriate feature set. Every build
also excludes the depth-chart-rank feature from the start (its data stops at 2024, so it was missing for
exactly the 2026 season I project — it had broken the RB trees until I dropped it) and runs a check that
no *other* feature has that "present in training, absent for 2026" problem.

**Wide receivers** swap the running-back college block for a receiving one: college receiving production
and the PFF receiving grades (route grade, yards-per-route-run, contested-catch rate, drop rate). Results
(2021–2025, 1,242 receiver-seasons): rank correlation **+0.74** (veterans +0.74, rookies +0.68). Against
Sleeper on the 657 covered seasons, **Sleeper ranks a little better (+0.80 vs. +0.74)** but the average
errors are essentially even (38.5 vs. 39.2) — I do not beat the market on ranking, though closer than RB.
Like RB it is conservative at the very top (Chase, Lamb, Nacua below Sleeper), so a large negative gap on
a star is the model's low-bias, not a signal.

**Tight ends** use that same receiving feature set (tight ends are receivers too), with two cautions.
It is the thinnest of the three receiving positions (~22–27 rookie test players a season), and TE scoring
is lopsided — a few every-down tight ends score a lot, a long tail near nothing — which flatters the
average-error number and makes ranking the real producers the hard part. It held up better than I
expected: **+0.73** pooled (veterans +0.74; the thin rookie arm +0.64, a bit above RB's +0.55, partly
because the heavy zero mass is easy to order). Sleeper is still better (+0.80 vs +0.74). One surprise:
the TE model is *less* conservative at the top (it projects Kyle Pitts and George Kittle *above* Sleeper).

**Quarterbacks are the one place I held part of the model back.** QBs use a passing set — college passing
*grades* (accuracy, completion, big-time-throw rate, pressure handling) rather than a box-score — and the
*veteran* model works fine (ranks QB seasons at **+0.70**). But the *rookie* model failed the honesty
test, so I did not ship it: there are only 7–13 rookie QBs a year, and a rookie QB's season hinges on the
one thing the data can't see — whether he starts. Fit anyway, it mostly re-sorted players by draft
position (which the market already prices) and projected full starter seasons for QBs everyone expects to
sit (a mid-round rookie the market pegged at ~14 points came out at ~136). So **QB veterans are projected
and QB rookies show no projection.** And bluntly: quarterback is where the market is *best* — Sleeper ranks
QB seasons at +0.85 vs. my +0.73, the furthest behind the market of any position — and, like RB and WR,
the QB model is conservative on the very top. That completes all four skill positions.
