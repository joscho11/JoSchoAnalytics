"""CANONICAL seasonal evaluation: can the model identify over/undervalued players vs ADP?

Standard MAE/rank-corr reward agreeing with the market on the easy calls (Chase = top 5).
The edge is ONLY in the disagreements. So we evaluate CONDITIONAL ON ADP:

  our_dev[i]    = adp_pos_rank[i] - our_pos_rank[i]      (how far WE move them off ADP; + = we're higher)
  actual_dev[i] = adp_pos_rank[i] - actual_pos_rank[i]   (how far they ACTUALLY beat their ADP)

Edge = corr(our_dev, actual_dev). If our disagreements are noise it's ~0 (placebo). Positive
and stable = real skill at finding mispriced players. We also report:
  - bold-call hit rate: when we strongly disagree with ADP, do players move our way? (vs placebo)
  - surprise-catch rate: of the season's biggest ADP busts/steals, how many did we lean right on?
  - a 2025 scorecard of the biggest surprises and what our model said.

INJURY FILTER: mid-season injuries are unpredictable noise, so we GRADE the model only on
players who missed <= 6 games (played >= MIN_GAMES_PLAYED in a 17-game season). Ranks are
computed over the full drafted pool (real finish positions); we just don't judge the model on
players whose season was wrecked by an injury it could never have foreseen. (This also sweeps
up the few pre-season-known injuries like Aiyuk -- slightly unfair since those are predictable,
but the sample is too thin to handle separately; an accepted simplification.)

Uses our STANDALONE model (LightGBM PPG x constant games -> positional finish), no Sleeper/ADP
in the features, so this measures OUR independent edge. Pooled 2021-2025 (one season is too noisy).
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adp_value_model as avm
import model_bakeoff as mb
from college_rookie_test import attach_college

LGBM = ("lgbm", dict(num_leaves=31, learning_rate=0.03, n_estimators=600, reg_lambda=3, subsample=0.8))
MIN_GAMES_PLAYED = 11   # grade only players who missed <= 6 games (17-game season); injuries are noise
rng = np.random.default_rng(42)


def build():
    df = avm.add_bias_features(attach_college(pd.read_csv(avm.newest_dataset())))
    ppg_feats = [c for c in mb.FEATS if c in df.columns and c not in ("prior_games_missed", "missed_prior_season")]
    pool = df[(df["adp_overall_rank"] <= 180) & df["target_ppg"].notna()].copy()
    tr = df[df["target_ppg"].notna()]
    chunks = []
    for N in range(2021, 2026):
        te = pool[pool["season"] == N].copy()
        if len(te) < 20:
            continue
        te["ppg_pred"] = mb.fit_predict(LGBM[0], LGBM[1], tr[tr.season < N], te, ppg_feats)
        gconst = pool[pool["season"] < N]["target_games"].mean()
        te["our_total"] = te["ppg_pred"] * gconst
        te["actual_total"] = te["target_ppg"] * te["target_games"]
        chunks.append(te)
    a = pd.concat(chunks, ignore_index=True)
    # positional ranks within the drafted pool, per season+position
    grp = a.groupby(["season", "position"])
    a["adp_rk"] = grp["adp_pos_rank"].transform(lambda s: s.rank(method="min"))
    a["our_rk"] = grp["our_total"].transform(lambda s: s.rank(ascending=False, method="min"))
    a["act_rk"] = grp["actual_total"].transform(lambda s: s.rank(ascending=False, method="min"))
    a["our_dev"] = a["adp_rk"] - a["our_rk"]
    a["actual_dev"] = a["adp_rk"] - a["act_rk"]
    return a


def main():
    a_full = build()
    a = a_full[a_full["target_games"] >= MIN_GAMES_PLAYED].copy()   # canonical: healthy players only
    print(f"graded pool: {len(a)} healthy player-seasons (missed <=6 games); "
          f"{len(a_full)-len(a)} injury-wrecked seasons excluded\n")

    # ---- core edge: corr(our_dev, actual_dev), pooled + per season, vs placebo ----
    r = a["our_dev"].corr(a["actual_dev"])
    plac = np.mean([pd.Series(rng.permutation(a["our_dev"].values)).corr(a["actual_dev"]) for _ in range(300)])
    r_unf = a_full["our_dev"].corr(a_full["actual_dev"])
    print("=== ADP-MISPRICING SKILL: corr(our deviation from ADP, actual deviation from ADP) ===")
    print(f"  pooled 2021-2025 (healthy): {r:+.3f}   placebo(shuffled): {plac:+.3f}   edge: {r-plac:+.3f}")
    print(f"  (for reference, with injury-wrecked seasons included: {r_unf:+.3f})")
    print("  per season (healthy): " + "  ".join(
        f"{int(N)}:{g['our_dev'].corr(g['actual_dev']):+.2f}" for N, g in a.groupby("season")))

    # ---- bold-call hit rate: |our_dev|>=5, did the player move our way? ----
    bold = a[a["our_dev"].abs() >= 5].copy()
    bold["right"] = np.sign(bold["our_dev"]) == np.sign(bold["actual_dev"])
    base = np.mean([(np.sign(rng.permutation(bold["our_dev"].values)) == np.sign(bold["actual_dev"])).mean()
                    for _ in range(300)])
    print(f"\n=== BOLD CALLS (we move a healthy player >=5 spots off ADP), n={len(bold)} ===")
    print(f"  leaned the RIGHT direction: {bold['right'].mean()*100:.0f}%   placebo: {base*100:.0f}%   "
          f"edge: {(bold['right'].mean()-base)*100:+.0f}pp")

    # ---- surprise-catch: of the biggest ACTUAL surprises, did we lean right? ----
    surp = a[a["actual_dev"].abs() >= 10].copy()
    surp["right"] = np.sign(surp["our_dev"]) == np.sign(surp["actual_dev"])
    print(f"\n=== SURPRISE-CATCH (healthy players who finished >=10 spots off their ADP), n={len(surp)} ===")
    print(f"  we leaned the right direction on: {surp['right'].mean()*100:.0f}%  (50% = coin flip)")

    # ---- 2025 scorecard: biggest steals & busts among healthy players, what we said ----
    a25 = a[a.season == 2025]
    def row(r):
        p = r["position"]
        lean = "RIGHT" if np.sign(r["our_dev"]) == np.sign(r["actual_dev"]) and r["our_dev"] != 0 else \
               ("flat" if r["our_dev"] == 0 else "wrong")
        return (f"  {r['player'][:20]:20s} {p:3s}  ADP {p}{int(r['adp_rk']):<2d} "
                f"-> finished {p}{int(r['act_rk']):<2d}  | we said {p}{int(r['our_rk']):<2d}  [{lean}]")
    print("\n=== 2025 biggest STEALS (finished way above ADP) — did we catch them? ===")
    for _, r in a25.sort_values("actual_dev", ascending=False).head(8).iterrows():
        print(row(r))
    print("\n=== 2025 biggest BUSTS (finished way below ADP) — did we fade them? ===")
    for _, r in a25.sort_values("actual_dev").head(8).iterrows():
        print(row(r))


if __name__ == "__main__":
    main()
