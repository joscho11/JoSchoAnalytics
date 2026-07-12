"""Apply licensed per-population labels to phase4_band_2026.csv (in-schema).

PRODUCT post-process — runs AFTER `phase4_band.py --artifact` (whose statistical
design is frozen; this script never touches bands/probabilities). It:
  1. bridges each band row to its season_dataset_2014_2026.csv 2026 row
     (norm_name + shared alias table + position);
  2. computes the POPULATION flag from the frozen prereg conventions
     (definitions are conventions — no outcome is touched; 2026 has none):
       stable_role   = is_rookie == 0 AND team == prior-season team (both
                       non-null) AND prior_games >= 14           (H6/H11)
       volatile_*    = everything else (H12's union), split RB/WR vs QB/TE
                       because the H12 license covers RB/WR only;
  3. writes the LICENSED signal_status wording per population (H11/H12
     OUTCOMES verbatim; QB/TE volatile stated plainly unvalidated);
  4. adds value_gap = adp_pos_rank - sleeper_pos_rank (both 2026 market
     inputs; descriptive column, no tiers, no bucketing).
Tiers remain unvalidated: no tier field or tier language exists anywhere.
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _utils import norm_name

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BAND = HERE / "phase4_band_2026.csv"
DATASET = HERE / "season_dataset_2014_2026.csv"

ALIAS = {"gabriel davis": "gabe davis", "robby anderson": "robbie chosen",
         "hollywood brown": "marquise brown", "kenny gainwell": "kenneth gainwell"}
nmz = lambda s: ALIAS.get(norm_name(s), norm_name(s))

POWERED = "powered by Sleeper's projections vs the draft market"
LABELS = {
    "stable_role": (
        "disagreement signal validated in aggregate and freshness-controlled "
        "(verified against a dated contemporaneous market — Underdog, best "
        "ball; format delta on the wording); threshold tiers unvalidated"),
    "volatile_rb_wr": (
        "disagreement signal validated in aggregate, freshness-controlled "
        "(dated best-ball market; format delta); threshold tiers unvalidated; "
        "aggregate validation only — no player-level or sub-group claim"),
    "volatile_qb_te": (
        "signal unvalidated for volatile QB/TE; threshold tiers unvalidated"),
}


def main():
    band = pd.read_csv(BAND)
    assert len(band) == 180
    ds = pd.read_csv(DATASET, usecols=["player", "player_id", "position", "team",
                                       "season", "is_rookie", "prior_games",
                                       "sleeper_pts_half_ppr"])
    d26 = ds[ds.season == 2026].copy()
    d26["nn"] = d26["player"].map(nmz)
    prior = ds[ds.season == 2025][["player_id", "team"]].rename(
        columns={"team": "prior_team"})
    d26 = d26.merge(prior, on="player_id", how="left")
    d26["stable"] = ((d26.is_rookie == 0) & d26.team.notna() & d26.prior_team.notna()
                     & (d26.team == d26.prior_team) & (d26.prior_games >= 14))
    key = d26.drop_duplicates(["nn", "position"])[
        ["nn", "position", "player_id", "team", "stable", "is_rookie",
         "sleeper_pts_half_ppr"]]

    band["nn"] = band["player"].map(nmz)
    m = band.merge(key, on=["nn", "position"], how="left")
    missing = m[m["player_id"].isna()]
    assert missing.empty, f"band rows without a 2026 dataset row: {missing.player.tolist()}"

    m["population"] = "volatile_qb_te"
    m.loc[m.stable.astype(bool), "population"] = "stable_role"
    m.loc[~m.stable.astype(bool) & m.position.isin(["RB", "WR"]),
          "population"] = "volatile_rb_wr"
    m["signal_status"] = m["population"].map(LABELS)
    m["powered_by"] = POWERED

    # descriptive disagreement gap (two 2026 market inputs; no outcomes exist)
    m["sleeper_pos_rank"] = m.groupby("position")["sleeper_pts_half_ppr"] \
                             .rank(ascending=False, method="first")
    m["value_gap"] = m["adp_pos_rank"] - m["sleeper_pos_rank"]

    out = m.drop(columns=["nn", "stable", "sleeper_pts_half_ppr", "sleeper_pos_rank"])
    out.to_csv(BAND, index=False)
    print(f"labeled {len(out)} rows; populations: "
          f"{out.population.value_counts().to_dict()}")
    print(f"value_gap present: {out.value_gap.notna().sum()}/180; "
          f"team present: {out.team.notna().sum()}/180")
    for pop, lab in LABELS.items():
        print(f"  {pop}: \"{lab[:70]}…\"")


if __name__ == "__main__":
    main()
