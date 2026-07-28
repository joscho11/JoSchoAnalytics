# A guide to the weekly fantasy model

This is the plain-language tour of the weekly fantasy football projection system — the part of
the project that predicts how many fantasy points each player will score *next week*. It's
separate from the pre-season Draft Board, whose projection engine is documented in
`fantasy/projections/GUIDE.md`, whose talent columns are in `fantasy/talent/GUIDE.md`, and whose
closed band-research campaign is in `fantasy/seasonal_projections/GUIDE.md`.
I built and run this, and my aim here is to explain how it
works and to be straight about how good it actually is.

## What I'm trying to do

Every week during the NFL season, I want a good estimate of how many fantasy points each skill
player — quarterback, running back, wide receiver, tight end — will score in their next game.
"Fantasy points" here means half-PPR scoring, a common system where a player gets points for
yards and touchdowns plus half a point per catch (PPR stands for "points per reception," and
"half" means half a point each). These projections do two jobs: they help set weekly lineups,
and they feed the DraftKings lineup optimizer (its own guide is in `fantasy/dfs/`).

The bar I have to clear is not "predict points" in the abstract — it's "predict them better than
the obvious simple method." The obvious method is to just average a player's last three games and
call that the projection. If my model can't beat that, it isn't worth running. So a three-week
rolling average is the baseline every result is measured against.

A quick note on why this is a *different* model from the betting side and the Draft Board. The
betting model predicts team outcomes; the Draft Board predicts a whole season before it starts.
This one predicts a single player's next game, using how they've been used and performing
recently — information that only exists *during* the season.

## How it works, end to end

**Data in.** A pipeline pulls and joins everything I need from nflreadpy (a public NFL data
library): player game stats, expected-points data, schedules, Vegas lines, weather, injury
reports, and depth charts. That lands in one big table, `raw_dataset.csv`, about 35,000 rows —
one row per player per week — by 84 columns.

**Features.** From the raw table I build the model's actual inputs (called features). The core
ones are rolling averages — a player's production over their last 3 and 5 games — plus the
*trend* between them, which is just the 3-game average minus the 5-game average: a positive trend
means a player is heating up, a negative one means cooling down. I add matchup difficulty (how many
fantasy points a defense has been giving up to that position lately, which separates a soft matchup
from a tough one), the strength of the opponent overall, and the team's Vegas implied point total —
how many points the betting market expects that team to score, which is one of the strongest
available hints at game flow, since a team expected to score a lot gives its skill players more
chances. On top of that I fold in weather, and whether the player is healthy and starting according
to the latest depth chart. All of that produces `features_dataset.csv`, about 40,000 rows by 97
columns.

Why these inputs and not just last week's points? Because a single game is noisy — a player can
have a quiet week against a great defense and a huge week when the script breaks his way. Averaging
recent form smooths that out, the trend catches players whose role is genuinely changing, and the
matchup and game-total features capture the *situation* the player is walking into, which last
week's raw score can't see.

**No leakage.** The same discipline as the betting side applies: every rolling number is computed
with a one-week shift, so a player's current-week stats can never sneak into their own
current-week prediction. There's one fantasy-specific twist I want to call out, because it's a
subtle trap. When I attach a player's prior-season numbers, I don't just grab "the row above" —
I do an explicit season-to-season join keyed on the player. The reason: a player who missed a
whole season should get a blank for that season, not have his stats from two years ago quietly
pulled forward as if nothing happened. Getting this wrong doesn't crash anything — it just makes
the model silently wrong, which is worse.

**The models.** I train one model per position — a separate XGBoost regressor (a tree-based model
that predicts a number) for quarterbacks, running backs, receivers, and tight ends. Each learns
its position's own scoring pattern. They train on 2020–2024 and I hold out 2025 as a clean test
season. Each is saved as a model file in `fantasy/models/`.

