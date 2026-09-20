# College Basketball daily releases

The College Basketball page is a single public Beta surface for the daily 2027
score-and-winner predictions. It reads only sanitized, hash-verified CSV and JSON
releases under `data/releases/cbb_daily/`; it never loads model files, features,
credentials, raw CBBD responses, or provider-level rows.

The score model is universal and does not consume the spread. A provider-neutral
median CBBD spread is joined after prediction. A play is highlighted only when the
absolute model edge is at least 8.5 points. This is an exploratory shadow policy,
not a promise of betting success. Historical benchmark results are descriptive and
do not prove when a line became available. Live records use genuine timestamped
2027 snapshots only.

To publish a validated card locally:

```powershell
python -m publishing.cbb_cli publish-card --artifact <csv> --metadata <json>
python -m publishing.cbb_cli publish-results --artifact <csv> --metadata <json>
python -m publishing.cbb_cli status
```

Builds are immutable and date-keyed. Corrections create a new build and update the
date pointer; prior builds remain available for audit and rollback.
