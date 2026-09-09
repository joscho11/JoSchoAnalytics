# Anytime TDs

The tab defaults to the published 2026 Week 1 live comparison board. It also
keeps the 2025 Weeks 10-17 demo selectable from the Year and Week controls.
The model compares our chance a skill player scores a rushing or receiving
touchdown with a sportsbook Yes price. Passing touchdowns are out. The page is
for fun, not a proven edge. Bet responsibly.

Training lives in the private `td_count_model_beta` repo. This public tree only
ships CSV.

## What the board is

Every skill player the books quoted that week, sorted by our P(TD). It is not a
pick list. A short "we like these" card lost on 2025, and a typical quote is
around one in five, so misses will outnumber hits. That is the bet, not a broken
model.

| Column | Meaning |
|---|---|
| Our P(TD) | Our chance of a rushing or receiving TD |
| Book | Implied Yes from the one manually pasted US sportsbook price |
| vs book | Our probability minus the book, in percentage points. Not a bet |
| Our fair | American odds implied by our P(TD) |
| P(2+) | Chance of two or more rushing or receiving TDs |
| Hit | Did they score a rushing or receiving TD? |

On a phone the grid keeps #, Player, Ours, Book, and Hit. Position tabs swipe.
Live boards are grouped by matchup and then team (for example, NE vs SEA,
with separate NE and SEA sections).

## How it scored in 2025

Product arm: 34 locked usage features plus that week's Sleeper half-PPR
projection. The anytime price is not an input.

| Slice | Priced rows | Result |
|---|---:|---|
| Full 2025 overlap | 5,310 | Books about 0.08% more accurate (0.13985 vs 0.13996 on the season score) |
| Demo weeks 10-17 | 2,524 | Our numbers were closer in 5 of 8 weeks. Books still won the eight-week total |
| Yes-edge cut | 960 | Lost vs the book. Not a betting record |

Week 18 is out (rest and backups). Sleeper's dump has no freeze timestamp.

## Live 2026 manual-paste contract

Joseph pastes one US sportsbook's Yes prices whenever practical. About three
hours before kickoff is preferred, but early preparation captures are accepted
and labeled with their actual lead time; only a post-kickoff timestamp blocks a
row. The canonical input is `td_count_model_beta/live/2026_week01_<slate>.csv`
with `season`, `week`, `kickoff_et`, `snapped_at_et`, `book`, `player`, `team`,
`opponent`, and `yes_amer`. `yes_amer` is an American-odds Yes price. No Odds
API is called.

The publisher normalizes names using the explicit alias file when needed,
checks the Week 1 schedule, timestamps, odds, duplicates, and player-game
coverage, then writes a frozen per-slate release. Unmatched pasted names are
reported in release metadata and excluded from scoring rather than silently
fuzzy-matched. Defense and the synthetic "No Touchdown Scorer" row are not
skill-player predictions.

Each successful slate is appended to
`betting/anytime_td/anytime_td_2026_week01.csv`. Existing game rows remain
byte-for-byte frozen; changing a frozen price requires the explicit replacement
flag and creates `replacement_audit.jsonl`. A missing paste leaves that slate
off the board. Pregame `Hit` and scored totals stay blank until outcomes are
attached; null outcomes never render as “No”.

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
this public directory. Attach results later through the grading workflow; do
not backfill an ungraded game with zeros.

## Public files

| Path | Role |
|---|---|
| `anytime_td/` | Frozen 2025 week CSVs plus `meta.json` |
| `../site_pages/page_anytime_td.py` | Comparison board |
| `../tests/test_anytime_td.py` | Offline AppTest |

The live producer is in the private `td_count_model_beta` repo:
`scripts/publish_live_week.py`. Its input contract is `live/README.md`.
