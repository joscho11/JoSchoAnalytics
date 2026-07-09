"""PHASE 0 — apples-to-apples benchmark of the WEEKLY fantasy model vs Sleeper.

The repo has never actually benchmarked the weekly model against Sleeper's WEEKLY
projections (only the SEASONAL model vs Sleeper's season totals). This harness does it
honestly, on the 2025 holdout (production pkls trained 2020-2024 -> genuinely OOS):

  1. Target-semantics audit: target = next PLAYED game (stats rows only exist for games
     appeared in), so inactive-as-zero blending does NOT occur in train/eval. But bye/
     injury gaps mean some targets are 2+ weeks out on stale features -> quantified.
  2. Matchup misalignment audit: a row's matchup features (opponent, Vegas, def-vs-pos)
     describe the row's CURRENT game, while the target is the NEXT game -> quantified.
  3. Baseline ladder on identical universes: roll3 avg / season-to-date avg / Sleeper /
     our model. Metrics that matter for lineups: MAE, within position-week Spearman,
     top-N hit rate, and a weekly best-lineup sim (1QB/2RB/3WR/1TE) graded on actuals.

Universes: U0 = every scored row (our usual eval universe); U1 = rows Sleeper also
projects for the target game; U2 = U1 with Sleeper proj >= 5 (fantasy-relevant pool).

Sleeper weekly source: https://api.sleeper.com/projections/nfl/{season}/{week}
(undocumented graph endpoint; verified live for 2021 and 2025; carries pts_half_ppr and
inline player names). Cached to sleeper_weekly_proj_{season}.csv next to this script.

Run:  python fantasy/benchmark_weekly.py
"""
import sys, time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "seasonal_projections"))
from _utils import norm_name  # same normalization used for the seasonal Sleeper join

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SEASON = 2025
WEEKS = range(1, 19)
POSITIONS = ["QB", "RB", "WR", "TE"]
TOP_N = {"QB": 12, "RB": 24, "WR": 24, "TE": 12}
LINEUP = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
SLEEPER_CACHE = HERE / f"sleeper_weekly_proj_{SEASON}.csv"


