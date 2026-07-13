# A guide to the betting models

This is the plain-language tour of the betting side of the project: the model that bets NFL
point spreads, the experimental one that bets over/unders, and the language model that writes
up each game. I wrote all of it, and I run it live. My goal here is to explain how it works and
to be honest about what holds up and what doesn't — not to sell you anything.

## What I'm trying to do

When a sportsbook posts a line like "Chiefs by 7," that number is not their best guess at the
final margin. It's the number they think will split the betting money evenly, so they collect
their cut no matter who wins. To make money betting against that line, I don't need to predict
who wins — I need to predict which *side of the line* is mispriced, and I need to be right often
enough to overcome the book's cut.

That bar is a specific number. At standard pricing you risk \$110 to win \$100, so you have to
win **52.4%** of your bets just to break even. (That figure is called the break-even rate; it's
just the price of the bet expressed as a win percentage.) Everything on the betting side is
measured against 52.4%. Beating it consistently is hard because the line is already sharp — the
market has absorbed the injuries, the weather, and the public opinion before I ever see it. So
the honest question isn't "can I predict football," it's "can I find a small, repeatable edge in
an efficient market without fooling myself." Most of the engineering is about not fooling myself.

The right thing to measure against is the market, not a naive average. A model that beats
"predict the historical average" has proven nothing. The bars that matter are the opening line
(the book's first number) and the closing line (the book's final, sharpest number right before
kickoff). I'll be specific below about which one I beat.

## How it works, end to end

**Data in.** I pull play-by-play, schedules, injuries, and depth charts from a public NFL data
library called nflreadpy, going back to 1999. Every number a game's prediction uses has to be
knowable *before* that game kicks off — this is the single most important rule, because the
easiest way to build a model that looks brilliant and loses money is to accidentally let a game
see its own result. I enforce it with a technique called a rolling window with a one-game shift:
every "recent form" number for a game is computed only from earlier games. This is what people
mean by "no data leakage."

**Features.** From that raw data I build 85 numbers per game (these are called features — the
inputs the model learns from). The most important one is rolling EPA, short for Expected Points
Added, which measures how much each play moved a team toward scoring while accounting for down,
distance, and field position — a much better read on team quality than raw yards. Others include
strength of schedule (who a team actually played), a talent score built from All-Pro selections
with injured stars subtracted out, and situational stats like sacks and third-down rate. After
an ablation study (systematically dropping the least useful features and re-checking the score),
I cut the 85 down to the **35** that actually carry signal — fewer inputs means less room to
overfit, which is when a model memorizes noise instead of learning the pattern.

**The model.** I use an ensemble — a blend of several models — because different algorithms make
different mistakes, and averaging them cancels some of the noise. The primary model, which I call
Ensemble fixed75, is 75% XGBoost (a tree-based model good at capturing "this matters only when
that is also true" interactions) and 25% Ridge (a simple, stable linear model that doesn't chase
noise). It predicts the home team's margin, which I compare to the Vegas line to find an edge.

Separately, three models (XGBoost, Ridge, and LightGBM) each vote on which side to bet. When all
three independently agree *and* the ensemble's edge is at least 3 points, I call that a **HIGH**
confidence pick; agreement with at least a 1-point edge is **MEDIUM**; anything else is **PASS**
(no bet). Requiring both agreement and a real edge is a filter: it throws away the coin-flips.

**Validation.** I test the way the model would actually have been used: train on everything up to
a year, test on the next year, and step forward. This is called walk-forward validation, and it's
the only honest kind when time matters — you can never use the future to predict the past. On top
of that, the production models train through 2024 and I hold out 2025 entirely as a live test.

**Totals model.** The over/under market gets its own separate model, because "who's better" and
"how many points" are different questions. It leans on a known quirk: casual bettors love betting
the OVER, so books nudge the total a little high, which leaves the UNDER slightly underpriced. So
this model only bets UNDER, and only when two of its models agree. It uses the 35 spread features
plus 14 built for scoring (the posted total, weather including wind, pace, dome flag, and rolling
points). I keep it strictly separate from the spread model.

