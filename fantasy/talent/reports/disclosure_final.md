# Talent Score & Rookie Score — disclosure copy (DRAFT for owner sign-off)

First-person singular throughout. Expands SPEC §f. Every claim below is bound by
the website content law: disagreements described, never verdicts; aggregate
patterns, never player-level calls; no model-performance claims.

---

**What the Talent Score is.** My Talent Score is a model-based estimate of what a
player does with each opportunity — each carry, route, or throw — separated from
his situation where that separation is statistically identifiable. It is not a
summary of his production, and models can be wrong. Volume is excluded by design:
how often a player is used lives in the confidence channel instead — a player
with fewer opportunities gets a wider range and a lower confidence weight, not a
lower score for the missing volume.

**How to read the number.** Scores run roughly 40–99 within each position. The
bracketed range is the honest uncertainty; the score is the middle of what my
model believes, and the range is how far it could reasonably be off. A dagger (†)
marks lower-confidence rows and a double dagger (‡) the lowest-confidence rows.
A 50 here means the weakest draftable player at the position — not a
league-average one. The distribution is honest rather than forced: most positions
show a handful of players below 50.

**One caution the math requires.** The estimator I use ranks players correctly
and keeps the overall distribution honest, but an individual score is not each
player's best point estimate — I traded a little per-player precision for an
honest spread. Read ranks and ranges before reading single numbers.

**What the Rookie Score is.** For 2026 rookies at RB, WR, and TE, the Rookie
Score is a college-production read: box-score performance scaled against past
drafted prospects at the same position. It describes what the player did in
college; it does not claim to predict NFL performance or fantasy value. No
college instrument ships for rookie QBs, so their cell shows a dash.

**Two different scales.** The Talent Score ranks NFL players against NFL players;
the Rookie Score ranks prospects against past prospects. A 90 in one column is
not a 90 in the other, and neither column feeds any other number on this board.

**Where college data enters a veteran's score.** For early-career running backs
I blend a college prior into the NFL estimate at the agreement level I actually
measured — which is weak (a correlation of about 0.385, measured against my
unshrunk composite, not against the displayed score; the displayed score applies
reliability shrinkage on top). At wide receiver and tight end the measured
agreement was near zero, so their scores are NFL-only. The college share of any
early-career RB's score is shown in the advanced view; for established players
it is small — about 10% for a three-year veteran.

**Quarterbacks are measured differently.** One starter per team means a QB's
situation cannot be separated from him — the QB largely IS the passing situation.
So QB scores are unadjusted for situation: a different kind of estimate under the
same header, and I say so rather than pretend otherwise. QB facets measure
completion rate versus expectation — overall and on throws of 20+ air yards —
ball-placement discipline, and rushing value.

**How much situation matters.** Where I can separate situation (team and
opponent effects at RB, WR, and TE), it explains roughly 8% of week-to-week
variance. Most of what you see week to week is noise; the score is built to look
through that noise, not to deny it exists.

**Known soft spots, disclosed.** Within a position, some of my measures are
correlated with each other (notably at QB, and between the two TE measures), so
a position's facets are not fully independent reads — I keep them because each
passed its own admission gate. The TE broken-tackle measure is fragile: at my
final estimation settings, nearly half of its resampled splits showed no
separable player signal. It stays in the composite because a one-measure TE
score would be worse, but its low confidence weight does the protecting, and TE
rows carry the flags to show it.

**What none of this is.** These columns never combine with the Gap, the ranges,
the Top-12 chance, or the bust number — my testing showed efficiency measures do
not predict draft-market error, so I keep them strictly separate. Nothing here
is a recommendation about any single player.
