# Weekly publication contract

Status: checked against the current CLI, validators, manifest, and grading workflow on 2026-09-10.
At this check, the clean 2026 Week 1 prediction release and fantasy release are active and no 2026 release has been graded.

This package is the only public write boundary for spread predictions and weekly
fantasy projections. Producer repositories write candidates to their own `outputs/`
directories; the website validates, snapshots, and activates them. No new top-level
folder under `cowork_OS` is required.

## Release lifecycle

1. `spread_v3_prod` or `weekly_projections_v2_prod` writes a weekly CSV plus
   `<artifact>.metadata.json` sidecar.
2. `publishing.cli publish` verifies the schema, season/week, identifiers,
   duplicates, finite values, model version, SHA-256, row and coverage claims,
   timezone-aware production time, and exact NFL schedule coverage.
   A live prediction candidate must also carry `tuesday_spread_book`,
   `tuesday_spread_price`, and `tuesday_median_spread_line`; its
   `tuesday_spread_line` is the best captured quote for the recommended side.
3. A passing candidate is copied into an immutable build directory under
   `data/releases/builds/`. Only then does the manifest's active pointer move.
   A post-kickoff correction may explicitly set `correction.model_update: true`
   when a validated model replacement changes the model version; line and
   schedule controls remain mandatory.
4. Weekly Predictions and Weekly Fantasy use that active pointer as their default.
   Track Record stays on 2025 until a 2026 prediction release has at least one final
   graded game.
5. `.github/workflows/grade_releases.yml` polls after game windows. Prediction
   and fantasy results are written separately under `data/releases/results/`;
   the released prediction or projection snapshot is never edited. The same
   action attaches rushing/receiving TD outcomes to the live ATTD CSV after a
   final game has a complete enough player-stat feed.

The checked-in manifest also drives the `Published`, `Scheduled`, and
`Awaiting projections` badges. A missing, malformed, or hash-mismatched
artifact fails closed and cannot become the default.

## Publish a producer candidate

Run from the JoSchoAnalytics directory. If `--schedule` is omitted for a live
candidate, the CLI obtains the season schedule through `nflreadpy` before validating.

```powershell
python -m publishing.cli publish `
  --artifact ..\spread_v3_prod\outputs\predictions_2026_week01.csv `
  --metadata ..\spread_v3_prod\outputs\predictions_2026_week01.metadata.json

python -m publishing.cli publish `
  --artifact ..\weekly_projections_v2_prod\independent_model\outputs\projections_2026_week01.csv `
  --metadata ..\weekly_projections_v2_prod\independent_model\outputs\projections_2026_week01.metadata.json
```

A validation failure returns exit code 1 and leaves the active and previous pointers
unchanged. `--no-activate` registers a passing build without moving the default.

## Status, scheduling, grading, and rollback

```powershell
python -m publishing.cli status
python -m publishing.cli schedule --product fantasy --season 2026 --week 1
python -m publishing.cli grade-published
python -m publishing.cli rollback --product predictions
python -m publishing.cli rollback --product fantasy --build-id <build-id>
```

Rollback only changes the manifest pointer and re-verifies the stored artifact hash.
It does not copy over or delete any build. Regrading unchanged inputs is idempotent,
so the scheduled workflow creates no commit when results have not changed.

## Bootstrap baseline

`python -m publishing.cli bootstrap` registers validated immutable copies of the
2025 Weeks 10–17 demo data, activates Week 10 for both products, schedules the
prediction Week 1 target, and leaves fantasy Week 1 awaiting its candidate. It does
not modify the legacy tracker or fantasy CSVs.
