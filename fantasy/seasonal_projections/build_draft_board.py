"""Build the draft board (Model A x Model B) and evaluate the ADP edge thesis.

Combines the two models into a season projection, then into a *draft* value:

    projected_total = PPG_pred (Model A, per position)  x  games_pred (Model B)
    vor             = projected_total - replacement_total[position]

The board ranks by VOR (value over replacement), not raw points, because raw
points stack every QB at the top -- that is not how drafts work, and the market's
ADP is itself a VOR ranking, so VOR makes the our-vs-ADP comparison fair. Within
position we also compute our rank and the value/reach gap vs the market's ADP
positional rank (positive gap = we like a player more than the room does).

HOW THE BOARD IS EVALUATED (reframed 2026-06-08):
  The CANONICAL evaluation is `surprise_eval.py` -- the board's real job is to identify
  OVER/UNDERVALUED players vs ADP, not to win the overall ranking (the market already
  ranks the easy calls -- Chase top-5 -- perfectly). So we grade it CONDITIONAL ON ADP:
  the correlation between our deviation from ADP and the player's ACTUAL deviation from
  ADP, with mid-season-injury seasons (missed > 6 games) excluded since injuries are
  unpredictable noise. Pooled 2021-2025 that ADP-mispricing skill is ~+0.20 (placebo ~0,
  positive every season), concentrated on OPPORTUNITY/role moves, not injuries. That is
  the headline number; run `python surprise_eval.py` for the full scorecard.

  Two secondary checks remain in this file:
  1. Projection accuracy on the 2025 holdout (PPG MAE, games MAE, our season total vs
     Sleeper). Clean out-of-sample; answers "is the projection good," not "do we have edge."
  2. `eval_edge_thesis` -- the OVERALL-rank backtest. Kept for the record, but it is the
     WRONG lens: our VOR ranking loses to ADP on the overall order (dominated by easy
     calls). The mispricing skill above is where the real edge lives.

The board's display ranking is a three-way blend of our VOR rank, ADP, and Sleeper's own
season projection (see three_way_blend_test.py and BLEND_WEIGHTS, ~0.2/0.3/0.5); the
value/reach gap (adp_pos_rank - our_pos_rank) is the ADP-mispricing call the canonical
eval grades. Best standalone model per the bakeoff is LightGBM (PPG, injury features
dropped) x constant games -- see model_bakeoff.py / surprise_eval.py.

Writes draft_board_{board_season}.csv (BOARD_SEASON env var, default = latest season).
Run:  python fantasy/seasonal_projections/build_draft_board.py
"""
import os
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

sys.path.insert(0, str(Path(__file__).resolve().parent))   # sibling imports resolve as script or import
import rookie_features as rf

HERE       = Path(__file__).resolve().parent
# Use the newest season dataset on disk: the base build is season_dataset_2014_2025.csv;
# build_2026_board.py adds season_dataset_2014_2026.csv (same rows + the upcoming season).
_DATASETS  = sorted(HERE.glob("season_dataset_*.csv"))
DATA       = _DATASETS[-1] if _DATASETS else HERE / "season_dataset_2014_2025.csv"
MODELS_DIR = HERE / "models"
POSITIONS  = ["QB", "RB", "WR", "TE"]
# Board season is the latest season in the dataset by default; override for an
# annual refresh with e.g. BOARD_SEASON=2026 once that season's rows exist. A
# future season with no actuals / no ADP yet is handled gracefully (projections
# only). BACKTEST_SEASONS auto-derives to the ADP-era seasons before the board.
BOARD_SEASON = int(os.environ.get("BOARD_SEASON", 0)) or None
ADP_FIRST_SEASON = 2020   # Sleeper ADP only exists 2020+
SEED = 42

# 12-team VOR replacement baselines (rank of the last "startable" player per pos)
REPL = {"QB": 14, "RB": 30, "WR": 36, "TE": 14}
# a real fantasy draft is ~15 rounds x 12 teams; ignore the undrafted ADP tail
DRAFTED_MAX_RANK = 180
# Recommended draft order = a THREE-way blend of within-pool ranks:
#   blend = W_OUR*our_rank + W_ADP*adp_rank + W_SLEEPER*sleeper_rank
# Sleeper's own season projection is the strongest single signal; adding it lifts the
# board well past pure ADP. Weights confirmed via fine sweep + leave-one-season-out
# (three_way_blend_test.py): held-out 3-way beats the old our/ADP 2-way in 5/5 seasons,
# mean +0.063 Spearman rho (~2 SE), LOSO weights cluster at our 0.2 / adp 0.3 / slp 0.5.
# Our model keeps real (small) weight -- it's not redundant on top of the two market signals.
BLEND_WEIGHTS = {"our": 0.20, "adp": 0.30, "sleeper": 0.50}

