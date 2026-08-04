# Claude implementation brief: dated 2026 Sleeper projection and ADP snapshots

## Objective

Implement a durable, point-in-time snapshot system for the 2026 preseason so the ADP-consensus study can later compare Sleeper projections, ADP, and our model at genuinely matched historical cutoffs. Begin capturing immediately. Do not claim that August 1–2, 2026 can be reconstructed retrospectively.

This is implementation work, not a proposal. Inspect the repository, make the changes, run the relevant tests, execute one live capture if network access is available, and report the exact files, timestamps, hashes, schedule, retention guarantees, and any unresolved limitation.

Repository root:

`C:\Users\josep\Desktop\random_stuff\cowork_OS\JoSchoAnalytics`

Research project:

`fantasy/projections/research/adp_consensus_agreement_2026-08-02`

## Read before changing anything

Read all repository instructions and relevant memory files first. At minimum, inspect:

- `.github/workflows/board_refresh.yml`
- `fantasy/seasonal_projections/refresh_board_adp.py`
- `fantasy/seasonal_projections/fetch_adp.py`
- `fantasy/seasonal_projections/ARTIFACTS.md`
- the relevant `.gitignore` rules
- the research project's `README.md`, `CLAUDE_LEAKAGE_AUDIT.md`, and pipeline notebooks
- any tests covering seasonal projection fetching or board refreshes

The repository already has a daily 13:00 UTC preseason refresh. Reuse and extend that workflow unless inspection proves it unsuitable. Do not create a second competing schedule.

## Point-in-time capture requirements

For every successful daily capture, retain the exact source response used to obtain Sleeper ADP and projections, plus a normalized analytical snapshot derived only from that response. ADP and projection values must share the same retrieval event.

Preserve, when supplied by the source:

- Sleeper player ID, name, normalized name, team, and position
- every available ADP field and positional/overall rank field
- every available Sleeper projection and component field, including scoring-format totals, games projected, passing, rushing, receiving, kicking, and defensive fields rather than a hand-selected subset
- the contemporaneous player-ID-to-player-metadata mapping used for normalization or joins; do not rely on a future mutable player directory to interpret an old snapshot

For provenance, record:

- retrieval timestamp in UTC and America/New_York
- season and source endpoint
- HTTP status, content type, and any `Date`, `ETag`, or `Last-Modified` response headers
- SHA-256 of the exact raw response bytes
- SHA-256 of every normalized output
- row counts, unique-player counts, required-field checks, and duplicate-ID checks
- the hash/version of the capture and normalization logic used
- success/failure status and a diagnostic message

Never overwrite a prior capture. Use an unambiguous timestamped directory or filename such as `YYYY-MM-DDTHHMMSSZ`. Write atomically so an interrupted fetch cannot look valid. Retain the exact raw response, compressed if appropriate, not just parsed values.

Reject unhealthy responses rather than publishing them as valid snapshots. Add explicit checks for HTTP failures, malformed JSON, implausibly low row counts, missing expected field families, duplicate player IDs, and widespread null/sentinel values. Record failed attempts separately without allowing them into the valid snapshot index.

## Existing behavior and privacy fence

Preserve the existing live-board overlay behavior and its output contract. The new archive is research evidence, not an input into the live board, player recommendations, or video selections. Keep the raw snapshots and derived research snapshots private/untracked in the same spirit as the existing `adp_logs/` fence. Do not accidentally commit private research artifacts or add an active consumer.

Do not add a `.py` file under the research project, whose reproducibility audit asserts that its analytical implementation is notebook-contained. It is acceptable and preferable to extend the existing automation module under `fantasy/seasonal_projections/`, with hermetic tests alongside the existing automation tests.

## Retention is a required result, not a vague intention

The current GitHub Actions artifact retention appears to be 90 days. That is enough to bridge August into part of the season but may not be enough for final 2026 validation. Inspect the actual repository/workflow limits and implement the strongest durable private retention available with the already-authorized repository infrastructure.

The target is recoverability through at least February 15, 2027. Do not introduce a new external service, secret, paid resource, or public artifact without Joseph's approval. Do not quietly commit the snapshots if that violates the existing privacy fence.

If the available infrastructure cannot guarantee that date, implement everything that is safely possible now—the durable local untracked archive, daily private workflow artifact, hashes, manifest, and validation—and state the exact remaining retention gap plainly. Do not label retention solved if it is not. Provide one minimal follow-up choice Joseph can authorize to close the gap.

## Workflow behavior

Extend the existing daily preseason job rather than duplicating it. The capture should occur before any lossy selection of fields. Preserve the current season-start guard unless the research requirement warrants a narrowly documented adjustment. A failed research snapshot must be visible and diagnosable; decide deliberately whether it should block the board overlay, and document the chosen failure isolation.

The workflow artifact should include the dated raw response, normalized snapshot, metadata/provenance record, and append-only manifest/ledger needed to verify the capture later. Ensure artifact paths do not accidentally omit hidden or nested files.

Because the system is being added on August 3, explicitly document that August 1–2 have no genuine archived snapshots and must not be backfilled from current data under historical labels.

## Tests and validation

Add hermetic fixture-based tests that require no live network access. At minimum prove:

- identical raw input produces identical normalized output and hashes
- row ordering cannot change the normalized hash
- two captures never overwrite each other
- malformed/truncated/low-row/duplicate-ID responses are rejected
- failed attempts cannot enter the valid index
- the historical player mapping is sufficient to interpret the normalized rows without consulting a newer directory
- the existing board overlay output remains compatible
- private snapshot paths remain ignored by version control

Then run the relevant test suite and any structural/reproducibility checks affected by the changes. Inspect the working tree first and preserve unrelated user changes.

If network access is available, perform one real capture immediately and validate its raw and normalized hashes from disk. Do not fabricate a successful live capture if access is blocked.

## Research-facing audit notebook

Add a small 2026 snapshot-audit notebook only if it can be integrated without weakening or breaking the existing eight-notebook audit. Its purpose is to index captures, verify hashes and timestamp coverage, surface gaps, and later compare projection/ADP movement across cutoffs. It must not contaminate the completed 2021–2025 estimates or silently become part of that historical panel.

Follow Joseph's required notebook structure exactly:

- introduction markdown cell first
- every code cell immediately preceded by an `Explain` markdown cell describing what it will do
- every code cell immediately followed by an `Interpretation` markdown cell explaining and analyzing its stored result
- conclusion and next-steps markdown cell last
- executed outputs retained and checked

If adding the notebook now would compromise the established pipeline's strict audit, defer the notebook, explain why, and provide a precise integration point once multiple snapshots exist. Do not weaken an audit merely to make an extra file pass.

## Final response

Report:

1. the exact files changed and why;
2. the actual daily schedule in UTC and America/New_York;
3. the first real capture timestamp, row count, raw hash, and normalized hash, or the exact reason no live capture was possible;
4. the archive and manifest locations;
5. the tested retention guarantee and any gap through February 15, 2027;
6. test and validation results with exact counts;
7. confirmation that the existing board behavior and privacy fence remain intact;
8. any unavoidable limitation requiring Joseph's decision.

Do not describe a planned feature as implemented. Verify claims from the files and executed outputs.
