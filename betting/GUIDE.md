# Betting models

Status: checked against the current code and release contract on 2026-09-15.

The betting area contains the 2026 spread product, a frozen 2025 demo, and an experimental totals model. These systems do not share the same claim or lifecycle.

## Current 2026 spread product

The live spread producer is `spread_v3_prod`, a separate private repository. It writes candidate predictions and a SHA-256 sidecar. This public repository validates those candidates, stores immutable builds, and activates them through the [publishing contract](../publishing/README.md).

The 2026 display logic lives in `live_2026.py`:

- The model predicts home margin from information available by Tuesday at 9:00 a.m. ET.
- The promoted QB-retaining Sunday-to-Tuesday Ridge with injured-reserve starters marks `HIGH` at an absolute 3.0-point edge from the Tuesday US median, then grades those tickets at the best US Tuesday number.
- Starting in 2026, the Tuesday US median drives the model, pick, edge, and `HIGH` flag. The best captured US quote for the recommended side is displayed separately and drives grading.
- A later market move alone can remove a `HIGH` label, but cannot add one. A separately validated model-version correction can change edges and `HIGH` labels while retaining the frozen Tuesday line.
- The final regular-season week is excluded from `HIGH` labels.
- There is no `MEDIUM` tier and no all-bets performance claim.
- Every game remains visible, including `PASS` games.

The promoted model's 2021-2025 chronological walk-forward evaluation produced 446 `HIGH` labels: 251 wins, 186 losses, and 9 pushes. Excluding pushes, that is 251/437 = 57.44% ATS, with a one-sided 95% Wilson lower bound of 53.51%, graded at each pick's best captured US Tuesday quote. The model it replaced scored 261/449 (58.13%); the difference is not statistically established either way. The new model trains its quarterback inputs on the passer who actually took the first dropback of each game, using only stats known before that game, and it drops the earlier uncertain-QB flag. A three-way test showed the versions tie within noise (253/434, 254/434, 251/437), so the choice rests on training the model on what it is fed live. The model has 44 core features and 47 fitted inputs: five general injury features and vacated snaps were removed; three QB features remain; Sunday-to-Tuesday spread/total movement and Tuesday moneyline-spread gap are included with three train-fold-fitted missingness flags. The `ir_starters_diff` input is the home-minus-away count of non-QB starters on regular injured reserve (designated-to-return players are not counted). It reads each team's roster from its previous game, the latest roster before the Tuesday prediction, and counts a player as a starter if he played at least 50% of offensive or defensive snaps for that team in any of his last three games (or averaged 50% for that team last season if he has not played for it this season). The special-teams EPA feature uses the net two-sided definition (each team's own special-teams EPA minus the opponent's, in the same game; the one-sided defect is D76 in the workspace data-defects log).

When a team's starting QB is unsettled, I list each possible QB with a probability. The model scores the game once per QB, and the official pick is the probability-weighted average of those scores. It is `HIGH` only if the averaged gap is at least 3.0 points and every QB with at least a 25% chance points the same way as the average. The 2026 board shows the official blended pick and hides individual QB projection paths. Those blended games are not part of the historical benchmark. This is historical research, not a guarantee of future results. Each weekly release records the model version that produced it.

## What appears on the site

The current weekly page reads only active release artifacts. It shows the model margin, the line used for the Tuesday decision, the current line when available, the model side, confidence, and result after grading.

The frozen 2025 demo remains available for reproducibility. It used a three-voter consensus with `HIGH`, `MEDIUM`, and `PASS` labels. Those rules do not describe the 2026 product.

## Results and claim boundaries

| System | Evaluation | Result | Current interpretation |
|---|---:|---:|---|
| Promoted actual-starter QB market Ridge with team-scoped injured-reserve starters and net two-sided special-teams EPA | 2021-2025 chronological walk-forward | 251/437, 57.44% ATS; 9 pushes among 446 HIGH labels | Wilson lower 53.51%; Tuesday-median selection, best US Tuesday quote grading |
| Archived in-repo spread model | Corrected 2018-2025 audit | 129/238, 54.20% ATS | No demonstrated edge; 95% Wilson lower bound is 47.86% |
| Totals model | Walk-forward cross-validation | 55.7% UNDER accuracy, n=575 | Research result, not a deployed performance claim |
| Totals model | 2025 live tracking, Weeks 10-17 | 52.2%, n=46 | Too small and too close to chance for an edge claim |

Earlier spread evaluations are historical records only. The pregame-leakage result of 64.2% was retracted; the corrected archived result was 129/238. The 192/336 figure was withdrawn because its same-week injury join postdated Tuesday. The former 253/436 benchmark is superseded for current-model claims; its archived audit remains available for provenance. The QB-retaining model without the injured-reserve input (223/390, Wilson lower 53.02%) is also superseded; `market_model_benchmark_v2.json` keeps it as history. The bundle before the price-median units fix (256/432, 59.26%) is in `market_model_benchmark_v4.json`, the units-fix bundle (246/430, 57.21%) is in `market_model_benchmark_v5.json`, and the uncertain-QB-flag bundle (261/449, 58.13%) is in `market_model_benchmark_v6.json`; all are history. The current public benchmark is generated from `market_model_benchmark_v7.json`.

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

The latest live 2026 board compares rushing and receiving TD chances against a
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
