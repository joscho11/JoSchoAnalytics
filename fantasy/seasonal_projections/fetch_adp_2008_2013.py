"""FFC historical ADP 2008-2013, extending the benchmark for the Step 1b panel.

Format per season follows PREREGISTRATION.md Amendment 1 / A2 (deepest of
half-PPR > PPR > standard, probed 2026-07-09): PPR for 2010, 2011, 2013;
standard for 2008, 2009, 2012 (PPR too thin those years). Standard-scoring
seasons are excluded from the pre-registered TE gate; they are benchmark
context only.

Output: ffc_adp_2008_2013.csv (same schema as ffc_adp_2014_2019.csv)
Run:  python fetch_adp_2008_2013.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_historical_adp import fetch_year, _fmt_for          # reuse the fetcher
import fetch_historical_adp as fha

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
OUT  = HERE / "ffc_adp_2008_2013.csv"
FMT  = {2008: "standard", 2009: "standard", 2010: "ppr",
        2011: "ppr", 2012: "standard", 2013: "ppr"}


def main():
    frames = []
    for year, fmt in FMT.items():
        fha._fmt_for = lambda y, _f=fmt: _f          # pin the pre-registered format
        d = fetch_year(year)
        d["fmt"] = fmt
        print(f"  {year} ({fmt:8s}): {len(d):3d} skill players  top: {d['player'].iat[0]}")
        frames.append(d)
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT, index=False)
    print(f"\nwrote {OUT.name}  ({len(out):,} rows, {out['season'].nunique()} seasons)")


if __name__ == "__main__":
    main()