# ---------------------------------------------------------------- sleeper fetch
def fetch_sleeper_weekly() -> pd.DataFrame:
    if SLEEPER_CACHE.exists():
        return pd.read_csv(SLEEPER_CACHE)
    rows = []
    for wk in WEEKS:
        url = f"https://api.sleeper.com/projections/nfl/{SEASON}/{wk}"
        params = [("season_type", "regular")] + [("position[]", p) for p in POSITIONS]
        r = requests.get(url, params=params, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0 (benchmark harness)"})
        r.raise_for_status()
        n = 0
        for rec in r.json():
            st, pl = rec.get("stats") or {}, rec.get("player") or {}
            pts = st.get("pts_half_ppr")
            pos = (pl.get("fantasy_positions") or [None])[0]
            if pts is None or pos not in POSITIONS:
                continue
            rows.append({"week": wk, "position": pos, "slp_proj": float(pts),
                         "name": f"{pl.get('first_name','')} {pl.get('last_name','')}".strip()})
            n += 1
        print(f"  sleeper {SEASON} wk{wk:2d}: {n} projections")
        time.sleep(0.4)
    out = pd.DataFrame(rows)
    out["norm_name"] = out["name"].map(norm_name)
    # collisions (same normalized name + position + week): keep the larger projection
    out = (out.sort_values("slp_proj", ascending=False)
              .drop_duplicates(["norm_name", "position", "week"]))
    out.to_csv(SLEEPER_CACHE, index=False)
    return out


# ---------------------------------------------------------------- build the frame
def build_frame() -> pd.DataFrame:
    feats = pd.read_csv(HERE / "features_dataset.csv")
    feats = feats[feats.season == SEASON].copy()

    # target week/opponent = the player's next played game (reconstructed from raw rows)
    raw = pd.read_csv(HERE / "raw_dataset.csv",
                      usecols=["player_id", "season", "week", "opponent_team"])
    raw = raw.sort_values(["player_id", "season", "week"])
    raw["target_week"] = raw.groupby(["player_id", "season"])["week"].shift(-1)
    raw["target_opp"] = raw.groupby(["player_id", "season"])["opponent_team"].shift(-1)
    feats = feats.merge(raw, on=["player_id", "season", "week", "opponent_team"], how="left")
    feats["gap"] = feats.target_week - feats.week

    # our model predictions (per-position pkls, trained 2020-2024 -> OOS on 2025)
    feats["ours"] = np.nan
    for pos in POSITIONS:
        art = joblib.load(HERE / "models" / f"{pos.lower()}_model.pkl")
        m = feats.position == pos
        if m.any():
            feats.loc[m, "ours"] = art["model"].predict(feats.loc[m, art["feature_cols"]])

    # baselines: trailing-3 average (existing feature) + season-to-date average, both
    # strictly point-in-time (from games up to and including the row's week W).
    hdr = pd.read_csv(HERE / "raw_dataset.csv", nrows=0).columns
    use = ["player_id", "season", "week"] + [c for c in ("fantasy_points", "fantasy_points_ppr") if c in hdr]
    stats = pd.read_csv(HERE / "raw_dataset.csv", usecols=use)
    stats = stats[stats.season == SEASON].copy()
    if "fantasy_points_ppr" in stats.columns:      # half-PPR = midpoint of std and full-PPR
        stats["pts"] = (stats["fantasy_points"] + stats["fantasy_points_ppr"]) / 2
    else:
        stats["pts"] = stats["fantasy_points"]
    stats = stats.sort_values(["player_id", "week"])
    stats["s2d"] = stats.groupby("player_id")["pts"].transform(
        lambda x: x.expanding().mean())          # through the row's week W (pre-target)
    feats = feats.merge(stats[["player_id", "week", "s2d"]], on=["player_id", "week"], how="left")
    feats["roll3"] = feats["fantasy_points_half_ppr_roll3"]  # NOTE: lagged (thru W-1); s2d thru W

    # sleeper projection for the TARGET game
    slp = fetch_sleeper_weekly()
    feats["norm_name"] = feats.player_display_name.map(norm_name)
    feats = feats.merge(slp[["norm_name", "position", "week", "slp_proj"]],
                        left_on=["norm_name", "position", "target_week"],
                        right_on=["norm_name", "position", "week"],
                        how="left", suffixes=("", "_slp"))
    return feats


# ---------------------------------------------------------------- metrics
def spearman_by_week(df, col):
    out = []
    for (_, wk), g in df.groupby(["position", "target_week"]):
        if len(g) >= 8 and g[col].notna().all():
            out.append(g[col].corr(g.target_half_ppr, method="spearman"))
    return np.nanmean(out)


def topn_hit(df, col):
    hits = []
    for (pos, wk), g in df.groupby(["position", "target_week"]):
        n = TOP_N[pos]
        if len(g) < n * 1.5:
            continue
        pred_top = set(g.nlargest(n, col).player_id)
        real_top = set(g.nlargest(n, "target_half_ppr").player_id)
        hits.append(len(pred_top & real_top) / n)
    return np.nanmean(hits)


def lineup_points(df, col):
    total = 0.0
    for wk, g in df.groupby("target_week"):
        for pos, k in LINEUP.items():
            total += g[g.position == pos].nlargest(k, col).target_half_ppr.sum()
    return total


def ladder(df, label):
    methods = [("trailing-3 avg", "roll3"), ("season-to-date", "s2d"),
               ("OUR model", "ours"), ("Sleeper", "slp_proj")]
    methods = [(n, c) for n, c in methods if df[c].notna().any()]
    print(f"\n===== {label}  (n={len(df):,}) =====")
    print(f"{'method':16s} {'MAE':>6s} {'rank-rho':>9s} {'topN-hit':>9s} {'lineup pts':>11s}")
    for name, col in methods:
        sub = df[df[col].notna()]
        mae = (sub[col] - sub.target_half_ppr).abs().mean()
        print(f"{name:16s} {mae:6.2f} {spearman_by_week(sub, col):9.3f} "
              f"{topn_hit(sub, col):9.1%} {lineup_points(sub, col):11.0f}")
    print("per-position MAE (ours vs Sleeper):")
    for pos in POSITIONS:
        g = df[(df.position == pos) & df.slp_proj.notna()]
        if len(g):
            print(f"  {pos}: ours {(g.ours - g.target_half_ppr).abs().mean():5.2f}"
                  f"  sleeper {(g.slp_proj - g.target_half_ppr).abs().mean():5.2f}  (n={len(g)})")


def main():
    df = build_frame()
    scored = df[df.target_half_ppr.notna() & df.ours.notna()].copy()

    print("\n################ AUDITS ################")
    gaps = scored.gap.value_counts(normalize=True).sort_index()
    print("target gap (weeks until the game being predicted):")
    print("  " + "  ".join(f"gap {int(k)}: {v*100:.1f}%" for k, v in gaps.head(5).items()))
    mis = (scored.opponent_team != scored.target_opp).mean()
    print(f"matchup features describe a DIFFERENT game than the target: {mis*100:.1f}% of rows")
    for lo, hi, lbl in [(1, 1, "gap=1 (normal)"), (2, 2, "gap=2 (bye)"), (3, 99, "gap>=3 (missed time)")]:
        g = scored[(scored.gap >= lo) & (scored.gap <= hi)]
        if len(g):
            print(f"  OUR MAE on {lbl:22s}: {(g.ours - g.target_half_ppr).abs().mean():5.2f}  (n={len(g):,})")

    print("\n################ BASELINE LADDER ################")
    ladder(scored, "U0: every scored row (our usual eval universe)")
    u1 = scored[scored.slp_proj.notna()]
    ladder(u1, "U1: Sleeper also projects the target game")
    ladder(u1[u1.slp_proj >= 5], "U2: U1 and Sleeper proj >= 5 (fantasy-relevant)")

    unmatched = scored[scored.slp_proj.isna() & (scored.target_half_ppr >= 8)]
    print(f"\nsanity: scored >=8 pts but NO sleeper match (name-join misses): {len(unmatched)} rows")
    if len(unmatched):
        print("  e.g.", unmatched.player_display_name.value_counts().head(5).index.tolist())


if __name__ == "__main__":
    main()
