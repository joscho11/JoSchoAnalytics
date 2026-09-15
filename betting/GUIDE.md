# Betting models

Status: checked against the current code and release contract on 2026-09-08.

The betting area contains the 2026 spread product, a frozen 2025 demo, and an experimental totals model. These systems do not share the same claim or lifecycle.

## Current 2026 spread product

The live spread producer is `spread_v3_prod`, a separate private repository. It writes candidate predictions and a SHA-256 sidecar. This public repository validates those candidates, stores immutable builds, and activates them through the [publishing contract](../publishing/README.md).

The 2026 display logic lives in `live_2026.py`:

- The model predicts home margin from information available by Tuesday at 9:00 a.m. ET.
- The current leakage-fixed 2021-2025 benchmark marks `HIGH` when the model differs from the Tuesday US median by at least 3.0 points, then grades those tickets at the best US Tuesday number.
- Starting in 2026, the Tuesday US median drives the model, pick, edge, and `HIGH` flag. The best captured US quote for the recommended side is displayed separately and drives grading.
- A later line can remove a `HIGH` label, but cannot create one.
- The final regular-season week is excluded from `HIGH` labels.
- There is no `MEDIUM` tier and no all-bets performance claim.
- Every game remains visible, including `PASS` games.

The current leakage-fixed historical evaluation contains 436 qualifying picks from 2021 through 2025. It went 253-183 ATS, or 58.03%, scored at the best US Tuesday number on the same HIGH tickets. The one-sided lower confidence bound is 54.10%, above the declared 52.4% break-even threshold. Those historical tickets were selected against the Tuesday US median; the median grade was 249/437, Wilson 53.05%. This is the current benchmark, not a substitute for graded 2026 results. No 2026 games have been graded yet. The superseded 2.5-point benchmark was 295/526, 56.08%, Wilson 52.50%. The withdrawn 192/336 = 57.14% figure used same-week injury reports that postdate Tuesday.

## What appears on the site

The current weekly page reads only active release artifacts. It shows the model margin, the line used for the Tuesday decision, the current line when available, the model side, confidence, and result after grading.

The frozen 2025 demo remains available for reproducibility. It used a three-voter consensus with `HIGH`, `MEDIUM`, and `PASS` labels. Those rules do not describe the 2026 product.

## Results and claim boundaries

| System | Evaluation | Result | Current interpretation |
|---|---:|---:|---|
| Current clean spread benchmark | 2021-2025 locked historical evaluation | 295/521, 56.62% ATS | Median-triggered tickets; Wilson lower 53.03%, above 52.4%; graded at best US Tuesday number |
| Archived in-repo spread model | Corrected 2018-2025 audit | 129/238, 54.20% ATS | No demonstrated edge; 95% Wilson lower bound is 47.86% |
| Totals model | Walk-forward cross-validation | 55.7% UNDER accuracy, n=575 | Research result, not a deployed performance claim |
| Totals model | 2025 live tracking, Weeks 10-17 | 52.2%, n=46 | Too small and too close to chance for an edge claim |

The archived spread model once showed an apparent 64.2% result. That number was retracted after a pregame feature leak and player-identity errors were found. The corrected result is 129/238. A later 192/336 = 57.14% Tuesday HIGH figure was withdrawn after the same-week injury join was found to postdate the Tuesday slot. The current leakage-fixed 3.0-point benchmark is 253/436, 58.03%, Wilson 54.10%, with best-quote grading; the Tuesday median grade is 249/437, Wilson 53.05%. The superseded 2.5-point benchmark was 295/526, 56.08%, Wilson 52.50%.

## Totals model

The 2025 totals work is an UNDER-only experiment shown as a demo. It is not on the 2026 week page. The filters below are research choices, not evidence of future profitability:

- only positive UNDER edges;
- predicted total below 45;
- dome games excluded;
- late-season games excluded from the tracked subset.

## Data and release flow

```text
private producer
    -> candidate CSV + SHA-256 sidecar
    -> publishing validation
    -> immutable data/releases/builds artifact
    -> active manifest pointer
    -> weekly page
    -> separate grading ledger
```

Publication keeps prediction inputs immutable. Final scores and ATS results are stored under `data/releases/results/` rather than written back into the released prediction CSV.

## Public repository map

| Path | Role |
|---|---|
| `live_2026.py` | 2026 confidence and display rules |
| `calibration.py` | Cover rates from the graded tracker |
| `predictions_tracker.csv` | Graded 2025 demo plus any stamped 2026 rows |
| `totals_tracker.csv` | 2025 experimental totals tracking |
| `slate_2026.csv` | 2026 matchup skeleton for the week page |
| `../publishing/` | Candidate validation, immutable builds, activation, rollback, and grading |
| `../site_pages/page_weekly_predictions.py` | Release-backed weekly spread page |
| `../data/releases/` | Immutable published prediction builds |

Training code for the live spread is in the private `spread_v3_prod` repository. This public tree does not ship notebooks or serialized models.

## Anytime TDs

The live 2026 Week 1 board compares rushing and receiving TD chances against a
manually pasted US-book Yes price. The 2025 weeks 10-17 demo remains selectable
for historical context. Full manual-paste and cumulative-freeze contract:
[anytime_td/GUIDE.md](anytime_td/GUIDE.md).

## Reproducing the public state

The public repository can validate and display a candidate, but it cannot retrain the private 2026 spread producer. To inspect what is live:

```bash
python -m publishing.cli status
python -m publishing.cli validate --artifact path/to/candidate.csv --metadata path/to/candidate.metadata.json
```

Use the immutable build ID and SHA-256 value in the manifest when comparing a site result with an exported candidate.
