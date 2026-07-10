"""Step 1b data-only validation of season_dataset_2002_2025.csv.

Reports (NO model metrics, NO model-vs-ADP numbers — 2008-2015 stays unseen):
  1. Feature coverage by season: every feature whose null rate crosses 50%
     anywhere on the panel, with the season it comes online (era boundaries).
  2. Era drift in the target: games-weighted mean PPG by position and season
     band, so the A3 normalization question is sized with data.
  3. Row counts by position and season band.

Run:  python fantasy/seasonal_projections/validate_extended_dataset.py
"""
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
df = pd.read_csv(HERE / "season_dataset_2002_2025.csv")
real = df[df.reconstructed == 0]
FEATS = [c for c in df.columns if c.startswith(("prior_", "ppg_", "career_", "vacated_"))
         or c in ("age", "years_exp", "draft_round", "draft_pick", "coach_changed", "qb_changed")]

print(f"rows {len(df):,} | active {len(real):,} | seasons {df.season.min()}-{df.season.max()} "
      f"| Model-A usable {df.target_ppg.notna().sum():,}\n")

print("=== 1. era boundaries (features with >50% null anywhere) ===")
null_by_season = real.groupby("season")[FEATS].apply(lambda g: g.isna().mean())
for c in FEATS:
    s = null_by_season[c]
    if s.max() > 0.5:
        online = s[s < 0.5].index.min()
        print(f"  {c:26s} null {s.max():>4.0%} worst | <50% null from {online} "
              f"| 2020s null {s.loc[s.index >= 2020].mean():.0%}")

print("\n=== 2. era drift: games-weighted mean target PPG by position ===")
band = pd.cut(real.season, [2001, 2005, 2010, 2015, 2020, 2025],
              labels=["2002-05", "2006-10", "2011-15", "2016-20", "2021-25"])
t = real[real.target_ppg.notna()].copy()
t["band"] = band[t.index]
drift = t.groupby(["band", "position"], observed=True).apply(
    lambda g: (g.target_ppg * g.sample_weight).sum() / g.sample_weight.sum(), include_groups=False).unstack()
print(drift.round(2).to_string())

print("\n=== 3. active player-seasons by position x band ===")
r = real.copy(); r["band"] = band
print(r.pivot_table(index="band", columns="position", values="player_id",
                    aggfunc="count", observed=True).to_string())
