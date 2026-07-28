# The NFL Talent Score and College Talent Score — a plain-language guide

*Last updated 2026-07-27, after the per-position migration (SPEC R34–R41). There
are now **eight** dedicated builds — one for each of NFL and college × QB, RB, WR,
TE — and every board column reads one of them. The older single R29 build
(`talent_score_2026.csv`) still sits on disk but feeds no column any more;
`rookie_score_2026.csv` survives only as a fallback where a college build has no
coverage. I wrote this for a smart reader with no machine-learning background.
Full technical detail lives in SPEC.md.*

## 1. What this is trying to do

The Draft Board used to carry one context column: a single efficiency percentile.
I replaced it with two columns that answer two different questions.

The **NFL Talent Score** answers: *what does this player do with each opportunity —
each carry, route, or throw — separated from his situation, where that separation
is statistically possible?* It is a model-based estimate, which means a piece of
math produced it and the math can be wrong. It is not a summary of production. A
player who piled up numbers on volume alone will not score well here, and a player
stuck in a bad offense will not be punished for the offense where I can measure
the offense's effect.

The **College Talent Score** answers a different question for 2026 rookies: *how
did this prospect produce in college, measured against past prospects at his
position who reached the NFL?* It describes college production. It does not claim
to predict NFL careers or fantasy outcomes, and I say that plainly because rookie
projection is exactly where numbers get oversold.

**Two hard limits on the college side, stated up front.** There is no
strength-of-schedule adjustment anywhere in it — a carry against Alabama and a
carry against a Group of Five defence count the same, which is why several of the
top 2026 college scores belong to small-school players the draft market did not
rate. And the underlying charting data covers **FBS only**, so a prospect from a
smaller division can never be scored and renders blank by construction, not by
failure.

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
On the NFL side, players are joined across sources by their league ID, never by
name, after a name-matching bug once swapped two players with the same surname.
**The college side cannot do that**, and it is worth being explicit about why: a
brand-new rookie has no league ID yet, so he carries a placeholder, and the rookie
board's placeholders do not always match the season dataset's for the same person.
No shared ID namespace exists between the college charting data and my NFL data.
So those four joins are name joins — but *guarded* ones: a name that is ambiguous
on **either** side is refused and left blank rather than guessed. When I first
tried to force an ID join there, it silently produced a confident wrong answer —
it matched four long-retired players as this year's rookie class and zero of the
actual ones. Blank is the honest output; a wrong player is not.

**Facets.** Each position gets a small set of per-opportunity measures I call
facets — things like broken tackles per carry, yards after catch versus what the
catch situation predicted, or completion rate versus expectation. Volume is
excluded by design: how often a player is used tells you about his coach's plans,
not his per-play skill. Each facet had to pass six admission gates (section 5)
before it could ship.

**Situation adjustment — what the shipped scores actually do, corrected 2026-07-27.**
The earlier version of this guide described a week-grain model that split each
week's performance into the player's own effect, his team-season's effect and the
opponent's effect, and netted the last two out. **That was the retired R29 build.
None of the eight shipped per-position scores does it.** R34–R41 standardise each
facet within position within season, decay older seasons, and shrink toward the
position mean by sample size — there is **no team term and no opponent term
anywhere in them.**

So the honest statement is the weaker one: these scores are per-opportunity rates
and grades, not situation-adjusted estimates. A back running behind a better line
and a receiver catching passes from a better quarterback are not compensated for
it. (The one thing the facet *choice* does is avoid rewarding volume, which is a
coach's decision rather than a player's skill.) On the college side there is
additionally no strength-of-schedule adjustment. I would rather state the limit
than claim an adjustment the code does not make.

