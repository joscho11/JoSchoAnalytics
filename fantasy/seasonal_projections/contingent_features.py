"""Contingent-opportunity features (Version A) — injury-RISK-weighted opportunity held
by the teammates AHEAD of you in the pecking order.

The idea (user, 2026-06-08): if CeeDee Lamb gets hurt, George Pickens' target opportunity
spikes. We can't use that for a DRAFT-TIME seasonal projection (who gets hurt in Week 8 is
unknowable in August -> using it would be leakage). But at draft time we DO know two
leak-safe things: (a) how concentrated the target/carry tree is, and (b) how fragile the
players ahead of you are (prior games missed + age). So:

  contingent_tgt_opp(P) = sum over teammates Q with a HIGHER prior target share of
                          ( Q's prior target share  x  Q's fragility )
  contingent_rush_opp(P) = same, using prior carry share (for RBs)

"fragility" is a heuristic injury-risk score from prior-season games missed + an age bump,
floored so even a healthy teammate's share is partly "at risk." Everything is prior-season
(N-1) usage/durability + age, all known by an August draft. NO in-season injury events.

This is the durability-weighted complement to `ret_tgt_competition` (raw crowding) and
`vacated_target_share` (players who actually left). Import add_contingent_opportunity(df).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

CONTINGENT_COLS = ["contingent_tgt_opp", "contingent_rush_opp"]


def _fragility(df):
    """Leak-safe injury-risk score in ~[0.05, 0.85] from prior games missed + age."""
    gm_rate = (df["prior_games_missed"].fillna(0).clip(0, 17) / 17.0)
    age = df["age"].fillna(26.0)
    pos = df["position"]
    age_risk = np.where((pos == "RB") & (age >= 28), 0.15,
                np.where(pos.isin(["WR", "TE"]) & (age >= 30), 0.10,
                np.where((pos == "QB") & (age >= 36), 0.10, 0.0)))
    return np.clip(0.12 + 0.60 * gm_rate.values + age_risk, 0.05, 0.85)


def _contingent(share, frag, eps=0.01):
    """For each player i: the fragility-weighted opportunity of higher-usage teammates,
    REDISTRIBUTED to i in proportion to i's own existing share (so a player with no role
    absorbs ~nothing; the realistic next-man-up absorbs the most).

      contingent[i] = share[i] * sum_{j: share[j] > share[i]} share[j]*frag[j] / (S - share[j])
    """
    S = share.sum()
    if S <= 0:
        return np.zeros_like(share)
    term = share * frag / (S - share + eps)         # per source j
    higher = share[None, :] > share[:, None]        # [i,j] = j ahead of i
    return share * (higher * term[None, :]).sum(axis=1)


def add_contingent_opportunity(df):
    d = df.reset_index(drop=True).copy()
    frag = _fragility(d)
    tshare = d["prior_target_share"].fillna(0).values
    # rush share = player's prior carries-per-game normalized within team-season
    car = d["prior_carries_pg"].fillna(0)
    team_car = d.groupby(["team", "season"])["prior_carries_pg"].transform(
        lambda s: s.fillna(0).sum()).replace(0, np.nan)
    rshare = (car / team_car).fillna(0).values

    ct = np.zeros(len(d))
    cr = np.zeros(len(d))
    for _, idx in d.groupby(["team", "season"]).indices.items():
        ct[idx] = _contingent(tshare[idx], frag[idx])
        cr[idx] = _contingent(rshare[idx], frag[idx])

    d["contingent_tgt_opp"] = ct
    d["contingent_rush_opp"] = cr
    return d


def main():
    import glob
    HERE = Path(__file__).resolve().parent
    ds = sorted(glob.glob(str(HERE / "season_dataset_2014_*.csv")))
    f = next((p for p in ds if p.endswith("2014_2025.csv")), ds[-1])
    out = add_contingent_opportunity(pd.read_csv(f))
    print(out[["player", "season", "position", "team"] + CONTINGENT_COLS].describe(include="all").loc[["mean", "max"]].to_string())
    # sanity: biggest contingent target opportunities (WR/TE behind a big, fragile teammate)
    pc = out[(out["season"] == 2025) & out["position"].isin(["WR", "TE"])]
    print("\n2025 biggest contingent_tgt_opp (most to gain if the guys ahead get hurt):")
    cols = ["player", "position", "team", "contingent_tgt_opp", "prior_target_share"]
    print(pc.sort_values("contingent_tgt_opp", ascending=False).head(10)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
