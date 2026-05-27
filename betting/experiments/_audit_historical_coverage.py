"""Audit historical coverage of every data source feeding PROD_FEATURES_35.

For each data source (PBP, schedules, NGS, AllPro CSV, injuries) we check:
  - What is the earliest year with actual data (not just metadata)?
  - For derived features (rolling, prev-year lookups), what training-year
    range is "fully populated" (no median-fill, no zero-fill)?

We don't assume — we hit nflreadpy live and verify.
"""
import sys
import json
import warnings
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import nflreadpy as nfl
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent

print("="*78)
print("  STAGE 1 — independent verification of each data source")
print("="*78)

# ── 1. Schedules: how far back? ──────────────────────────────────────────────
print("\n[1] Schedules (nfl.load_schedules)")
sched = nfl.load_schedules(list(range(1999, 2010))).to_pandas()
print(f"  Loaded 1999-2009: {len(sched):,} games")
print(f"  Has spread_line? {sched['spread_line'].notna().sum():,} of {len(sched):,} rows ({sched['spread_line'].notna().mean()*100:.1f}%)")
print(f"  Has home_coach? {sched['home_coach'].notna().sum():,} ({sched['home_coach'].notna().mean()*100:.1f}%)")
print(f"  Has home_qb_name? {sched['home_qb_name'].notna().sum():,} ({sched['home_qb_name'].notna().mean()*100:.1f}%)")
print(f"  Year-by-year spread_line coverage:")
for y in sorted(sched['season'].unique()):
    s = sched[sched['season']==y]
    pct = s['spread_line'].notna().mean()*100
    print(f"    {int(y)}: {pct:.1f}% non-null")

# ── 2. PBP: how far back is EPA reliable? ────────────────────────────────────
print("\n[2] PBP / EPA (nfl.load_pbp) — checking 2005-2009 sample")
for y in [2005, 2007, 2009, 2011]:
    pbp = nfl.load_pbp([y]).to_pandas()
    rp = pbp[pbp['play_type'].isin(['run','pass']) & pbp['posteam'].notna() & pbp['defteam'].notna()]
    epa_pct = rp['epa'].notna().mean() * 100
    yds_pct = rp['yards_gained'].notna().mean() * 100
    pass_w_passer = rp[(rp['play_type']=='pass') & rp['passer_player_name'].notna()]
    print(f"  {y}: {len(rp):,} run/pass plays | EPA non-null {epa_pct:.1f}% | yards non-null {yds_pct:.1f}% | "
          f"pass-with-passer-name {len(pass_w_passer):,}")

# ── 3. NGS: what is the actual lower bound? ──────────────────────────────────
print("\n[3] NGS passing (nfl.load_nextgen_stats)")
try:
    ngs = nfl.load_nextgen_stats(seasons=[2014, 2015, 2016, 2017], stat_type='passing').to_pandas()
    print(f"  Got {len(ngs):,} rows for 2014-2017")
    for y in sorted(ngs['season'].unique()):
        n = (ngs['season']==y).sum()
        att_sum = ngs[(ngs['season']==y) & (ngs['week']==0)]['attempts'].sum()
        cpae_present = ngs[(ngs['season']==y) & (ngs['week']==0)]['completion_percentage_above_expectation'].notna().sum()
        print(f"    {int(y)}: {n:,} rows | season-agg attempts sum {att_sum:,.0f} | CPAE present {cpae_present:,}")
except Exception as e:
    print(f"  ERROR: {e}")

# ── 4. AllPro CSV: how far back? ─────────────────────────────────────────────
print("\n[4] AllPro CSV (nfl_allpro_1997_2025.csv)")
allpro_path = ROOT / 'betting/nfl_allpro_1997_2025.csv'
ap = pd.read_csv(allpro_path)
print(f"  {len(ap):,} rows | years {ap['Year'].min()}-{ap['Year'].max()}")
print(f"  Year-by-year row counts (sample):")
for y in [1997, 2000, 2003, 2005, 2008, 2010, 2014, 2020, 2024]:
    n = (ap['Year']==y).sum()
    print(f"    {y}: {n} entries")

# ── 5. Injuries: how far back? ───────────────────────────────────────────────
print("\n[5] Injuries (nfl.load_injuries) — testing year-by-year from 2005")
for y in [2005, 2007, 2008, 2009, 2010, 2012, 2014]:
    try:
        inj = nfl.load_injuries(seasons=[y]).to_pandas()
        print(f"  {y}: {len(inj):,} rows | seasons present: {sorted(inj['season'].unique()) if len(inj)>0 else 'none'}")
    except Exception as e:
        print(f"  {y}: ERROR — {type(e).__name__}: {str(e)[:100]}")

print("\n" + "="*78)
print("  STAGE 1 COMPLETE — see output above for what's actually available")
print("="*78)
