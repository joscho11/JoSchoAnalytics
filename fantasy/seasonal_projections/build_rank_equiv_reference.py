"""Build rank_equiv_reference.csv — display-only units table for the 2026 board.

Construction (a units table, NOT a signal — no model, no ADP, no disagreement
statistic; it touches completed-season outcomes only as a points-to-rank
dictionary, and touches no 2026 outcomes, which do not exist):

  1. From season_dataset_2014_2026.csv take seasons 2021-2025.
  2. Actual season half-PPR points = target_ppg * target_games (rows with a
     non-null target_ppg, i.e. players with >= 3 games played).
  3. Within each (season, position), rank players by actual points descending
     (rank 1 = the position's best finish that season).
  4. mean_pts per (position, finish_rank) = the mean of that rank's points
     across the five seasons; only ranks present in ALL five seasons are kept.

The board converts a points value to "≈ POS-N in a typical season" by nearest
mean_pts within the row's position. Q1 scope fence: this is a function of
(position, actuals) only.

Run:  python fantasy/seasonal_projections/build_rank_equiv_reference.py
"""
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATASET = HERE / "season_dataset_2014_2026.csv"
OUT = HERE / "rank_equiv_reference.csv"

SEASONS = list(range(2021, 2026))


def main():
    ds = pd.read_csv(DATASET, usecols=["season", "position", "target_ppg",
                                       "target_games"])
    ds = ds[ds.season.isin(SEASONS) & ds.target_ppg.notna()].copy()
    ds["actual_pts"] = ds.target_ppg * ds.target_games
    ds["finish_rank"] = ds.groupby(["season", "position"])["actual_pts"] \
                          .rank(ascending=False, method="first").astype(int)

    ref = (ds.groupby(["position", "finish_rank"])["actual_pts"]
             .agg(mean_pts="mean", n_seasons="size").reset_index())
    ref = ref[ref.n_seasons == len(SEASONS)].drop(columns="n_seasons")
    ref["mean_pts"] = ref["mean_pts"].round(1)
    ref.to_csv(OUT, index=False)

    print(f"wrote {OUT.name}: {len(ref)} rows")
    for pos in ["QB", "RB", "WR", "TE"]:
        sub = ref[ref.position == pos]
        anchors = sub[sub.finish_rank.isin([1, 12, 24, 36])]
        print(f"  {pos}: ranks 1-{sub.finish_rank.max()}; "
              + "; ".join(f"{pos}{int(r.finish_rank)}={r.mean_pts}"
                          for r in anchors.itertuples()))


if __name__ == "__main__":
    main()
