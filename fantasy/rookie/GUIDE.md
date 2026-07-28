# Rookie Board — a guide

## 1. What I'm trying to do

Every spring the NFL drafts a new class of skill-position rookies — quarterbacks, running
backs, wide receivers, tight ends — and every fantasy manager has to guess which of them will
actually matter. I wanted a single, honest number for each drafted rookie: the probability that
he becomes a *productive* fantasy player early in his career. I call it the **hit probability**,
and it drives the Rookie Board.

I defined "productive" on football grounds, before I looked at any results: a rookie **hits** if,
in any of his first three NFL seasons, he finishes among the top 24 at running back or receiver
(startable in a 12-team league) or the top 12 at quarterback or tight end (a weekly starter). Best
of three years, because plenty of good players need a season to arrive.

A "hit" = at least one startable season in a player's first three years. Precisely: does he finish,
in any one of his first three NFL seasons, at or above the positional threshold — for RBs that's a
top-24 finish in season-total half-PPR (RB2-or-better). One qualifying season out of three clears the
bar. It is not "a good season on average," not a share of his seasons, and not a per-year rate. It's
a binary, best-of-three outcome.

The hard part isn't building a model — it's that there's already a very good predictor sitting in
plain sight: **draft capital** (where a player was drafted; the earlier the pick, the more the
whole league believed in him). Draft capital is the *market's* price on a rookie, set by thirty-two
front offices with scouting budgets I can't match. So the real question this project asks is not
"can I predict rookie hits?" — it's "can college production and athletic testing tell me anything
the draft slot doesn't already know?" That is a high bar, and the honest prior going in was that
it's very hard to beat. Draft capital is the baseline everything here is measured against — never a
naive average.

## 2. How it works, end to end

**The panel.** I took every drafted QB/RB/WR/TE from the 2015–2023 draft classes — nine classes,
712 players — because each of those classes has now played three full NFL seasons, so I can see who
hit. For each player I computed his best positional finish (ranked by total half-PPR points) across
his first three seasons and turned it into a 0/1 hit label. Then I score the classes I *can't* grade
yet — 2024, 2025, and the brand-new 2026 class — the same way the model would score any future
rookie.

**The features.** Everything is known on draft day, so nothing about the future can leak backward
into a prediction (**leakage** — accidentally letting a model peek at information it wouldn't have
had at prediction time — is the cardinal sin here, and the design rules it out by construction). I
use five groups: draft capital (round, pick); athletic testing from the NFL Combine (40-yard dash,
vertical, broad jump, 3-cone, shuttle, bench, height, weight, plus derived speed/size scores);
college box production (dominator rating, receiving/rushing shares, efficiency, career totals);
college grades and efficiency from PFF (a subscription scouting service — its numbers are used here
per PFF); and age at draft. Many rookies skip Combine drills, so a lot of that data is simply
missing. I do **not** invent it: a missing measurement stays missing and the model learns a branch
for "unknown," rather than being handed a fake league-average value that would read as a real one.

