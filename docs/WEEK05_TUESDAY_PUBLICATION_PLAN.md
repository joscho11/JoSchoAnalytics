# Week 5 Tuesday website publication: Luna implementation brief

Prepared October 6, 2026. Target: NFL 2026 Week 5. This is a plan; no captures,
prediction runs, activation, or deployment were performed while preparing it.

## Outcome and decisions

Complete the Tuesday input captures, generate fantasy and spread candidates with
the existing production models, validate them, and activate both in the public
`JoSchoAnalytics` checkout. Review the resulting pages and commit scoped changes.
Joseph performs the Git push that updates the deployed website.

Joseph explicitly authorized **paid Odds API recovery of the Sunday baseline
first**, with **Monday DraftKings quotes as the backup if usable paid data is
unavailable**. This decision does not need another confirmation. The backup must
retain its Monday observation time and single-book provenance.

Use the project-review skill for evidence and the developing-with-streamlit skill
for page validation. Read applicable `AGENTS.md` before edits. Preserve unrelated
changes, especially the private seasonal-market snapshots and fantasy inactive
logs. Public pages continue to consume CSV/JSON releases; models stay private.

## Verified starting point

| Item | Local evidence on October 6 |
| --- | --- |
| Public website | `main`, `c8d03a5`; clean when inspected; both active products are Week 4, with no Week 5 builds |
| Fantasy release | `fantasy-2026w04-acd94fff81e3`, 399 rows; model `weekly-fantasy-v2-l1_wipe_prior_share_ranks-ad79f409f0b3` |
| Spread release | `predictions-2026w04-f3e67139da16`; model `spread-v3-prod-sunday-tuesday-market-46-qb-ir-scoped-flag-b4a325000b7a` |
| Week 5 slate | 15 games and 30 participating teams; Week 4 had 16 games |
| Free Tuesday capture | `workspace/nfl/raw/odds_api_tuesday/raw/2026_w05.json`, captured October 6 about 11:11 ET; 15 events and complete capture coverage |
| Tuesday player directory | `workspace/nfl/raw/sleeper/tuesday/2026_w05.json` exists from the spread capture |
| Fantasy projections capture | `workspace/nfl/raw/sleeper/tuesday/2026_w05_projections.json` is absent |
| Fantasy automation | `weekly-fantasy-tuesday-refresh` failed before fetching, because the private Week 5 lineup override CSV is absent |
| Paid Tuesday capture | Absent; task failed before an API request because the selector assumes 16 games |
| Sunday baseline | `workspace/nfl/raw/odds_api_rebuild/sunday_1120/2026_w05.json`: manual DraftKings email, observed Monday October 5 at 06:48 ET; exact underlying quote capture time is unknown |
| Recent game inputs | Spread PBP and the latest full fantasy outcome captures cover Weeks 1-3; Week 4 refresh is required |

The intended scheduled slot and actual capture time are different. Preserve both;
do not label the existing Tuesday capture as an actual 09:00 pull or the Monday
quotes as observed Sunday. Older READMEs and the fantasy holdout-export notebook
describe superseded workflows. Current source, bundle hashes, and release metadata
take precedence.

## Ownership and order

Luna coordinates, integrates, runs the notebook, verifies candidates, and owns the
final handoff. Use two bounded subagents where they help: one owns the spread
bye-week/source-validator fixes and tests; one owns fantasy input capture and
lineup preparation. Their files must not overlap. The coordinator owns common
refreshes and public publication, so workers never activate manifests or repeat
API pulls independently. Use Luna for routine work; reserve Sol for unresolved
as-of or model-contract reasoning.

### 1. Establish a reproducible run

From `C:/Users/josep/Desktop/random_stuff/cowork_OS`, record each affected repo's
branch, HEAD, dirty paths, model hashes, and current active/previous build IDs.
Recheck the inputs because scheduled tasks can change local files during work.

Use the verified executables rather than bare `python`, which resolves to a
Windows Store alias here:

