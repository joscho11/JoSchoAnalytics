# A guide to the 2026 Draft Board

> **Note (2026-07-22): the Draft Board PAGE was rebuilt** into a season-projection comparison table —
> 245 rows and 13 columns: Sleeper ADP + Position Rank beside Sleeper's and a from-scratch model's
> season projections, the rank gap for each, two descriptive talent columns from `fantasy/talent/`, and
> a disclosed 44-player analyst scenario on the displayed model number. A detail toggle (on by default)
> collapses it to a compact 9-column comparison view; the CSV export always carries all 13.
> It **no longer renders the calibrated band** described below, and it **no longer renders the single
> 2025-efficiency column** described below either — that was superseded by the two per-position talent
> columns. This GUIDE documents the **closed band research campaign** and the frozen
> `phase4_band_2026.csv` / `talent_index_2026.csv` — kept on disk for the campaign **only**;
> verified 2026-07-27, neither is an input to the daily ADP refresh, whose one frozen input is
> `season_dataset_2014_2026.csv`. NOT the live page. For the current page see
> `fantasy/projections/GUIDE.md` (the projection engine) and `fantasy/talent/GUIDE.md` (the
> talent columns).

This is the plain-language tour of the pre-season Draft Board and the research behind it. I built
this, and I ran a long, disciplined research program to figure out what it can honestly say. My
aim here is to explain how it works and to be careful and exact about what has been shown and what
has not. The board describes patterns; it does not tell you what to do.

## What I'm trying to do

Before a fantasy draft, every player has a market price. That price is their ADP — average draft
position, the consensus draft slot across thousands of real drafts. ADP is the crowd's verdict on
a player, and it's very good, because it already absorbs offseason news, coaching changes, and
depth-chart moves.

Two things I set out to do. First, the research question: can anything I build rank drafted
players better than ADP already does? That's a hard, honest bar — the market, not a naive average,
is what I have to beat, exactly like beating the betting line instead of predicting the average
game. Second, the product: pair the market's single-number projection with something the market
doesn't give you — a calibrated *range* around it, so you can see not just where a player is
projected but how wide the outcomes realistically are.

Everything the board shows is a pattern across many players. It is not a rating of any one player,
and it is not a set of instructions.

## How it works, end to end

**The price.** For each player I take their ADP as the market price, and their position rank by
that price (the number-1 running back off the board, the number-2, and so on).

**The point estimate.** The single-number season projection comes from the market — specifically
from Sleeper (a fantasy platform) and its published projections measured against the draft market.
I don't dress the market's estimate up as my own. What I add sits on top of it.

**The range (this is my contribution).** Around the point estimate I build a calibrated band: a
Floor, an Expected, and a Ceiling for the player's season points, plus a chance to finish in the
top 12 at the position and a chance of a poor season. "Calibrated" means the range is drawn so the
percentages are honest — a Floor set so that about 1 in 10 players finish below it, an Expected in
the true middle, a Ceiling about 1 in 10 finish above. I build it with two standard tools. The
first is isotonic regression, a method that fits a smooth line which only ever goes one direction
(better draft price maps to more expected points, never backwards). The second is looking at the
spread of past errors around that line — how far real seasons landed from the projection — and
using those to draw the Floor and Ceiling. Crucially, the errors are not bell-shaped: high picks
have a long downside from injuries, and lower picks have a long upside from breakouts, so I don't
assume a tidy symmetric curve.

**The projection-vs-price gap.** The board also shows, for each player, the difference between
where projections rank them and where their price ranks them. This is the `value_gap` column, and
it's descriptive: a positive number means the projections rank the player higher than the price
does, a negative number the reverse. I'll be precise below about exactly what has and hasn't been
shown about this gap.

**A separate efficiency column.** There's a descriptive column showing how a player ranked on a
2025 efficiency measure (for example, yards a running back gained over what an average back would
have on the same carries). It is context only. It is never mixed into the range, the gap, or
anything else, because I tested whether it predicts where the market is off and it does not — so it
sits on its own, clearly separated.

**How I know any of this holds up: pre-registration.** The thing that makes this more than a hunch
is a discipline called pre-registration. Before running a test, I write down exactly what I'll
measure, what result would count as a pass, and that the test fires only once. That stops me from
running twenty variations and keeping the flattering one. Every claim on the board traces back to
one of those pre-registered tests, and the whole ledger is in `PREREGISTRATION.md`.

