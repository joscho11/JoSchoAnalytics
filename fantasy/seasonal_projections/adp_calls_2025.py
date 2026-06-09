"""2025 ADP-MISPRICING calls from the production model (the canonical view).

Not projection accuracy -- the calls. For the drafted pool, rank by our production
projection (Model A LightGBM x constant games) and by ADP, then show every player we move
>= 5 spots off ADP (a "bold call"): BUY = we rank them higher than the market (undervalued),
FADE = lower (overvalued). Grade each by whether they actually moved our way vs ADP. Mid-season
injuries (missed > 6 games) are flagged and excluded from the hit-rate, per surprise_eval.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA = HERE / "season_dataset_2014_2025.csv"
MODELS_DIR = HERE / "models"
POSITIONS = ["QB", "RB", "WR", "TE"]
BOLD = 5            # "off ADP by >= 5 spots"
MIN_GAMES = 11     # missed <= 6 games (else injury-wrecked -> excluded from grading)


def predict_2025():
    df = pd.read_csv(DATA)
    pool = df[(df["adp_overall_rank"] <= 180) & df["target_ppg"].notna()].copy()
    gconst = pool[pool.season < 2025]["target_games"].mean()
    te = pool[pool.season == 2025].copy()
    te["ppg_pred"] = np.nan
    for pos in POSITIONS:
        art = joblib.load(MODELS_DIR / f"{pos.lower()}_ppg_model.pkl")
        m = te.position == pos
        te.loc[m, "ppg_pred"] = np.clip(art["model"].predict(te.loc[m, art["feature_cols"]]), 0, None)
    te["our_total"] = te["ppg_pred"] * gconst
    te["actual_total"] = te["target_ppg"] * te["target_games"]
    g = te.groupby("position")
    te["adp_rk"] = g["adp_pos_rank"].transform(lambda s: s.rank(method="min"))
    te["our_rk"] = g["our_total"].transform(lambda s: s.rank(ascending=False, method="min"))
    te["act_rk"] = g["actual_total"].transform(lambda s: s.rank(ascending=False, method="min"))
    te["value"] = te["adp_rk"] - te["our_rk"]        # + = we say undervalued (BUY)
    te["actual_dev"] = te["adp_rk"] - te["act_rk"]   # + = actually beat ADP
    return te


def row(r, pos):
    healthy = r["target_games"] >= MIN_GAMES
    if not healthy:
        res = "injury"
    elif np.sign(r["value"]) == np.sign(r["actual_dev"]) and r["value"] != 0:
        res = "RIGHT"
    else:
        res = "wrong"
    return (f"  {r['player'][:20]:20s}  ADP {pos}{int(r['adp_rk']):<2d} -> we say {pos}{int(r['our_rk']):<2d} "
            f"(value {int(r['value']):+d})  -> finished {pos}{int(r['act_rk']):<2d}   [{res}]")


def main():
    te = predict_2025()
    for POS in ["RB", "WR"]:
        d = te[te.position == POS].copy()
        bold = d[d["value"].abs() >= BOLD]
        buys = bold[bold["value"] >= BOLD].sort_values("value", ascending=False)
        fades = bold[bold["value"] <= -BOLD].sort_values("value")
        healthy = bold[bold["target_games"] >= MIN_GAMES]
        hit = (np.sign(healthy["value"]) == np.sign(healthy["actual_dev"])).mean() if len(healthy) else float("nan")

        print(f"\n================  2025 {POS} — ADP-mispricing calls (off ADP by >= {BOLD})  ================")
        print(f"  {len(bold)} bold calls | hit rate on healthy calls: {hit*100:.0f}%  (n={len(healthy)}, 50% = coin flip)\n")
        print(f"  UNDERVALUED (we rank them above the market):")
        for _, r in buys.iterrows():
            print(row(r, POS))
        print(f"\n  OVERVALUED (we rank them below the market):")
        for _, r in fades.iterrows():
            print(row(r, POS))


if __name__ == "__main__":
    main()