```powershell
$root = 'C:\Users\josep\Desktop\random_stuff\cowork_OS'
$producerPy = 'C:\Users\josep\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$sitePy = Join-Path $root 'JoSchoAnalytics\.venv-test\Scripts\python.exe'
```

The producer runtime is Python 3.12 with scikit-learn 1.9.1. The site environment
works and has Streamlit 1.59.1, pytest, and notebook libraries. Producer forward
and audit `--help` commands and public validation/publication CLI signatures were
checked successfully. Do not use `C:/tmp/jsa-bt/Scripts/python.exe`, which points
to an inaccessible Store interpreter in this session.

Create one canonical operational notebook in the private repo:
`JoSchoAnalytics_private/notebooks/weekly_website_release.ipynb`. Parameterize
season/week, input paths, versioned output directories, and publication switches.
Represent input inspection, recovery, game-data refresh, each model's scoring,
audits, review tables/charts, and public publication as separate executable
stages. Import existing producer logic rather than copying its feature recipe.
Use explicit producer subprocess executables when the notebook kernel differs.
Default activation to false until the review gates pass. Keep cells near eight
minutes, enforce a maximum of 900 seconds, and split long pulls by source rather
than allowing a single oversized cell. Public-repo rules prohibit notebooks there.

### 2. Fix the actual spread bye-week blockers

Replace fixed participation assumptions with canonical schedule sets in:

- `spread_v3_prod/src/tuesday_odds.py::_slate_week` (currently requires 16).
- `spread_v3_prod/src/odds.py::validate_tuesday_snapshot` (currently requires 16).
- `spread_v3_prod/src/forward.py::_read_slate` (currently requires 16).
- `spread_v3_prod/src/forward.py` synthetic-state coverage (currently requires
  all 32 teams, although only 30 play this week).

Require a nonempty, unique schedule slate, exact scheduled game/team coverage,
one state per participating team/game, and two state rows per game. Keep the
separate 32-team checks for league-wide coach, staff, and win-total source tables.

Generalize `scripts/audit_forward_release.py` from Week 4: schedule-derived game
counts, history through week minus one, and validated paid-first/free-fallback
Tuesday selection. Derive week-sensitive feature expectations from legal inputs
instead of pinning Week 4's games-played or venue-HFA values. Gate Week 4-specific
report sections by their week. Retain model hash/contract, replay, finite values,
line agreement, QB, source timing, and continuous-feature z-score hard stops.

Add meaningful 15-game/30-team fixtures, missing and duplicate scheduled-quote
failures, and regression coverage for 16-game weeks. Do not refit, promote a new
model, change HIGH from the 3.0-point Tuesday-median rule, or qualify HIGH using
the shopped execution quote. `run_prod.py publish` promotes/refits models according
to its options; it is not the weekly forward command.

### 3. Recover Sunday odds once, then validate the authorized backup

Implement a targeted helper, for example
`spread_v3_prod/scripts/capture_paid_sunday.py --season 2026 --week 5 --out <path> --fallback <manual-path>`.
This is a new helper to implement, not an existing CLI. Use a separate immutable
destination:
`workspace/nfl/raw/odds_api_rebuild/sunday_1120_paid_recovery/2026_w05.json`.

Compute the anchor using `market_history.sunday_before_week` and the canonical
schedule. The Week 5 target is **October 4 at 23:20 ET**, equivalent to
**October 5 at 03:20 UTC**. Use existing `market_history.fetch_historical` with
`spreads,totals,h2h`, US regions, and American odds. The source's estimated cost
is 30 paid credits; record the response's actual quota usage. Never log keys or
credential-bearing URLs, and never invoke season-wide backfill for this one week.

Before requesting, validate/reuse a complete file at that destination if one
already exists. Otherwise make one targeted historical request. Use
`coverage_report`, `_record`, and the immutable writer; require the provider
timestamp at or before the requested anchor, exact 15 scheduled pairs, correct
quote signs, and usable spread quotes. Preserve any missing totals/moneylines in
the existing missing-feature policy and report them. An incomplete/unusable paid
slate cannot be mixed with manual quotes one game at a time. Log a clear reason
and select the whole authorized manual slate instead when paid data is unavailable.

