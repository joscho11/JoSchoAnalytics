"""Build the seasonal VALUE BOARD: our model's calls vs the draft room (ADP).

This is the shippable, honest, OURS framing (decided 2026-06-08):
  - Headline = OUR independent projection (production Model A = LightGBM, no injury feats)
    x a constant games estimate, ranked within position, compared to the market's ADP.
  - value = adp_pos_rank - our_pos_rank   (+ = we rank them above the room = BUY/undervalued)
  - Confidence tiers from the size of the disagreement; FADES are gated to players with a
    real decline catalyst (aging or declining production) and never young (<=2 yrs) -- the
    only fades that beat a coin flip (see fade_deep_dive.py).
  - Sleeper's own projection is included PURELY as a transparent comparison column (and a
    "does Sleeper agree" flag). It is NOT our edge and not part of the call.

Honest scope: our calls beat the casual ADP line (~68% on confident buys, season-stable);
sharper public projections like Sleeper's are still better. A draft cross-check, not alpha.

Writes value_board_{season}.csv for each available season (2025 completed, 2026 upcoming).
Run:  python fantasy/seasonal_projections/build_value_board.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

sys.path.insert(0, str(Path(__file__).resolve().parent))   # local imports regardless of CWD
from incoming_competition import add_incoming_competition

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
MODELS_DIR = HERE / "models"
POSITIONS = ["QB", "RB", "WR", "TE"]
DRAFTED_MAX = 180
# season -> dataset that contains it (2026 lives in the appended dataset)
SEASON_DATA = {2025: HERE / "season_dataset_2014_2025.csv",
               2026: HERE / "season_dataset_2014_2026.csv"}


def const_games(df):
    """Average games a drafted player actually plays (historical pool) -- the games multiplier.
    Computed from whatever dataset is being built (every season dataset contains 2014-2024),
    so it works even if only the appended future-season dataset is present."""
    pool = df[(df.adp_overall_rank <= DRAFTED_MAX) & df.target_games.notna() & (df.season < 2025)]
    if pool.empty:                                  # degenerate fallback (shouldn't happen)
        return 14.5
    return float(pool["target_games"].mean())


def call_and_tier(value, age_cliff, declining, young):
    """BUY tiers by gap size; FADE only with a decline catalyst and never young."""
    gated_fade = (age_cliff or declining) and not young
    if value >= 8:
        return "BUY", "HIGH", ""
    if value >= 5:
        return "BUY", "MEDIUM", ""
    if value <= -8 and gated_fade:
        return "FADE", "HIGH", "age cliff" if age_cliff else "declining"
    if value <= -5 and gated_fade:
        return "FADE", "MEDIUM", "age cliff" if age_cliff else "declining"
    return "", "", ""


def build_one(season, df, gconst):
    pool = df[(df.season == season) & (df.adp_overall_rank <= DRAFTED_MAX) & df.adp_pos_rank.notna()].copy()

    pool["ppg_pred"] = np.nan
    for pos in POSITIONS:
        art = joblib.load(MODELS_DIR / f"{pos.lower()}_ppg_model.pkl")
        missing = [c for c in art["feature_cols"] if c not in pool.columns]
        assert not missing, (f"{pos} model expects features absent from the dataset: {missing}. "
                             "Retrain Model A (train_model_a.py) or rebuild the dataset so they match.")
        m = pool.position == pos
        if m.any():
            pool.loc[m, "ppg_pred"] = np.clip(art["model"].predict(pool.loc[m, art["feature_cols"]]), 0, None)

    # ROOKIES have no prior NFL stats, so Model A can't really project them. Override their
    # projection with the dedicated rookie model (draft capital + combine measurables + landing
    # spot) when it's available -- the right signal for a player with no NFL history.
    rk_path = MODELS_DIR / "rookie_ppg_model.pkl"
    if rk_path.exists() and "is_rookie" in pool.columns and (pool["is_rookie"] == 1).any():
        from rookie_features import add_rookie_features
        rk = joblib.load(rk_path)
        rmask = pool["is_rookie"] == 1
        rfeat = add_rookie_features(pool[rmask])
        pool.loc[rmask, "ppg_pred"] = np.clip(rk["model"].predict(rfeat[rk["feature_cols"]]), 0, None)
        pool["is_rookie_proj"] = rmask                # mark which projections came from the rookie model

    pool["our_proj"] = pool["ppg_pred"] * gconst

    g = pool.groupby("position")
    pool["our_rank"] = g["our_proj"].rank(ascending=False, method="min")
    pool["adp_rank"] = g["adp_pos_rank"].rank(method="min")          # re-rank within the pool
    pool["value"] = (pool["adp_rank"] - pool["our_rank"])
    has_slp = "sleeper_pts_half_ppr" in pool.columns and pool["sleeper_pts_half_ppr"].notna().any()
    if has_slp:
        pool["sleeper_rank"] = g["sleeper_pts_half_ppr"].rank(ascending=False, method="min")

    # gating inputs. Defaults are deliberately asymmetric so a missing value never *creates*
    # a fade: unknown age -> 26 (assume prime, no age-cliff), unknown experience -> veteran
    # (so the "not young" guard doesn't shield a real vet from a fade by accident).
    age = pool["age"].fillna(26)
    pos = pool["position"]
    pool["age_cliff"] = (((pos == "RB") & (age >= 27)) | (pos.isin(["WR", "TE"]) & (age >= 29))
                         | ((pos == "QB") & (age >= 34)))
    pool["declining"] = pool["ppg_trend"].fillna(0) < -1
    pool["young"] = pool["years_exp"].fillna(99) <= 2

    calls = pool.apply(lambda r: call_and_tier(r["value"], r["age_cliff"], r["declining"], r["young"]), axis=1)
    pool["call"], pool["tier"], pool["reason"] = zip(*calls)

    # INCOMING-COMPETITION guard: our prior-stats model can't see touches ARRIVING (a rookie, a
    # signing, a returning starter, a newly-crowded backfield). Suppress BUYs on incumbents whose
    # room just got more competition — the market already prices it; we'd otherwise flag a false buy.
    comp_full = add_incoming_competition(df[df.season == season])
    # align on the shared original index; assert full coverage so a future pool-rebuild that
    # resets the index can't silently drop every contested flag (reindex -> all-NaN -> "").
    assert pool.index.isin(comp_full.index).all(), \
        "incoming-competition index misalignment: pool rows missing from comp (did pool get reindexed?)"
    comp = comp_full.reindex(pool.index).fillna("")
    pool["contested"] = ""                                  # only set for buys we actually hold off on
    _supp = (pool["call"] == "BUY") & (comp != "")
    pool.loc[_supp, "contested"] = comp[_supp]
    pool.loc[_supp, ["call", "tier"]] = ["", ""]

    # RETURNING-FROM-INJURY guard: when the PLAYER'S OWN prior season was injury-shortened, his
    # depressed prior-year stats make the projection unreliable in BOTH directions (walk-forward:
    # post-injury WR MAE ~2.8 vs ~1.3 healthy, and NO fixable systematic bias — a games-weighted
    # baseline / injury flag added nothing OOS). The model can't tell "healthy bounce-back" from
    # "aging/injury-prone fade", so we don't issue a confident BUY/FADE off it — we flag it.
    # (Distinct from the contested guard above, which is about NEW teammates arriving.)
    missed_prior = pool["missed_prior_season"].fillna(0) if "missed_prior_season" in pool.columns else 0
    ret_inj = ((pool["prior_games_missed"].fillna(0) >= 6) & (pool["prior_games"].fillna(0) >= 3)
               & (missed_prior != 1))
    pool["injury_return"] = ""
    _inj = ret_inj & pool["call"].isin(["BUY", "FADE"])
    pool.loc[_inj, "injury_return"] = "returning from injury"
    pool.loc[_inj, ["call", "tier", "reason"]] = ["", "", ""]

    # does Sleeper lean the same way vs ADP? (transparent comparison only)
    if has_slp:
        slp_dev = pool["adp_rank"] - pool["sleeper_rank"]
        pool["sleeper_agrees"] = np.where(pool["value"] > 0, slp_dev > 0,
                                  np.where(pool["value"] < 0, slp_dev < 0, np.nan))

    # actuals: only treat the season as graded when MOST of the pool has a real result, so a
    # half-played (in-progress) season isn't ranked as if it were complete.
    if pool["target_ppg"].notna().mean() >= 0.5:
        pool["actual_total"] = pool["target_ppg"] * pool["target_games"]
        # re-group (the groupby above predates this column) so actual_rank ranks the new column
        pool["actual_rank"] = pool.groupby("position")["actual_total"].rank(ascending=False, method="min")
        # missed > 6 games -> the finish is injury-driven, not a real test of the call. Flag it so the
        # board shows "injured" instead of grading it a hit/miss (consistent with surprise_eval, which
        # excludes these seasons because injuries are unpredictable).
        pool["injured"] = pool["target_games"] < 11

    keep = ["player", "position", "team", "our_proj", "our_rank", "adp_rank", "value",
            "call", "tier", "reason", "contested", "injury_return", "years_exp", "age"]
    for c in ["sleeper_rank", "sleeper_agrees", "actual_rank", "actual_total", "injured"]:
        if c in pool.columns:
            keep.append(c)
    out = pool[keep].sort_values(["position", "adp_rank"]).reset_index(drop=True)
    out.to_csv(HERE / f"value_board_{season}.csv", index=False)
    nb = (out.call == "BUY").sum(); nf = (out.call == "FADE").sum(); nc = (out.contested != "").sum()
    ni = (out.injury_return != "").sum()
    print(f"  {season}: {len(out)} players | {nb} BUY, {nf} FADE, {nc} contested, {ni} injury-flagged "
          f"(calls suppressed) | sleeper {'incl' if has_slp else 'MISSING'} | "
          f"actuals {'yes' if 'actual_rank' in out.columns else 'no'}")
    return out


def main():
    for season, path in SEASON_DATA.items():
        if path.exists():
            df = pd.read_csv(path)
            build_one(season, df, const_games(df))
    print("\ndone")


if __name__ == "__main__":
    main()
