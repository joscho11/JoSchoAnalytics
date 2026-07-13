# Artifacts manifest — `fantasy/seasonal_projections/`

Every tracked file in this directory, with its status. Facts only. Statuses:

- **FROZEN** — hash-pinned or one-shot; do not regenerate or edit (the shipped 2026 board,
  the pre-registered test results, the campaign constitution). Re-running a one-shot test is a
  campaign violation — read the JSON, never re-fire.
- **REGENERABLE** — a data/cache artifact a named script rebuilds.
- **ACTIVE TOOL** — a script that is still run (a builder, a fetcher, a test, or a fired-test
  harness whose code is frozen but which stays for reference/reproduction).
- **RETIRED** — kept for history; not shipped and not part of the live board or the frozen
  campaign record.

Frozen hashes recorded 2026-07-12 (SHA256, first 16 hex).

## Shipped 2026 Draft Board (FROZEN)

| File | Status | Notes |
|---|---|---|
| `phase4_band_2026.csv` | FROZEN | The shipped board. SHA256 `5727a65f012cd504`. Built by `phase4_band.py` → `apply_board_labels.py`, now byte-frozen. READ-ONLY. |
| `talent_index_2026.csv` | FROZEN | Descriptive 2025-efficiency context column. SHA256 `e36b284efaf78b02`. Built by `build_talent_index.py`, now frozen. Never blended with the value signal. |
| `season_dataset_2014_2026.csv` | FROZEN | Dataset feeding the 2026 board. SHA256 `ca3118c772d56f03` (regenerated 2026-07-12, Gainwell alias fix). Regenerable by `build_2026_board.py` but pinned to this hash for the shipped board. |
| `rank_equiv_reference.csv` | REGENERABLE | Points→finish-rank display table for the board. Built by `build_rank_equiv_reference.py`. |

## Campaign record (FROZEN — one-shot, never regenerate)

| File | Status | Notes |
|---|---|---|
| `PREREGISTRATION.md` | FROZEN | The campaign constitution. OUTCOMES section is append-only; rules above it are never edited. |
| `h6_results.json` | FROZEN | H6 fired result (PASS, pooled r +0.300). |
| `h7_results.json` | FROZEN | H7 fired result (FAIL, r −0.013). |
| `h8v_results.json` | FROZEN | H8v fired result (FAIL). |
| `h11_results.json` | FROZEN | H11 fired result (PASS, freshness control). |
| `h12_results.json` | FROZEN | H12 fired result (PASS, volatile RB/WR). |
| `step2_results.json` | FROZEN | H4 residual-model result (FAIL). |
| `phase0_benchmark_results.json` | FROZEN | Phase-0 walk-forward ladder of record. |
| `phase4_validation.json` | FROZEN | Band coverage validation (LOSO 79.4% / 49.8%). |
| `extension_gate_results.json` | FROZEN | A4 history-extension gate result (FAIL). |
| `model_a_compare_results.json` | FROZEN | Model-A bakeoff result (retired arc). |
| `sleeper_ex2020_results.json` | FROZEN | Ex-2020 Sleeper restatement. |

## Fired-test + benchmark harnesses (ACTIVE TOOL — code frozen, `--fire` spent)

| File | Status | Notes |
|---|---|---|
| `phase0_benchmark.py` | ACTIVE TOOL | The benchmark harness of record. |
| `h6_value_signal.py` | ACTIVE TOOL | H6 harness; `--fire` spent. Code frozen. |
| `h7_talent_signal.py` | ACTIVE TOOL | H7 harness; `--fire` spent. |
| `h8v_competition_signal.py` | ACTIVE TOOL | H8v harness; `--fire` spent. |
| `h11_freshness_signal.py` | ACTIVE TOOL | H11 harness; `--fire` spent. |
| `h12_volatile_signal.py` | ACTIVE TOOL | H12 harness; `--fire` spent. |
| `step2_residual_model.py` | ACTIVE TOOL | H4 harness; `--fire` spent. |
| `extension_gate.py` | ACTIVE TOOL | A4 extension-gate harness (FAILED, closed). |
| `recompute_sleeper_ex2020.py` | ACTIVE TOOL | Ex-2020 Sleeper restatement. |

## Board build + data tools (ACTIVE TOOL / REGENERABLE data)

