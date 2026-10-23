# Anytime TDs

The tab defaults to the latest published 2026 live comparison board. It also keeps the 2025 Weeks 10-17 demo selectable from the Year and
Week controls.
The model compares my chance a skill player scores a rushing or receiving
touchdown with a sportsbook Yes price. Passing touchdowns are out. The page is
for fun, not a proven edge. Bet responsibly.

Training lives in the private `td_count_model_beta` repo. This public tree only
ships CSV.

## Canonical releases and reconstructed results

`releases_manifest.json` (schema version 1) can bind a week's canonical CSV
to one JSON metadata file. Each `releases` entry contains `season`, `week`,
`csv`, `metadata`, `prediction_mode`, and `model_version`. Paths are relative
to this directory and must remain inside it. Metadata repeats the season,
week, model version, and prediction mode. Duplicate weekly entries, missing
artifacts, or disagreements are publication errors.

Without a manifest entry, only the exact `anytime_td_YYYY_weekWW.csv` filename
is canonical. Suffixed CSVs and backup files never replace it. The page,
paper tracker, and scheduled graders share this selection rule.

An NGS backfill has `prediction_mode: retrospective` and is labeled
"Retrospective reconstruction; historical input availability unverified."
It describes probabilities computed after the games, not picks published
before kickoff. Original releases remain in the private producer's audit
archive. The season-to-date cards combine each week's latest canonical release
through the selected week, including retrospective republished predictions.
The season caption identifies weeks recomputed after the games. The selected-week
cards cover that week alone. A partially locked live week
may contain rows from two model versions; their row metadata preserves the version.
Missing reconstructed probabilities remain pending and cannot create bets.

## What the board is

Every skill player the books quoted that week, sorted by `ATTD Value Gap`
(my P(TD) minus the book probability, highest first). It is not a pick list.
A short "I like these" card lost on 2025, and a typical quote is around one in
five, so misses will outnumber hits. That is the bet, not a broken model.

| Column | Meaning |
|---|---|
| Model ATTD Odds | My model American odds plus percentage chance of a rushing or receiving TD |
| Book ATTD Odds | The book's American odds plus implied percentage chance of a rushing or receiving TD |
| ATTD Value Gap | Book-minus-model American-odds gap plus model-minus-book percentage differential |
| Hit | Did they score a rushing or receiving TD? |

The First TD view has no value gap. Its columns are Model First TD Odds, Book
First TD Odds, Expected Return, and Hit (did they score the game's first
touchdown).

On a phone the grid keeps #, Player, Model, Book, Value, and Hit. Position tabs swipe.
Live boards are grouped by matchup and then team (for example, NE vs SEA,
with separate NE and SEA sections).

The **Market** control switches between Anytime TD, 2+ TD, and First TD; only
one renders at a time. **2+ TD** exposes model 2+ TD odds, the current DraftKings 2+ TD
price, and the 2+ TD value gap when those prices are included in the pasted
release; players without a listed 2+ price are omitted from that market view.
Before games begin, releases without the market show a clear not-implemented
placeholder. Completed matchups without a published 2+ market do not receive
retroactive model odds. Once grading supplies their final outcomes, they are
counted only in a results-only tally, not in betting W-L, units, ROI, or a
backtest.

There is no historical 2+ TD backtest and no published 2+ TD test results yet.
Treat the 2+ probabilities and paper-betting cards as forward-looking tracking
only, not evidence of model accuracy or profitability.

**First TD** exposes my model's First TD odds, DraftKings' First TD price with
the chance that price implies, and an **Expected Return** for players with a
listed First TD price. Expected return is my model's chance times the decimal
payout (stake included), minus 1: the average profit per unit staked if my
chance were exactly right.

First TD is a different kind of probability than Anytime or 2+ TD: exactly one
player can score a game's first touchdown, so the model splits one pool per
game. A player's share is his portion of the game's expected rushing plus
receiving touchdowns (passing touchdowns are credited to the receiver), raised
to a power k = 1.1, which sharpens the split slightly toward favorites. That
share is scaled by 0.9397, the chance an offensive skill player scores first at
all; the rest goes to defense, special teams, or no score. The model does not
predict which team scores first. Weeks 1 to 6 and the published `p_first`
column use k = 1 (no sharpening). `p_first_v3` is the sharpened column, used
from Week 7.

The board sorts by expected return at the quoted DraftKings price, highest
first. The book cell shows DraftKings' implied percentage, which includes the
book's margin. A no-vig percentage (the book's chance with the margin removed)
appears only on desktop, and only when a complete quote pool was captured. The
older First TD "value gap" column is gone. Treat this view as entertainment,
not evidence that the model works or pays.

**Display-only games.** NE vs SEA and SF vs LA (both completed before either
market had a published DraftKings price) are kept visible in the 2+ TD and
First TD views as fun, model-only look-backs: Model odds and Hit show real
values, Book odds show "Not implemented yet," no value figure is computed, and any
graded outcome is counted only in a results-only tally, never in betting
W-L, units, ROI, or a backtest. This is the same treatment both markets give
any other completed matchup without a published price for that market;
these two are just guaranteed to hit it, since the pasted odds for both
markets always postdated these games.