For fallback only, add a narrow 2026 Week 5 `manual-draftkings-email` validator in
`forward.py`. Require the correct season/week and canonical 15 games, one
DraftKings book per game, valid markets, the existing source-document provenance,
and the honest Monday 06:48 ET observation before the Tuesday prediction cutoff.
It falls inside the existing Sunday-night-to-Monday-morning recovery window, but
the current generic late-Sunday guard does not support this manual source.
Keep the nominal Sunday marker separate, disclose that exact quote capture time
is unknown, and carry this exception and paid-attempt outcome into coverage and
release metadata. The declared email hash is not independently verified unless
the original source document is found. Preserve the original manual file bytes.

Test paid valid/complete selection, unavailable/incomplete paid fallback, truthful
Monday timestamps, wrong-week/late/tampered fallback rejection, and unchanged
generic historical timing guards. Do not add a broad cutoff bypass.

The new helper must exit nonzero if neither source validates, and emit a JSON
selection report containing `selected_path`, `selected_source`, validation status,
source hash, and paid-attempt outcome. In the notebook, from `spread_v3_prod`,
set the selected path explicitly before the scoring stage:

```powershell
$paidSundayPath = Join-Path $root 'workspace\nfl\raw\odds_api_rebuild\sunday_1120_paid_recovery\2026_w05.json'
$manualSundayPath = Join-Path $root 'workspace\nfl\raw\odds_api_rebuild\sunday_1120\2026_w05.json'
$selectionJson = & $producerPy scripts\capture_paid_sunday.py --season 2026 --week 5 --out $paidSundayPath --fallback $manualSundayPath
if ($LASTEXITCODE -ne 0) { throw 'Sunday source recovery failed' }
$sundaySelection = $selectionJson | ConvertFrom-Json
$selectedSundayPath = $sundaySelection.selected_path
if (-not $selectedSundayPath -or -not (Test-Path -LiteralPath $selectedSundayPath)) { throw 'Validated Sunday source path missing' }
```

### 4. Complete fantasy captures and refresh completed-game inputs

Prepare the missing private
`JoSchoAnalytics_private/data/lineup_news/2026_w05_lineup_overrides.csv` with the
16-column `local_refresh.OVERRIDE_FIELDS` contract. Review current source-backed
Out/replacement information for this week's actual matchups. An empty reviewed
snapshot may use headers only when the review finds no manual overrides; absence
of the old file is not evidence that there are no unavailable players. Do not
copy Week 4's rows or invent replacement starters. Sync the reviewed file to
`workspace/nfl/raw/news/2026_w05_lineup_overrides.csv` using the existing helper.

Create only the missing Sleeper weekly projection snapshot. Reuse the existing
Tuesday player directory; the current `capture_sleeper_inputs` helper overwrites
both fixed filenames, so add create-only/reuse behavior or a targeted projection
capture helper. Fetch regular-season QB/RB/WR/TE projections, save a list payload
inside an envelope with real UTC request/capture timestamps and season/week, and
record its SHA-256. No bare-list/unverified-projection override for live scoring.

Run the current-season fantasy refresh in bounded stages from
`weekly_projections_v2_prod/independent_model/scripts/pull_current_season.py`.
Its current `main()` prints the S1-S4 gate results but returns zero even when a
gate fails. Make failed gates stop the notebook and launcher, either by fixing
that exit contract or by explicitly asserting the structured results. Require
Week 4 player stats, opportunity, snap counts, PBP, schedule, and team EPA;
preserve existing per-source missingness policies for auxiliary feeds.

Then refresh the spread cache through
`spread_v3_prod/scripts/refresh_current_pbp.py`. Its `fetch()` is isolated from
validation/write logic, so prefer passing the just-captured PBP/schedule through
that existing validation path to avoid another large pull. Keep full-week
completeness, old-column/game retention, hash-bound backup, and atomic replacement.
If using its CLI unchanged, `--dry-run` followed by a write fetches twice; avoid
that duplication through a small cached-input wrapper. Verify Weeks 1-4 and all
16 Week 4 finals/played-game IDs, with no Week 5 outcomes in model inputs.

