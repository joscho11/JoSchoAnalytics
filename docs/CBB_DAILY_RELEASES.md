# College Basketball daily releases

The College Basketball page ("Daily predictions", Beta) is a single public surface
for the daily 2026-27 score-and-winner predictions. In the card metadata and the
contract that season is `2027`. It reads only sanitized, hash-verified CSV and JSON
releases under `data/releases/cbb_daily/`; it never loads model files, features,
credentials, raw CBBD responses, or provider-level rows.

## What the page shows

Predictions lead. Every game on a card carries a predicted score, margin, total,
winner and win probability, and the page shows them with team names. The score
model is universal and never consumes the spread.

A "View" menu picks which of the day's games are on screen, ESPN style. There is no
"All games" view, so every game must be in Top 25 or in at least one conference.

- **Menu:** "Top 25 (N games)" first, then each conference that has a game that day, in the order of
  `data/cbb/conference_order_2027.json`, labelled like "SEC (6 games)". A blank or unlisted
  conference goes under "Other", last.
- **Membership:** Top 25 is a game with either team ranked. A conference view is a game with
  either team in that conference, so a cross-conference game appears in both views.
- **Default:** Top 25. With no poll, or no ranked team playing, the default is the first listed
  conference. The date picker resets a stale choice: the search box is cleared, a Top 25 choice
  goes back to that day's default, and a conference choice stays only if the new day has it.
- **Sort, in every view:** absolute gap (`model_edge`) descending for games with a line, then
  games with no line by tip time, then home team. The gap is how far the model's predicted margin is from
  the sportsbook line. Each card shows `Line: Kentucky -5.5 · Gap 1.90 toward Kentucky` (the line names the
  team it favors; the gap names the team the model leans to relative to the line) or `No line yet`, and
  plays carry an "8.5+ gap, exploratory" badge. Ranked teams show `#N` before the name.
- **Search:** a non-empty team search looks through all of the day's games and ignores the view.

Below the games sits an exploratory ATS shadow (8.5-point policy). A provider-neutral
median CBBD spread is joined after prediction. A game becomes a shadow pick only when
the absolute model gap is at least 8.5 points. Spreads are shown exactly as collected
(for example -3.25, -3, PK) and gaps to two decimals, so a gap of +8.46 is never
displayed as an 8.5-point play. This is not a promise of betting success and it failed
its own 2026 gate. Historical benchmark results are descriptive and do not prove when
a line became available. Live records use genuine timestamped snapshots only.

A season prediction record (winner correct, average margin miss, average total miss
over finished games) sits above the ATS record. It is computed from the published
cards plus their result overlays and carries an honest "too early to read" caption
while the sample is small.

## Card contract (`cbb_daily_card_v2`)

`publishing/cbb_daily.py` accepts only `schema_version == "cbb_daily_card_v2"`. No v1
build was ever published, so v1 is rejected rather than migrated. The product ids
(`cbb_daily_spreads`, `cbb_daily_spreads_results`), the manifest (schema_version 1),
the 8.5 threshold, the frozen hashes, the forbidden-column list and the results
contract (`cbb_daily_results_v1`) are unchanged.

v2 adds one required metadata field, `line_snapshot_status`:

| Value | Meaning | Rows allowed |
|---|---|---|
| `official` | an official pre-tip line snapshot (08:45 to 09:00 ET) was used | at least one `market_status == "available"` row |
| `unavailable` | no official snapshot exists for the date | zero available rows |
| `rejected` | a snapshot existed but failed validation, so the card was rebuilt without lines | zero available rows |

Rules for a non-empty card:

- `line_snapshot_status` is `official` if and only if at least one row is `available`.
- A card whose rows are all `market_status == "missing_line"` is a valid
  predictions-only card. There is no longer a rule that a card needs a line.
- Every `available` row keeps its existing checks: finite spread, margin and edge,
  `ats_pick` matching the 8.5 threshold, and a `line_retrieved_at_utc` inside
  08:45 to 09:00 ET on game day and before tip-off.
- Every `missing_line` row must be marked `line_unavailable`.

An empty `no_games_scheduled` card accepts any of the three status values.

## Optional fields: conferences, AP ranks and the poll

The producer writes four optional row columns and one optional metadata field. The schema
stays `cbb_daily_card_v2` and an older card without them still loads (every game then
falls under "Other" and Top 25 is empty). The validator checks only what is present.

