"""ADP Value Model — find UNDERvalued / OVERvalued players vs Sleeper ADP.

The reframe (vs the old projection board)
-----------------------------------------
The old board built an *independent* season projection and hoped it would
out-rank ADP. It doesn't, and the reason is structural: an independent
projection from prior-season stats is noisier than ADP, so when the two
disagree it's usually our noise, not the market's error. ADP prices "who was
good last year" perfectly.

So instead of projecting in a vacuum, this model predicts the ADP RESIDUAL: how
much a player will beat or miss the per-game finish their ADP slot implies,
using situational signal the market is known to underweight (the Year-2 QB leap,
injury bounce-back, vacated opportunity, the age cliff). The output per player is
a value score:

    value = adp_pos_rank - pred_pos_rank
      value > 0  -> we rank them ahead of the market  -> UNDERVALUED (buy)
      value < 0  -> market ranks them ahead of us      -> OVERVALUED  (fade)

What "value" is judged on
-------------------------
Half-PPR points PER GAME (target_ppg). This is deliberate: we're asking whether
the market mis-judged a player's TALENT / ROLE / SITUATION, not whether they got
unlucky with injuries (injury variance is mostly a freak hit — see Model B, ρ
~0.57). Availability is a separate axis. Per-game value is the right target for
"did the market misprice this player."

The honest test
---------------
Walk-forward: train on seasons < N, predict N (no leakage). 2025 is the live
holdout. The headline metric is the BUY/FADE hit-rate — when the model says buy,
does the player actually finish ahead of their ADP? — plus per-position Spearman
ρ vs ADP and vs Sleeper's own projection. If our situational features don't add
signal over [ADP + Sleeper], we say so.

Run:  python adp_value_model.py            # walk-forward backtest + 2025 verdict
"""
import sys
import glob
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent


# ── data ─────────────────────────────────────────────────────────────────────
def newest_dataset():
    files = sorted(glob.glob(str(HERE / "season_dataset_2014_*.csv")))
    if not files:
        raise FileNotFoundError("no season_dataset_2014_*.csv — run build_season_dataset.py")
    # prefer the dataset that ENDS at 2025 (the trained range) for backtesting;
    # the 2026 file appends a no-actuals season we don't backtest on.
    f = next((p for p in files if p.endswith("2014_2025.csv")), files[-1])
    return f


# situational features the model is allowed to see (NO adp / sleeper / target)
SITU = [
    "prior_ppg", "prior_half_ppr", "prior_games", "prior_snap_share_pg",
    "ppg_2yr", "ppg_3yr", "ppg_trend", "career_high_ppg",
    "prior_targets_pg", "prior_carries_pg", "prior_receptions_pg", "prior_touches_pg",
    "prior_target_share", "prior_air_yards_share", "prior_adot",
    "prior_td_rate", "prior_yptarget", "prior_ypc", "prior_rec_epa", "prior_rush_epa",
    "age", "years_exp", "draft_round", "draft_pick",
    "prior_team_pass_rate", "prior_team_plays", "coach_changed", "qb_changed",
    "vacated_target_share", "vacated_rush_share",
    "prior_games_missed", "is_rookie", "missed_prior_season",
]

# ADP-bias features added here (each a documented market-inefficiency thesis)
BIAS = ["year2_qb", "sophomore_skill", "year3_wr_te", "injury_bounceback",
        "vet_decline", "ascending_usage"]

MARKET = ["adp_pos_rank", "adp_half_ppr", "sleeper_pts_half_ppr"]  # anchor inputs
CAT = ["position"]


def add_bias_features(df):
    """Situation flags targeting known ADP biases (all from prior-only info)."""
    d = df.copy()
    pos = d["position"]
    yx = d["years_exp"]
    # Year-2 QB who actually played as a rookie — the leap the market lags on.
    d["year2_qb"] = ((pos == "QB") & (yx == 1) & (d["prior_games"].fillna(0) >= 6)).astype(int)
    # Sophomore skill (RB/WR/TE) — usage/role often expands in year 2.
    d["sophomore_skill"] = ((yx == 1) & pos.isin(["RB", "WR", "TE"])).astype(int)
    # Year-3 WR/TE — the classic target-share breakout window.
    d["year3_wr_te"] = ((yx == 2) & pos.isin(["WR", "TE"])).astype(int)
    # Injury bounce-back: a proven player (high career high) who lost time last
    # year — the market over-applies a recency/durability discount.
    hi = d["career_high_ppg"].fillna(0)
    thr = pos.map({"QB": 16, "RB": 11, "WR": 10, "TE": 8}).fillna(10)
    d["injury_bounceback"] = ((d["prior_games_missed"].fillna(0) >= 5) & (hi >= thr)
                              & (d["missed_prior_season"] == 0)).astype(int)
    # Veteran decline (fade): RB age>=28, WR/TE age>=30, QB age>=36.
    age = d["age"].fillna(0)
    d["vet_decline"] = (((pos == "RB") & (age >= 28))
                        | (pos.isin(["WR", "TE"]) & (age >= 30))
                        | ((pos == "QB") & (age >= 36))).astype(int)
    # Ascending usage: young and trending up in production.
    d["ascending_usage"] = ((yx <= 3) & (d["ppg_trend"].fillna(0) > 1.5)).astype(int)
    return d


