# Week 6 Thursday TD Props: Luna implementation plan

> Historical planning snapshot prepared October 15, 2026 for NFL Week 6. This brief records the intended work and evidence available then; it is not the current release procedure or project status. See the [documentation index](README.md), [touchdown props guide](../betting/anytime_td/GUIDE.md), and [publishing guide](../publishing/README.md) for current references.

Prepared October 15, 2026, for Joseph. This document is the canonical handoff.
Planning only: no odds releases, projections, activation, or deployment were run.

## Scope and decisions

- Refresh the existing public Streamlit website, `https://joschoanalytics.streamlit.app`, through its local producer and public-release workflow. This is not a Sites-hosted project.
- Publish the supplied DraftKings prices for Anytime TD, 2+ TD, and First TD where supported by the existing contracts. Preserve the frozen model and paper-tracking rules.
- Weekly Fantasy already has a Week 6 Tuesday release. There is no routine Thursday fantasy release. Review current confirmed availability news; refresh fantasy only if verified changes require it. A new TD price alone does not require new fantasy projections.
- Keep Tuesday captures and immutable releases. Use a unique Thursday release label and staging directory. Commit validated changes; Joseph performs the push. Local activation does not verify the hosted site or establish publication before kickoff.

## Verified starting point

| Item | Local evidence |
| --- | --- |
| Public repository | `JoSchoAnalytics`, clean when checked; HEAD `4d96619` |
| TD Week 6 | Exact fallback `betting/anytime_td/anytime_td_2026_week06.csv`: 164 rows across 12 games; Tuesday release at `td_count_model_beta/live/releases/2026_week06_week06_tuesday_draftkings.*` |
| TD canonical selection | `releases_manifest.json` binds Weeks 1-5 only; Week 6 currently uses the exact fallback filename |
| New paste | 370 parsed quote rows across all 14 scheduled games: 344 named player rows and 26 D/ST rows; all accepted rows have all three prices |
| New coverage | ARI at LA and BUF at LV are absent from the current 12-game TD board and present in the paste |
| Parser uncertainty | Fourteen single-price No Touchdown Scorer entries lack a market assignment. They remain unresolved. Unicode minus signs parse correctly |
| Fantasy | Active public build `fantasy-2026w06-902f3a5d9ab2`, 344 rows, produced October 13 at 21:34:46 UTC; Tuesday provisional availability signals are intentional |
| Fantasy cadence | Tuesday 09:00 refresh; daily 09:00 lineup checks and Sunday 11:30 checks. Reviewed confirmed-Out/replacement changes trigger subsequent refreshes |
| Missing prerequisite | `JoSchoAnalytics_private/data/lineup_news/2026_w06_lineup_overrides.csv` is absent; logged checks through Thursday failed on it |
| Publication pitfall | `JoSchoAnalytics_private/scripts/local_refresh.py::run_fantasy` publishes under the private root. Its success would not update the public website |

Source attachment:
`C:/Users/josep/.codex/attachments/24c516f4-95c7-4796-9b00-ccdba64f06ca/Pasted text.txt`

SHA-256: `07baea62fffdcb8c67a46098a574bf85d80dd56939868c4c2b6eb1e303bb8dea`.
Its observed filesystem write time is October 15 at 22:55:33 UTC, or 18:55:33 ET.
That is receipt evidence, not proof of the exact DraftKings capture time. Preserve
this distinction in metadata; use the receipt time as an explicitly labeled
observation proxy if no more precise source timestamp exists. Never backdate a run.

## Ownership and execution order

Luna owns orchestration, source selection, notebook execution, integration,
activation, verification, and the final handoff. Recheck repository status and
hashes before work because scheduled processes may change files.

Use bounded subagents with separate file ownership:

1. A routine Luna worker audits the preserved paste, parsed prices, identity reconciliation, and source counts. It does not activate releases or perform independent duplicate pulls.
2. A Sol worker handles the TD activation-helper changes and regression tests below. This requires reasoning about immutable artifacts and weekly refreshes.
3. Luna reviews fantasy news and the missing lineup prerequisite, then chooses the forward input. Escalate unresolved as-of/model-contract questions to Sol.

Read workspace and project `AGENTS.md` and the developing-with-streamlit skill.
Leave unrelated snapshots, logs, source files, and model bundles intact. Do not
run spread, totals, DFS, retraining, or historical backfill as part of this task.

### 1. Establish the clock and preserve the input