Reuse today's live injury/depth/roster/players captures when eligible; verify
roster parity and exact hashes. Refresh only missing/stale required sources.
Choose the prediction as-of instant after the required captures complete, using
the code's actual Tuesday eligibility policy. Never backdate new observations.

### 5. Generate candidates and review the model inputs

Use new versioned producer output directories. From their respective roots:

```powershell
# weekly_projections_v2_prod
& $producerPy independent_model\src\forward.py --season 2026 --week 5 --projections ..\workspace\nfl\raw\sleeper\tuesday\2026_w05_projections.json --directory ..\workspace\nfl\raw\sleeper\tuesday\2026_w05.json --lineup-overrides ..\workspace\nfl\raw\news\2026_w05_lineup_overrides.csv --out-dir independent_model\outputs\week05_live_v1

# spread_v3_prod, after its patches and Sunday source selection
& $producerPy src\tuesday_odds.py select --season 2026 --week 5
$asOf = (Get-Date).ToUniversalTime().ToString('o')
& $producerPy src\forward.py --season 2026 --week 5 --as-of $asOf --sunday-market $selectedSundayPath --out-dir outputs\week05_live_v1
```

`$selectedSundayPath` is the validated paid recovery file, or the authorized
manual file after the scoped fallback adapter passes. Tuesday selection should
reuse today's whole free snapshot if no valid paid 09:00 artifact exists. Do not
make an additional paid Tuesday request as part of the Sunday recovery. If
explicitly pinning Tuesday paths, use the same file for `--odds` and
`--market-tuesday`.

Both products must emit the Week 5 forward parquet, coverage JSON, weekly CSV,
and SHA-256 metadata sidecar. Verify frozen model identities, fantasy staleness
and feature-health reports, all four fantasy positions across the 30 scheduled
teams, valid team/opponent pairs, and hard-unavailable exclusions. Surface unusual
values and missingness rather than hiding diagnostics.

Prepare a concrete 30-team QB input table with selected player IDs, prior-game
sources, eligible reports/statuses, and uncertainty flags. Follow the frozen QB
precedence rules; do not invent overrides or scenarios. The current release
auditor explicitly requires the QB table Joseph approved. Present this completed
table for that approval if no applicable Week 5 approval exists, then save the
approved JSON; do not manufacture approval merely to satisfy the gate.

```powershell
# spread_v3_prod, after the QB review gate
& $producerPy scripts\audit_forward_release.py --season 2026 --week 5 --out-dir outputs\week05_live_v1 --report artifacts\week05_input_review_v1.json --qb-approved artifacts\week05_qb_table_approved_v1.json
```

Require audit status passed and no hard failures. Include a compact game/edge/HIGH
table, fantasy position and team counts, and a small fantasy-vs-Sleeper review
chart with plain-language interpretation. Render charts within about 30 seconds
and inspect the actual output for legibility and clipping.

### 6. Validate, activate publicly, visually review, and commit

Use public `JoSchoAnalytics/publishing.cli`, with the same refreshed local schedule
for both validations. Do not use normal `run_lineup_refresh.ps1 -Mode fantasy`
for website publication: it currently publishes under the **private** root.
Its `-DryRun` still captures/builds, so it is not a read-only inspection command.

From `JoSchoAnalytics`:

```powershell
$schedule = '..\workspace\nfl\nfl_2026_schedule.csv'
$fantasy = '..\weekly_projections_v2_prod\independent_model\outputs\week05_live_v1\projections_2026_week05.csv'
$fantasyMeta = '..\weekly_projections_v2_prod\independent_model\outputs\week05_live_v1\projections_2026_week05.metadata.json'
$spread = '..\spread_v3_prod\outputs\week05_live_v1\predictions_2026_week05.csv'
$spreadMeta = '..\spread_v3_prod\outputs\week05_live_v1\predictions_2026_week05.metadata.json'
& $sitePy -m publishing.cli validate --artifact $fantasy --metadata $fantasyMeta --schedule $schedule
& $sitePy -m publishing.cli validate --artifact $spread --metadata $spreadMeta --schedule $schedule
```

