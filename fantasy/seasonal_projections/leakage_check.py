"""Is Sleeper's projection (pts_half_ppr) a clean PRESEASON projection, or contaminated
by in-season info? The /projections/regular/{season} endpoint for a completed season could
return an updated/end-of-season projection -> leakage that would explain the 84-90% buy rate.

Smoking-gun test: Sleeper also publishes projected games (sleeper_gp). A genuine preseason
projection CANNOT know who gets hurt, so it should project ~16-17 games for nearly everyone.
If sleeper_gp tracks ACTUAL games (low for injury busts), the projection is in-season-aware.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
SLP = pd.read_csv(HERE / "sleeper_adp_2020_2026.csv")
DS = pd.read_csv(HERE / "season_dataset_2014_2025.csv")


def main():
    a = DS[DS.target_ppg.notna()][["season", "norm_name", "position", "target_ppg", "target_games"]]
    s = SLP[["season", "norm_name", "position", "sleeper_gp", "sleeper_pts_half_ppr", "adp_half_ppr"]]
    m = a.merge(s, on=["season", "norm_name", "position"], how="inner")
    m = m[m.season.between(2020, 2024)].copy()        # completed seasons with Sleeper data
    m["actual_total"] = m["target_ppg"] * m["target_games"]
    print(f"matched player-seasons (2020-2024): {len(m)}\n")

    print("=== sleeper_gp (Sleeper's PROJECTED games) ===")
    print(f"  distribution: min {m.sleeper_gp.min():.0f}  median {m.sleeper_gp.median():.0f}  "
          f"max {m.sleeper_gp.max():.0f}  | distinct values: {m.sleeper_gp.nunique()}")
    print(f"  corr(sleeper_gp, ACTUAL games): {m['sleeper_gp'].corr(m['target_games']):+.3f}")
    print(f"  MAE(sleeper_gp vs actual games): {(m['sleeper_gp']-m['target_games']).abs().mean():.2f}")

    print("\n=== THE TELL: what did Sleeper project for players who got HURT? ===")
    hurt = m[m.target_games <= 5].sort_values("target_games")
    print(f"  players who played <=5 games (n={len(hurt)}):")
    print(f"    mean sleeper_gp = {hurt.sleeper_gp.mean():.1f}   (clean preseason should be ~15-17)")
    print(f"    mean actual games = {hurt.target_games.mean():.1f}")
    print("  sample (a clean projection would show ~16 gp regardless of the injury):")
    print(f"    {'player(norm)':22s} {'season':>6} {'actual_g':>8} {'sleeper_gp':>10} {'sleeper_pts':>11} {'actual_pts':>10}")
    for _, r in hurt.head(12).iterrows():
        print(f"    {r['norm_name'][:22]:22s} {int(r['season']):>6} {int(r['target_games']):>8} "
              f"{r['sleeper_gp']:>10.1f} {r['sleeper_pts_half_ppr']:>11.1f} {r['actual_total']:>10.1f}")

    print("\n=== Sleeper POINTS projection vs actual ===")
    print(f"  corr(sleeper_pts, actual_total): {m['sleeper_pts_half_ppr'].corr(m['actual_total']):+.3f}")
    print(f"  MAE(sleeper_pts vs actual_total): {(m['sleeper_pts_half_ppr']-m['actual_total']).abs().mean():.1f}")
    # if Sleeper points strongly anticipates actual games (injuries), that's the leak signature
    print(f"  corr(sleeper_pts, actual GAMES): {m['sleeper_pts_half_ppr'].corr(m['target_games']):+.3f}")
    print(f"  corr(ADP-implied [-adp], actual GAMES): {(-m['adp_half_ppr']).corr(m['target_games']):+.3f}")


if __name__ == "__main__":
    main()