## A map of the key files

I keep a full, file-by-file manifest in `ARTIFACTS.md` (what's frozen, what's regenerable, what's
retired). The handful that matter most:

| File | What it is |
|---|---|
| `phase4_band_2026.csv` | The band from the closed campaign — the market point estimate plus my calibrated range. Frozen; **rendered nowhere since the 2026-07-22 page rebuild**. |
| `talent_index_2026.csv` | The retired 2025-efficiency context column. Frozen; kept for the closed campaign only. **Renders nowhere and is read by nothing** — superseded by the per-position builds in `fantasy/talent/`. |
| `phase4_band.py` | The engine that builds the range (isotonic line + error spread). |
| `apply_board_labels.py` | Adds the population flags and the licensed wording to the board. |
| `draft_board_2026.py` | The Draft Board **page** (one of the site's nine `st.Page` modules) - the rebuilt season-projection comparison table, which reads none of the band artifacts. |
| `PREREGISTRATION.md` | The research constitution — every test, its rule written in advance, and its result. |
| `ARTIFACTS.md` | The full file manifest. |

## Honest results

**The range works, and I can put a number on it.** When I drew these ranges for past seasons and
checked them, about 8 in 10 players finished inside their 80% range — almost exactly what the math
promises. I checked that on roughly 900 player-seasons from 2021 through 2025, and the range beats
a simple constant-width band. That calibration is the product's real contribution.

**Can I beat the market's ranking with my own features? No.** I built a model on prior-season stats
and tested, in a pre-registered one-shot, whether it improved on ADP. It did not. That's a clean
negative, and it matches the lesson from the betting side: a market consensus already prices in
information a stats model can't see.

**Does the projection-vs-price disagreement carry real information? Yes — in aggregate.** A separate
pre-registered test showed that when the projections and the market disagree, that disagreement
does carry information about where the market's ranking is off, measured across the 2021–2025
seasons. Two follow-up tests strengthened it: one confirmed the signal isn't just an artifact of
the projections being fresher than the draft prices, and one confirmed it holds for running backs
and receivers in changing situations when checked against prices captured at the same moment as the
projections.

I have to be exact about the boundary of that result, because the discipline is the whole point:

- It is validated **in aggregate only** — as a pattern across many players. It is **not** a claim
  about any individual player, and there is no accuracy or hit-rate claim attached to it.
- For quarterbacks and tight ends in changing situations, the disagreement is **not** validated —
  there aren't enough such players in the past seasons to test it reliably, and those rows are
  marked on the board.
- The size of any single gap is not something I've validated, and there are no threshold groupings
  applied to it.

**Two more settled negatives.** The efficiency measure described above does not predict where the
market is off (which is exactly why it's a context-only column). And the amount of new competition
arriving in a player's situation over the offseason is already priced by the market — another
pre-registered test that came back negative.

**What the whole program adds up to:** a calibrated range that is genuinely useful and honestly
measured, sitting on top of the market's own estimate, with a disagreement signal that is real in
aggregate and carefully bounded.

## The rules and fences, and why they exist

- **The board describes; it does not instruct.** It states disagreements descriptively and states
  validation in aggregate. It carries no verdicts, no groupings, and no claim about what will
  happen to any single player. This is a licensing discipline, and the wording on the board is
  fixed — I translate it into plain language without making it stronger or weaker.
- **No accuracy or hit-rate claims, ever, about the ranking.** The one number I do stand behind is
  the range calibration (the "about 8 in 10 inside the 80% range"), which is a statement about the
  range, not about picking players.
- **The efficiency column is never combined with anything.** It's context, kept physically
  separate, because testing showed it doesn't predict market error.
- **The research tests fire exactly once.** Each pre-registered test is a single shot with its rule
  written in advance; the results are frozen in the record. Re-running one to get a nicer number
  would destroy the very thing that makes it trustworthy.
- **Some data is sealed for good.** The 2008–2015 seasons were never touched by any of this
  analysis and stay that way, and Sleeper's 2020 projections are set aside because they turned out
  to be near-copies of the actual results — so every projection number here excludes 2020.

The short version: the market gives the point estimate; my contribution is a calibrated range
around it, honestly measured; and the disagreement between projections and price carries real
information in aggregate, stated carefully and never as a claim about any one player.