# ── ranking + metrics ────────────────────────────────────────────────────────
def pos_rank(s, ascending=False):
    """Rank within the series (1 = best). ascending=False => higher value is rank 1."""
    return s.rank(ascending=ascending, method="min")


def wmean_pos_spearman(df, pred_col, actual_col="target_ppg"):
    """n-weighted mean of per-position Spearman ρ (rank corr) between pred and actual."""
    num = den = 0.0
    for _, g in df.groupby("position"):
        g = g.dropna(subset=[pred_col, actual_col])
        if len(g) < 5:
            continue
        rho = g[pred_col].rank().corr(g[actual_col].rank())
        if pd.notna(rho):
            num += rho * len(g)
            den += len(g)
    return num / den if den else np.nan


def fit_predict(train, test, feats, cat=CAT):
    """Train a pooled CatBoost (position as native categorical) and predict test PPG."""
    tr = train.dropna(subset=["target_ppg"]).copy()
    use = [c for c in feats if c in tr.columns]
    for c in cat:
        tr[c] = tr[c].astype(str)
    Xtr = tr[use + cat].copy()
    pool = Pool(Xtr, tr["target_ppg"], cat_features=cat, weight=tr["sample_weight"].clip(lower=1))
    m = CatBoostRegressor(iterations=400, depth=5, learning_rate=0.04, loss_function="MAE",
                          l2_leaf_reg=4.0, random_seed=42, verbose=0, allow_writing_files=False)
    m.fit(pool)
    te = test.copy()
    for c in cat:
        te[c] = te[c].astype(str)
    return m.predict(te[use + cat])


# ── walk-forward backtest ────────────────────────────────────────────────────
DRAFTED_MAX_RANK = 180   # only the realistically-draftable pool; deep ADP dregs trivially "beat ADP"


def backtest(df, test_seasons=range(2021, 2026), buy_thresh=4, drafted_max=DRAFTED_MAX_RANK):
    """For each test season, rank by several signals, score vs actual, and measure
    the BUY/FADE hit-rate of OUR value model. Train only on strictly-prior seasons.

    The pool is restricted to ADP overall top `drafted_max` so the hit-rate isn't a
    pool-edge artifact (waiver-tier players nearly always 'beat' their ADP slot).
    """
    df = add_bias_features(df)
    # draftable pool = top-N by ADP with a gradeable per-game finish
    graded = df[(df["adp_overall_rank"] <= drafted_max) & df["target_ppg"].notna()].copy()

    rows, buys, fades = [], [], []
    for N in test_seasons:
        train = df[(df["season"] < N) & (df["adp_pos_rank"].notna())]
        test = graded[graded["season"] == N].copy()
        if len(test) < 30 or train["target_ppg"].notna().sum() < 100:
            continue

        test["pred_situ"] = fit_predict(train, test, SITU + BIAS)            # ours, no market
        test["pred_mkt"]  = fit_predict(train, test, MARKET)                 # market consensus only
        test["pred_mb"]   = fit_predict(train, test, MARKET + BIAS)          # market + 6 thesis flags
        test["pred_full"] = fit_predict(train, test, SITU + BIAS + MARKET)   # ours + market anchor

        # actual within-position finish (1 = best by actual PPG)
        test["actual_posrk"] = test.groupby("position")["target_ppg"].transform(lambda s: pos_rank(s))
        # our predicted within-position rank (full model = the production signal)
        test["pred_posrk"] = test.groupby("position")["pred_full"].transform(lambda s: pos_rank(s))
        # re-rank ADP WITHIN the graded pool so all ranks share a population
        test["adp_posrk"] = test.groupby("position")["adp_pos_rank"].transform(lambda s: pos_rank(s, ascending=True))

        rho_adp = wmean_pos_spearman(test.assign(_a=-test["adp_pos_rank"]), "_a")
        rho_slp = wmean_pos_spearman(test, "sleeper_pts_half_ppr")
        rho_situ = wmean_pos_spearman(test, "pred_situ")
        rho_mkt = wmean_pos_spearman(test, "pred_mkt")
        rho_mb = wmean_pos_spearman(test, "pred_mb")
        rho_full = wmean_pos_spearman(test, "pred_full")

        # value = how far ahead of the market we rank them (positive = buy)
        test["value"] = test["adp_posrk"] - test["pred_posrk"]
        # did they actually beat their ADP slot? (finished better than drafted)
        test["beat_adp"] = test["adp_posrk"] - test["actual_posrk"]   # >0 = outperformed ADP

        by = test[test["value"] >= buy_thresh]
        fd = test[test["value"] <= -buy_thresh]
        buy_hit = (by["beat_adp"] > 0).mean() if len(by) else np.nan
        fade_hit = (fd["beat_adp"] < 0).mean() if len(fd) else np.nan
        buys.append(by.assign(season=N)); fades.append(fd.assign(season=N))

        rows.append(dict(season=N, n=len(test), rho_adp=rho_adp, rho_sleeper=rho_slp,
                         rho_ours=rho_situ, rho_mkt=rho_mkt, rho_mb=rho_mb, rho_full=rho_full,
                         n_buy=len(by), buy_hit=buy_hit, n_fade=len(fd), fade_hit=fade_hit))
    res = pd.DataFrame(rows)
    buys = pd.concat(buys, ignore_index=True) if buys else pd.DataFrame()
    fades = pd.concat(fades, ignore_index=True) if fades else pd.DataFrame()
    return res, buys, fades