Record actual ET/UTC time, repo HEAD/status, active fantasy build, canonical TD
paths/hashes, model hash, and rollback files. SEA at DEN starts **October 15 at
20:15 ET**. The other games are October 18 and October 19.

Before kickoff, all 14 games may be refreshed. At or after kickoff, exclude
SEA at DEN from the prospective paste and retain its existing 22 public rows,
including prices, model probabilities, enrichment, provenance, and settlement
fields. Repeat the cutoff check before activation. If a staged target game starts
during review, restage only future games. Do not bypass the publisher clock or
use retrospective mode for the live website. Report any unrefreshed matchup.

Copy the original attachment byte-for-byte to a uniquely named private raw source
under `td_count_model_beta/live/`; include `received_20261015T185533ET` in the name
if using receipt evidence. Verify its hash. Keep raw, parsed full-slate, and any
future-only execution CSV distinct. Derive matchups and kickoffs from the canonical
schedule, not the computer's interpretation of the paste's word "Today."

### 2. Build the Week 6 operational notebook and reconcile the paste

Use `td_count_model_beta/notebooks/07_live_week06.ipynb` as the canonical Week 6
TD pipeline/review notebook, importing existing helpers. The existing
`07_live_week05.ipynb` is a reference, not a safe executable Week 6 template:
its dates, counts, week paths, and activation flag are hardcoded. Set activation
false initially. Separate parse, availability, scoring, enrichment, review,
activation, and validation into executable stages; aim for eight-minute cells
and enforce the 900-second limit.

Use `scripts/parse_draftkings_text.py::parse` in the notebook so reconciliation
and First TD pool issues are retained. An equivalent CLI is:

```powershell
# From td_count_model_beta; define paths and the documented observation time first.
& $tdPy scripts/parse_draftkings_text.py $raw $parsed --slate $slate --snapped-at $observedEt
```

Reconcile source entries, accepted quotes, unresolved identities, explicit
availability exclusions, and model-pending rows by game. Do not expect 344
final model rows merely because 344 named players were quoted. Review new names
and aliases without fuzzy matching or fabricated IDs. Include compact
before/after game and market counts and price-change tables.

Keep `--first-pool-complete` unset and `--no-td-market unknown` for this supplied
text. Do not guess which column contains the lone No Touchdown Scorer quote.
Retain First TD quoted prices and valid model probabilities, but leave de-vigged
book probabilities, value gaps, and First TD betting eligibility unavailable
where complete-pool evidence is missing. Show that limitation clearly. D/ST
outcomes can inform a verified quote pool but never become skill-player model
predictions. Do not remove integrity checks to make a market appear populated.

### 3. Review availability and decide whether fantasy needs a refresh

Check current official team/NFL availability evidence and record source, actual
observation time, game, canonical IDs, and replacement context. Preserve the
existing fantasy policy: Tuesday's numeric projection signal can retain an
Out/Doubtful label provisionally; it is not medical clearance. Terminal roster
exclusions and confirmed manual overrides still apply. TD has its own stricter
Wednesday-onward Sleeper Out policy; do not copy fantasy's exemption into TD.

Create the missing private Week 6 reviewed lineup CSV using the existing
`local_refresh.OVERRIDE_FIELDS` contract. A header-only file is valid only after
review finds no additional manual overrides. Use `sync_override` to update the
shared `workspace/nfl/raw/news/2026_w06_lineup_overrides.csv`. Preserve the
existing Week 6 QB override files. Absence of the old lineup file is not evidence
that nobody is unavailable.

If no confirmed change requires recomputation, retain the active fantasy build
and use the reviewed Tuesday forward parquet for TD. Verify its coverage,
source eligibility, feature contract, hash, and pre-kickoff timestamps; Tuesday
timing alone neither proves nor disproves suitability on Thursday. Completed
game inputs should cover through Week 5 only. Refresh missing/stale required
inputs once if needed, without overwriting frozen Tuesday captures.

If confirmed changes require a refresh, create a new producer output directory
and reuse the frozen Tuesday projection/directory envelopes plus reviewed
overrides. Existing CLI, from `weekly_projections_v2_prod`:

```powershell
& $producerPy independent_model/src/forward.py --season 2026 --week 6 --projections $tuesdayProjections --directory $tuesdayDirectory --lineup-overrides $reviewedOverrides --qb-input-overrides $qbOverrides --previous-forward $tuesdayForward --out-dir $thursdayFantasyOut
```