EXCLUDE = {
    "player_id", "player", "norm_name", "team", "position", "season", "reconstructed",
    "target_ppg", "target_games", "sample_weight",
    "adp_half_ppr", "adp_overall_rank", "adp_pos_rank", "sleeper_pts_half_ppr",
}
B_FEATURES = ["age", "years_exp", "is_rookie", "missed_prior_season",
              "prior_games", "prior_games_missed", "prior_carries_pg", "prior_touches_pg",
              "prior_targets_pg", "prior_snap_share_pg", "draft_round", "draft_pick", "position"]


def load_models():
    """Per-position Model A + Model B + the (optional) rookie model.

    The rookie model is used for rookies' PPG inside the board blend; if its pkl
    is absent the board still works (rookies fall back to the veteran model).
    """
    a = {pos: joblib.load(MODELS_DIR / f"{pos.lower()}_ppg_model.pkl") for pos in POSITIONS}
    b = joblib.load(MODELS_DIR / "availability_model.pkl")
    rk_path = MODELS_DIR / "rookie_ppg_model.pkl"
    rookie = joblib.load(rk_path) if rk_path.exists() else None
    return a, b, rookie


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


def predict(df, model_a, model_b, rookie_model=None):
    """Attach ppg_pred, games_pred, projected_total, vor to a copy of df.

    If `rookie_model` is given, rookies' PPG comes from it instead of the veteran
    Model A (the validated board behavior -- improves the rookie slice of the blend;
    see rookie_blend_test.py). The standalone-vs-ADP edge backtest calls this WITHOUT
    a rookie model, so that documented thesis is unchanged.
    """
    d = df.copy()
    d["position"] = d["position"].astype(str)
    d["ppg_pred"] = np.nan
    for pos, art in model_a.items():
        m = d.position == pos
        if m.any():
            d.loc[m, "ppg_pred"] = np.clip(art["model"].predict(d.loc[m, art["feature_cols"]]), 0, None)
    if rookie_model is not None and "is_rookie" in d.columns:
        rk_mask = d["is_rookie"] == 1
        if rk_mask.any():
            d = rf.add_rookie_features(d)        # join combine cols (preserves vet ppg_pred already set)
            d.loc[rk_mask, "ppg_pred"] = np.clip(
                rookie_model["model"].predict(d.loc[rk_mask, rookie_model["feature_cols"]]), 0, None)
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
    """Rank a single-season prediction frame by VOR, blend with ADP, compute the gap.

    Two rankings are produced:
      our_*       -- our independent VOR ranking (used for the value/reach view)
      blend_*     -- the recommended draft order: a three-way blend of our VOR rank,
                     ADP rank, and Sleeper-projection rank (BLEND_WEIGHTS), among
                     players the market drafts. Beats pure ADP and the old 2-way
                     (three_way_blend_test.py). NaN where ADP is absent.
    """
    b = d.copy()
    b["our_overall_rank"] = b["vor"].rank(ascending=False, method="min")
    b["our_pos_rank"] = b.groupby("position")["vor"].rank(ascending=False, method="min")
    # value/reach gap: positive = we rank higher (better) than the market's positional ADP
    b["value_gap"] = b["adp_pos_rank"] - b["our_pos_rank"]

    # blended ranking within the drafted pool (lower blend_score = earlier pick).
    # Rank within ADP top-DRAFTED_MAX_RANK only -- the SAME population three_way_blend_test.py
    # validated the weights on. Players beyond the drafted pool (or with no ADP) get NaN
    # blend_rank, as a real draft wouldn't reach them.
    b["blend_score"] = np.nan
    b["blend_rank"] = np.nan
    b["blend_pos_rank"] = np.nan
    has = b["adp_overall_rank"].le(DRAFTED_MAX_RANK)
    if has.any():
        sub = b[has]
        our_r = sub["vor"].rank(ascending=False, method="average")
        adp_r = sub["adp_overall_rank"].rank(ascending=True, method="average")
        # Sleeper's season projection (higher = better). Missing it -> defer that term
        # to ADP so the player still ranks (Sleeper coverage on the drafted pool is ~99%).
        slp_r = sub["sleeper_pts_half_ppr"].rank(ascending=False, method="average").fillna(adp_r) \
            if "sleeper_pts_half_ppr" in sub.columns else adp_r
        score = (BLEND_WEIGHTS["our"] * our_r + BLEND_WEIGHTS["adp"] * adp_r
                 + BLEND_WEIGHTS["sleeper"] * slp_r)
        b.loc[has, "blend_score"] = score
        b.loc[has, "blend_rank"] = score.rank(ascending=True, method="min")
        b.loc[has, "blend_pos_rank"] = score.groupby(sub["position"]).rank(ascending=True, method="min")
    return b.sort_values("vor", ascending=False)


def fmt(x, n=1):
    return "" if pd.isna(x) else f"{x:.{n}f}"