**Quarterbacks are the asterisk.** One starter per team means a QB's situation
cannot be separated from him — the QB largely *is* the passing situation. So QB
scores ship unadjusted: a different kind of estimate under the same column header.
The NFL QB build (R34) scores nine facets on the ~49 quarterbacks who cleared 300
dropbacks across 2023–25: passing grade, completion rate versus expectation
(overall and on throws of 20+ air yards), big-time-throw and turnover-worthy-play
rates, accuracy, EPA per dropback, performance under pressure, and designed
rushing. Pressure **is** now measured — the earlier build could not see it — but it
sits on a small enough sample that it contributes little, which is the honest
caveat to keep rather than a gap to claim I closed.

Two consequences I have not engineered away. Designed rushing carries a quarter of
the composite, so **an immobile quarterback cannot score well here** however well
he throws. And what the set still does not measure is off-script improvisation and
pre-snap work.

**Multiple seasons.** Recent seasons count more, on a declared decay (about a
3.5-season half-life). Declared means I chose the number and wrote it down rather
than fitting it to results — an age-22 season and an age-29 season are different
physical players, and no autocorrelation study can settle that honestly.

**The reliability weight, w.** Every facet estimate gets shrunk toward the
position average based on sample size: w runs from 0 (no data, fully shrunk) to 1
(huge sample, barely shrunk). The shrinkage constant is derived from the data —
how noisy single plays are versus how much players truly differ. This is the
confidence channel, and it is where volume actually lives: a thin sample gets a
low w, not a low score — and below his position's volume floor, no score at all.
(No interval is computed or shown anywhere: `ci_lo`/`ci_hi` exist only in the
retired R29 artifact, and no shipped build emits them. The † / ‡ markers described in
earlier versions of this guide belonged to the R29 display and **do not render on
the current board** — today a player below his position's volume floor is simply
left blank rather than flagged.) The uncertainty is real whether or not it is
printed: read ranks before single numbers.

**The scale.** Scores are clipped to **50–99** within each position (40–99 for the
college QB build, an inconsistency I have recorded and not yet resolved), anchored
so the 90s are elite. **50 is the floor of the display, not a league-average
player** — a score sitting exactly on 50 or 99 is pinned by the clip, not measured
there. The estimator is not the constrained empirical-Bayes method earlier versions
of this guide described (that was R29): each shipped build applies **per-facet
method-of-moments reliability shrinkage** and then a two-point anchor onto the
0–100 scale. The caution that does apply is a double shrink — a thin facet is
pulled toward the position mean, and an early-career player is then pulled again
toward his college prior, so his composite moves twice. **Ranks are the reliable
read; there are no ranges to read.**

**Early-career players and the pipe — rewritten 2026-07-27.** A player in his
first three NFL seasons gets a college prior blended into his NFL estimate. This
now happens at **all four positions**, not just running back: the earlier "WR and
TE are NFL-data-only" statement described the retired R29 build and is no longer
true — `nfl_wr_score_2026.csv` and `nfl_te_score_2026.csv` both carry the blend.
A veteran takes **zero** college regardless of how thin his recent window is; the
window decides which football describes him, never whether I know him at all.

**What the blend actually consumes, and why that matters.** Each NFL build reads
its own college sibling — the NFL RB score blends the **R36 PFF college index**,
not the older play-by-play one. That distinction is load-bearing, because the two
measured differently: the play-by-play index reached 0.474 noise-corrected /
0.215 raw (n=300 drafted RBs, college finals 2016–2023) while **the R36 index
that actually ships in the blend fired at rc +0.329 — below my bar, DEAD.** The
build's own provenance file records it as "descriptive, not validated," and that
is the honest label. Do not cite 0.474 as the strength of what ships; it belongs
to an instrument the current blend does not consume. (The older 0.385 figure came
from a flawed sample and is retired outright.)

Every college instrument came back below the bar, so none of them may be cited as
validation of anything. The empirical-Bayes weighting handles this on its own
without intervention — among the players who blend at all, the college share sits
around 0.06–0.07 at receiver and tight end. It is a small descriptive nudge, not a
prediction.

