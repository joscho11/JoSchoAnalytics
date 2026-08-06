"""Run the pipeline with the v2 features and report development estimates.

Governed by PREREGISTRATION Amendment 4. NO GATE FIRES HERE. Every number on seasons 2015 to 2025
is a development estimate under A4.3 and may be used to compare candidates against each other, never
as an unbiased out-of-sample result. 2026 is sealed and is not scored.

HARNESS VALIDATION COMES FIRST
------------------------------
Before any v2 number is believed, this reruns the v1 feature set and requires it to reproduce the
figures notebook 02 and notebook 03 recorded. If M2 does not land on 2.3719 and M4-c does not land
on 2.3650, the harness is wrong and every comparison below it is meaningless, so it says so and
stops rather than reporting a difference that is really a bug.

Run:  python futures/eval_v2.py
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
FUT = REPO / "futures"
sys.path.insert(0, str(FUT / "season_team_totals"))
import m4_engine as eng  # noqa: E402

DATA, ART = FUT / "data", FUT / "artifacts"
SEED, N_SIMS_INNER, N_SIMS = 20260802, 4000, 20000
ALPHA_GRID = (0.01, 0.1, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0)
FALLBACK_ALPHA = 10.0

# What v1 recorded. Reproducing these is the licence to believe anything else printed here.
V1_REFERENCE = {"M2_ridge": 2.3719, "M4c": 2.3650, "B0_market": 2.2453, "B1_persistence": 2.8296}
TOL = 0.0002

NEW_FEATURES = ["qb_returning", "qb_prior_epa_per_att", "qb_prior_cpoe", "qb_prior_attempts",
                "allpro_weighted", "allpro_offense", "allpro_defense",
                "roster_continuity", "reserve_count"]


def load():
    audit = json.loads((ART / "data_audit.json").read_text(encoding="utf-8"))
    meta = json.loads((ART / "model_metadata.json").read_text(encoding="utf-8"))
    panel = pd.read_parquet(DATA / "team_season_panel_v2.parquet")
    venue = pd.read_parquet(DATA / "season_schedule_context.parquet")
    sched = pd.read_parquet(DATA / "schedules_snapshot.parquet")
    smin, smax = int(audit["outcomes"]["season_min"]), max(
        int(audit["outcomes"]["season_max"]), int(audit["predict_season"]["season"]))
    sched = sched[(sched["game_type"] == "REG") & sched["season"].between(smin, smax)].copy()
    fr = {"OAK": "LV", "SD": "LAC", "STL": "LA"}
    sched["home_franchise"] = sched["home_team"].replace(fr)
    sched["away_franchise"] = sched["away_team"].replace(fr)
    venue["no_home_field"] = venue["explicit_neutral"] | venue["international_game"]
    games = sched.merge(venue[["game_id", "no_home_field"]], on="game_id", how="inner")
    games["hfa_mult"] = np.where(games["no_home_field"], 0.0, 1.0)
    return audit, meta, panel, games


def fit_direct(tr: pd.DataFrame, feats, target, alpha):
    """M2: ridge straight onto the win count. Imputer and scaler fitted on training rows only."""
    imp = SimpleImputer(strategy="median").fit(tr[feats])
    sc = StandardScaler().fit(imp.transform(tr[feats]))
    m = Ridge(alpha=alpha).fit(sc.transform(imp.transform(tr[feats])), tr[target].to_numpy())
    return imp, sc, m


def predict_direct(fit, df, feats):
    imp, sc, m = fit
    return m.predict(sc.transform(imp.transform(df[feats])))


def select_tau_03(games, feat, feats, train_seasons, tie_rate, alpha, panel, target, T):
    """Tau selection exactly as notebook 03 did it, which is NOT what m4_engine does.

    03's `coverage80_for` simulates the inner validation season through `simulate(T, ...)`, and that
    helper seeds on the OUTER fold: `default_rng(seed + int(T))`. `m4_engine.select_tau` seeds on the
    validation season instead (`seed + int(va_s)`). Both are defensible, but they are different
    random streams, so the engine picks a different tau on 3 of the 10 folds (2015, 2020, 2024) and
    the pooled MAE lands 0.0004 off what 03 recorded. Reproducing 03 requires 03's convention.
    """
    inner = eng.inner_folds(train_seasons)
    if len(inner) < 2:
        return float(eng.TAU_FALLBACK), True
    scores = {}
    for tau in eng.TAU_GRID:
        covs = []
        for tr_s, va_s in inner[-3:]:
            g_tr, X_tr = eng.game_design(games, feat, tr_s, feats)
            f = eng.fit_margin(g_tr, X_tr, alpha, tie_rate)
            g_va, X_va = eng.game_design(games, feat, [va_s], feats, settled_only=False)
            s = eng.simulate_wins(f, g_va, X_va, n_sims=N_SIMS_INNER, seed=SEED + int(T), tau=tau)
            ev = panel[(panel["season"] == va_s) & panel["has_target"]]
            lo, hi = s.quantile(.10), s.quantile(.90)
            covs.append(float(np.mean([bool(lo[r["franchise"]] <= r[target] <= hi[r["franchise"]])
                                       for _, r in ev.iterrows() if r["franchise"] in s.columns])))
        scores[tau] = float(np.mean(covs))
    return float(min(eng.TAU_GRID, key=lambda t: (abs(scores[t] - 0.80), t))), False


def m2_alpha(panel, feats, target, train_seasons):
    """Inner expanding-season selection inside the training window only.

    ALL inner folds, not the last six. Notebook 02 iterates the full list; truncating to [-6:] here
    changed the selected alpha on 5 of 10 folds and moved pooled MAE by 0.006.
    """
    folds = eng.inner_folds(train_seasons)
    if len(folds) < 2:
        return FALLBACK_ALPHA, True
    scores = {}
    for a in ALPHA_GRID:
        errs = []
        for tr_s, va_s in folds:
            tr = panel[panel["season"].isin(tr_s) & panel["has_target"]]
            va = panel[(panel["season"] == va_s) & panel["has_target"]]
            if len(tr) < 32 or va.empty:
                continue
            f = fit_direct(tr, feats, target, a)
            errs.append(float(np.abs(predict_direct(f, va, feats) - va[target]).mean()))
        if errs:
            scores[a] = float(np.mean(errs))
    return (float(min(scores, key=lambda a: (scores[a], a))), False) if scores else (FALLBACK_ALPHA, True)


def run(label, feats, panel, games, folds, target, complete, do_m4=True):
    feat_idx = panel.set_index(["season", "franchise"])[feats]
    tie_rate = float((games["result"] == 0).mean())
    rows_m2, rows_m4 = [], []
    per_fold = {}
    for T in folds:
        train_seasons = [s for s in complete if s < T]
        ev = panel[(panel["season"] == T) & panel["has_target"] & panel["line_covered"]]

        tr = panel[panel["season"].isin(train_seasons) & panel["has_target"]]
        a, fb = m2_alpha(panel, feats, target, train_seasons)
        pred2 = predict_direct(fit_direct(tr, feats, target, a), ev, feats)
        rows_m2 += list(np.abs(pred2 - ev[target].to_numpy()))

        rec = {"m2_alpha": a, "m2_fallback": fb, "n_eval": int(len(ev))}
        if do_m4:
            alpha, afb, _ = eng.select_alpha(games, feat_idx, feats, train_seasons, tie_rate,
                                             ALPHA_GRID, FALLBACK_ALPHA)
            tau, tfb = select_tau_03(games, feat_idx, feats, train_seasons, tie_rate, alpha,
                                     panel, target, T)
            g_tr, X_tr = eng.game_design(games, feat_idx, train_seasons, feats)
            fit = eng.fit_margin(g_tr, X_tr, alpha, tie_rate)
            g_te, X_te = eng.game_design(games, feat_idx, [T], feats, settled_only=False)
            sim = eng.simulate_wins(fit, g_te, X_te, n_sims=N_SIMS, seed=SEED + T, tau=tau)
            mu = sim.mean()
            pred4 = np.array([mu.get(f, np.nan) for f in ev["franchise"]])
            rows_m4 += list(np.abs(pred4 - ev[target].to_numpy()))
            rec |= {"m4_alpha": alpha, "m4_tau": tau, "m4_fallback": bool(afb or tfb)}
        per_fold[str(T)] = rec
        print(f"    {T}  n={len(ev):>3}  M2 a={a:<6g}" + (f"  M4c tau={rec.get('m4_tau'):<4g}" if do_m4 else ""))
    out = {"label": label, "n_features": len(feats), "n_rows": len(rows_m2),
           "M2_ridge": float(np.mean(rows_m2)), "per_fold": per_fold}
    if do_m4:
        out["M4c"] = float(np.mean(rows_m4))
    return out


def main():
    audit, meta, panel, games = load()
    target = audit["target"]["column"]
    folds = [int(s) for s in audit["folds"]["test_seasons"]]
    strict = [int(s) for s in audit["folds_strict_sensitivity"]["test_seasons"]]
    complete = [int(s) for s in audit["outcomes"]["complete_seasons"]]
    V1 = list(meta["features"]["columns"])
    V2 = V1 + NEW_FEATURES

    print(f"folds {folds}  |  v1 {len(V1)} features  |  v2 {len(V2)} features")
    print(f"strict subset {strict}\n")

    t0 = time.time()
    print("  [1/2] v1 feature set (harness validation)")
    r1 = run("v1", V1, panel, games, folds, target, complete)
    print(f"\n  [2/2] v2 feature set (+{len(NEW_FEATURES)})")
    r2 = run("v2", V2, panel, games, folds, target, complete)
    print(f"\n  elapsed {time.time()-t0:.0f}s\n")

    # ---- harness validation -------------------------------------------------------------
    ok = True
    print("HARNESS VALIDATION (v1 must reproduce the recorded numbers)")
    for k, want in (("M2_ridge", V1_REFERENCE["M2_ridge"]), ("M4c", V1_REFERENCE["M4c"])):
        got = r1[k]
        good = abs(got - want) <= TOL
        ok &= good
        print(f"  {k:<10} recorded {want:.4f}   reproduced {got:.4f}   "
              f"{'MATCH' if good else 'MISMATCH  <<<'}")
    if not ok:
        print("\nHARNESS DOES NOT REPRODUCE v1. Every comparison below would be a bug, not a result.")
        return 1

    b0 = V1_REFERENCE["B0_market"]
    print(f"\nRESULTS (development estimates, PREREGISTRATION A4.3; {r1['n_rows']} rows, "
          f"{len(folds)} seasons)")
    print(f"{'model':<12}{'v1 MAE':>10}{'v2 MAE':>10}{'change':>10}{'vs B0':>10}")
    print("-" * 52)
    for k in ("M2_ridge", "M4c"):
        d = r2[k] - r1[k]
        print(f"{k:<12}{r1[k]:>10.4f}{r2[k]:>10.4f}{d:>+10.4f}{r2[k]-b0:>+10.4f}")
    print(f"{'B0 market':<12}{b0:>10.4f}{b0:>10.4f}{0.0:>+10.4f}{0.0:>+10.4f}")
    print("\nnegative change = the new features helped. vs B0 still positive = still behind the "
          "archived consensus.")

    res = {"governed_by": "PREREGISTRATION Amendment 4 (A4.3): development estimates, no gate fires",
           "status": "DEVELOPMENT ESTIMATE, NOT OUT-OF-SAMPLE",
           "sealed": {"season": 2026, "note": "not scored anywhere in this run"},
           "harness_validation": {"reproduced_v1": True, "reference": V1_REFERENCE, "tol": TOL},
           "new_features": NEW_FEATURES, "v1": r1, "v2": r2,
           "written_at_utc": datetime.now(timezone.utc).isoformat()}
    (ART / "v2_development_results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"\nwrote futures/artifacts/v2_development_results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