| File | Status | Notes |
|---|---|---|
| `phase4_band.py` | ACTIVE TOOL | Band engine (walk-forward isotonic + residual quantiles). |
| `apply_board_labels.py` | ACTIVE TOOL | Post-process: population flags + licensed `signal_status` wording. |
| `build_talent_index.py` | ACTIVE TOOL | Regenerates `talent_index_2026.csv` (descriptive only). |
| `build_2026_board.py` | ACTIVE TOOL | Seeds the 2026 dataset rows. |
| `build_season_dataset.py` | ACTIVE TOOL | Builds the base per-(player, season) dataset. |
| `build_rank_equiv_reference.py` | ACTIVE TOOL | Builds `rank_equiv_reference.csv`. |
| `_utils.py` | ACTIVE TOOL | Shared helpers (`norm_name`, constants). |
| `snapshots.py` | ACTIVE TOOL | Snapshot helper used by the dataset build. |
| `fetch_adp.py` | ACTIVE TOOL | Fetches Sleeper ADP + projections. |
| `fetch_college.py` | ACTIVE TOOL | Fetches college production features. |
| `fetch_historical_adp.py` | ACTIVE TOOL | Fetches FFC historical ADP (2014–2019). |
| `fetch_adp_2008_2013.py` | ACTIVE TOOL | Fetches FFC historical ADP (2008–2013). |
| `test_seasonal_projections.py` | ACTIVE TOOL | Hermetic dataset-transform tests (in CI). |
| `test_draft_board.py` | ACTIVE TOOL | Hermetic board-logic tests (in CI). |
| `sleeper_adp_2020_2026.csv` | REGENERABLE | By `fetch_adp.py`. |
| `season_dataset_2014_2025.csv` | REGENERABLE | By `build_season_dataset.py` (pre-2026 training dataset). |
| `college_features.csv` | REGENERABLE | By `fetch_college.py`. |
| `college_production_2014_2024.csv` | REGENERABLE | By `fetch_college.py`. |
| `ffc_adp_2014_2019.csv` | REGENERABLE | By `fetch_historical_adp.py`. |
| `ffc_adp_2008_2013.csv` | REGENERABLE | By `fetch_adp_2008_2013.py`. |
| `qb_context_features.csv` | REGENERABLE | By `qb_context_features.py` (retired-arc feature). |
| `ecr_preseason.csv` | REGENERABLE | Expert-consensus-rank cache (external source). |

## Retired arc (RETIRED — kept for history, not shipped)

| File | Status | Notes |
|---|---|---|
| `build_value_board.py` | RETIRED | Engine for the retired Draft Value Finder tab (BUY/FADE). Kept; no tab renders it. |
| `draft_board_2025.csv` | RETIRED | Output of the retired three-way-blend engine (no verdict columns). Regenerable by `build_draft_board.py`. |
| `draft_board_2026.csv` | RETIRED | Same as above, 2026. Not the shipped board (`phase4_band_2026.csv` is). |
| `build_draft_board.py` | RETIRED | Three-way-blend board engine (earlier arc). |
| `board_view.py` | RETIRED | View helper for the retired blend board. |
| `train_model_a.py` | RETIRED | Model A (per-position PPG) trainer. |
| `train_model_b.py` | RETIRED | Model B (availability) trainer. |
| `train_rookie_model.py` | RETIRED | Rookie PPG trainer. |
| `rookie_features.py` | RETIRED | Rookie-model feature source (earlier arc). |
| `model_a_compare.ipynb` | RETIRED | Model-A algorithm bakeoff notebook. |
| `model_bakeoff.py` | RETIRED | Algorithm/hyperparameter bakeoff. |
| `blend_experiment.py` | RETIRED | Two-way our/ADP weight sweep. |
| `three_way_blend_test.py` | RETIRED | Three-way blend weight sweep. |
| `rookie_blend_test.py` | RETIRED | Rookie-handling A/B/C blend test. |
| `rookie_model_experiment.py` | RETIRED | Standalone rookie bakeoff vs ADP. |
| `diagnose_vet_rookie.py` | RETIRED | Vet-vs-rookie backtest split diagnostic. |
| `surprise_eval.py` | RETIRED | ADP-mispricing-skill eval (superseded by the pre-registered campaign). |
| `eval_projection.py` | RETIRED | PPG MAE metric panel. |
| `eval_totals.py` | RETIRED | Season-total eval. |
| `eval_contingent.py` | RETIRED | Contingent-opportunity eval (no signal). |
| `contingent_features.py` | RETIRED | Teammate-injury-risk features (no signal). |
| `opportunity_features.py` | RETIRED | Opportunity features (overfit). |
| `qb_context_features.py` | RETIRED | QB-context features (overfit). |
| `incoming_competition.py` | RETIRED | Incoming-competition guard for the retired value board. |
| `fade_deep_dive.py` | RETIRED | Fade-gate justification analysis. |
| `value_eval.py` | RETIRED | Earlier value-edge eval suite. |
| `value_eval_extended.py` | RETIRED | Extended-history value eval. |
| `adp_value_model.py` | RETIRED | ADP-residual value model experiment. |
| `rankings_2025.py` | RETIRED | 2025 standalone-model rankings. |
| `totals_board_2025.py` | RETIRED | 2025 season-total board. |
| `college_rookie_test.py` | RETIRED | College-production rookie experiment (network/training script). |
| `_validate_models.py` | RETIRED | Model-bakeoff validation helper. |
| `validate_extended_dataset.py` | RETIRED | Extended-dataset (2002+) validation (A4 gate FAILED). |
| `season_dataset_2002_2025.csv` | RETIRED | Extended-history dataset from the A4 gate (FAILED). **Do not touch.** |

## Not tracked (gitignored)

| Path | Notes |
|---|---|
| `content/` | TikTok content-sourcing sheets (descriptive-only extraction from the frozen board). Gitignored 2026-07-12. |
| `value_board_2025.csv`, `value_board_2026.csv` | Removed from git 2026-07-12 (retired Draft Value Finder data); history preserves them. |