The baseline forward is
`independent_model/outputs/week06_live_tuesday/forward_2026_week06.parquet`.
Its Tuesday projection and directory inputs are under
`workspace/nfl/raw/sleeper/tuesday/2026_w06_projections.json` and `2026_w06.json`.
`--previous-forward` currently copies inputs only for locked players still present
in the newly built frame; it does not restore missing prior players, and scoring
runs afterward. Compare the full started-game player/game key set and all public
row values against the active release, including projections, stat heads,
availability, and provenance. If they differ, fix the producer's locked-row handling
under focused tests before activating fantasy. Require passing staleness/feature-health
gates, 28 scheduled teams, four-position coverage, truthful timestamps, and
explicit unavailable/replacement handling. Retain negative-projection diagnostics.
Do not invoke an unverified-projection bypass or refit the frozen model.

Validate and publish a warranted fantasy candidate from the **public** repository:

```powershell
& $sitePy -m publishing.cli validate --artifact $fantasyCsv --metadata $fantasyMetadata --schedule $schedule
& $sitePy -m publishing.cli publish --artifact $fantasyCsv --metadata $fantasyMetadata --schedule $schedule
```

Run the second command only after the first and the review pass. If unchanged,
report "reviewed; no fantasy refresh warranted" with evidence. Avoid using
`run_lineup_refresh.ps1 -Mode fantasy` for public publication: it also defaults
to capture/output paths that can overwrite frozen inputs. Do not casually run
`-Mode check` as a state-only repair: Week 6 lacks a successful fingerprint, so
the check can initiate a fresh private-root fantasy build. Restoring the reviewed
file resolves one prerequisite; it does not repair the publication target.
Repairing the scheduler's private/public architecture is separate follow-up scope.

### 4. Stage the TD refresh and enrich First TD

Pin `artifacts/td_lgbm_poisson_product_ngs_44.pkl`, SHA-256
`ec6171e5902a84b5986edd68adca7b8703006c8f8b57b020597dbc29fd0daac7`,
model version `td_product_ngs_44_frozen_2025_v1`. Pass the chosen forward explicitly;
the publisher's generic default is not the Tuesday versioned path.

Capture one fresh timestamped Sleeper directory snapshot and reuse it for each
attempt. Verify source hashes and as-of eligibility. Review presumed Out entries,
vacated red-zone shares, unresolved players, missing projections, QB replacement
gaps, and the frozen First TD candidate mass. Ordinary missing model inputs fail
closed; only existing documented pending-row semantics may be used.

Use a unique stage outside `live/`, for example
`td_count_model_beta/artifacts/staging/week06_thursday_<actual-run-stamp>/`.
Seed `stage/site/anytime_td_2026_week06.csv` from the current canonical enriched
board. Copy the unchanged per-slate metadata JSON for each retained game's `slate`
into `stage/releases/`, including
`2026_week06_week06_tuesday_draftkings.json` where referenced. The First TD enricher
clears unstarted games' enrichment before reading their frozen candidate mass;
without those prior records, retained unstarted games lose their probabilities.
Assert unchanged First TD values and eligibility for every retained game. This
seeding also preserves Thursday's rows in a future-only refresh.

```powershell
# From td_count_model_beta; $executionPaste excludes any already-started game.
& $tdPy scripts/publish_live_week.py $executionPaste $releaseLabel --forward $chosenForward --model $frozenModel --lineup-overrides $reviewedOverrides --sleeper-snapshot $snapshot --replace --stage-only --output-dir $stage
& $tdPy first_td/src/publish_site_columns.py --week 6 --input-csv $stagedBase --release-dir $stagedReleases --output-csv $enriched
```

Use a label such as `week06_thursday_draftkings_<actual-run-stamp>`; do not reuse
Tuesday's label. `--replace` deliberately replaces the requested future games'
old player rows and records the changes, including players no longer quoted.
It does not authorize changing started games. First TD enrichment must use the
new frozen candidate-mass records, not silently rescore from a default forward.
Require one player/game row, valid probability bounds, `p_ge2 <= p_ge1`, correct
price alignment, and explicit unverified First TD pools.

### 5. Fix the activation helper, then activate once

`scripts/activate_td_site_release.py` currently hardcodes Week 5 and a Week 5
filename and treats existing producer site mirrors as immutable. Calling it
unchanged will fail for this refresh. Make a scoped, tested generalization:

