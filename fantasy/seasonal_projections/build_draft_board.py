"""Build the draft board (Model A x Model B) and evaluate the ADP edge thesis.

Combines the two models into a season projection, then into a *draft* value:

    projected_total = PPG_pred (Model A, per position)  x  games_pred (Model B)
    vor             = projected_total - replacement_total[position]

The board ranks by VOR (value over replacement), not raw points, because raw
points stack every QB at the top -- that is not how drafts work, and the market's
ADP is itself a VOR ranking, so VOR makes the our-vs-ADP comparison fair. Within
position we also compute our rank and the value/reach gap vs the market's ADP
positional rank (positive gap = we like a player more than the room does).

Two evaluations, both honest:
  1. Projection accuracy on the 2025 holdout (PPG MAE, games MAE, and our season
     total vs Sleeper's own projection as a benchmark). 2025 is unseen by the
     production models, so this is clean out-of-sample.
  2. The edge thesis (backtest 2020-2024). This RETRAINS both models walk-forward
     (train on seasons < N, predict N) so it is genuinely out-of-sample -- the
     production pkls were trained through 2024 and would leak here. Question: does
     ranking by our VOR correlate with actual draft value better than ADP does?

Writes draft_board_2025.csv.
Run:  python fantasy/seasonal_projections/build_draft_board.py
"""
import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from scipy.stats import spearmanr
from catboost import CatBoostRegressor

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE       = Path(__file__).resolve().parent
DATA       = HERE / "season_dataset_2014_2025.csv"
MODELS_DIR = HERE / "models"
POSITIONS  = ["QB", "RB", "WR", "TE"]
BOARD_SEASON   = 2025
BACKTEST_SEASONS = [2020, 2021, 2022, 2023, 2024]
SEED = 42

# 12-team VOR replacement baselines (rank of the last "startable" player per pos)
REPL = {"QB": 14, "RB": 30, "WR": 36, "TE": 14}
# a real fantasy draft is ~15 rounds x 12 teams; ignore the undrafted ADP tail
DRAFTED_MAX_RANK = 180

EXCLUDE = {
    "player_id", "player", "norm_name", "team", "position", "season", "reconstructed",
    "target_ppg", "target_games", "sample_weight",
    "adp_half_ppr", "adp_overall_rank", "adp_pos_rank", "sleeper_pts_half_ppr",
}
B_FEATURES = ["age", "years_exp", "is_rookie", "missed_prior_season",
              "prior_games", "prior_games_missed", "prior_carries_pg", "prior_touches_pg",
              "prior_targets_pg", "prior_snap_share_pg", "draft_round", "draft_pick", "position"]


def load_models():
    a = {pos: joblib.load(MODELS_DIR / f"{pos.lower()}_ppg_model.pkl") for pos in POSITIONS}
    b = joblib.load(MODELS_DIR / "availability_model.pkl")
    return a, b


def _tuned_params():
    """Per-position Model A params + pooled Model B params, from the saved tunings."""
    a = json.loads((HERE / "model_a_compare_results.json").read_text())
    b = json.loads((MODELS_DIR / "model_b_metrics.json").read_text())["best_params"]
    a_params = {pos: a.get(pos, {}).get("algos", {}).get("catboost", {}).get("best_params", {})
                for pos in POSITIONS}
    return a_params, b


def train_fold(train_df, a_params, b_params, feats):
    """Train per-position Model A (games-weighted) + pooled Model B on train_df only."""
    a = {}
    for pos in POSITIONS:
        tr = train_df[(train_df.position == pos) & train_df.target_ppg.notna()]
        m = CatBoostRegressor(iterations=500, loss_function="MAE", random_seed=SEED,
                              verbose=0, allow_writing_files=False, **a_params[pos])
        m.fit(tr[feats], tr.target_ppg, sample_weight=tr.sample_weight)
        a[pos] = {"model": m, "feature_cols": feats}
    trb = train_df.copy(); trb["position"] = trb.position.astype(str)
    mb = CatBoostRegressor(iterations=500, loss_function="MAE", random_seed=SEED,
                           verbose=0, allow_writing_files=False, **b_params)
    mb.fit(trb[B_FEATURES], trb.target_games, cat_features=["position"])
    return a, {"model": mb, "feature_cols": B_FEATURES}