## 2026 paper-betting tracker

The live board highlights a row when the raw probability gap is at least +1.0
percentage point (raised from +0.5pp on 2026-09-19). That is a transparent 1U paper-bet candidate, not a
recommendation. The season-to-date cards aggregate the newest published file
for each 2026 week, deduplicate player-game rows, settle only final
`scored_anytime` outcomes, and use the stored DraftKings American price for
profit. Open bets remain visible but do not enter Net units or ROI.

When there are at least five settled games and 20 settled bets, the page shows
an **Approx. 95% ROI range** from 10,000 deterministic game-block bootstrap
resamples. This is an empirical uncertainty range, not a guarantee.

The 2+ TD rule changed on 2026-09-19 at my direction, and the First TD rule
changed again for Week 7. Each market has its own Net units, ROI, record, and
uncertainty cards, and those cards remain pending until DraftKings prices and
graded outcomes (`scored_two_plus` / `scored_first`) exist for that market.
Results-only outcomes are shown separately and are never treated as historical
bets.

- **2+ TD** was a flat +0.5pp gap; it now requires the model probability to
  be at least 1.25x DraftKings' implied probability, with that implied
  probability at least 2%. A flat gap rewards long shots (the same 0.5pp gap
  is a 50% relative edge on a 1% price and a 3% relative edge on a 15%
  price), and the 2026-09-19 board's 37 flagged players under the old rule
  skewed almost entirely to long shots. `attd_tracker.qualifies_two_plus_ratio`.
- **First TD best-value rule**, tracked from Week 7. Each game gets at most one
  pick: the quoted player with the highest expected return, only if that
  return is above zero and the price is +599 or shorter. Each pick is a flat
  1 unit. I freeze picks game by game before kickoff with
  `python -m publishing.cli freeze-first-td-v3 --season 2026 --week N`, run
  after every paste. A frozen game keeps its pick even if a later paste
  re-prices it, and a game that has started is refused. The strategy id is
  `first_td_best_value_v3`. The +599 cap is the floor of the cap rule, not a
  finding: no price band shows DraftKings hiding less margin.
- **First TD, Weeks 1 to 6** keep the earlier rule on their cards: a gap of at
  least 3.0 percentage points against the no-vig price AND a positive expected
  return at the real price (`attd_tracker.qualifies_first_td_ev`). An interim
  "actual EV" rule (every positive-return quote, `first_td_actual_ev_v2`) was
  retired before any Week 7 game kicked off and was never tracked.

Neither 2+ TD nor First TD has a price-history backtest to validate its rule
against (no 2+ or First TD price archive exists anywhere in this project for
any season), so both rules are a design choice, not a demonstrated edge.

First TD results:

- In an earlier check, DraftKings' full 2026 First TD pools implied about 131%
  to 134%. That excess is the book's margin, and it is about the same at every
  price.
- Sharpening (k = 1.1) lowered log loss (a score for probabilities, lower is
  better) on the 2025 holdout of 256 games by a few thousandths. Every
  interval includes zero, so the gain is within noise.
- A retrospective replay on Weeks 2 to 6 lost about 59% for the interim v2 rule
  (343 bets, 5 hits) and about 51% for v3 (8 bets, 1 hit). That proves nothing
  either way.
- Proving a 5% edge at +1000 prices would take about 16,000 bets.
- Nothing here is a proven edge.

Why +1.0pp: +0.5pp and +1.0pp were the two thresholds fixed before the 2025
holdout was scored. On the deployed product model +1.0pp was 1,428 bets, +117.31U,
+8.21% ROI (-8.51% to +25.49%), against +0.5pp at 1,605 bets, +6.83% (-9.12% to
+23.61%). Both intervals cross zero, so this is a choice between two
indistinguishable rules, not a demonstrated edge. The season-to-date cards
re-score every published 2026 week under the current rule, so Week 1 is now
counted at +1.0pp.

The audited 2025 DraftKings strategy artifact is
`strategy_backtest_2025_draftkings.json`. It records the fixed +0.5pp result,
threshold scan, controls, drawdown, and bootstrap settings for the anytime-TD
market; it does not contain a 2+ TD backtest. The research 34-feature arm and
the deployed 35-feature product arm are separate evidence bases: the product
holdout is 1,605 bets, +109.6U, +6.83% ROI, with a game-block interval that
crosses zero. The older +10.95% result belongs to the research artifact and
must not be presented as the live-product result.

## How it scored in 2025

Product arm: 34 locked usage features plus that week's Sleeper half-PPR
projection. The anytime price is not an input.

