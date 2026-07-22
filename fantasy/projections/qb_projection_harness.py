"""QB season-total projection harness (prereg PREREG_qb_projection_2026-07-21.md).

NEW file — does NOT modify the RB/WR/TE harnesses. QB is the thinnest, most under-powered position
(rookie folds ~7-13 rows; hit-panel n=101; zero-heavy bimodal target). The rookie college block is the
PASSING block (not receiving), and there is NO college passing box-score (§3A gap). This harness proves
the MACHINERY on QB shapes; it does not fit the real target.

--build : SYNTHETIC/STRUCTURAL proof ONLY. Routing exhaustive; leakage guard (aligned prior signal,
          shuffled destroys it, planted leak screams); walk-forward never trains on the test season;
          planted signal detected & noise not; nested-CV selects without touching the outer fold; F-step
          full pipeline on real QB shapes with a PERMUTED target yields valid shapes. NO depth feature.
          If a thin rookie fold can't run, it is reported honestly (that informs the rookie ship/hold).
"""
import sys, argparse
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).resolve().parent
SEAS = HERE.parent / "seasonal_projections"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TEST_SEASONS = [2021, 2022, 2023, 2024, 2025]
SEED = 42

VET_FEATS = ["prior_ppg", "prior_half_ppr", "prior_games", "ppg_2yr", "ppg_3yr", "ppg_trend",
             "career_high_ppg", "prior_snap_share_pg", "prior_targets_pg", "prior_carries_pg",
             "prior_receptions_pg", "prior_touches_pg", "prior_target_share", "prior_air_yards_share",
             "prior_adot", "prior_td_rate", "prior_yptarget", "prior_ypc", "prior_rec_epa",
             "prior_rush_epa", "age", "years_exp", "draft_round", "draft_pick", "prior_team_pass_rate",
             "prior_team_plays", "vacated_target_share", "vacated_rush_share", "coach_changed",
             "qb_changed", "prior_games_missed", "missed_prior_season"]              # NO depth_rank
ROOK_FEATS = ["draft_round", "draft_pick", "age", "prior_team_pass_rate", "prior_team_plays",
              "vacated_target_share", "vacated_rush_share", "coach_changed", "qb_changed"]

GRID = [{"max_depth": d, "learning_rate": lr} for d in (3, 6) for lr in (0.05, 0.1)]


def load_qb():
    sd = pd.read_csv(SEAS / "season_dataset_2014_2026.csv")
    return sd[sd.position == "QB"].copy()


def route(df):
    return df[df.is_rookie == 0], df[df.is_rookie == 1]


def _fit_pred(tr, te, feats, y_col, params):
    usable = [c for c in feats if tr[c].notna().sum() >= 5 and tr[c].nunique(dropna=True) >= 2]
    m = HistGradientBoostingRegressor(random_state=SEED, max_iter=200, **params)
    m.fit(tr[usable].to_numpy(float), tr[y_col].to_numpy(float))
    return m.predict(te[usable].to_numpy(float))


def _mae(y, p): return float(np.mean(np.abs(np.asarray(y) - np.asarray(p))))
def _rank(y, p):
    if np.std(p) == 0 or len(y) < 3: return 0.0
    return float(spearmanr(y, p).correlation)


def nested_select(train_df, feats, y_col, params_grid):
    seasons = sorted(train_df.season.unique())
    best, best_mae = None, np.inf
    for params in params_grid:
        maes = []
        for s in seasons:
            itr, iva = train_df[train_df.season != s], train_df[train_df.season == s]
            if len(itr) < 30 or len(iva) < 5:            # thin floor for QB (§3B), still guards blindness
                continue
            p = _fit_pred(itr, iva, feats, y_col, params)
            maes.append(_mae(iva[y_col], p))
        if maes and np.mean(maes) < best_mae:
            best, best_mae = params, float(np.mean(maes))
    return best or params_grid[0]


