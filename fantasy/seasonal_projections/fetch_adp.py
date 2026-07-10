"""Cache Sleeper preseason ADP + Sleeper's own season projections.

Source: the undocumented (but stable) Sleeper projections endpoint
    GET https://api.sleeper.app/v1/projections/nfl/regular/{season}
Each player record carries draft-position fields (adp_half_ppr, adp_ppr,
adp_std, adp_2qb) and Sleeper's own full-season point/stat projections
(pts_half_ppr, rush_yd, rec_yd, ...).

ADP is a LIVE rolling aggregate of real Sleeper drafts. For a completed
season it is frozen at its final draft-season state, i.e. the late-August
"draft-time market" consensus. There is no timestamp in the data.

Coverage notes (verified empirically):
  - Sleeper uses 999.0 as a sentinel for "no ADP / undrafted". We drop those.
  - 2019 is 100% sentinel (no real ADP), so the usable floor is 2020.
  - Real-ADP (draftable) counts grow over time as Sleeper retained more
    draft data: ~355 in 2020 up to ~1,840 in 2025.

We store ADP purely as a benchmark for our own seasonal projection model
(does the model under/over-value a player vs the market). ADP is never a
model feature. Sleeper's pts_half_ppr is stored as a second benchmark.

Join key for downstream use: normalized name + position + season. Sleeper's
gsis_id field is too sparsely populated to join on (even stars lack it), so
we follow the same name-normalization convention used elsewhere in the repo.

Output: fantasy/seasonal_projections/sleeper_adp_2020_2026.csv
Run:    python fantasy/seasonal_projections/fetch_adp.py
"""
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))   # so _utils imports regardless of CWD
from _utils import norm_name, ADP_SENTINEL, SKILL_POSITIONS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE        = Path(__file__).resolve().parent
OUT_CSV     = HERE / "sleeper_adp_2020_2026.csv"
# 2019 is all-sentinel; 2020-2025 are completed (ADP frozen at their draft-time state);
# 2026 is the live upcoming season -- its ADP already exists (early best-ball drafts) and
# keeps growing toward the late-August consensus. Refresh this cache to pull current 2026 ADP.
SEASONS     = list(range(2020, 2027))
HEADERS     = {"User-Agent": "Mozilla/5.0 (BettingEdge seasonal_projections cache)"}
BASE        = "https://api.sleeper.app/v1"
SKILL       = set(SKILL_POSITIONS)

# Fields we keep from each projection record. ADP first (the benchmark),
# then Sleeper's own season projections (a second benchmark for our model).
ADP_FIELDS  = ["adp_half_ppr", "adp_ppr", "adp_std", "adp_2qb"]
PROJ_FIELDS = ["pts_half_ppr", "pts_ppr", "pts_std",
               "rush_yd", "rush_td", "rec", "rec_yd", "rec_td",
               "pass_yd", "pass_td", "gp"]


def load_players() -> dict:
    print("Loading player metadata (/players/nfl) ...")
    r = requests.get(f"{BASE}/players/nfl", headers=HEADERS, timeout=60)
    r.raise_for_status()
    players = r.json()
    print(f"  {len(players):,} players in metadata")
    return players


def fetch_season(season: int, players: dict) -> pd.DataFrame:
    r = requests.get(f"{BASE}/projections/nfl/regular/{season}", headers=HEADERS, timeout=60)
    r.raise_for_status()
    data = r.json()

    rows = []
    for pid, rec in data.items():
        if not isinstance(rec, dict):
            continue
        adp = rec.get("adp_half_ppr")
        if adp is None or adp >= ADP_SENTINEL:     # drop missing + 999 sentinels (undrafted)
            continue
        meta = players.get(pid, {})
        pos  = meta.get("position") or (meta.get("fantasy_positions") or [None])[0]
        if pos not in SKILL:
            continue
        full = meta.get("full_name") or f"{meta.get('first_name','')} {meta.get('last_name','')}".strip()
        if not full or full.lower() == "player invalid":   # Sleeper junk/placeholder rows
            continue
        row = {
            "season":         season,
            "sleeper_id":     pid,
            "player":         full,
            "norm_name":      norm_name(full),
            "position":       pos,
        }
        for f in ADP_FIELDS:
            row[f] = rec.get(f)
        for f in PROJ_FIELDS:
            row[f"sleeper_{f}"] = rec.get(f)
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("adp_half_ppr").reset_index(drop=True)
    # QUARANTINE (2026-07-10 provenance audit): Sleeper's stored 2020 "projections"
    # are near-actuals, not projections — gp varies per player and correlates +0.91
    # with actual games played (Mixon proj 88.0/gp 6 = his real 89 pts/6 games;
    # Barkley proj 35.1/gp 2 = his week-2 ACL season), corr(proj, actual)=0.968 vs
    # 0.81-0.86 every other season. 2021+ pass every probe (constant full-slate gp,
    # injury busts keep high projections, refetch-stable). The 2020 ADP fields are
    # NOT affected (Barkley ADP rank 4 / Mixon 6 prove ADP is preseason) and are kept.
    if season == 2020:
        for f in PROJ_FIELDS:
            df[f"sleeper_{f}"] = pd.NA
    df["adp_overall_rank"] = range(1, len(df) + 1)
    # Positional ADP rank (e.g. WR12, RB5) — useful for the draft board view.
    df["adp_pos_rank"] = df.groupby("position")["adp_half_ppr"].rank(method="first").astype(int)
    return df


def main():
    players = load_players()
    frames = []
    for season in SEASONS:
        t = time.time()
        try:
            df = fetch_season(season, players)
            frames.append(df)
            print(f"  {season}: {len(df):>4} skill players with ADP  "
                  f"(top: {df.iloc[0]['player']} {df.iloc[0]['adp_half_ppr']:.1f})  "
                  f"({time.time()-t:.1f}s)")
        except Exception as e:
            print(f"  {season}: ERROR {e}")

    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV}  ({len(out):,} player-seasons, {out['season'].nunique()} seasons)")

    # Sanity summary
    print("\nPer-season skill-player counts:")
    print(out.groupby("season").size().to_string())
    print("\nName-collision check (same norm_name+position+season):")
    dupes = out.groupby(["season", "norm_name", "position"]).size()
    dupes = dupes[dupes > 1]
    print(f"  {len(dupes)} collisions" if len(dupes) else "  none — join key is unique per season")


if __name__ == "__main__":
    main()