**Prop models.** On top of the four main models, I train eight more that predict *individual*
stats rather than total points — passing yards, rushing yards, receiving yards, and receptions,
split across the positions where each matters. These exist as a reference for prop bets, where the
question isn't "how many fantasy points" but "will this specific stat land over or under the number
a sportsbook posted." Each of the eight uses the same features as its position's main model but
aims at a different target — a receiver's receiving-yards model and his receptions model share
inputs but predict different things. One honest caveat I want to flag: these eight are independent
models, so their stat predictions won't add up to exactly the same number as the main points
projection. That's expected — each was trained to be as accurate as it can be on its own stat, not
to reconcile with the others — but it means they're a reference, not a tidy breakdown of the points
number.

**Weekly run.** During the season, an inference pipeline detects the next unplayed week, pulls
that week's game context (spread, total, weather, home/away), takes each player's most recent form,
rebuilds the live defensive-matchup numbers from the current season's play-by-play, folds in the
latest injury and depth-chart status (and drops players ruled Out), runs all twelve models, and
writes the week's projections to a CSV. That file is what the dashboard's Weekly Fantasy tab and
the DFS optimizer read.

## A map of the key files

| File | What it is |
|---|---|
| `fantasy/data_pipeline.ipynb` | Pulls and joins the raw data into `raw_dataset.csv`. |
| `fantasy/features.ipynb` | Builds the model inputs into `features_dataset.csv`. |
| `fantasy/model.ipynb` | Trains and evaluates the per-position models. |
| `fantasy/retrain_models.py` | The one command that retrains all twelve models (4 main + 8 prop) consistently. |
| `fantasy/predict_fantasy.ipynb` | The weekly run that writes the projections. |
| `fantasy/models/*.pkl` | The trained model files. |
| `fantasy/fantasy_projections/` | The weekly projection CSVs the dashboard reads. |

## Honest results

On the held-out 2025 season, the model beats the three-week-average baseline at every position.
Here's the full picture — I'm showing the error (mean absolute error, the average number of
fantasy points the projection is off by; lower is better) next to the baseline's error:

| Position | Test rows | Model error | Baseline error |
|---|---|---|---|
| Quarterback | 571 | 6.81 | 7.49 |
| Running back | 1,397 | 4.40 | 4.59 |
| Receiver | 2,215 | 3.96 | 4.06 |
| Tight end | 1,145 | 3.16 | 3.48 |

So the model is a real improvement over the naive method, but a modest one — it shaves roughly
half a point to two-thirds of a point of error off the baseline. That's genuinely useful for
setting lineups and building DFS rosters, and I'm not going to dress it up as more than it is.
Tight ends have the lowest error because tight-end scoring is the most concentrated and
predictable week to week; quarterbacks have the highest because their scoring swings the most.

What's untested: the eight prop models exist and are trained the same way, but I don't publish a
verified live hit-rate for them against real sportsbook prop lines — treat them as a reference
signal, not a proven edge.

## The rules and fences, and why they exist

- **The three-week average is the baseline, always.** A projection model that can't beat a simple
  average isn't earning its complexity. Every result is stated against it.
- **Every rolling feature uses a one-week shift.** No current-week information reaches a
  current-week prediction. This is the difference between a model that works and one that only
  looks like it works in a backtest.
- **Prior-season stats use an explicit player-keyed join, never a positional shortcut.** A missed
  season becomes a blank, not stale data pulled forward. Silent wrongness is the danger here.
- **2025 is held out on purpose.** I keep a clean, unseen season to measure against and improve
  toward. When I eventually fold 2025 into training, I do it deliberately, not by accident.
- **The projection CSVs live in `fantasy/fantasy_projections/` and nowhere else.** The dashboard
  and the writer both depend on that exact path; moving it silently breaks the weekly run.
- **The prop models don't reconcile to the points model,** and I say so — they're independent
  estimates for a different question, not a breakdown of the points projection.

The short version: a genuine, modest improvement over the simple baseline at every position,
useful for lineups and DFS, with the prop models offered as a reference rather than a proven edge.
