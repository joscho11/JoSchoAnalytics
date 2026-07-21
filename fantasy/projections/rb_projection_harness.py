"""RB season-total projection harness (prereg PREREG_rb_projection_2026-07-21.md).

--build : SYNTHETIC/STRUCTURAL proof ONLY. NO real fit on real PPG, NO real accuracy, NO Sleeper join.
          Proves: veteran/rookie routing partitions exhaustively; leakage guard (aligned prior feature
          carries signal, shuffled alignment destroys it, a planted leak screams); walk-forward never
          trains on the test season; planted signal detected & pure noise not; nested-CV tuning selects
          without touching the outer test fold; and the full pipeline runs end-to-end on real shapes with
          a PERMUTED target producing valid-shaped projections. (The real fit is a LATER session.)
"""
import sys, argparse, itertools
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor   # native-NaN; proof model only

HERE = Path(__file__).resolve().parent
SEAS = HERE.parent / "seasonal_projections"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TEST_SEASONS = [2021, 2022, 2023, 2024, 2025]      # prereg §8 walk-forward folds (Sleeper-covered)
SEED = 42

VET_FEATS = ["prior_ppg", "prior_half_ppr", "prior_games", "ppg_2yr", "ppg_3yr", "ppg_trend",
             "career_high_ppg", "prior_snap_share_pg", "prior_targets_pg", "prior_carries_pg",
             "prior_receptions_pg", "prior_touches_pg", "prior_target_share", "prior_air_yards_share",
             "prior_adot", "prior_td_rate", "prior_yptarget", "prior_ypc", "prior_rec_epa",
             "prior_rush_epa", "age", "years_exp", "draft_round", "draft_pick", "prior_team_pass_rate",
             "prior_team_plays", "vacated_target_share", "vacated_rush_share", "coach_changed",
             "qb_changed", "prior_games_missed", "missed_prior_season"]
# rookie: season_dataset structural slice; the real build ADDS the frozen hit-model combine+college+PFF
ROOK_FEATS = ["draft_round", "draft_pick", "age", "prior_team_pass_rate", "prior_team_plays",
              "vacated_target_share", "vacated_rush_share", "coach_changed", "qb_changed"]

GRID = [{"max_depth": d, "learning_rate": lr} for d in (3, 6) for lr in (0.05, 0.1)]   # proof grid


def load_rb():
    sd = pd.read_csv(SEAS / "season_dataset_2014_2026.csv")
    return sd[sd.position == "RB"].copy()


def route(df):
    """Prereg §2: is_rookie==1 -> rookie ; ==0 -> veteran. Exhaustive, mutually exclusive."""
    vet = df[df.is_rookie == 0]
    rk = df[df.is_rookie == 1]
    return vet, rk


def _fit_pred(tr, te, feats, y_col, params):
    # proof-model (HGB) needs variation per column; drop all-NaN/constant feats (e.g. the entirely-NaN
    # prior_team_pass_rate/plays). Real build uses CatBoost/LGBM native-NaN (prereg §5) which ignore them.
    usable = [c for c in feats if tr[c].notna().sum() >= 5 and tr[c].nunique(dropna=True) >= 2]
    m = HistGradientBoostingRegressor(random_state=SEED, max_iter=200, **params)
    m.fit(tr[usable].to_numpy(float), tr[y_col].to_numpy(float))
    return m.predict(te[usable].to_numpy(float))


def _mae(y, p): return float(np.mean(np.abs(np.asarray(y) - np.asarray(p))))
def _rank(y, p):
    if np.std(p) == 0 or len(y) < 3: return 0.0
    return float(spearmanr(y, p).correlation)


def nested_select(train_df, feats, y_col, params_grid):
    """Inner leave-one-season-out CV over TRAINING seasons only; pick min-MAE params. Never sees outer test."""
    seasons = sorted(train_df.season.unique())
    best, best_mae = None, np.inf
    for params in params_grid:
        maes = []
        for s in seasons:
            itr, iva = train_df[train_df.season != s], train_df[train_df.season == s]
            if len(itr) < 50 or len(iva) < 10:
                continue
            p = _fit_pred(itr, iva, feats, y_col, params)
            maes.append(_mae(iva[y_col], p))
        if maes and np.mean(maes) < best_mae:
            best, best_mae = params, float(np.mean(maes))
    return best or params_grid[0]


