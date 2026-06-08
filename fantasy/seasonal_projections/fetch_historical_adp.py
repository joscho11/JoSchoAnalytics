"""Historical ADP from FantasyFootballCalculator (key-less) to fill 2014-2019.

Sleeper ADP only exists 2020+, which caps the value model at ~6 seasons (~700 rows)
and leaves it noise-limited. FFC publishes free historical ADP that lets us extend the
ADP benchmark back to 2014, ~2.5x the training data. We use:
  - FFC half-PPR for 2018-2019 (real half-PPR ADP exists)
  - FFC PPR for 2014-2017 (half-PPR not published that far back; PPR ranks are nearly
    identical to half-PPR, which sits between standard and PPR) -- documented proxy.
2020+ continues to use the Sleeper half-PPR ADP already in season_dataset.

Output: ffc_adp_2014_2019.csv  (season, norm_name, position, ffc_adp, ffc_overall_rank, ffc_pos_rank)
Run:  python fetch_historical_adp.py
"""
import sys
import json
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _utils import norm_name, SKILL_POSITIONS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
OUT = HERE / "ffc_adp_2014_2019.csv"
YEARS = range(2014, 2020)
SKILL = set(SKILL_POSITIONS)


def _fmt_for(year):
    return "half-ppr" if year >= 2018 else "ppr"   # half-ppr only published 2018+


def fetch_year(year, teams=12):
    fmt = _fmt_for(year)
    url = f"https://fantasyfootballcalculator.com/api/v1/adp/{fmt}?teams={teams}&year={year}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=30).read())
    rows = []
    for p in data.get("players", []):
        pos = p.get("position")
        if pos not in SKILL:
            continue
        rows.append({"season": year, "player": p.get("name"), "position": pos,
                     "team": p.get("team"), "ffc_adp": p.get("adp"), "fmt": fmt})
    df = pd.DataFrame(rows)
    df = df[df["ffc_adp"].notna()].sort_values("ffc_adp").reset_index(drop=True)
    df["norm_name"] = df["player"].map(norm_name)
    df["ffc_overall_rank"] = df["ffc_adp"].rank(method="min").astype(int)
    df["ffc_pos_rank"] = df.groupby("position")["ffc_adp"].rank(method="min").astype(int)
    return df


def main():
    frames = []
    for y in YEARS:
        d = fetch_year(y)
        print(f"  {y} ({_fmt_for(y):8s}): {len(d):3d} skill players  top: {d['player'].iat[0]} ({d['position'].iat[0]})")
        frames.append(d)
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT, index=False)
    print(f"\nwrote {OUT.name}  ({len(out):,} rows, {out['season'].nunique()} seasons)")
    return out


if __name__ == "__main__":
    main()
