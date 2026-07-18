# The Talent Score and Rookie Score — a plain-language guide

*Last updated 2026-07-16, at the R29 build (talent_score_2026.csv, 214 players;
rookie_score_2026.csv, 28 rookies). I wrote this for a smart reader with no
machine-learning background. Full technical detail lives in SPEC.md; the signed
disclosure copy is in reports/disclosure_final.md.*

## 1. What this is trying to do

The Draft Board used to carry one context column: a single efficiency percentile.
I replaced it with two columns that answer two different questions.

The **Talent Score** answers: *what does this player do with each opportunity —
each carry, route, or throw — separated from his situation, where that separation
is statistically possible?* It is a model-based estimate, which means a piece of
math produced it and the math can be wrong. It is not a summary of production. A
player who piled up numbers on volume alone will not score well here, and a player
stuck in a bad offense will not be punished for the offense where I can measure
the offense's effect.

The **Rookie Score** answers a different question for 2026 rookies: *how did this
prospect produce in college, measured against past drafted prospects at his
position?* It describes college production. It does not claim to predict NFL
careers or fantasy outcomes, and I say that plainly because rookie projection is
exactly where numbers get oversold.

Both columns are context only. A pre-registered test (H7 — a hypothesis whose
pass/fail rule I wrote down before looking) found that efficiency measures like
these do **not** predict where the draft market is wrong. So these columns never
mix with the board's price-comparison columns — not in the math, not in the
layout, not in a sentence. They tell you what a player does, not what he is worth
on draft day.

## 2. How it works, end to end

**Data in.** Play-by-play data (every NFL play since 2018, with an expected-yards
model attached), weekly rushing and receiving detail from Pro Football Reference,
and league tracking data used only as a numerator — never as a denominator,
because its coverage is incomplete and incomplete denominators quietly bias rates.
Players are joined across sources by their league ID, never by name matching,
after a name-matching bug once swapped two players with the same surname.

**Facets.** Each position gets a small set of per-opportunity measures I call
facets — things like broken tackles per carry, yards after catch versus what the
catch situation predicted, or completion rate versus expectation. Volume is
excluded by design: how often a player is used tells you about his coach's plans,
not his per-play skill. Each facet had to pass six admission gates (section 5)
before it could ship.

**Situation adjustment.** For running backs, receivers, and tight ends I fit a
model that splits each week's performance into the player's own effect, his
team-season's effect, and the opponent's effect. In plain terms: the model asks
"how does everyone do against this defense, and how does this offense lift or sink
everyone in it," and nets those out. The honest size of that adjustment is small —
team and opponent together explain roughly 8% of week-to-week variance. Most
week-to-week movement is noise, and the score is built to look through the noise,
not to deny it exists.

**Quarterbacks are the asterisk.** One starter per team means a QB's situation
cannot be separated from him — the QB largely *is* the passing situation. So QB
scores ship unadjusted: a different kind of estimate under the same column header.
The QB facets measure completion rate versus expectation (overall, and separately
on throws of 20+ air yards), ball-placement discipline, and rushing value. Just as
important is what the QB set does **not** measure: performance under pressure,
off-script improvisation, and pre-snap work. I built and screened a
pressure-performance facet family (sacks per pressure, pressure rate, pocket time)
under a pre-registered rule, and none survived — the best of them repeated
year-to-year at 0.27 where my bar is 0.30. Close, but a bar is a bar; those gaps
remain open and disclosed.

**Multiple seasons.** Recent seasons count more, on a declared decay (about a
3.5-season half-life). Declared means I chose the number and wrote it down rather
than fitting it to results — an age-22 season and an age-29 season are different
physical players, and no autocorrelation study can settle that honestly.

**The reliability weight, w.** Every facet estimate gets shrunk toward the
position average based on sample size: w runs from 0 (no data, fully shrunk) to 1
(huge sample, barely shrunk). The shrinkage constant is derived from the data —
how noisy single plays are versus how much players truly differ. This is the
confidence channel, and it is where volume actually lives: a thin sample gets a
wide range and a low w, not a low score. On the board, † marks lower-confidence
rows (w below 0.40) and ‡ the lowest (below 0.30). The interval around each score
is the honest uncertainty, and it is the primary display — read ranges before
single numbers.

**The scale.** Scores run roughly 40–99 within each position, anchored so the
90s are elite and 50 means the weakest draftable player — **not** a league-average
one. The estimator behind the display (a constrained empirical-Bayes method)
optimizes rank order and keeps the overall distribution honest, at a known cost:
an individual score is not each player's single best point estimate. Ranks and
ranges are the reliable reads.

**Early-career players and the pipe.** For running backs early in their careers, I
blend in a college prior at the strength I actually measured: the correlation
between my college index and my NFL estimate is about 0.385 at RB — weak, and
disclosed as weak. That correlation was measured against the unshrunk composite,
not the displayed score, and the displayed score applies reliability shrinkage on
top. At WR the measured agreement was zero and at TE it fell below my bar, so
receivers and tight ends early in their careers are NFL-data-only, shrunk toward
the position mean. For a several-year veteran the college share is about 10%.