**The language model.** A large language model (an AI that reads and writes text — here, Claude)
writes a short analysis of each game using five tools that look up the prediction, live injuries,
line movement, and head-to-head history. It doesn't override the model; it's the qualitative
sanity check a raw number can't give — it flags when an injury or sharp money cuts against the
pick. Its write-ups are cached each week and shown in the dashboard.

## A map of the key files

| File | What it is |
|---|---|
| `betting/features.py` | The single source of truth for the 85-feature pipeline. All the models read from this. |
| `betting/model_comparison.ipynb` | Where I compare model designs and retrain the production spread models. |
| `betting/predict_betting.ipynb` | The weekly spread pipeline that pulls live data and writes predictions. |
| `betting/predict_totals.ipynb` | The weekly over/under pipeline. |
| `betting/sports_betting_agent.ipynb` | The language-model game write-ups. |
| `betting/models/*.pkl` | The trained models (saved model files). |
| `betting/predictions_tracker.csv` | The running log of every spread pick and its result. |
| `betting/test_features.py` | Automated tests that lock the feature pipeline (run on every change). |

## Honest results

**The spread model's real number is 64.2% against the spread versus the opening line, on its
HIGH-confidence tier** — that's 380 wins out of 592 bets, measured walk-forward and out-of-sample
across 2018–2025. Against a break-even of 52.4%, that's a real edge. In the 2025 live test (weeks
10–17, 117 graded games) the HIGH tier hit 64.7% (11 of 17), MEDIUM hit 59.5% (25 of 42), and
overall the model was 56.4%. The live samples are small and there will be losing weeks; the point
is to track it honestly over multiple seasons.

**One thing I'm careful about: the model does not beat the closing line.** Early on it looked like
it did, but that was a mirage — the model's most important feature is nearly identical to the
closing line itself (they correlate at 0.994), so "beats the close" was just the model echoing the
market. Measured honestly against the *opening* line, the edge is real (the 64.2% above); measured
against the *closing* line, there's no edge. So I never claim the model beats the close, and I
never claim what's called closing line value. Being able to state that plainly is the point of all
the validation discipline.

**The spread model is at its ceiling.** I ran a long list of "make it better" experiments —
weather features, re-weighting the ensemble, an extra "ULTRA" confidence tier, time-decay
weighting, extending the training data back to 2009. Almost all were rejected against a strict
bar. The lesson that kept repeating: the gains from here are in execution (shopping for better
prices, sizing bets, tracking closing line value), not in more model tuning.

**The totals model is experimental and I label it that way.** In cross-validation the UNDER-only
strategy hit 55.7% (on 575 picks), but the live sample so far is 52.2% on just 46 picks — right at
break-even, and far too small to tell a real edge from luck. So on the dashboard it carries an
amber "tracking only — do not bet" banner, and it stays that way until a full season of picks is
in.

## The rules and fences, and why they exist

- **Every result carries its sample size, date range, and baseline.** "64% ATS" alone is not a
  claim; "64.2% ATS-vs-open, 380/592, walk-forward 2018–2025" is. A number without those three
  things has fooled someone before and will again.
- **The feature list order is a contract.** The order of the feature lists determines the exact
  bytes of the trained models, so an automated test locks it. If I reorder features, I have to
  retrain and update the test in the same change. This exists because I once reordered a list "for
  readability" and silently changed every model.
- **A "refactor only" claim has to be proven, not asserted.** If I move model code around and
  claim it didn't change behavior, I prove it by checking the trained model files are byte-for-byte
  identical.
- **I never claim the model beats the closing line, and never claim closing line value** — see the
  0.994 correlation story above.
- **EXPERIMENTAL stays EXPERIMENTAL** until a full live season clears the bar. The totals model
  doesn't get promoted on a hot 46-pick stretch.
- **Live data beats the backtest.** When the test set and the small live sample disagree on a
  close call, I trust the live read for real-money decisions — that's how the ULTRA tier got cut
  after it fired only twice in seven weeks.

None of this is financial advice, and sports betting carries real risk. The honest summary is: a
real, measurable edge against the opening line on the confident tier; no edge against the closing
line; and a totals model that's promising but unproven.