**The college side (2026-07-27).** Every position now has its own dedicated
college build, each scored on charting facets rather than box-score counting
stats, and each anchored on past prospects at that position who reached the NFL:

- **QB (R35)** — six facets: passing grade, accuracy, big-time-throw and
  turnover-worthy-play rates, designed rushing, and pressure. Rushing carries as
  much weight as passing grade, ratified knowingly. 742 quarterbacks scored. On
  the boards this build **fills blanks only** — the older box-score build carried
  no quarterbacks at all, so there was nothing to overwrite.
- **RB (R36)** — rush and receiving facets, 65/35 nominal. 1,395 backs.
- **WR (R38)** — route grade and yards per route run dominate. 2,872 receivers.
- **TE (R40)** — the same receiving shape, on the thinnest panel. 1,101 tight ends.

RB, WR and TE **replace** the older box-score value wherever they cover a player.
That was an owner decision, and I disagreed with it on the RB side: the box-score
instrument's play-by-play sibling measured *better* against NFL outcomes than this
one did. The older values remain recoverable on disk; nothing was overwritten in
the artifacts, only in what the boards display.

**The honest verdict on all four: they are dead as predictors.** Each was measured
against NFL outcomes under a pre-registered rule and each came back below the bar.
They ship as a description of what a prospect did in college, and that is the only
thing they may be cited as. A high college score attached to a future bust is the
instrument working as described, not failing.

A recurring lesson from building them, worth stating because it is not obvious:
**a facet measured on very few plays contributes far less than its stated weight.**
Contested catches are the clearest case — a college tight end sees a median of
seven a season, so that facet lands near 3% of the composite whatever number I
write next to it. And when I tried raising the weight to compensate, the archetype
players the facet exists to reward moved the *wrong* way, because the weight has to
come out of facets they were already good at. I measured that before reading any
anchor results, and left the weights alone.

No hand, including mine, moved a weight to flatter a player. **The two columns are
two different scales**: the NFL column ranks NFL players against NFL players, the
college column ranks prospects against past prospects, and a 90 in one is not a 90
in the other.

## 3. Map of the key files

| File | What it is |
|---|---|
| `config.py` | The owner-ratified weights (dated R-numbers), position override, name aliases — the only place tuning lives |
| `facets.py` | Builds every facet's input data, with schema checks and join audits |
| `model.py` | The week-grain situation model, split-half signal estimation, and the derived shrinkage constants |
| `composite.py` | Combines facets into the score, applies the scale, ranks deterministically |
| `build_nfl_{qb,rb,wr,te}_score.py` | The four NFL builds (SPEC R34/R37/R39/R41) → `nfl_{pos}_score_2026.csv` |
| `build_college_{qb,rb,wr,te}_score.py` | The four college builds (R35/R36/R38/R40) → `college_{pos}_score_2026.csv` |
| `*_score_2026.provenance.json` | One per build: spec, decay, weights, the shrinkage constants, the anchor pool, and the artifact's own checksum |
| `build_talent_score.py` / `build_rookie_score.py` | The earlier single-build entry points (R29), retained but no longer feeding a board column |
| `talent_score_2026.csv` | The R29 artifact. **Superseded at every position — feeds no rendered column.** Kept on disk, unregenerated, hash-pinned |
| `rookie_score_2026.csv` | The R29 rookie artifact. Now a fallback only, where a college build has no coverage |
| `SPEC.md` | The full ruled architecture, including the frozen-artifact fence |
| `rho_provenance.json` | The archived college-agreement measurements, all four registered estimators |
| `research/` | The pre-registration and results of the pressure-facet screen |
| `tests/` | The build tests plus golden regressions; the repo root adds `tests/test_nfl_qb_score.py` and `tests/test_college_qb_score.py`, which pin the per-position board wiring, the guarded name joins, and the rule that importing a build must never run it |

## 4. Honest results