| Slice | Priced rows | Result |
|---|---:|---|
| Full 2025 overlap | 5,310 | Books about 0.08% more accurate (0.13985 vs 0.13996 on the season score) |
| Demo weeks 10-17 | 2,524 | My numbers were closer in 5 of 8 weeks. Books still won the eight-week total |
| Audited +0.5pp DraftKings rule | 2,055 | +225.0U, 10.9% ROI; bootstrap range -3.9% to +26.3%, so the interval still crosses zero |

Week 18 is out (rest and backups). Legacy Sleeper dumps have no freeze
timestamp and are therefore marked as-of-unverified. New product snapshots
must carry a timestamped capture envelope strictly before the first slate
kickoff; the forward builder fails closed otherwise.

## Live 2026 manual-paste contract

I paste one US sportsbook's Yes prices whenever practical. About three
hours before kickoff is preferred, but early preparation captures are accepted
and labeled with their actual lead time. A live publish is refused once any
game in the requested slate has started. Retrospective scoring is allowed only
with an explicit isolated output directory and cannot write the public board.
For Sunday slates, the expected handoff is early Sunday morning before the
slate. The canonical input is `td_count_model_beta/live/2026_week01_<slate>.csv`
with `season`, `week`, `kickoff_et`, `snapped_at_et`, `book`, `player`, `team`,
`opponent`, and `yes_amer`. The parser/publisher also preserves the optional
`first_amer` and `two_plus_amer` DraftKings prices. All three are American
odds. No Odds API is called. `first_amer` is the First TD price. The First TD
model probability does not come from the quoted set. It comes from the frozen
candidate mass saved in the release metadata (every skill player's expected
touchdowns in the game, quoted or not).
`td_count_model_beta/first_td/src/publish_site_columns.py` computes the flat
`p_first` from that mass and, only when a complete quote pool was captured, the
no-vig `book_first_p_devigged`, before the release is copied into this public
directory. The site derives `p_first_v3` from the same frozen mass.

The publisher normalizes names using the explicit alias file when needed,
checks the Week 1 schedule, timestamps, odds, duplicates, and player-game
coverage, then writes a frozen per-slate release. Unmatched pasted names are
reported in release metadata and excluded from scoring rather than silently
fuzzy-matched. Defense and the synthetic "No Touchdown Scorer" row are not
skill-player predictions.

Each successful slate is appended to
`betting/anytime_td/anytime_td_2026_week01.csv`. Existing game prediction and
price fields remain byte-for-byte frozen; changing a frozen price requires the
explicit replacement flag and creates `replacement_audit.jsonl`. A missing
paste leaves that slate off the board. Pregame `Hit` and scored totals stay
blank until outcomes are attached; null outcomes never render as “No”. A
verified lineup replacement may appear with DraftKings odds while its model
fields say `Pending` if the current-week model input is absent; that row is
excluded from value-gap and paper-bet accounting until the model input is
available. Rows with synthetic identities or zero prior games are also marked
non-bettable by default and carry an eligibility reason for review. For
grading, an absent quoted player is not assumed to have scored zero: confirmed
zero-snap/inactive rows are voided, participating zero-TD rows are losses, and
rows without participation evidence remain pending.

## Rebuild and publish

From `td_count_model_beta`, convert a copied DraftKings text page (or prepare
the canonical CSV directly), then publish predictions:

```text
python scripts/parse_draftkings_text.py <pasted-text.txt> live/2026_week01_<slate>.csv --snapped-at "YYYY-MM-DD HH:MM"
python scripts/publish_live_week.py live/2026_week01_<slate>.csv <slate>
```

The publisher fits the live product arm on the rebuilt historical artifact
(the 34 locked features plus the current-week Sleeper half-PPR projection),
scores only players quoted by that paste, and copies the cumulative CSV into
this public directory. Attach results later through the grading workflow. The
workflow marks a game final only after the schedule has final scores and the
player-stat feed covers both teams (or every quoted player); otherwise its rows
remain pending rather than being backfilled with zeros. After a matchup is
fully graded, the page's default moves to the next unplayed matchup in kickoff
order, with alphabetical ordering for simultaneous games.

## Public files

| Path | Role |
|---|---|
| `anytime_td/` | Frozen 2025 week CSVs plus `meta.json` |
| `anytime_td/strategy_backtest_2025_draftkings.json` | Audited historical +0.5pp DraftKings strategy result |
| `anytime_td/strategies/first_td_best_value_v3/` | Frozen v3 params (`params.json`) and the weekly First TD pick ledgers |
| `anytime_td/strategies/first_td_actual_ev_v2/` | Retired interim rule, marked by `SUPERSEDED.json`; never tracked |
| `../publishing/first_td_strategy.py`, `first_td_v3.py` | Freeze and settle logic, and the sharpened-share formula |
| `../site_pages/page_anytime_td.py` | Comparison board |
| `../tests/test_anytime_td.py` | Offline AppTest |

The live producer is in the private `td_count_model_beta` repo:
`scripts/publish_live_week.py`. Its input contract is `live/README.md`.
