# NFL Talent Score & College Talent Score — disclosure copy (DRAFT for owner sign-off)

First-person singular throughout. Expands SPEC §f. Every claim below is bound by
the website content law: disagreements described, never verdicts; aggregate
patterns, never player-level calls; no model-performance claims.

> **Revised 2026-07-27** for the per-position migration (SPEC R34–R41). The two board columns are
> now **NFL Talent Score** and **College Talent Score**, fed by eight dedicated builds rather than
> the two R29 artifacts this copy was originally written against. The paragraphs below have been
> brought into line; anything describing the R29 display (the †/‡ confidence markers, the advanced
> view, the 0.385 agreement figure) was retired with it.

---

**What the NFL Talent Score is.** It is a model-based estimate of what a
player does with each opportunity — each carry, route, or throw — separated from
his situation where that separation is statistically identifiable. It is not a
summary of his production, and models can be wrong. Volume is excluded by design:
how often a player is used tells you about his coach's plans, not his per-play
skill. A player with fewer opportunities gets a lower confidence weight — and,
below his position's volume floor, no score at all — never a lower score for the
missing volume.

**How to read the number.** Scores are clipped to **50–99** within each position (40–99 for the
college quarterback build, an inconsistency I have recorded and not yet resolved). **50 is the
floor of the display, not a league-average player** — a score sitting on 50 has been clipped
there and could belong further down. A player below his position's volume floor is left **blank**
rather than placed on another position's scale. The uncertainty behind each number is real
whether or not it is printed, so read ranks before single numbers.

**One caution the math requires — restated 2026-07-27.** The earlier version of
this paragraph described a constrained empirical-Bayes estimator that traded
per-player precision for an honest spread, and told you to read "ranks and
ranges". **That was the retired R29 build, and no range is computed or shown
anywhere today** — no shipped artifact carries an interval and the board renders
none. The caution the shipped math actually requires is a double shrink: each
facet is pulled toward the position mean by how little data sits behind it, and
then an early-career player is pulled again toward his college prior, so his
composite moves twice. And a score sitting exactly on the clip floor or ceiling
is pinned there, not measured there. Read ranks before single numbers.

**What the College Talent Score is.** For 2026 rookies at **all four positions** — QB, RB, WR and
TE — it is a college-production read, scaled against past prospects at the same position who
reached the NFL. Each position has its own dedicated build. It describes what the player did in
college; it does not claim to predict NFL performance or fantasy value.

**Two limits on it I will not paper over.** There is **no strength-of-schedule adjustment**:
production against a weaker opponent counts exactly the same as production against a stronger one,
which is why several of the highest college scores belong to small-school players the draft market
rated far lower. And the underlying charting data is **FBS only**, so a prospect from a smaller
division can never be scored — that blank is by construction, not a failed lookup.

**Two different scales.** The NFL Talent Score ranks NFL players against NFL players; the College
Talent Score ranks prospects against past prospects. A 90 in one column is not a 90 in the other,
and neither column feeds any other number on this board.

**Where college data enters a veteran's score.** For players in their first three NFL seasons I
blend a college prior into the NFL estimate; a veteran with a thin recent window takes **zero**
college, because the window decides which football describes him, not whether I know him at all.
Every college instrument I built was measured against NFL outcomes and every one came back below
my ship bar — so the blend is descriptive, never validation, and the empirical-Bayes weighting
drives the college share close to zero on its own (a median of about 6-7% at receiver and tight
end among the players who blend at all).

**Which number belongs to what — corrected 2026-07-27.** The old 0.385 agreement figure came from
a flawed sample and is **retired**. Its replacement, 0.474 noise-corrected / 0.215 raw (n=300),
belongs to the **play-by-play** college index — and **the shipped blend does not consume that
index.** Each NFL build reads its own college sibling, so the running-back blend takes the PFF
college index, which fired at **rc +0.329, below the bar, DEAD**; the build's own provenance file
records it as "descriptive, not validated". So: no college instrument ships as a validated signal
at any position, and 0.474 must not be quoted as the strength of what ships.

**Quarterbacks are measured differently.** One starter per team means a QB's
situation cannot be separated from him — the QB largely IS the passing situation.
So QB scores are unadjusted for situation: a different kind of estimate under the
same header, and I say so rather than pretend otherwise. QB facets measure passing grade,
completion rate versus expectation — overall and on throws of 20+ air yards — ball-placement
discipline, accuracy, efficiency per dropback, performance under pressure, and designed rushing.
Pressure **is** measured now, on a small enough sample that it contributes little. One consequence
I have not engineered away: designed rushing carries a quarter of the composite, so **an immobile
quarterback cannot score well here** however well he throws.

**How much situation the score removes — corrected 2026-07-27: none.** An earlier version of this
copy said team and opponent effects were separated out and explained roughly 8% of week-to-week
variance. That described the retired R29 build. **None of the eight shipped per-position scores
carries a team term or an opponent term** — they are per-opportunity rates and grades,
standardised within position within season and shrunk by sample size. A back running behind a
better line is not compensated for it, and on the college side there is no strength-of-schedule
adjustment either. What the facet choice does do is avoid rewarding volume, which reflects a
coach's plans rather than a player's skill. I would rather state the limit than claim an
adjustment the code does not make.

**Known soft spots, disclosed.** Within a position, some of my measures are
correlated with each other (notably at QB), so a position's facets are not fully
independent reads — I keep them because each passed its own admission gate.

The bigger one: **a measure taken on very few plays contributes far less than the weight I
assign it.** Contested catches are the clearest case — a college tight end sees a median of seven
a season, so that measure lands near 3% of his score whatever number sits next to it. Deep targets
and per-target efficiency at tight end are in the same position. I measured this before reading
any results, and when I tried raising the weight to compensate, the players the measure exists to
reward moved the *wrong* way, because the weight has to come out of measures they were already
good at. So the weights ship as ratified, and I would rather say the stated weights are not quite
what the score does than imply otherwise.

**What none of this is.** These columns never combine with the projections, the position ranks or
the gap columns — my testing showed efficiency measures do not predict draft-market error, so I
keep them strictly separate. Nothing here is a recommendation about any single player.
