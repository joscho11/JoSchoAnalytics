"""Reproducible artifact for the 'Opp touchdown' drive-classification defect.

DEFECT. Drive outcomes were classified with `str.contains("Touchdown", case=False)`, which also
matches the category **'Opp touchdown'** — a defensive or return score BY THE OPPONENT. The offense
was credited +7 for being scored on, and the same flag fed red-zone TD rate.

FIX. An exact category mapping (build_segment_offense.DRIVE_POINTS). 'Touchdown' is the ONLY
category counting as an offensive touchdown. Any unmapped category raises rather than being
silently classified.

This script regenerates the impact numbers quoted in prereg v3.3 §4 from raw play-by-play, so the
claim is checkable rather than remembered. Writes data/drive_impact_report.csv.

Run:  python report_drive_impact.py
"""
import pathlib

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"
SEASONS = [2014, 2018, 2022, 2025]          # the seasons the v3.3 measurement used

BUGGY_TD = lambda s: s.str.contains("Touchdown", case=False, na=False)   # noqa: E731
EXACT_TD = lambda s: s.eq("Touchdown")                                    # noqa: E731

POINTS = {"Touchdown": 7.0, "Field goal": 3.0, "Safety": -2.0, "Opp touchdown": 0.0}


def _pts(cat, td_mask_fn):
    """Points credited to the offense under a given TD rule."""
    base = cat.map({"Field goal": 3.0, "Safety": -2.0}).fillna(0.0)
    return np.where(td_mask_fn(cat), 7.0, base)


def build():
    import nflreadpy as nfl

    pbp = nfl.load_pbp(SEASONS).to_pandas()
    # `fixed_drive_result` is the companion of `fixed_drive`, NOT of `drive`. Pairing it with
    # `drive` undercounts ('Opp touchdown' 320 instead of 611) because the two drive numberings
    # disagree. REG-only, because the experiment is defined on regular-season play.
    pbp = pbp[pbp.season_type == "REG"]
    d = pbp[["season", "posteam", "game_id", "fixed_drive", "fixed_drive_result",
             "yardline_100"]].copy()
    d = d[d.posteam.notna() & d.fixed_drive_result.notna()]

    # one row per drive
    drv = (d.sort_values(["game_id", "fixed_drive"])
             .groupby(["season", "posteam", "game_id", "fixed_drive"], as_index=False)
             .agg(cat=("fixed_drive_result", "first"),
                  reached_rz=("yardline_100", lambda s: bool((s <= 20).any()))))

    counts = drv.cat.value_counts().rename_axis("drive_category").reset_index(name="n_drives")
    print("=== ENUMERATED DRIVE CATEGORIES ===")
    print(counts.to_string(index=False))
    opp_td = int(counts.loc[counts.drive_category == "Opp touchdown", "n_drives"].sum())
    print(f"\n'Opp touchdown' drives (each previously credited +7 to the OFFENSE): {opp_td}")

    drv["pts_buggy"] = _pts(drv.cat, BUGGY_TD)
    drv["pts_fixed"] = _pts(drv.cat, EXACT_TD)
    drv["td_buggy"] = BUGGY_TD(drv.cat).astype(int)
    drv["td_fixed"] = EXACT_TD(drv.cat).astype(int)
    # Red-zone TD RATE must restrict the NUMERATOR to drives that actually reached the red zone;
    # dividing all TD drives by red-zone trips lets an 'Opp touchdown' drive that never reached the
    # red zone inflate the numerator without touching the denominator.
    drv["rztd_buggy_n"] = (drv.td_buggy & drv.reached_rz.astype(int)).astype(int)
    drv["rztd_fixed_n"] = (drv.td_fixed & drv.reached_rz.astype(int)).astype(int)

    ts = (drv.groupby(["season", "posteam"])
            .agg(drives=("cat", "size"),
                 ppd_buggy=("pts_buggy", "mean"), ppd_fixed=("pts_fixed", "mean"),
                 rz=("reached_rz", "sum"),
                 rztd_buggy=("rztd_buggy_n", "sum"), rztd_fixed=("rztd_fixed_n", "sum"))
            .reset_index())
    ts["ppd_delta"] = ts.ppd_fixed - ts.ppd_buggy
    ts["rz_rate_buggy"] = ts.rztd_buggy / ts.rz
    ts["rz_rate_fixed"] = ts.rztd_fixed / ts.rz
    ts["rz_delta"] = ts.rz_rate_fixed - ts.rz_rate_buggy

    ts["rank_buggy"] = ts.groupby("season").ppd_buggy.rank(ascending=False, method="min")
    ts["rank_fixed"] = ts.groupby("season").ppd_fixed.rank(ascending=False, method="min")
    ts["rank_moved"] = (ts.rank_fixed - ts.rank_buggy).abs()

    print("\n=== TEAM-SEASON IMPACT ===")
    print(f"team-seasons examined           : {len(ts)}")
    print(f"team-seasons AFFECTED           : {int((ts.ppd_delta.abs() > 1e-12).sum())}")
    print(f"points/drive  mean change       : {ts.ppd_delta.mean():+.3f}")
    print(f"points/drive  max |change|      : {ts.ppd_delta.abs().max():.3f}")
    print(f"red-zone TD rate mean change    : {ts.rz_delta.mean():+.3f}")
    print(f"red-zone TD rate max |change|   : {ts.rz_delta.abs().max():.3f}")

    print("\n=== RANK CHURN BY SEASON (points/drive) ===")
    churn = (ts.groupby("season")
               .agg(teams=("posteam", "size"),
                    teams_changing_rank=("rank_moved", lambda s: int((s > 0).sum())),
                    max_places_moved=("rank_moved", "max"))
               .reset_index())
    print(churn.to_string(index=False))

    ts.to_csv(DATA / "drive_impact_report.csv", index=False)
    counts.to_csv(DATA / "drive_category_counts.csv", index=False)
    print(f"\nwrote {DATA/'drive_impact_report.csv'} and {DATA/'drive_category_counts.csv'}")
    return ts, counts


if __name__ == "__main__":
    build()
