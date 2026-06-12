"""Why do FADE calls struggle, and can we fix them? Uses the FULL 11 seasons of ADP
(FFC 2014-2019 + Sleeper 2020-2025) for a bigger fade sample, then dissects fades.

A fade = we rank a player LOWER than ADP (we think they're overvalued). The 6-season dive
showed fades hit only ~46% (young fades 38%). Hypothesis: a fade only works when there's a
CONCRETE decline catalyst the model sees and ADP underweights (aging, declining production,
lost role) -- not just "our prior-stats model ranks them cheap" (which fails on young/ascending
players who have upside we can't see). We test fade hit-rate across candidate separators and
look for a rule that isolates the fades worth making.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adp_value_model as avm
import model_bakeoff as mb
from college_rookie_test import attach_college
import value_eval_extended as vx

LGBM = ("lgbm", dict(num_leaves=31, learning_rate=0.03, n_estimators=600, reg_lambda=3, subsample=0.8))
MIN_GAMES = 11
BOLD = 5


def build(test_seasons=range(2016, 2026)):
    df = avm.add_bias_features(attach_college(pd.read_csv(vx.HERE / "season_dataset_2014_2025.csv")))
    df = vx.attach_historical_adp(df)
    ppg_feats = [c for c in mb.FEATS if c in df.columns and c not in ("prior_games_missed", "missed_prior_season")]
    pool = df[(df["adp_overall_rank"] <= 180) & df["target_ppg"].notna() & df["adp_pos_rank"].notna()].copy()
    tr_all = df[df["target_ppg"].notna()]
    chunks = []
    for N in test_seasons:
        te = pool[pool.season == N].copy()
        tr = tr_all[tr_all.season < N]
        if len(te) < 20 or len(tr) < 200:
            continue
        te["ppg_pred"] = mb.fit_predict(LGBM[0], LGBM[1], tr, te, ppg_feats)
        gconst = pool[pool.season < N]["target_games"].mean()
        te["our_total"] = te["ppg_pred"] * gconst
        te["actual_total"] = te["target_ppg"] * te["target_games"]
        chunks.append(te)
    a = pd.concat(chunks, ignore_index=True)
    g = a.groupby(["season", "position"])
    a["adp_rk"] = g["adp_pos_rank"].transform(lambda s: s.rank(method="min"))
    a["our_rk"] = g["our_total"].transform(lambda s: s.rank(ascending=False, method="min"))
    a["act_rk"] = g["actual_total"].transform(lambda s: s.rank(ascending=False, method="min"))
    a["our_dev"] = a["adp_rk"] - a["our_rk"]
    a["actual_dev"] = a["adp_rk"] - a["act_rk"]
    return a[a["target_games"] >= MIN_GAMES].copy()


def hit(g, fade=True):
    # for fades, "right" = player finished BELOW their ADP (actual_dev < 0)
    return (np.sign(g["our_dev"]) == np.sign(g["actual_dev"])).mean()


def main():
    a = build()
    bold = a[a["our_dev"].abs() >= BOLD]
    buys = bold[bold["our_dev"] > 0]
    fades = bold[bold["our_dev"] < 0].copy()
    print(f"11-season (2016-2025) healthy bold calls: {len(bold)} (buys {len(buys)}, fades {len(fades)})")
    print(f"  BUY hit: {hit(buys)*100:.0f}% (n={len(buys)})   FADE hit: {hit(fades)*100:.0f}% (n={len(fades)})\n")

    # candidate decline catalysts (all prior-known)
    pos = fades["position"]
    age = fades["age"].fillna(26)
    fades["age_cliff"] = (((pos == "RB") & (age >= 27)) | (pos.isin(["WR", "TE"]) & (age >= 29))
                          | ((pos == "QB") & (age >= 34))).astype(int)
    fades["declining"] = (fades["ppg_trend"].fillna(0) < -1).astype(int)
    fades["young"] = (fades["years_exp"] <= 2).astype(int)
    fades["big_fade"] = (fades["our_dev"] <= -10).astype(int)
    fades["lost_role"] = (fades.get("ret_tgt_competition", pd.Series(0, index=fades.index)).fillna(0) > 0.5).astype(int)
    fades["qb_change"] = fades.get("qb_changed", pd.Series(0, index=fades.index)).fillna(0).astype(int)

    print("=== FADE hit-rate by candidate separator (>50% = a fade worth making) ===")
    print(f"  {'split':28s} {'flag=1':>14} {'flag=0':>14}")
    for name, col in [("age cliff (old)", "age_cliff"), ("declining prod (trend<-1)", "declining"),
                      ("young (exp<=2)", "young"), ("big fade (>=10 spots)", "big_fade"),
                      ("crowded target room", "lost_role"), ("QB changed", "qb_change")]:
        s1 = fades[fades[col] == 1]; s0 = fades[fades[col] == 0]
        c1 = f"{hit(s1)*100:3.0f}% (n={len(s1)})" if len(s1) >= 8 else f"  - (n={len(s1)})"
        c0 = f"{hit(s0)*100:3.0f}% (n={len(s0)})" if len(s0) >= 8 else f"  - (n={len(s0)})"
        print(f"  {name:28s} {c1:>14} {c0:>14}")

    # combine the promising ones into a "good fade" rule and test
    print("\n=== RULE: only fade if (age cliff OR declining) AND not young ===")
    good = fades[((fades.age_cliff == 1) | (fades.declining == 1)) & (fades.young == 0)]
    bad = fades[~(((fades.age_cliff == 1) | (fades.declining == 1)) & (fades.young == 0))]
    print(f"  qualifying fades: {hit(good)*100:.0f}% (n={len(good)})   |  filtered-out fades: {hit(bad)*100:.0f}% (n={len(bad)})")
    combo = pd.concat([buys, good])
    print(f"  overall calls (buys + good fades): {hit(combo)*100:.0f}% (n={len(combo)})  "
          f"vs all bold {hit(bold)*100:.0f}% (n={len(bold)})")


if __name__ == "__main__":
    main()
