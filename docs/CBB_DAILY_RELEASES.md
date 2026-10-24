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

Below the games sits an exploratory ATS shadow (8.5-point policy). A provider-neutral
median CBBD spread is joined after prediction. A game becomes a shadow pick only when
the absolute model edge is at least 8.5 points. Spreads are shown exactly as collected
(for example -3.25, -3, PK) and edges to two decimals, so an edge of +8.46 is never
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
