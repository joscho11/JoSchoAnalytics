"""Does COLLEGE production beat ADP on the rookie slice? (the real-edge dig)

The ADP-value backtest showed the market is efficient on veterans but weak on
rookies (no NFL prior to price). College production (dominator, production/game,
efficiency) is the orthogonal signal NFL stats can't contain. This tests whether
it actually adds edge over the market ON ROOKIES, walk-forward, 2025 the live test.

Compares, on the drafted rookie pool, per-position Spearman ρ (pred vs actual
finish) and BUY/FADE hit-rate vs ADP:
  ADP          - market draft rank
  Sleeper      - Sleeper's own projection
  draft-only   - what we know about a rookie WITHOUT college (capital, age)
  draft+college- adds the college features
  college-only - college signal alone

Run:  python college_rookie_test.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adp_value_model as avm   # reuse fit_predict, pos_rank, wmean_pos_spearman

HERE = Path(__file__).resolve().parent

DRAFT_ONLY = ["draft_round", "draft_pick", "age"]
COLLEGE = ["cfb_final_dom", "cfb_best_dom", "cfb_scrim_ypg", "cfb_rec_ypg", "cfb_rush_ypg",
           "cfb_rec_pg", "cfb_scrim_td", "cfb_ypc", "cfb_ypr", "cfb_final_recshare",
           "cfb_seasons", "cfb_final_class", "cfb_breakout_class", "cfb_career_scrim_yds"]
MARKET = ["adp_pos_rank", "adp_half_ppr", "sleeper_pts_half_ppr"]


def attach_college(df):
    feat = pd.read_csv(HERE / "college_features.csv")
    keep = ["norm_name"] + [c for c in COLLEGE if c in feat.columns]
    out = df.merge(feat[keep], on="norm_name", how="left")
    return out


def rookie_backtest(df, test_seasons=range(2022, 2026), buy_thresh=4, drafted_max=180):
    df = avm.add_bias_features(df)
    rook = df[(df["is_rookie"] == 1) & (df["adp_overall_rank"] <= drafted_max)
              & df["target_ppg"].notna()].copy()
    cov = rook["cfb_final_dom"].notna().mean()
    print(f"drafted rookies (graded): {len(rook)}  | college-feature coverage: {cov*100:.0f}%\n")

    preds = []   # collect per-test-season predictions for pooled metrics
    for N in test_seasons:
        tr = rook[rook["season"] < N]
        te = rook[rook["season"] == N].copy()
        if len(te) < 8 or len(tr) < 25:
            continue
        te["p_draft"]   = avm.fit_predict(tr, te, DRAFT_ONLY)
        te["p_college"] = avm.fit_predict(tr, te, COLLEGE)
        te["p_full"]    = avm.fit_predict(tr, te, DRAFT_ONLY + COLLEGE)
        preds.append(te)
    allp = pd.concat(preds, ignore_index=True)

    # pooled per-position ρ (concatenate all walk-forward test rookies, then rank within position)
    def rho(col, asc=False):
        return avm.wmean_pos_spearman(allp.assign(_x=(-allp[col] if asc else allp[col])), "_x")
    metrics = {
        "ADP": rho("adp_pos_rank", asc=True),
        "Sleeper": rho("sleeper_pts_half_ppr"),
        "draft-only": rho("p_draft"),
        "college-only": rho("p_college"),
        "draft+college": rho("p_full"),
    }

    # buy/fade hit-rate of the draft+college model vs ADP (within position, pooled)
    allp["adp_posrk"] = allp.groupby(["season", "position"])["adp_pos_rank"].transform(lambda s: avm.pos_rank(s, ascending=True))
    allp["pred_posrk"] = allp.groupby(["season", "position"])["p_full"].transform(lambda s: avm.pos_rank(s))
    allp["actual_posrk"] = allp.groupby(["season", "position"])["target_ppg"].transform(lambda s: avm.pos_rank(s))
    allp["value"] = allp["adp_posrk"] - allp["pred_posrk"]
    allp["beat_adp"] = allp["adp_posrk"] - allp["actual_posrk"]
    buys = allp[allp["value"] >= buy_thresh]
    fades = allp[allp["value"] <= -buy_thresh]

    print("Pooled rookie backtest (walk-forward, drafted pool) — per-position Spearman ρ:")
    for k, v in metrics.items():
        mark = "  <- market" if k in ("ADP", "Sleeper") else ""
        print(f"  {k:14s} {v:6.3f}{mark}")
    print(f"\n  Does college add over draft capital?  draft+college − draft-only = "
          f"{metrics['draft+college'] - metrics['draft-only']:+.3f}")
    print(f"  Does our model beat the market?        draft+college − ADP        = "
          f"{metrics['draft+college'] - metrics['ADP']:+.3f}   "
          f"(vs Sleeper {metrics['draft+college'] - metrics['Sleeper']:+.3f})")
    print(f"\n  BUY  hit-rate: {(buys['beat_adp']>0).mean()*100:.0f}%  (n={len(buys)})   [50% = no edge]")
    print(f"  FADE hit-rate: {(fades['beat_adp']<0).mean()*100:.0f}%  (n={len(fades)})")

    # 2025 live rookie buys
    b25 = buys[buys["season"] == 2025].sort_values("value", ascending=False)
    if len(b25):
        print("\n  2025 rookie BUY calls (college-driven value vs ADP):")
        for _, p in b25.head(10).iterrows():
            hit = "OK " if p["beat_adp"] > 0 else "x  "
            print(f"    {hit} {p['player']:22s} {p['position']:3s} pred {p['position']}{int(p['pred_posrk'])}"
                  f" vs ADP {p['position']}{int(p['adp_posrk'])} -> finished {p['position']}{int(p['actual_posrk'])}")
    return metrics, allp


def main():
    df = pd.read_csv(avm.newest_dataset())
    df = attach_college(df)
    rookie_backtest(df)


if __name__ == "__main__":
    main()
