"""How to make the buy/fade calls better (keeping BOTH). Two levers, on 11 seasons:

  1. CONFIDENCE TIERS  -- does a bigger disagreement with ADP hit at a higher rate?
                          (would give HIGH/MEDIUM buy & fade tiers like the betting model)
  2. SLEEPER CONSENSUS -- when our model AND Sleeper both disagree with ADP the same way,
                          is the call much stronger? (the betting model's voter-agreement
                          idea: two independent signals both off the market = high confidence)

Fades are gated to the "good fade" subset found in fade_deep_dive (decline catalyst, not young).
Consensus tests are limited to 2018+ (Sleeper projection exists then).
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fade_deep_dive as fdd


def hit(g):
    return (np.sign(g["our_dev"]) == np.sign(g["actual_dev"])).mean()


def line(label, g):
    return f"  {label:34s} {hit(g)*100:3.0f}%  (n={len(g)})" if len(g) >= 8 else f"  {label:34s}   - (n={len(g)})"


def main():
    a = fdd.build()
    g = a.groupby(["season", "position"])
    a["sleeper_rk"] = g["sleeper_pts_half_ppr"].transform(lambda s: s.rank(ascending=False, method="min"))
    a["sleeper_dev"] = a["adp_rk"] - a["sleeper_rk"]

    pos, age = a["position"], a["age"].fillna(26)
    a["age_cliff"] = (((pos == "RB") & (age >= 27)) | (pos.isin(["WR", "TE"]) & (age >= 29)) | ((pos == "QB") & (age >= 34)))
    a["declining"] = a["ppg_trend"].fillna(0) < -1
    a["young"] = a["years_exp"] <= 2

    buys = a[a["our_dev"] >= 5].copy()
    gfades = a[(a["our_dev"] <= -5) & (a["age_cliff"] | a["declining"]) & (~a["young"])].copy()
    print(f"buys n={len(buys)} | gated fades n={len(gfades)}\n")

    print("=== LEVER 1: confidence by disagreement size ===")
    print(line("BUY  small gap (5-9)", buys[buys.our_dev < 10]))
    print(line("BUY  big gap (>=10)", buys[buys.our_dev >= 10]))
    print(line("FADE small gap (5-9)", gfades[gfades.our_dev > -10]))
    print(line("FADE big gap (>=10)", gfades[gfades.our_dev <= -10]))

    print("\n=== LEVER 2: Sleeper consensus (2018+; does Sleeper agree vs ADP?) ===")
    bs = buys[buys.sleeper_dev.notna()]
    fs = gfades[gfades.sleeper_dev.notna()]
    print(line("BUY  all (with Sleeper)", bs))
    print(line("BUY  + Sleeper also undervalues", bs[bs.sleeper_dev > 0]))
    print(line("BUY  but Sleeper disagrees", bs[bs.sleeper_dev <= 0]))
    print(line("FADE all (with Sleeper)", fs))
    print(line("FADE + Sleeper also overvalues", fs[fs.sleeper_dev < 0]))
    print(line("FADE but Sleeper disagrees", fs[fs.sleeper_dev >= 0]))

    print("\n=== combined HIGH-confidence tier (big gap AND Sleeper agrees) ===")
    print(line("BUY  HIGH", bs[(bs.our_dev >= 8) & (bs.sleeper_dev > 0)]))
    print(line("FADE HIGH", fs[(fs.our_dev <= -8) & (fs.sleeper_dev < 0)]))


if __name__ == "__main__":
    main()
