# Seasonal projections on this site

The Draft Board's current behavior is defined by the page code and the files
listed below. ADP overlays are refreshable inputs; their contents can change
independently of this guide.

This public folder is the Draft Board's operational surface: the frozen 2014-2026
season dataset the board keys on, the daily Sleeper, ESPN, and Yahoo ADP overlays, and the
refresh scripts. Training and serialized models are private.

## What the page shows

The Draft Board is a 180-player comparison table. For each player it places the
market price (Sleeper ADP by default, ESPN ADP or Yahoo ADP as an alternate) next to my season
projection and Sleeper's projection, plus positional ranks, rank gaps, and two
descriptive talent columns. It is not a buy/fade tool and it does not render a
calibrated floor/ceiling band.

The displayed Model Proj is a published CSV under `fantasy/projections/results/`.
I do not retrain it in this repository.

## How the market columns update

`refresh_board_adp.py`, `refresh_board_espn_adp.py`, and `refresh_board_yahoo_adp.py`
pull current ADP and rewrite only `board_adp_live_2026.csv`,
`board_espn_adp_live_2026.csv`, and `board_yahoo_adp_live_2026.csv`. They do not
touch the frozen season dataset or the projection CSVs. After the 2026 season
start date the scheduled refresh pauses unless forced.

Coverage floors are locked in the refresh modules. A pull that matches too few
board players is refused rather than publishing a stale overlay with today's date.

## Public files

| Path | Role |
|---|---|
| `season_dataset_2014_2026.csv` | Frozen board universe |
| `board_adp_live_2026.csv` | Live Sleeper ADP overlay |
| `board_espn_adp_live_2026.csv` | Live ESPN ADP overlay |
| `board_yahoo_adp_live_2026.csv` | Live Yahoo ADP overlay |
| `board_espn_ids_2026.csv` | ESPN player-id map |
| `board_yahoo_ids_2026.csv` | Yahoo player-id map |
| `fetch_adp.py`, `fetch_espn_adp.py`, `fetch_yahoo_adp.py` | Market pulls |
| `refresh_board_adp.py`, `refresh_board_espn_adp.py`, `refresh_board_yahoo_adp.py` | Overlay writers |
| `apply_board_labels.py` | Shared name normalization |
| `_utils.py` | Shared helpers |

## Fences

- Do not name the 75/25 Sleeper mix on the board or in Help.
- Talent scores are descriptive context, not a prediction.
- Yahoo unmatched rows stay blank. Never fill them from Sleeper or ESPN.
- Do not restore training scripts, notebooks, or `.pkl` files here.