| Field | Meaning | Rule |
|---|---|---|
| `home_conference`, `away_conference` | CBBD conference short name, for example `SEC`, `A-10`, `Pac-12` | read as text; blank is allowed; a purely numeric value is rejected |
| `home_rank`, `away_rank` | AP Top 25 rank | blank or a whole number from 1 to 25; ties are legal (two #25s); the CSV prints `3`, not `3.0` |
| `top25` (metadata) | the poll behind the ranks: `{"poll": "AP Top 25", "poll_date": "YYYY-MM-DD", "week": int or null, "source": "cbbd" or "static_snapshot"}`, or `null` when no poll was available | any rank needs a non-null `top25`; `week == 1` is shown as "(preseason)" |

Each pair of columns must be both present or both absent. The page caption reads
"Top 25: AP poll of {date} (preseason). Conference order: WarrenNolan.com conference ranking,
snapshot of {captured_on}."

Coverage describes Division I games only. The producer no longer counts `not_d1_v_d1`
exclusions, and the page also subtracts any such count from an older card and never names it,
so the caption reads "Showing 80 of 119 Division I games on the schedule. Not shown: 39 with no
confirmed start time."

## Conference order file

`data/cbb/conference_order_2027.json` sets the order of the conference entries in the View menu.
It is a repo file read by `cbb_daily_data.load_conference_order()`, not part of a release, and
`JSA_CBB_FIXTURE_DIR` never replaces it.

- `order`: the 32 conference names exactly as WarrenNolan.com lists them, best ranked first.
- `aliases`: CBBD short name to display name, only where they differ (`A-10` to `Atlantic 10`,
  `WCC` to `West Coast`, and so on). Every alias must point at a name in `order`, and all 32 CBBD
  short names for 2027 must resolve to a listed conference (a test checks this).
- `source`, `captured_on` (ISO date) and `note`.
- If the file is missing or malformed the page falls back to alphabetical order, and says so in
  the caption. It never fails the page.

**Refresh by hand once NCAA NET starts (about early December).** Before then the order carries
last season's values onto this season's lineups.

1. Open https://www.warrennolan.com/basketball/2027/net-conference and read the conference
   names from top to bottom.
2. Replace `order` with them. Keep each name as the site spells it, and keep all 32.
3. Add an `aliases` entry for any name that differs from the CBBD short name. Keep the existing ones.
4. Set `captured_on` to today's date and adjust `note`.
5. Run `python -m pytest tests/test_cbb_daily_contract.py tests/test_cbb_daily_page.py`, commit the
   file, and push.

Source and terms: WarrenNolan.com's robots.txt allows crawling and the site publishes no terms
for reuse. This file is a short hand-copied list of conference names in ranked order, not a
scrape run by code, and the page credits the source in its caption. Check the site's terms
again before copying anything beyond that list.

## Results for a predictions-only card

Results keep the v1 contract. For a card with no lines the pick on every row is
`no_play_line_unavailable`, so each finalized game must be graded `no_play` and its
`actual_cover_margin` is blank. A `win`, `loss` or `push` for a game with no line is
rejected. Finalized games still carry `home_score`, `away_score` and
`actual_home_margin`, which is what the prediction record uses.

## Publishing and rollback

```powershell
python -m publishing.cbb_cli publish-card --artifact <csv> --metadata <json>
python -m publishing.cbb_cli publish-results --artifact <csv> --metadata <json>
python -m publishing.cbb_cli status
python -m publishing.cbb_cli rollback-card --date <YYYY-MM-DD> [--build-id <id>]
python -m publishing.cbb_cli rollback-results --date <YYYY-MM-DD> [--build-id <id>]
```

Builds are immutable and date-keyed. Corrections create a new build and update the
date pointer; prior builds remain available for audit and rollback. A rollback only
moves the pointer, so commit `data/releases/cbb_daily/` afterward. A date's first
build has nothing to roll back to; revert the commit instead.

## Tests and fixtures

`tests/test_cbb_daily_contract.py` covers the contract and
`tests/test_cbb_daily_page.py` renders the page under AppTest. The browser suites set
`JSA_CBB_FIXTURE_DIR` to `tests/visual/fixtures/cbb_daily_empty`, an empty release root,
so the `cbb_daily_empty` scene keeps showing the empty state after real cards land.
The override is honored only when `APP_OFFLINE=1`; production never reads it.
`.gitattributes` forces `data/releases/cbb_daily/**` to LF so a Windows checkout cannot
rewrite a CSV and break its sha256.
