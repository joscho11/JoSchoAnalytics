# Anytime TDs

The tab defaults to the latest published 2026 live comparison board (currently
Week 2). It also keeps the 2025 Weeks 10-17 demo selectable from the Year and
Week controls.
The model compares our chance a skill player scores a rushing or receiving
touchdown with a sportsbook Yes price. Passing touchdowns are out. The page is
for fun, not a proven edge. Bet responsibly.

Training lives in the private `td_count_model_beta` repo. This public tree only
ships CSV.

## What the board is

Every skill player the books quoted that week, sorted by `ATTD Value Gap`
(our P(TD) minus the book probability, highest first). It is not a pick list.
A short "we like these" card lost on 2025, and a typical quote is around one in
five, so misses will outnumber hits. That is the bet, not a broken model.

| Column | Meaning |
|---|---|
| Model ATTD Odds | Our model American odds plus percentage chance of a rushing or receiving TD |
| Book ATTD Odds | The book's American odds plus implied percentage chance of a rushing or receiving TD |
| ATTD Value Gap | Book-minus-model American-odds gap plus model-minus-book percentage differential |
| Hit | Did they score a rushing or receiving TD? |

First TD view columns swap in Model/Book/Value Gap for the first-touchdown
market and keep Hit (did they score the game's first touchdown).

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
counted only in a results-only tally—not in betting W-L, units, ROI, or a
backtest.

There is no historical 2+ TD backtest and no published 2+ TD test results yet.
Treat the 2+ probabilities and paper-betting cards as forward-looking tracking
only, not evidence of model accuracy or profitability.

**First TD** exposes model First TD odds, DraftKings' First TD
price (de-vigged within the game), and the First TD value gap for players
with a listed First TD price. First TD is a fundamentally different kind of
probability than Anytime or 2+ TD: exactly one player can score a game's
first touchdown, so the model allocates each game's probability mass
proportionally to Anytime TD rate across the whole candidate pool, scaled
by the historical rate an offensive skill player scores first at all
(pooled 2021-2025: about 94.3% of games; the rest go to defense, special
teams, or no score in that game). The book side is genuinely de-vigged
within each game (proportional normalization across every quoted player),
unlike the Yes-only Anytime quote, because First TD is a real one-winner
market. There is no historical First TD backtest of any kind anywhere in
this project, for any season -- only a forward live-week board. Treat this
view as entertainment more than the 2+ TD view, not evidence of model
accuracy or profitability.

**Display-only games.** NE vs SEA and SF vs LA (both completed before either
market had a published DraftKings price) are kept visible in the 2+ TD and
First TD views as fun, model-only look-backs: Model odds and Hit show real
values, Book odds and the value gap show "Not implemented yet," and any
graded outcome is counted only in a results-only tally, never in betting
W-L, units, ROI, or a backtest. This is the same treatment both markets give
any other completed matchup without a published price for that market;
these two are just guaranteed to hit it, since the pasted odds for both
markets always postdated these games.

## 2026 paper-betting tracker

The live board highlights a row when the raw probability gap is at least +0.5
percentage point. That is a transparent 1U paper-bet candidate, not a
recommendation. The season-to-date cards aggregate the newest published file
for each 2026 week, deduplicate player-game rows, settle only final
`scored_anytime` outcomes, and use the stored DraftKings American price for
profit. Open bets remain visible but do not enter Net units or ROI.

When there are at least five settled games and 20 settled bets, the page shows
an **Approx. 95% ROI range** from 10,000 deterministic game-block bootstrap
resamples. This is an empirical uncertainty range, not a guarantee. The 2+
TD and First TD toggles use the same +0.5pp candidate rule and each have
their own Net units, ROI, record, and uncertainty cards. Those cards remain
pending until DraftKings prices and graded outcomes (`scored_two_plus` /
`scored_first`) exist for that market. Results-only outcomes are shown
separately and are never treated as historical bets.

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
| Demo weeks 10-17 | 2,524 | Our numbers were closer in 5 of 8 weeks. Books still won the eight-week total |
| Audited +0.5pp DraftKings rule | 2,055 | +225.0U, 10.9% ROI; bootstrap range -3.9% to +26.3%, so the interval still crosses zero |

Week 18 is out (rest and backups). Legacy Sleeper dumps have no freeze
timestamp and are therefore marked as-of-unverified. New product snapshots
must carry a timestamped capture envelope strictly before the first slate
kickoff; the forward builder fails closed otherwise.

## Live 2026 manual-paste contract

Joseph pastes one US sportsbook's Yes prices whenever practical. About three
hours before kickoff is preferred, but early preparation captures are accepted
and labeled with their actual lead time. A live publish is refused once any
game in the requested slate has started. Retrospective scoring is allowed only
with an explicit isolated output directory and cannot write the public board.
For Sunday slates, the expected handoff is early Sunday morning before the
slate. The canonical input is `td_count_model_beta/live/2026_week01_<slate>.csv`
with `season`, `week`, `kickoff_et`, `snapped_at_et`, `book`, `player`, `team`,
`opponent`, and `yes_amer`. The parser/publisher also preserves the optional
`first_amer` and `two_plus_amer` DraftKings prices. All three are American
odds. No Odds API is called. `first_amer` now also feeds the First TD view's
lambda-share model probability and its within-game de-vig of the book price
(`td_count_model_beta/first_td/src/publish_site_columns.py` computes
`p_first` and `book_first_p_devigged` from the same release before it is
copied into this public directory).

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
| `../site_pages/page_anytime_td.py` | Comparison board |
| `../tests/test_anytime_td.py` | Offline AppTest |

The live producer is in the private `td_count_model_beta` repo:
`scripts/publish_live_week.py`. Its input contract is `live/README.md`.