def _fmt(x):
    return "  n/a" if pd.isna(x) else f"{x:5.3f}"


def main():
    path = newest_dataset()
    df = pd.read_csv(path)
    print(f"dataset: {Path(path).name}  ({len(df):,} rows)\n")

    res, buys, fades = backtest(df)
    print("Walk-forward backtest — per-position Spearman ρ (pred rank vs actual finish):")
    print("  draftable pool only (ADP overall top 180). Baselines to beat: ADP, Sleeper.\n")
    print(f"  {'season':>6} {'n':>4} | {'ADP':>6} {'Sleeper':>7} {'OURS':>6} {'mkt-only':>8} {'OURS+mkt':>8} |"
          f" {'buys':>5} {'hit%':>5} | {'fades':>5} {'hit%':>5}")
    for _, r in res.iterrows():
        print(f"  {int(r.season):>6} {int(r.n):>4} | {_fmt(r.rho_adp)} {_fmt(r.rho_sleeper)} "
              f"{_fmt(r.rho_ours)} {_fmt(r.rho_mkt)} {_fmt(r.rho_full)}   | {int(r.n_buy):>5} "
              f"{'  n/a' if pd.isna(r.buy_hit) else f'{r.buy_hit*100:4.0f}%'} | {int(r.n_fade):>5} "
              f"{'  n/a' if pd.isna(r.fade_hit) else f'{r.fade_hit*100:4.0f}%'}")

    m = res.mean(numeric_only=True)
    print("\n  " + "-" * 86)
    print(f"  {'mean':>6} {int(m.n):>4} | {_fmt(m.rho_adp)} {_fmt(m.rho_sleeper)} "
          f"{_fmt(m.rho_ours)} {_fmt(m.rho_mkt)} {_fmt(m.rho_full)}   |"
          f"       {m.buy_hit*100:4.0f}% |       {m.fade_hit*100:4.0f}%")

    # pooled hit-rate across all test seasons (the honest headline)
    allbuy = (buys["beat_adp"] > 0).mean() if len(buys) else np.nan
    allfade = (fades["beat_adp"] < 0).mean() if len(fades) else np.nan
    print("\n  ===========================  VERDICT  ===========================")
    print(f"  pooled BUY  hit-rate: {allbuy*100:.1f}%  (n={len(buys)})   [50% = no edge]")
    print(f"  pooled FADE hit-rate: {allfade*100:.1f}%  (n={len(fades)})")
    print(f"  mean ρ:  ADP {m.rho_adp:.3f}  |  Sleeper {m.rho_sleeper:.3f}  |  "
          f"ours-only {m.rho_ours:.3f}  |  mkt-only {m.rho_mkt:.3f}  |  mkt+bias {m.rho_mb:.3f}  |  ours+mkt {m.rho_full:.3f}")
    print(f"  Do the 6 THESIS flags add over the market? mkt+bias − mkt-only = "
          f"{m.rho_mb - m.rho_mkt:+.3f}   (>0 means Year-2-QB/bounce-back/etc. help beyond ADP+Sleeper)")
    print(f"  Do ALL our features add over the market? ours+mkt − mkt-only = "
          f"{m.rho_full - m.rho_mkt:+.3f}")

    # 2025 live test, highlighted
    if 2025 in set(res["season"]):
        r25 = res[res.season == 2025].iloc[0]
        b25 = buys[buys.season == 2025] if len(buys) else pd.DataFrame()
        print("\n  --- 2025 LIVE TEST ---")
        print(f"  ρ: ADP {_fmt(r25.rho_adp)}  Sleeper {_fmt(r25.rho_sleeper)}  "
              f"ours {_fmt(r25.rho_ours)}  ours+mkt {_fmt(r25.rho_full)}")
        print(f"  buys {int(r25.n_buy)} (hit {r25.buy_hit*100:.0f}%)  "
              f"fades {int(r25.n_fade)} (hit {r25.fade_hit*100:.0f}%)")
        if len(b25):
            top = b25.sort_values("value", ascending=False).head(10)
            print("\n  top 2025 BUY calls (value = how far ahead of ADP we ranked them):")
            for _, p in top.iterrows():
                hit = "✓" if p["beat_adp"] > 0 else "✗"
                print(f"    {hit} {p['player']:22s} {p['position']:3s} "
                      f"pred {p['position']}{int(p['pred_posrk']):<2d} vs ADP {p['position']}{int(p['adp_posrk']):<2d}"
                      f"  -> finished {p['position']}{int(p['actual_posrk'])}")
    return res


if __name__ == "__main__":
    main()