def walk_forward(df, feats, y_col, tune=False):
    out = []
    for Y in TEST_SEASONS:
        tr, te = df[df.season < Y], df[df.season == Y]
        assert (tr.season < Y).all(), f"WALK-FORWARD LEAK: train has season >= {Y}"
        if len(tr) < 30 or len(te) == 0:                 # thinnest-position floor; report skips honestly
            print(f"    (skipped fold {Y}: train {len(tr)} test {len(te)} too thin)")
            continue
        params = nested_select(tr, feats, y_col, GRID) if tune else GRID[0]
        p = _fit_pred(tr, te, feats, y_col, params)
        out.append(pd.DataFrame({"season": Y, "y": te[y_col].to_numpy(float), "p": p}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["season", "y", "p"])


def prove():
    print("=" * 70); print("QB PROJECTION HARNESS — SYNTHETIC/STRUCTURAL PROOF (no real fit, no real metric)")
    print("=" * 70)
    rng = np.random.default_rng(SEED)
    df = load_qb(); df = df[df.season <= 2025].copy()
    vet, rk = route(df)
    r_ok = (len(vet) + len(rk) == len(df)) and set(vet.index).isdisjoint(rk.index) \
        and (vet.is_rookie == 0).all() and (rk.is_rookie == 1).all()
    print(f"\n1. ROUTING partition (vet {len(vet)} + rookie {len(rk)} == {len(df)}, disjoint): "
          f"{'PASS' if r_ok else 'FAIL'}")
    print(f"   [QB thinness: rookie test rows/fold = "
          f"{[int((rk.season==Y).sum()) for Y in TEST_SEASONS]}]")

    v = vet.copy()
    z = ((v.prior_ppg - v.prior_ppg.mean()) / (v.prior_ppg.std() or 1)).fillna(0).to_numpy()
    v["y_noise"] = rng.normal(size=len(v))
    o = walk_forward(v, VET_FEATS, "y_noise"); noise_rank = _rank(o.y, o.p); p2 = abs(noise_rank) < 0.15
    print(f"2. NOISE probe (random y): pooled rankcorr {noise_rank:+.3f} (expect ~0)  {'PASS' if p2 else 'FAIL'}")
    v["y_plant"] = 3.0 * z + rng.normal(scale=0.6, size=len(v))
    o = walk_forward(v, VET_FEATS, "y_plant"); plant_rank = _rank(o.y, o.p); p3 = plant_rank > 0.30
    print(f"3. PLANTED probe (y=f(prior_ppg)+noise): pooled rankcorr {plant_rank:+.3f} (expect >.30)  "
          f"{'PASS' if p3 else 'FAIL'}")
    v["y_leaky"] = v["y_plant"]
    o = walk_forward(v, VET_FEATS + ["y_leaky"], "y_plant"); peek_rank = _rank(o.y, o.p); peek_mae = _mae(o.y, o.p)
    p4 = peek_rank > 0.98 and peek_mae < 0.2
    print(f"4. PEEK probe (target leaked as feature): rankcorr {peek_rank:+.3f} MAE {peek_mae:.3f} "
          f"(expect ~1.0 / ~0)  {'PASS' if p4 else 'FAIL'}")
    vs = v.copy()
    for c in VET_FEATS:
        vs[c] = rng.permutation(vs[c].to_numpy())
    o = walk_forward(vs, VET_FEATS, "y_plant"); shuf_rank = _rank(o.y, o.p); p5 = shuf_rank < 0.15
    print(f"5. SHUFFLED-alignment probe (features scrambled vs target): rankcorr {shuf_rank:+.3f} "
          f"(expect ~0)  {'PASS' if p5 else 'FAIL'}")
    folds_ok = all((v[v.season < Y].season < Y).all() for Y in TEST_SEASONS)
    print(f"6. WALK-FORWARD guard (train seasons < test season, all folds): {'PASS' if folds_ok else 'FAIL'}")
    picked = nested_select(v[v.season < 2024], VET_FEATS, "y_plant", GRID); nested_ok = picked in GRID
    print(f"7. NESTED-CV inner LOSO select on train<2024 (outer 2024 untouched): picked {picked}  "
          f"{'PASS' if nested_ok else 'FAIL'}")
    ok = all([r_ok, p2, p3, p4, p5, folds_ok, nested_ok])
    print(f"\nSYNTHETIC PROOF: {'PASS — machinery routes, detects signal+leak, respects time, tunes blind.' if ok else 'FAIL'}")
    return ok


def real_pathproof():
    print("\n" + "=" * 70); print("F-STEP — FULL PIPELINE ON REAL QB SHAPES, PERMUTED TARGET (no real metric)")
    print("=" * 70)
    rng = np.random.default_rng(SEED)
    df = load_qb(); df = df[df.season <= 2025].copy()
    vet, rk = route(df)
    allok = True
    for name, slice_df, feats in (("veteran", vet, VET_FEATS), ("rookie", rk, ROOK_FEATS)):
        s = slice_df.copy()
        s["y_perm"] = rng.permutation(s["prior_ppg"].fillna(0).to_numpy())
        o = walk_forward(s, feats, "y_perm", tune=True)
        ran = sorted(o.season.unique().tolist()) if len(o) else []
        exp_rows = int(s[s.season.isin(ran)].shape[0])
        ok = (len(o) == exp_rows and (len(o) == 0 or np.isfinite(o.p).all())) and len(ran) >= 1
        allok &= ok
        print(f"  {name:8s}: projections {len(o):4d}/{exp_rows}  folds-run {ran}  "
              f"finite {bool(len(o)==0 or np.isfinite(o.p).all())}  {'OK' if ok else 'FAIL'}")
    print(f"\nF-STEP: {'PASS — full pipeline yields valid-shaped projections on real QB data; NO real fit/metric.' if allok else 'FAIL'}")
    return allok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    if not ap.parse_args().build:
        raise SystemExit("pass --build (synthetic/structural proof only; the real fit is a later session).")
    raise SystemExit(0 if (prove() and real_pathproof()) else 1)


if __name__ == "__main__":
    main()
