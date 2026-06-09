"""Deep dive to inform the seasonal revamp: where exactly is the ADP-mispricing edge,
and where does it break? Pooled 2021-2025 (single seasons are too noisy), healthy players.

Questions:
  1. Is the BUY side systematically better than the FADE side (the 2025 WR asymmetry)?
  2. WHAT do we fade wrongly -- are the wrong fades young/ascending players?
  3. Does a simple guard (don't fade young ascending players) fix the fade side
     without hurting the buy side?
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import surprise_eval as se

BOLD = 5


def hit(g):
    return (np.sign(g["our_dev"]) == np.sign(g["actual_dev"])).mean()


def main():
    a = se.build()
    a = a[a["target_games"] >= se.MIN_GAMES_PLAYED].copy()
    bold = a[a["our_dev"].abs() >= BOLD].copy()
    buys = bold[bold["our_dev"] > 0]
    fades = bold[bold["our_dev"] < 0]

    print(f"pooled 2021-2025 healthy bold calls: {len(bold)}  (buys {len(buys)}, fades {len(fades)})\n")
    print("=== 1. BUY vs FADE hit rate ===")
    print(f"  BUY  (undervalued): {hit(buys)*100:.0f}%  (n={len(buys)})")
    print(f"  FADE (overvalued):  {hit(fades)*100:.0f}%  (n={len(fades)})")
    print("  per position:")
    print(f"  {'pos':4} {'buy%':>6} {'n':>4}   {'fade%':>6} {'n':>4}")
    for pos in ["QB", "RB", "WR", "TE"]:
        b = buys[buys.position == pos]; f = fades[fades.position == pos]
        bp = f"{hit(b)*100:5.0f}%" if len(b) else "   - "
        fp = f"{hit(f)*100:5.0f}%" if len(f) else "   - "
        print(f"  {pos:4} {bp:>6} {len(b):>4}   {fp:>6} {len(f):>4}")

    print("\n=== 2. What do we fade WRONGLY? (fade = we said lower than ADP; wrong = they beat ADP) ===")
    fades = fades.copy()
    fades["wrong"] = np.sign(fades["our_dev"]) != np.sign(fades["actual_dev"])
    fades["young"] = fades["years_exp"] <= 2
    fades["ascending"] = (fades["years_exp"] <= 3) & (fades["ppg_trend"].fillna(0) > 0)
    for label, col in [("young (years_exp<=2)", "young"), ("ascending (yr<=3 & rising)", "ascending")]:
        sub = fades[fades[col]]; oth = fades[~fades[col]]
        print(f"  {label:28s}: fade hit {hit(sub)*100:4.0f}% (n={len(sub)})   "
              f"| everyone else: {hit(oth)*100:4.0f}% (n={len(oth)})")
    print(f"  mean age of RIGHT fades: {fades[~fades.wrong]['age'].mean():.1f}  "
          f"| WRONG fades: {fades[fades.wrong]['age'].mean():.1f}")
    print(f"  mean years_exp RIGHT fades: {fades[~fades.wrong]['years_exp'].mean():.1f}  "
          f"| WRONG fades: {fades[fades.wrong]['years_exp'].mean():.1f}")

    print("\n=== 3. GUARD: suppress fades on young ascending players ===")
    guard = (fades["years_exp"] <= 3) & (fades["ppg_trend"].fillna(0) > 0)
    kept_fades = fades[~guard]
    print(f"  fades after guard: {len(kept_fades)} (dropped {guard.sum()} young-ascending fades)")
    print(f"  fade hit rate:  before {hit(fades)*100:.0f}%  ->  after guard {hit(kept_fades)*100:.0f}%")
    overall_before = hit(bold)
    overall_after = hit(pd.concat([buys, kept_fades]))
    print(f"  overall bold-call hit: before {overall_before*100:.0f}%  ->  after guard {overall_after*100:.0f}%")


if __name__ == "__main__":
    main()