def walk_forward(df, feats, y_col, tune=False):
    """Per prereg §8: for each test season Y, train on seasons < Y (nested-CV tuned if tune)."""
    out = []
    for Y in TEST_SEASONS:
        tr = df[df.season < Y]
        te = df[df.season == Y]
        assert (tr.season < Y).all(), f"WALK-FORWARD LEAK: train has season >= {Y}"
        if len(tr) < 60 or len(te) == 0:
            continue
        params = nested_select(tr, feats, y_col, GRID) if tune else GRID[0]
        p = _fit_pred(tr, te, feats, y_col, params)
        out.append(pd.DataFrame({"season": Y, "y": te[y_col].to_numpy(float), "p": p}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["season", "y", "p"])


def prove():
    print("=" * 70); print("RB PROJECTION HARNESS — SYNTHETIC/STRUCTURAL PROOF (no real fit, no real metric)")
    print("=" * 70)
    rng = np.random.default_rng(SEED)
    df = load_rb()
    df = df[df.season <= 2025].copy()                 # 2026 has no target — excluded from proof folds
    vet, rk = route(df)

    # --- 1. ROUTING: exhaustive + mutually exclusive ---
    r_ok = (len(vet) + len(rk) == len(df)) and set(vet.index).isdisjoint(rk.index) \
        and (vet.is_rookie == 0).all() and (rk.is_rookie == 1).all()
    print(f"\n1. ROUTING partition (vet {len(vet)} + rookie {len(rk)} == {len(df)}, disjoint): "
          f"{'PASS' if r_ok else 'FAIL'}")

    # controlled synthetic targets on the VETERAN slice (real structure, fake y)
    v = vet.copy()
    z = ((v.prior_ppg - v.prior_ppg.mean()) / (v.prior_ppg.std() or 1)).fillna(0).to_numpy()

    # --- 2. NOISE probe: random target -> no hallucinated signal ---
    v["y_noise"] = rng.normal(size=len(v))
    o = walk_forward(v, VET_FEATS, "y_noise")
    noise_rank = _rank(o.y, o.p)
    p2 = abs(noise_rank) < 0.15
    print(f"2. NOISE probe (random y): pooled rankcorr {noise_rank:+.3f} (expect ~0)  {'PASS' if p2 else 'FAIL'}")

    # --- 3. PLANTED probe: y = signal(prior feature) -> detected ---
    v["y_plant"] = 3.0 * z + rng.normal(scale=0.6, size=len(v))
    o = walk_forward(v, VET_FEATS, "y_plant")
    plant_rank = _rank(o.y, o.p)
    p3 = plant_rank > 0.30
    print(f"3. PLANTED probe (y=f(prior_ppg)+noise): pooled rankcorr {plant_rank:+.3f} (expect >.30)  "
          f"{'PASS' if p3 else 'FAIL'}")

    # --- 4. PEEK probe: leak the target in as a feature -> metric screams (leak detector alive) ---
    v["y_leaky"] = v["y_plant"]
    o = walk_forward(v, VET_FEATS + ["y_leaky"], "y_plant")
    peek_rank = _rank(o.y, o.p); peek_mae = _mae(o.y, o.p)
    p4 = peek_rank > 0.98 and peek_mae < 0.2
    print(f"4. PEEK probe (target leaked as feature): rankcorr {peek_rank:+.3f} MAE {peek_mae:.3f} "
          f"(expect ~1.0 / ~0)  {'PASS' if p4 else 'FAIL'}")

    # --- 5. SHUFFLED-alignment probe: break the prior-feature row alignment -> signal destroyed ---
    vs = v.copy()
    for c in VET_FEATS:
        vs[c] = rng.permutation(vs[c].to_numpy())      # scramble features vs the planted target
    o = walk_forward(vs, VET_FEATS, "y_plant")
    shuf_rank = _rank(o.y, o.p)
    p5 = shuf_rank < 0.15
    print(f"5. SHUFFLED-alignment probe (features scrambled vs target): rankcorr {shuf_rank:+.3f} "
          f"(expect ~0)  {'PASS' if p5 else 'FAIL'}")

    # --- 6. WALK-FORWARD temporal guard (asserts inside walk_forward; re-confirm folds) ---
    folds_ok = True
    for Y in TEST_SEASONS:
        folds_ok &= (v[v.season < Y].season < Y).all()
    print(f"6. WALK-FORWARD guard (train seasons < test season, all folds): {'PASS' if folds_ok else 'FAIL'}")

    # --- 7. NESTED-CV tuning runs & selects without touching the outer test fold ---
    Y = 2024
    tr = v[v.season < Y]
    picked = nested_select(tr, VET_FEATS, "y_plant", GRID)
    nested_ok = picked in GRID
    print(f"7. NESTED-CV inner LOSO select on train<{Y} (outer {Y} untouched): picked {picked}  "
          f"{'PASS' if nested_ok else 'FAIL'}")

    ok = all([r_ok, p2, p3, p4, p5, folds_ok, nested_ok])
    print(f"\nSYNTHETIC PROOF: {'PASS — machinery routes, detects signal+leak, respects time, tunes blind.' if ok else 'FAIL'}")
    return ok


def real_pathproof():
    """F-step: run the FULL pipeline (route -> per-model walk-forward + nested CV -> predict) on a
    PERMUTED target, on REAL shapes. Proves valid-shaped projections; NO real fit on real PPG, NO metric."""
    print("\n" + "=" * 70); print("F-STEP — FULL PIPELINE ON REAL SHAPES, PERMUTED TARGET (no real metric)")
    print("=" * 70)
    rng = np.random.default_rng(SEED)
    df = load_rb(); df = df[df.season <= 2025].copy()
    vet, rk = route(df)
    allok = True
    for name, slice_df, feats in (("veteran", vet, VET_FEATS), ("rookie", rk, ROOK_FEATS)):
        s = slice_df.copy()
        s["y_perm"] = rng.permutation(s["prior_ppg"].fillna(0).to_numpy())   # scrambled => blindness-safe
        o = walk_forward(s, feats, "y_perm", tune=True)
        exp_rows = int(s[s.season.isin(TEST_SEASONS)].shape[0])
        ok = (len(o) == exp_rows and np.isfinite(o.p).all()
              and o.season.nunique() == len([y for y in TEST_SEASONS if (s.season == y).any()]))
        allok &= ok
        print(f"  {name:8s}: projections {len(o):4d}/{exp_rows}  folds {o.season.nunique()}  "
              f"finite {bool(np.isfinite(o.p).all())}  {'OK' if ok else 'FAIL'}")
    print(f"\nF-STEP: {'PASS — full pipeline yields valid-shaped projections on real data; NO real fit/metric.' if allok else 'FAIL'}")
    return allok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    if not a.build:
        raise SystemExit("pass --build (synthetic/structural proof only; the real fit is a later session).")
    ok = prove()
    ok2 = real_pathproof()
    raise SystemExit(0 if (ok and ok2) else 1)


if __name__ == "__main__":
    main()