def predict(df, model_a, model_b):
    """Attach ppg_pred, games_pred, projected_total, vor to a copy of df."""
    d = df.copy()
    d["position"] = d["position"].astype(str)
    d["ppg_pred"] = np.nan
    for pos, art in model_a.items():
        m = d.position == pos
        if m.any():
            d.loc[m, "ppg_pred"] = np.clip(art["model"].predict(d.loc[m, art["feature_cols"]]), 0, None)
    d["games_pred"] = np.clip(model_b["model"].predict(d[model_b["feature_cols"]]), 0, 17)
    d["projected_total"] = d["ppg_pred"] * d["games_pred"]
    d["vor"] = _vor(d, "projected_total")
    return d


def _vor(d, total_col):
    """Value over replacement: total minus the Nth-ranked total at that position."""
    out = pd.Series(np.nan, index=d.index)
    for pos, n in REPL.items():
        s = d.loc[d.position == pos, total_col].dropna().sort_values(ascending=False)
        repl = s.iloc[n - 1] if len(s) >= n else (s.iloc[-1] if len(s) else 0.0)
        out.loc[d.position == pos] = d.loc[d.position == pos, total_col] - repl
    return out


def make_board(d):
    """Rank a single-season prediction frame by VOR and compute the ADP gap."""
    b = d.copy()
    b["our_overall_rank"] = b["vor"].rank(ascending=False, method="min")
    b["our_pos_rank"] = b.groupby("position")["vor"].rank(ascending=False, method="min")
    # value/reach gap: positive = we rank higher (better) than the market's positional ADP
    b["value_gap"] = b["adp_pos_rank"] - b["our_pos_rank"]
    return b.sort_values("vor", ascending=False)


def fmt(x, n=1):
    return "" if pd.isna(x) else f"{x:.{n}f}"


def build_2025_board(df, model_a, model_b):
    d = df[df.season == BOARD_SEASON].copy()
    d = predict(d, model_a, model_b)
    board = make_board(d)

    cols = ["player", "position", "team", "ppg_pred", "games_pred", "projected_total", "vor",
            "our_overall_rank", "our_pos_rank", "adp_pos_rank", "adp_overall_rank",
            "value_gap", "sleeper_pts_half_ppr", "age", "years_exp",
            "target_ppg", "target_games"]
    board[cols].to_csv(HERE / "draft_board_2025.csv", index=False)

    print(f"\n=== 2025 draft board (top 20 overall, by VOR) ===")
    print(f"{'rk':>3} {'player':22} {'pos':3} {'VOR':>6} {'total':>6} {'ppg':>5} {'gms':>5} {'ADP':>5}")
    for _, r in board.head(20).iterrows():
        print(f"{int(r.our_overall_rank):>3} {str(r.player)[:22]:22} {r.position:3} "
              f"{fmt(r.vor):>6} {fmt(r.projected_total):>6} {fmt(r.ppg_pred):>5} "
              f"{fmt(r.games_pred):>5} {fmt(r.adp_overall_rank,0):>5}")

    # values / reaches among players the market actually drafts (top ~180 ADP)
    drafted = board[board.adp_overall_rank.le(DRAFTED_MAX_RANK)].copy()
    print(f"\n=== Biggest VALUES (we rank >= 6 pos-spots above ADP, drafted pool) ===")
    val = drafted[drafted.value_gap >= 6].sort_values("value_gap", ascending=False).head(10)
    for _, r in val.iterrows():
        print(f"  {str(r.player)[:22]:22} {r.position:3} our {r.position}{int(r.our_pos_rank):<3} "
              f"vs ADP {r.position}{int(r.adp_pos_rank):<3}  (gap +{int(r.value_gap)})")
    print(f"\n=== Biggest REACHES (market drafts >= 6 pos-spots above us, drafted pool) ===")
    rch = drafted[drafted.value_gap <= -6].sort_values("value_gap").head(10)
    for _, r in rch.iterrows():
        print(f"  {str(r.player)[:22]:22} {r.position:3} our {r.position}{int(r.our_pos_rank):<3} "
              f"vs ADP {r.position}{int(r.adp_pos_rank):<3}  (gap {int(r.value_gap)})")
    return board