If the schedule CSV is stale, update it from the newly verified schedule first.
Run public publication only after each product's validation and review succeed:

```powershell
& $sitePy -m publishing.cli publish --artifact $fantasy --metadata $fantasyMeta --schedule $schedule
& $sitePy -m publishing.cli publish --artifact $spread --metadata $spreadMeta --schedule $schedule
```

Check every exit code; stop on failure. Each command activates its product only
after validation. Preserve prior immutable builds and record both rollback IDs.
Fantasy may proceed independently if spread recovery or its QB gate is blocked;
report the incomplete product clearly instead of presenting mixed defaults as
completed work. Correct the stale fantasy next-release pointer using the existing
schedule CLI for the reviewed Week 5 target, rather than guessing a Week 6 date.

Focused validation commands, from the indicated repos:

```powershell
# spread_v3_prod: add the new bye-week/paid-Sunday tests to this bounded suite
& $producerPy -m pytest tests\test_tuesday_odds.py tests\test_forward_release.py tests\test_qb_selection.py tests\test_release_qb_metadata.py -q
# weekly_projections_v2_prod/independent_model
& $producerPy -m pytest tests\test_current_season_capture.py tests\test_forward.py tests\test_lineup_overrides.py tests\test_sleeper_weekly.py -q
# JoSchoAnalytics_private, if capture/coordinator helpers changed
& $producerPy -m pytest tests\test_local_refresh.py -q
# JoSchoAnalytics
$env:APP_OFFLINE = '1'
& $sitePy -m pytest tests\test_publishing_pipeline.py tests\test_weekly_fantasy_source.py tests\test_betting_pages.py tests\test_public_boundary.py -q
```

Render the actual Week 5 local pages at phone and desktop sizes. Confirm both
default to 2026 Week 5 with Published status; spreads show exactly 15 matchups
with correct sign/book/price/HIGH behavior; fantasy shows the reviewed universe,
availability, and legible tables. Inspect screenshots, spacing, clipping, and
provenance copy. Run the visual-regression suite if public layout/copy changes;
do not refresh Linux baselines for a data-only release. If page source changes,
run affected AppTest coverage with `APP_OFFLINE=1`.

Only then stage explicit changed paths and commit in each affected repo. Never
stage all of a dirty producer/private repo. Keep model bundles and existing
immutable snapshot bytes unchanged. Do not push. Hand Joseph the public commit
and the human push command; after that push, verify the live site when accessible.
Local activation alone does not confirm deployment.

## Acceptance and handoff

- Existing captures are reused; the missing fantasy projection envelope is
  captured; paid Sunday recovery or its authorized whole-slate Monday fallback
  has truthful provenance and recorded quota/outcome.
- Week 4 completed-game inputs pass their gates. Week 5 coverage is derived from
  the canonical schedule, and frozen model hashes do not change.
- Both candidates and public validators pass; spread QB approval and input audit
  pass; pages are visually reviewed at their intended sizes.
- Public active pointers name 2026 Week 5, with immutable releases and rollback
  IDs. Scoped commits are complete; deployment awaits Joseph's push.
- Report capture/source timestamps, chosen Sunday/Tues sources, fantasy row and
  position counts, 15-game/HIGH counts, model/build IDs, test/visual results,
  public commit, rollback IDs, and any incomplete gate in a concise handoff.

Evidence entrypoints: public `AGENTS.md` and `publishing/{cli,validators,publisher}.py`;
private `scripts/local_refresh.py` and `workspace/nfl/logs/lineup_refresh.jsonl`;
producer `src/{forward,tuesday_odds,odds,market_history}.py`,
`scripts/{audit_forward_release,refresh_current_pbp}.py`, fantasy
`independent_model/scripts/pull_current_season.py`, today's capture logs, and the
public release manifest. Recheck these before execution if the checkout changes.