**The model.** The hit probability comes from a **gradient-boosted tree model** (CatBoost — an
algorithm that builds hundreds of small decision trees, each fixing the last one's mistakes). I kept
its settings frozen to exactly what the research used. On top of it I fit a **calibration** step
(Platt scaling — a simple squeeze that makes the raw scores line up with reality, so that a group
the model calls "30%" really does hit about 30% of the time). Calibration is done out-of-sample by
leaving one draft class out at a time, so the displayed probabilities aren't flattered by the model
having already seen those players.

**The test.** To ask the real question, I ran a **walk-forward backtest** (train the model only on
draft classes that came *before* the class being tested, then roll forward — 2019 through 2023 as the
held-out test classes). I compared three versions: the **full** model (all five feature groups), a
**draft-capital-only** model (the market), and a **college-only** model (everything *except* draft
capital, so I can see whether the non-market signal exists at all). I also ran a **placebo check**:
shuffle the hit labels a thousand times and confirm the full model's apparent edge over draft capital
isn't the kind of thing that shows up by chance.

**What ships.** The board shows six things per rookie: (a) a descriptive college talent score, read
only from my separate talent library; (b) the hit probability, 0–100; (c) a rookie-year **season-total
half-PPR projection** from the RB, WR and TE season-total models, shown beside Sleeper's projection
with the difference between them (the QB rookie arm was built and held as too thin, so rookie QBs
show no projection); (d) the underlying feature stats; (e) each rookie's percentile within his
position across the 2015–2026 drafted panel, so you can see where he sits among peers; and (f) his
team, normalised at display time from the board CSVs' PFR-style codes to the site's canonical set.

Below the table sit four collapsed lists of **college players at each position who are not in this
year's rookie class** — the same College Talent instrument on the same scale. Most are still in
college; they appear on no rookie board, and the list says nothing about whether or when any of them
will be drafted.

**Three hit-probability columns.** I show the hit probability three ways, side by side — the fired
result made visible. The **Draft-Capital** column trains on only where a player was picked; the
**College** column trains on only his college production and athletic testing (draft slot removed);
the **Full** column uses everything. All three are the same model architecture and the same hit
definition — only the feature set changes. The pattern to read: the College column is a real but
weak ranker, the Draft-Capital column is strong, and the Full column is, across a class, no better
than Draft-Capital alone — because the college signal is already reflected in where a player was
drafted. Per player the three can diverge (the Full model will nudge a high pick up or down on his
college profile), but in aggregate Full ranks about as well as draft capital by itself. That is the
whole finding: college and athletic data are informative, and redundant with the market.

## 3. A map of the key files

| File | What it is |
|---|---|
| `PREREG_rookie_production_2026-07-20.md` | The pre-registration and the full research record — the design and the fired outcome, written down before and after. Read this for the science. |
| `harness/` | The frozen research harness: `assemble_panel.py`, `assemble_features.py`, `harness.py`, plus `FREEZE.md` (the exact SHA fingerprints) and `fire_rookie_results.pkl` (the one-shot metrics). |
| `build_rookie_board.py` | The product builder. Rebuilds the panel/features in a scratch folder, fits the shipped scorer, scores 2024–2026, surfaces the projection, joins the talent score, writes the board CSVs. |
| `models/rookie_hit_model.pkl` | The shipped hit-probability model (same architecture as the research, plus display calibration). |
| `board_data/rookie_board_{2024,2025,2026}.csv` | The board, one file per class. `oof_predictions.csv` holds out-of-fold scores for a future reliability chart. `DISCLOSURE.md` is the standing label. |
| `../../page_rookie_board.py` | The dashboard page that renders the board. |

## 4. Honest results

**The central claim failed, and that is the headline.** When I fired the one-shot test, the full
model scored an AUC of **0.843** (AUC — a ranking score where 0.5 is a coin flip and 1.0 is perfect)
on the 2019–2023 hold-out classes, and the draft-capital-only model scored **0.838** on the same
players. That gap, +0.005, is nothing: it sits well inside the placebo's chance range (the shuffled
null reached +0.069). Across every one of the pre-registered checks — ranking, calibration score,
fold-by-fold consistency, and the placebo — the full model did not clear the bar. **College
production and athletic testing add no measured edge beyond draft capital.** This is the rookie-board
version of a result I've now seen repeatedly in this repo: beating the market is hard, and here I
didn't.

The diagnostics say *why*, with one consistent story. The college-only model (draft capital removed)
still scored 0.713 — so college and athletic data genuinely carry signal about who hits; they're just
far weaker than draft position (0.838) and add nothing *on top* of it. Drop the Combine too and the
college-only number falls to 0.676. The market has already priced whatever the college and testing
numbers know. Base rates, for context: across the 712-player panel, rookies hit at 14.9% (QB), 28.6%
(RB), 16.2% (WR), and 14.4% (TE).

**Two honesty notes on the numbers.** First, the per-position results for QB (15 hits) and TE (19
hits) rest on very small counts, so I treat them as descriptive only — they neither rescue nor sink
the overall finding. Second, everything above is a **backtest, not a live test**. The clean
out-of-sample trial is future rookie classes; the first real one arrives at the end of the 2026
season. Until then the board carries the label "Backtested, not live-validated" on every surface, and
so should any number quoted from it.