- Derive season/week from validated staged metadata and verify every row agrees. Build a unique release path containing the Thursday label. Keep the frozen model restriction.
- Keep release score CSVs, feature sidecars, and versioned metadata immutable. Existing files with different bytes must still fail.
- Permit intentional updates of mutable weekly site mirrors and availability registries, using expected-old hashes and atomic writes. Do not apply an immutable-install check to an already-existing cumulative mirror.
- Add exactly one Week 6 manifest binding, or replace that week's single binding on later refreshes while retaining all previous versioned artifacts. Preserve Weeks 1-5 unchanged. Recheck the manifest before its final atomic switch.
- Install and verify all public/private payloads before selecting the new public release. Normalize CSV and JSON bytes to LF before hashing. Preserve both CSV and metadata hash checks.
- Enforce the supplied incomplete First TD pool policy and documented model-pending semantics. No broad relaxation of probability, identity, or timing checks is needed for this paste.
- Recheck current kickoff times for the newly scored games immediately before activation. Compare retained started-game rows and First TD enrichment against the pre-run canonical board.

Activation command after those changes and all review gates:

```powershell
& $tdPy scripts/activate_td_site_release.py $stagedMetadata $enriched --site-dir $publicTdDirectory --live-dir $privateLiveDirectory
```

The public directory is `JoSchoAnalytics/betting/anytime_td`; the private live
directory is `td_count_model_beta/live`. The manifest-bound release must be the
same board the page, tracker, and graders read. Use `canonical_td_releases` and
`read_td_release` to verify it. Keep the legacy weekly mirror aligned if retained.
Record the prior fallback path/hashes and the new manifest entry for rollback.

## Validation and handoff

Use existing project Python environments, not the Windows Store alias. Verified
entrypoints exist at `td_count_model_beta/.venv/Scripts/python.exe`,
`JoSchoAnalytics/.venv/Scripts/python.exe`, and
`C:/Users/josep/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`.
Confirm required packages and compatibility before execution. Stop on every
nonzero command exit; do not continue to activation after a failed gate.

Run focused existing coverage, with new meaningful activation refresh tests:

```powershell
# td_count_model_beta
& $tdPy -m pytest tests/test_parse_draftkings_text.py tests/test_live_publish.py tests/test_activate_td_site_release.py -q
# JoSchoAnalytics
$env:APP_OFFLINE = '1'
& $sitePy -m pytest tests/test_anytime_td.py tests/test_attd_tracker_accounting.py tests/test_td_release_manifest.py tests/test_public_td_manifest_portability.py tests/test_td_grading_dispatch.py tests/test_weekly_fantasy_source.py tests/test_public_boundary.py -q
```

Add targeted tests for Week 6 metadata/path agreement, existing weekly mirror
refresh, immutable history, duplicate weekly pointers, stale manifest rejection,
incomplete First TD pools, LF/hash portability, and kickoff/locked-row protection.
Run fantasy forward/lineup tests only if that code changes; run
`JoSchoAnalytics_private/tests/test_local_refresh.py` if coordinator code changes.

Review the actual local Week 6 TD page on desktop and phone in all three markets,
including new ARI/LA and BUF/LV matchups, capture-time copy, pending First TD book
fields, tracker behavior, and retained Thursday rows if locked. Review Weekly
Fantasy if refreshed, including provisional availability labels and started-game
rows. Inspect actual rendered charts and screenshots for clipping, legibility,
spacing, and overlap. AppTest the affected pages with `APP_OFFLINE=1`; run public
visual regression tests if page layout/copy changes. Do not update Linux screenshot
baselines for a data-only refresh. State any visual verification that cannot be
completed; do not claim passing screenshots based on AppTest alone.

Keep the stale fantasy `next_release` Week 6 Awaiting projections entry separate
from the valid active release. Correct it through the existing scheduling contract
only if needed for the requested page behavior; do not invent a Thursday date.

Commit explicit validated paths in each affected repository. Do not stage unrelated
work or push. Report the changed TD/game/market counts, excluded/unresolved names,
time basis, source/model hashes, First TD limitations, fantasy refresh decision,
tests, visual result, rollback paths, commits, and the human push command. After
Joseph pushes, verify the hosted pages if accessible. Until then, describe the
result as locally prepared, not deployed.

Evidence entrypoints: `td_count_model_beta/{live/README.md,src/live_publish.py,scripts/parse_draftkings_text.py,scripts/activate_td_site_release.py,first_td/src/publish_site_columns.py}`;
`weekly_projections_v2_prod/independent_model/src/forward.py`;
`JoSchoAnalytics_private/scripts/{LOCAL_REFRESH.md,local_refresh.py,register_local_refresh_tasks.ps1}`;
`workspace/nfl/logs/lineup_refresh.jsonl`;
public `publishing/{td_releases.py,cli.py}`, release manifests, and the two page modules.