**Volume is excluded by design, and that has a visible consequence:** some famous,
heavily-used players rank lower here than their reputation, because reputation
often tracks volume and this column deliberately does not. The confidence channel,
not the score, is where usage shows up.

**The college-to-NFL agreement numbers are modest and I ship them anyway** — and
in July 2026 I re-measured all of them on a corrected sample after finding my
original panel scored ~38% of its players on incomplete college careers. Corrected
numbers (pre-registered one-shot; drafted players, college finals 2016–2023;
noise-corrected / raw): **RB play-by-play 0.474 / 0.215 (n=300)** — the strongest
of them, and still weak. RB box-score fell to 0.298 (the old 0.385 came from the
flawed sample and is retired), WR is near zero on every instrument (box 0.028,
play-by-play 0.086, n≈305 — and near zero again across athletic, age, and
breakout-age features in a noise-controlled sweep), TE 0.295–0.312. All are lower
bounds because only players who made the NFL can be measured.

**Corrected 2026-07-27 — read this before quoting 0.474.** That figure belongs to
the play-by-play index, and **the shipped blend does not consume it.** Each NFL
build reads its own college sibling, so the NFL RB score blends the R36 PFF
college index, which fired at **rc +0.329 — below the bar, DEAD**. The same is
true at WR and TE, whose instruments are dead too. So the accurate summary is:
**no college instrument ships as a validated signal at any position**; all four
ship descriptively, the blend is a small empirical-Bayes nudge, and the earlier
"RB-only, labeled weak signal" framing no longer describes what the code does.

**The rookie index barely lines up with fantasy scoring, and I keep the honest
label.** As a report-only check against each prospect's best per-game half-PPR
season in his first three NFL years, the rank correlations are weak-to-nothing:
0.283 for running backs (n=166), 0.261 for tight ends (n=107), and 0.086 for
receivers (n=244, measured on a since-reverted fitted variant — the shipped equal
weighting was not separately measured and its NFL-talent agreement is ~zero).
That is the measurement behind the sentence up top: the College Talent Score
describes what a player did per opportunity in college; it does not claim to
predict his NFL or fantasy outcome. The four charting builds that replaced these
box-score instruments in July 2026 were each measured the same way and each came
back dead too — replacing the instrument did not rescue the claim, and I am not
going to pretend it did.

**The pressure screen came back negative on the R29 facet family** — sacks per
pressure repeated at 0.266 against a 0.30 bar, pressure rate turned out to measure
the offensive line rather than the quarterback, and pocket time could not be
measured reliably enough to judge. The R34 build reaches pressure through a
different source (a charted pressure passing grade) and does include it, but at
low measured reliability, so it contributes little. The gap is narrowed, not
closed.

**Some facets sit on far too few plays to carry their weight.** Across the eight
builds the worst cases are contested catches (a median of seven a season for a
college tight end), deep targets, and per-target EPA at tight end — each lands at a
few percent of the composite regardless of the weight written next to it. They stay
in because dropping them costs more than it gains, but they are effectively
decorative, and I would rather say so than imply the stated weights are what the
score actually does.

**Within a position, some facets are correlated with each other** (notably at QB),
so a position's facets are not fully independent reads. I disclose them rather than
pretend otherwise.

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
  logic, dated and ratified in `config.py`; no automated search chooses them. Two
  deliberate exceptions, both pre-registered and one-shot against my NFL talent
  estimate (rule written first): the RB rookie index is scored on the frozen
  play-by-play instrument that measured 0.474 (weak); the WR/TE rookie weights were
  put to a fitted test — WR's fit did not replicate on the corrected sample and
  was reverted to equal, TE's fit failed its gate and stayed equal. There I wanted
  the data, not my hand, to choose — and I accepted the answer when it said "equal."

The one-line version of this whole document: two honest, uncertain, deliberately
narrow measurements — shown with their uncertainty, fenced away from the value
columns, and documented where they fail.