**Face-validity.** Even though the model is essentially a calibrated restatement of draft capital, it
behaves sensibly. On the 2024 class, with two of three seasons observed, the top quarter of hit
probabilities has hit-so-far about 32% of the time versus 0% for the bottom quarter — a clean
directional split (descriptive only; not a validity claim). Elite, high-pick prospects land high;
late-round, low-production players land low. One number that looks surprising: the 2024 #1 overall
pick scored just 28 while the #2 pick in the same class scored 65 — quarterback probabilities run
lower than their draft slots suggest (so few rookie QBs finish top-12), and the college and athletic
features spread scores widely within a draft neighborhood even though they add no edge in aggregate.

**Coverage, and two honest limits.** Hit probability is filled for 100% of drafted rookies in all
three scored classes, since it needs only draft-day inputs. The rookie-year projection is a
season-total half-PPR estimate from the RB, WR, and TE season-total models; QB rookie projections are
intentionally withheld because the available QB sample is too thin and start-status uncertainty is too
large. Sleeper projections are shown only where Sleeper has published one, so a blank Sleeper column is
an unavailable market projection, not a failed load. The college talent score is read only from my
separate 2026 talent library. Since 2026-07-27 **every position has a dedicated college build**:
quarterback, running back, receiver and tight end each get their own, and the RB/WR/TE builds replace
the older box-score value wherever they cover a player while the QB build fills cells that were
previously blank. Remaining blanks are prospects outside FBS, who can never be covered because the
underlying charting data does not reach them, or names too ambiguous to match — which I leave blank
rather than guess. None of it carries a strength-of-schedule adjustment. It is blank for 2024–2025 by
design; I never backfill it.

The page also carries four collapsed lists of **college players at each position who are NOT in this
year's rookie class** — the same instrument on the same scale. Most are still in college. They appear
on no rookie board, and the list says nothing about whether or when any of them will be drafted.

Team codes on this page are normalised at display time: the board CSVs carry PFR-style codes
(NWE, KAN, LVR, …) and every other surface on the site uses the nflverse canonical set, so they are
mapped on render while the build artifact is left untouched.

## 5. The rules and fences that govern it

- **The research is closed.** The one-shot test fired exactly once, on 2026-07-20, and it is spent.
  I will never re-run it to chase a better number — that would be searching for the answer I want,
  which is exactly the mistake pre-registration exists to prevent. A genuinely new question needs a
  new pre-registration.
- **Re-scoring is not re-firing.** Next spring I can rebuild the board for the new class with
  `build_rookie_board.py` — that just applies the settled model to new players. It does not reopen
  the research and makes no new accuracy claim.
- **The projection models are surfaced, not rebuilt.** The Rookie Board reads the RB, WR, and TE
  season-total projection exports and never retrains them as part of the board build.
- **The talent score is read-only.** It comes from a separate library I don't own here; I join it,
  never regenerate it, and never fill its gaps.
- **PFF data stays private.** The licensed PFF season tables live in a git-ignored folder and never
  enter the public repository. The public board does not expose PFF grades, efficiency values, or
  percentiles; it shows only its non-PFF college-production and athletic context fields.
- **The placeholder-ID seam.** Brand-new draft classes arrive from the data feed with temporary,
  name-based player IDs (e.g. `LOV121782`) instead of the permanent IDs older players have. The hit
  probability is unaffected, but the projection and talent joins would miss the whole 2026 class on
  ID alone. I bridge those by name **and** position (and draft class where available), and I skip any
  ambiguous match rather than guess — which is why a few cells are blank. When the permanent IDs
  settle, this seam disappears.
- **Sealed history.** Draft classes from 2008–2015 remain untouched by any of this evaluation, as
  they are across the repo.

The one-sentence version: this is an honestly-labeled product built on top of a null result — the
hit probability is a calibrated, backtested restatement of draft capital, it does not beat the
market, and it says so on every screen.