def build_board(df, model_a, model_b, board_season, rookie_model=None):
    d = df[df.season == board_season].copy()
    if d.empty:
        print(f"\n(no rows for season {board_season} in the dataset; rebuild it first)")
        return d
    d = predict(d, model_a, model_b, rookie_model)
    board = make_board(d)
    has_adp = board.adp_overall_rank.notna().any()

    cols = ["player", "position", "team", "ppg_pred", "games_pred", "projected_total", "vor",
            "our_overall_rank", "our_pos_rank", "blend_rank", "blend_pos_rank",
            "adp_pos_rank", "adp_overall_rank", "value_gap", "sleeper_pts_half_ppr",
            "age", "years_exp", "target_ppg", "target_games"]
    out_path = HERE / f"draft_board_{board_season}.csv"
    board[cols].to_csv(out_path, index=False)

    if has_adp:
        # headline = the recommended draft order (our/ADP/Sleeper blend; beats pure ADP)
        rec = board[board.blend_rank.notna()].sort_values("blend_rank")
        _w = BLEND_WEIGHTS
        print(f"\n=== {board_season} draft board (top 20, blend: our {_w['our']:.0%} / "
              f"ADP {_w['adp']:.0%} / Sleeper {_w['sleeper']:.0%}) ===")
        print(f"{'rk':>3} {'player':22} {'pos':3} {'blend':>5} {'ourVOR':>6} {'ADP':>5}")
        for _, r in rec.head(20).iterrows():
            print(f"{int(r.blend_rank):>3} {str(r.player)[:22]:22} {r.position:3} "
                  f"{r.position}{int(r.blend_pos_rank):<3} {fmt(r.vor):>6} {fmt(r.adp_overall_rank,0):>5}")
    else:
        print(f"\n=== {board_season} draft board (top 20 overall, by VOR) ===")
        print(f"{'rk':>3} {'player':22} {'pos':3} {'VOR':>6} {'total':>6} {'ppg':>5} {'gms':>5}")
        for _, r in board.head(20).iterrows():
            print(f"{int(r.our_overall_rank):>3} {str(r.player)[:22]:22} {r.position:3} "
                  f"{fmt(r.vor):>6} {fmt(r.projected_total):>6} {fmt(r.ppg_pred):>5} {fmt(r.games_pred):>5}")

    if not has_adp:
        print(f"\n(no ADP for {board_season} yet -- projections only; values/reaches skipped "
              f"until Sleeper ADP lands ~August)")
        return board

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


def eval_accuracy(board, board_season):
    """PPG / games MAE vs actuals, and our season total vs Sleeper's projection.

    Skipped for a future board season whose games have not been played yet.
    """
    a = board[board.target_ppg.notna()]
    if a.empty:
        print(f"\n=== {board_season} projection accuracy ===")
        print(f"  (no actuals for {board_season} yet -- skipped until the season is played)")
        return
    print(f"\n=== {board_season} projection accuracy (holdout) ===")
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


def eval_edge_thesis(df, a_params, b_params, feats, backtest_seasons):
    """Walk-forward backtest: does our VOR ranking beat ADP at predicting finish?

    Retrains both models on seasons < N for each backtest year N, so the
    evaluation is genuinely out-of-sample (the production pkls would leak).
    Both rankings are judged against actual VOR (actual draft value), which is
    what ADP optimizes -- the fair target.
    """
    if not backtest_seasons:
        print("\n=== ADP edge thesis ===\n  (no completed ADP-era seasons to backtest)")
        return
    print(f"\n=== ADP edge thesis (walk-forward backtest {backtest_seasons[0]}-{backtest_seasons[-1]}) ===")
    print("  drafted pool only (ADP top {}); ranking quality vs actual VOR (Spearman rho):".format(DRAFTED_MAX_RANK))
    print(f"  {'season':>6} {'n':>4} {'ours':>7} {'ADP':>7} {'edge':>7}")
    rows, allpop = [], []
    for yr in backtest_seasons:
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
    if not allpop:
        return
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
    board_season = BOARD_SEASON or int(df.season.max())   # default = latest in dataset
    # backtest the ADP-era seasons that are fully played (strictly before the board)
    backtest_seasons = sorted(s for s in df.season.unique()
                              if ADP_FIRST_SEASON <= s < board_season)

    model_a, model_b, rookie_model = load_models()
    board = build_board(df, model_a, model_b, board_season, rookie_model)
    if board.empty:
        return
    eval_accuracy(board, board_season)
    a_params, b_params = _tuned_params()
    feats = [c for c in df.columns if c not in EXCLUDE]
    eval_edge_thesis(df, a_params, b_params, feats, backtest_seasons)
    print(f"\nWrote draft_board_{board_season}.csv to {HERE}")


if __name__ == "__main__":
    main()