**Rookies.** The Rookie Score covers RB, WR, and TE rookies on the 2026 ADP board
— including undrafted players the market is drafting — scored on a box-score
college index (production share, per-carry and per-catch efficiency) against a
pool of past drafted prospects. The weights inside that index are no longer a
placeholder. On 2026-07-17 a pre-registered, one-shot test — its pass/fail rule
written down before I looked — chose them by how well each college signal lines
up, out of fold, with my NFL talent estimate. For receivers the test put almost
all the weight on best-season dominator (the share of a college offense a player
accounted for) and none on final-season yardage share, which pointed the wrong
way; for running backs and tight ends the test kept equal weights. No hand,
including mine, moved a weight to flatter a player. No college QB instrument
ships, so rookie QBs show a dash in both columns with a note saying why. **The two columns are two different
scales**: the Talent Score ranks NFL players against NFL players, the Rookie Score
ranks prospects against past prospects, and a 90 in one is not a 90 in the other.

## 3. Map of the key files

| File | What it is |
|---|---|
| `config.py` | The owner-ratified weights (dated R-numbers), position override, name aliases — the only place tuning lives |
| `facets.py` | Builds every facet's input data, with schema checks and join audits |
| `model.py` | The week-grain situation model, split-half signal estimation, and the derived shrinkage constants |
| `composite.py` | Combines facets into the score, applies the scale, ranks deterministically |
| `build_talent_score.py` / `build_rookie_score.py` | The two build entry points, checkpointed and regression-tested |
| `talent_score_2026.csv` / `rookie_score_2026.csv` | The shipped artifacts (hash-pinned; regenerated only by an owner-ruled rebuild) |
| `SPEC.md` | The full ruled architecture, including the frozen-artifact fence |
| `rho_provenance.json` | The archived college-agreement measurements, all four registered estimators |
| `research/` | The pre-registration and results of the pressure-facet screen |
| `tests/` | 26 build tests plus golden regressions; the dashboard adds fence tests |

## 4. Honest results

**Volume is excluded by design, and that has a visible consequence:** some famous,
heavily-used players rank lower here than their reputation, because reputation
often tracks volume and this column deliberately does not. The confidence channel,
not the score, is where usage shows up.

**The college-to-NFL agreement numbers are modest and I ship them anyway:** RB
about 0.385, WR about zero (a well-powered null, n=278 players), TE about 0.254 —
all measured 2018–2025, all lower bounds because only players who made the NFL can
be measured. That is why the rookie blend is RB-only and labeled weak.

**Even with its weights re-set, the rookie index barely lines up with fantasy
scoring, and I keep the honest label.** As a report-only check I compared the
re-weighted index against each prospect's best per-game half-PPR season in his
first three NFL years: the rank correlation is 0.086 for receivers (n=244) —
essentially nothing — and 0.283 for running backs (n=166) and 0.261 for tight
ends (n=107), both weak. That is the measurement behind the sentence up top: the
Rookie Score describes what a player did per opportunity in college; it does not
claim to predict his NFL or fantasy outcome.

**The pressure screen came back negative.** All three candidate facets failed
their pre-registered gates: the best (sacks per pressure) repeated at 0.266
against a 0.30 bar; pressure rate turned out to measure the offensive line, not
the quarterback (it persists for players who stay put and collapses for players
who change teams); pocket time could not be measured reliably enough to judge. QB
pressure play stays an open, disclosed gap.

**One tight-end facet is fragile.** The TE broken-tackle measure shows no
separable player signal in nearly half of my resampling runs. It stays in the
composite because a one-facet TE score would be worse, but its low confidence
weight does the protecting and its rows carry the ‡ flag.

**Within a position, some facets are correlated with each other** (notably at QB,
and between the two TE facets), so a position's facets are not fully independent
reads. The sample is 31 scored QBs and TEs, too small to settle those correlations
precisely; I disclose them rather than pretend otherwise.

## 5. The rules and fences, and why each exists

- **Six admission gates for any facet.** Coverage must be measured, not assumed
  (a tracking feed once silently covered only a third of receiving weeks). The
  measure must be per-opportunity, not volume (volume is the market's information,
  not skill). It must persist year-to-year above a fixed bar (a stat that doesn't
  repeat is noise). It must not duplicate an existing facet (two copies of one
  signal double-count it). Workload is reported but never gates admission. And the
  data must show a separable player signal at all (estimated on 60 random
  split-halves, because a single split once produced a nonsense scale).
- **Pre-registration for anything that could flatter itself.** Decision rules are
  written to disk before results exist, and a failed screen is final — no
  re-running with adjusted thresholds. This is the only defense against a model
  grading its own homework.
- **Benchmarks are read-only report cards.** I keep a list of players whose
  placement I sanity-check, but no weight or parameter is ever chosen to move a
  named player — a permutation test showed a search like that can "hit" almost any
  list while quietly scrambling everyone else.
- **The H7 separation.** Because efficiency-over-expectation demonstrably does not
  predict market error, these columns never combine with the board's
  price-comparison columns — in code, in layout, or in copy. They say nothing
  about draft-day value.
- **Frozen artifacts.** The shipped CSVs are hash-pinned; a legitimate rebuild
  requires an owner ruling with old and new hashes reported. Nothing regenerates
  silently.
- **Weights are owner config.** Every weight vector is set by me on football
  logic, dated and ratified in `config.py`; no automated search chooses them. One
  deliberate exception: the rookie box-score index weights were set by a
  pre-registered, one-shot out-of-fold test against my NFL talent estimate (rule
  written down first, then ratified) — because there I wanted the data, not my
  hand, to choose among a few college signals.

The one-line version of this whole document: two honest, uncertain, deliberately
narrow measurements — shown with their uncertainty, fenced away from the value
columns, and documented where they fail.