def eval_2025_accuracy(board):
    """PPG / games MAE vs actuals, and our season total vs Sleeper's projection."""
    print(f"\n=== 2025 projection accuracy (holdout) ===")
    a = board[board.target_ppg.notna()]
    ppg_mae = float(np.mean(np.abs(a.ppg_pred - a.target_ppg)))
    g = board[board.target_games.notna()]
    gms_mae = float(np.mean(np.abs(g.games_pred - g.target_games)))
    print(f"  PPG   MAE = {ppg_mae:.3f}  (n={len(a)})")
    print(f"  games MAE = {gms_mae:.3f}  (n={len(g)})")

    # season-total projection: ours vs Sleeper's, both judged against actual total
    s = board[board.target_ppg.notna() & board.sleeper_pts_half_ppr.notna()].copy()
    if len(s):
        s["actual_total"] = s.target_ppg * s.target_games
        ours_mae    = float(np.mean(np.abs(s.projected_total - s.actual_total)))
        sleeper_mae = float(np.mean(np.abs(s.sleeper_pts_half_ppr - s.actual_total)))
        print(f"  season-total MAE  ours={ours_mae:.1f}  vs Sleeper proj={sleeper_mae:.1f}  (n={len(s)})")


def eval_edge_thesis(df, a_params, b_params, feats):
    """Walk-forward backtest: does our VOR ranking beat ADP at predicting finish?

    Retrains both models on seasons < N for each backtest year N, so the
    evaluation is genuinely out-of-sample (the production pkls would leak).
    Both rankings are judged against actual VOR (actual draft value), which is
    what ADP optimizes -- the fair target.
    """
    print(f"\n=== ADP edge thesis (walk-forward backtest {BACKTEST_SEASONS[0]}-{BACKTEST_SEASONS[-1]}) ===")
    print("  drafted pool only (ADP top {}); ranking quality vs actual VOR (Spearman rho):".format(DRAFTED_MAX_RANK))
    print(f"  {'season':>6} {'n':>4} {'ours':>7} {'ADP':>7} {'edge':>7}")
    rows, allpop = [], []
    for yr in BACKTEST_SEASONS:
        ma, mb = train_fold(df[df.season < yr], a_params, b_params, feats)
        d = predict(df[df.season == yr], ma, mb)
        pop = d[d.adp_overall_rank.le(DRAFTED_MAX_RANK) & d.target_ppg.notna()].copy()
        if len(pop) < 30:
            continue
        pop["actual_total"] = pop.target_ppg * pop.target_games
        pop["actual_vor"]   = _vor(pop, "actual_total")
        # ADP: lower rank number is better, so negate for a "higher=better" correlation
        rho_ours = float(spearmanr(pop.vor, pop.actual_vor).statistic)
        rho_adp  = float(spearmanr(-pop.adp_overall_rank, pop.actual_vor).statistic)
        rows.append((yr, len(pop), rho_ours, rho_adp))
        pop = make_board(pop)
        allpop.append(pop)
        print(f"  {yr:>6} {len(pop):>4} {rho_ours:>7.3f} {rho_adp:>7.3f} {rho_ours - rho_adp:>+7.3f}")
    if rows:
        mo = np.mean([r[2] for r in rows]); ma_ = np.mean([r[3] for r in rows])
        print(f"  {'mean':>6} {'':>4} {mo:>7.3f} {ma_:>7.3f} {mo - ma_:>+7.3f}")
        verdict = ("we add ranking signal over ADP" if mo > ma_ + 0.01
                   else "ADP is at least as good as us" if ma_ > mo + 0.01
                   else "we roughly match ADP (within noise)")
        print(f"  -> {verdict}")

    # value-vs-reach: do players we boost out-finish players we fade?
    print(f"\n  value-vs-reach (drafted pool): mean actual season points by our gap bucket")
    allpop = pd.concat(allpop, ignore_index=True)
    for name, grp in [("VALUE (gap>=+6)", allpop[allpop.value_gap >= 6]),
                      ("neutral (|gap|<6)", allpop[allpop.value_gap.abs() < 6]),
                      ("REACH (gap<=-6)", allpop[allpop.value_gap <= -6])]:
        if len(grp):
            print(f"    {name:20} n={len(grp):>4}  actual pts mean={grp.actual_total.mean():>6.1f}  "
                  f"median={grp.actual_total.median():>6.1f}")


def main():
    df = pd.read_csv(DATA)
    model_a, model_b = load_models()
    board = build_2025_board(df, model_a, model_b)
    eval_2025_accuracy(board)
    a_params, b_params = _tuned_params()
    feats = [c for c in df.columns if c not in EXCLUDE]
    eval_edge_thesis(df, a_params, b_params, feats)
    print(f"\nWrote draft_board_2025.csv to {HERE}")


if __name__ == "__main__":
    main()
