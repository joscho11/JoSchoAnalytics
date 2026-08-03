"""GENERIC POSITION-LEVEL PROJECTION CALIBRATION — harness for
PREREG_position_projection_calibration_2026-07-26.md.

Question: does one positive affine map per position, fitted only on strictly-earlier
out-of-fold predictions, correct the forecast-known draftable cohort's level/dispersion
without damaging full-panel accuracy?

MODES
  --check  STRUCTURAL ONLY. Builds both panels, runs every leakage/identity assert and the
           three synthetic probes, prints row/cluster/season counts and protected-artifact
           hashes. It computes NO calibration coefficient, NO calibrated prediction and NO
           challenger metric. Baseline-arm statistics are printed because the prereg's
           blindness disclosure already records them.
  --fire   THE ONE SHOT. Runs --check, then fits and evaluates the single frozen challenger
           and prints the mechanical gate arithmetic for both analyses.

Writes nothing into the repo. Scratch goes to $CALIB_SCRATCH.
Interpreter: JoSchoAnalytics/.venv-test/Scripts/python.exe
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, ttest_1samp

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
MODELS_DIR = HERE / "models"
RESULTS_DIR = HERE / "results"
SEAS = REPO / "fantasy" / "seasonal_projections"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SEAS))

SCRATCH = Path(os.environ.get(
    "CALIB_SCRATCH",
    r"C:/Users/josep/AppData/Local/Temp/claude/c--Users-josep-Desktop-random-stuff-cowork-OS/"
    r"19483edc-3155-4194-8790-1ec4281ff28f/scratchpad/calibration"))
SCRATCH.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- FROZEN CONSTANTS
SEED = 42
BOOT_DRAWS = 2000
OOF_SEASONS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]   # prereg §5.1
EVAL_A = [2021, 2022, 2023, 2024, 2025]                          # prereg §5.1
EVAL_B = [2022, 2023, 2024, 2025]                                # prereg §5.2 (2021 has no prior OOF)
SEALED_FLOOR = 2016                                              # no season < 2016 is ever scored

# prereg §7.3 gates
G1_REL = 0.030        # primary-panel MAE must improve by >= 3.0% of baseline
G5_ABS = 0.26         # full-panel MAE may not worsen by more than the measured junk-column floor
G6_REL = 0.010        # full-panel RMSE may not worsen by more than 1.0%
G3_MIN_SEASONS = 4    # of 5
G4_ALPHA = 0.05       # season-clustered t(4)

# prereg §5.3 cohort sizes; §5.1 learner pins
POSITIONS = {
    "QB": dict(module="build_qb_projection", vet="QB_VET_ALL", rook="QB_ROOK_ALL", top_k=12,
               wf="qb_walkforward_predictions.csv",
               vet_pkl="qb_veteran_model.pkl", rook_pkl=None,
               # no QB rookie model shipped -> pinned to the QB VETERAN deploy config (prereg §5.1)
               rook_params=dict(num_leaves=31, learning_rate=0.03, n_estimators=400)),
    "RB": dict(module="build_rb_projection", vet="VET_ALL", rook="ROOK_ALL", top_k=24,
               wf="walkforward_predictions.csv",
               vet_pkl="rb_veteran_model.pkl", rook_pkl="rb_rookie_model.pkl", rook_params=None),
    "WR": dict(module="build_wr_projection", vet="WR_VET_ALL", rook="WR_ROOK_ALL", top_k=24,
               wf="wr_walkforward_predictions.csv",
               vet_pkl="wr_veteran_model.pkl", rook_pkl="wr_rookie_model.pkl", rook_params=None),
    "TE": dict(module="build_te_projection", vet="TE_VET_ALL", rook="TE_ROOK_ALL", top_k=12,
               wf="te_walkforward_predictions.csv",
               vet_pkl="te_veteran_model.pkl", rook_pkl="te_rookie_model.pkl", rook_params=None),
}

PROTECTED_PKL = {
    "qb_veteran_model.pkl": "7632549f95995b9702baefdf016d7271",
    "rb_rookie_model.pkl": "da230ee66575ca574f02cbc2139e1a80",
    "rb_veteran_model.pkl": "167aca71a8511afcced37c0abc846004",
    "te_rookie_model.pkl": "f79dad0ab26af5cb4e06a9f1723328cd",
    "te_veteran_model.pkl": "5a2f0b504d4cc6fc9a2e04453fd76a44",
    "wr_rookie_model.pkl": "6c9a3f3ed02ce32c53594f383aade882",
    "wr_veteran_model.pkl": "17dfbcf01054bdd5ce032f2b55df9ad2",
}
ROOKIE_PPG_MD5 = "872467b2295fce27761f9e04da01b6e8"


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _self_sha256() -> str:
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def snapshot() -> dict:
    """MD5 of every protected artifact: the 7 pkls, rookie_ppg_model.pkl, every results CSV,
    the two user-owned overlay/scenario files, and both season_dataset CSVs."""
    files = sorted(MODELS_DIR.glob("*.pkl")) + sorted(RESULTS_DIR.glob("*.csv")) + [
        SEAS / "models" / "rookie_ppg_model.pkl",
        HERE / "wr_player_scenarios_2026.csv",
        SEAS / "season_dataset_2014_2025.csv",
        SEAS / "season_dataset_2014_2026.csv",
    ]
    return {str(f.relative_to(REPO)): _md5(f) for f in files if f.exists()}


# ------------------------------------------------------------------------------------ METRICS
def _mae(y, p):
    return float(np.mean(np.abs(np.asarray(y, float) - np.asarray(p, float))))


def _rmse(y, p):
    return float(np.sqrt(np.mean((np.asarray(y, float) - np.asarray(p, float)) ** 2)))


def _rho(y, p):
    return float(spearmanr(y, p).statistic)


def block(df: pd.DataFrame, pred_col: str) -> dict:
    y, p = df["y"].to_numpy(float), df[pred_col].to_numpy(float)
    return dict(n=len(df), clusters=df.player_id.nunique(), MAE=_mae(y, p), RMSE=_rmse(y, p),
                bias=float(np.mean(y - p)), med_bias=float(np.median(y - p)),
                predSD=float(np.std(p, ddof=1)), actSD=float(np.std(y, ddof=1)), rho=_rho(y, p))


def cluster_bootstrap_delta(df: pd.DataFrame, base_col: str, cal_col: str, seed=SEED, draws=BOOT_DRAWS):
    """Paired player-clustered bootstrap of MAE(cal) - MAE(base). Resamples player_id clusters."""
    rng = np.random.default_rng(seed)
    ids = df.player_id.unique()
    pos_of = {i: np.where(df.player_id.values == i)[0] for i in ids}
    ae_b = np.abs(df["y"].values - df[base_col].values)
    ae_c = np.abs(df["y"].values - df[cal_col].values)
    out = np.empty(draws)
    for k in range(draws):
        sel = np.concatenate([pos_of[i] for i in rng.choice(ids, size=len(ids), replace=True)])
        out[k] = ae_c[sel].mean() - ae_b[sel].mean()
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)), float(out.std())


# ------------------------------------------------------------- THE ONE FROZEN CHALLENGER (§4)
def fit_affine(fit_df: pd.DataFrame, pred_col: str) -> tuple[float, float]:
    """OLS of actual on raw prediction, intercept included. Two columns only: [1, pred].
    No weights, no robust loss, no winsorising, no cohort selection. Prereg §4."""
    X = np.column_stack([np.ones(len(fit_df)), fit_df[pred_col].to_numpy(float)])
    assert X.shape[1] == 2, "calibration design matrix must be exactly [intercept, raw prediction]"
    coef, *_ = np.linalg.lstsq(X, fit_df["y"].to_numpy(float), rcond=None)
    return float(coef[0]), float(coef[1])


def apply_affine(pred, a, b):
    return np.clip(a + b * np.asarray(pred, float), 0, None)


# ------------------------------------------------------------------------- ANALYSIS A PANEL
def _lgbm(params):
    from lightgbm import LGBMRegressor
    return LGBMRegressor(objective="mae", random_state=SEED, verbose=-1, n_jobs=-1, **params)


def deploy_params(pkl_name: str) -> dict:
    import joblib
    b = joblib.load(MODELS_DIR / pkl_name)
    assert b["family"] == "lightgbm", f"{pkl_name} is not LightGBM"
    return dict(b["params"]), list(b["feature_cols"])


def build_panel_a(pos: str, verbose=True) -> pd.DataFrame:
    """Fixed-config LightGBM walk-forward on the CORRECTED dataset, OOF seasons 2018-2025.
    Cached to scratch. Columns: season, grp, player_id, player, y, pred."""
    cache = SCRATCH / f"panelA_{pos}.parquet"
    if cache.exists():
        if verbose:
            print(f"    [{pos}] Analysis-A panel from cache {cache.name}")
        return pd.read_parquet(cache)

    cfg = POSITIONS[pos]
    mod = __import__(cfg["module"])
    t0 = time.time()
    vet, rook, _all = mod.assemble()
    if verbose:
        print(f"    [{pos}] assemble(): vet={len(vet)} rook={len(rook)} ({time.time()-t0:.0f}s)")

    arms = []
    for grp, feats_name, pkl, pinned in (("vet", cfg["vet"], cfg["vet_pkl"], None),
                                         ("rook", cfg["rook"], cfg["rook_pkl"], cfg["rook_params"])):
        feats = list(getattr(mod, feats_name))
        if pkl is not None:
            params, pkl_feats = deploy_params(pkl)
            assert pkl_feats == feats, (
                f"{pos}/{grp}: module feature pool != shipped pkl feature_cols — "
                f"the deploy contract moved, STOP")
        else:
            params = dict(pinned)
        df = (vet if grp == "vet" else rook).copy()
        arms.append((grp, df, feats, params))

    rows = []
    for grp, df, feats, params in arms:
        for S in OOF_SEASONS:
            tr = df[df.season < S].dropna(subset=["y"])
            te = df[df.season == S].dropna(subset=["y"])
            if len(tr) < 60 or len(te) == 0:
                if verbose:
                    print(f"    [{pos}/{grp}] {S}: SKIPPED (train={len(tr)}, test={len(te)})")
                continue
            assert tr.season.max() < S, f"WALK-FORWARD LEAK {pos}/{grp}/{S}"
            m = _lgbm(params)
            m.fit(tr[feats].to_numpy(float), tr["y"].to_numpy(float))
            p = np.clip(m.predict(te[feats].to_numpy(float)), 0, None)
            rows.append(pd.DataFrame({"season": S, "grp": grp, "player_id": te.player_id.values,
                                      "player": te.player.values, "y": te.y.values, "pred": p}))
    out = pd.concat(rows, ignore_index=True)
    out.to_parquet(cache, index=False)
    if verbose:
        print(f"    [{pos}] Analysis-A panel built: {len(out)} rows, seasons "
              f"{sorted(out.season.unique())} ({time.time()-t0:.0f}s)")
    return out


def build_panel_b(pos: str) -> pd.DataFrame:
    d = pd.read_csv(RESULTS_DIR / POSITIONS[pos]["wf"]).dropna(subset=["y", "pred"])
    return d[["season", "grp", "player_id", "player", "y", "pred"]].copy()


def top_cohort(df: pd.DataFrame, k: int) -> pd.DataFrame:
    """Forecast-known cohort: top-k by RAW BASELINE prediction within season. Prereg §5.3."""
    d = df.copy()
    d["_rk"] = d.groupby("season")["pred"].rank(ascending=False, method="first")
    return d[d._rk <= k].drop(columns="_rk")


# ------------------------------------------------------------------------- STRUCTURAL ASSERTS
def leakage_asserts(pos: str, panel: pd.DataFrame, eval_seasons: list, oof_min: int, label: str):
    errs = []
    if panel.season.min() < SEALED_FLOOR:
        errs.append(f"SEALED-SLICE VIOLATION: scored season {panel.season.min()} < {SEALED_FLOOR}")
    for Y in eval_seasons:
        fit_rows = panel[(panel.season >= oof_min) & (panel.season < Y)]
        if len(fit_rows) == 0:
            errs.append(f"{Y}: no strictly-prior OOF calibration rows")
        elif fit_rows.season.max() >= Y:
            errs.append(f"{Y}: calibration-fit season {fit_rows.season.max()} not < {Y}")
    assert not errs, f"[{pos}/{label}] LEAKAGE ASSERT FAILED: {errs}"
    return True


# ------------------------------------------------------------------------------------- PROBES
def probe_noise():
    """A rank-preserving map may not manufacture ranking information from a pure-noise predictor."""
    rng = np.random.default_rng(1)
    d = pd.DataFrame({"season": np.repeat([2021, 2022], 300),
                      "player_id": [f"p{i}" for i in range(600)],
                      "y": rng.gamma(2, 30, 600)})
    d["pred"] = rng.normal(60, 25, 600)                       # independent of y
    a, b = fit_affine(d[d.season == 2021], "pred")
    cal = apply_affine(d.loc[d.season == 2022, "pred"], a, b)
    r_base = _rho(d.loc[d.season == 2022, "y"], d.loc[d.season == 2022, "pred"])
    r_cal = _rho(d.loc[d.season == 2022, "y"], cal)
    ok = abs(r_cal - r_base) < 1e-9 or b <= 0
    return ok, f"b={b:+.4f} rho base {r_base:+.4f} -> cal {r_cal:+.4f} (|d|={abs(r_cal-r_base):.2e})"


def probe_planted():
    """A known affine miscalibration must be recovered and must produce a large MAE gain."""
    rng = np.random.default_rng(2)
    n = 800
    d = pd.DataFrame({"season": np.repeat([2021, 2022], n // 2),
                      "player_id": [f"q{i}" for i in range(n)]})
    d["pred"] = rng.uniform(0, 120, n)
    d["y"] = 2.0 * d["pred"] + 30.0 + rng.normal(0, 12, n)
    a, b = fit_affine(d[d.season == 2021], "pred")
    te = d[d.season == 2022]
    cal = apply_affine(te["pred"], a, b)
    gain = (_mae(te.y, cal) - _mae(te.y, te.pred)) / _mae(te.y, te.pred)
    ok = abs(b - 2.0) < 0.15 and abs(a - 30.0) < 8.0 and gain < -0.20
    return ok, f"recovered a={a:.2f} (30) b={b:.3f} (2.0); relative MAE change {gain*100:+.1f}%"


def probe_future_peek():
    """Fitting the calibration ON the test season must beat the honest strictly-prior fit."""
    rng = np.random.default_rng(3)
    frames = []
    for i, S in enumerate([2021, 2022, 2023]):
        n = 300
        pred = rng.uniform(0, 120, n)
        # season-specific miscalibration -> a prior-season fit cannot be optimal for the test season
        y = (1.4 + 0.6 * i) * pred + (10 + 40 * i) + rng.normal(0, 10, n)
        frames.append(pd.DataFrame({"season": S, "player_id": [f"r{S}_{j}" for j in range(n)],
                                    "pred": pred, "y": y}))
    d = pd.concat(frames, ignore_index=True)
    te = d[d.season == 2023]
    a_h, b_h = fit_affine(d[d.season < 2023], "pred")
    a_p, b_p = fit_affine(te, "pred")
    m_base = _mae(te.y, te.pred)
    m_h = _mae(te.y, apply_affine(te.pred, a_h, b_h))
    m_p = _mae(te.y, apply_affine(te.pred, a_p, b_p))
    ok = m_p < m_h - 1.0
    return ok, f"base {m_base:.2f} | honest prior-fit {m_h:.2f} | FUTURE-PEEK {m_p:.2f} (peek must be lowest)"


# --------------------------------------------------------------------------------------- CHECK
def run_check(verbose=True) -> dict:
    print("=" * 100)
    print("POSITION PROJECTION CALIBRATION — STRUCTURAL CHECK (no challenger fitted)")
    print("=" * 100)
    before = snapshot()

    print("\n[1] PROTECTED ARTIFACTS — pinned MD5s")
    bad = [f"{k}: {_md5(MODELS_DIR / k)} != {v}" for k, v in PROTECTED_PKL.items()
           if _md5(MODELS_DIR / k) != v]
    if _md5(SEAS / "models" / "rookie_ppg_model.pkl") != ROOKIE_PPG_MD5:
        bad.append("rookie_ppg_model.pkl CHANGED")
    assert not bad, f"PROTECTED ARTIFACT MISMATCH: {bad}"
    print(f"    7 projection pkls + rookie_ppg_model.pkl match their pins; "
          f"{len(before)} artifacts snapshotted")

    print("\n[2] SYNTHETIC PROBES (harness liveness — no real data touched)")
    probes = [("noise / no manufactured ranking", probe_noise()),
              ("planted affine signal recovered", probe_planted()),
              ("future-peek screams", probe_future_peek())]
    for name, (ok, msg) in probes:
        print(f"    {'PASS' if ok else 'FAIL'}  {name}: {msg}")
    assert all(ok for _, (ok, _) in probes), "SYNTHETIC PROBE FAILED — STOP"

    print("\n[3] ANALYSIS B — shipped out-of-fold panels (verbatim, hash-pinned)")
    panels = {}
    for pos in POSITIONS:
        f = RESULTS_DIR / POSITIONS[pos]["wf"]
        b = build_panel_b(pos)
        panels[(pos, "B")] = b
        leakage_asserts(pos, b, EVAL_B, 2021, "B")
        k = POSITIONS[pos]["top_k"]
        t = top_cohort(b[b.season.isin(EVAL_B)], k)
        print(f"    {pos}: {f.name} md5={_md5(f)} rows={len(b)} seasons={sorted(b.season.unique())}")
        print(f"        eval {EVAL_B}: full n={int(b.season.isin(EVAL_B).sum())} | "
              f"top{k} n={len(t)} clusters={t.player_id.nunique()} | "
              f"calibration-fit pool grows 2021 -> {max(EVAL_B)-1}")

    print("\n[4] ANALYSIS A — corrected-data fixed-config panels (this is the slow step)")
    for pos in POSITIONS:
        a = build_panel_a(pos, verbose=verbose)
        panels[(pos, "A")] = a
        leakage_asserts(pos, a, EVAL_A, min(OOF_SEASONS), "A")
        k = POSITIONS[pos]["top_k"]
        ev = a[a.season.isin(EVAL_A)]
        t = top_cohort(ev, k)
        fitpool = a[a.season < min(EVAL_A)]
        print(f"    {pos}: rows={len(a)} seasons={sorted(a.season.unique())} | "
              f"pre-2021 calibration pool n={len(fitpool)} ({sorted(fitpool.season.unique())})")
        print(f"        eval {EVAL_A}: full n={len(ev)} clusters={ev.player_id.nunique()} | "
              f"top{k} n={len(t)} clusters={t.player_id.nunique()} "
              f"(rookies {int((t.grp=='rook').sum())})")
        per = ev.groupby("season").size().to_dict()
        print(f"        per-season eval rows: {per}")

    print("\n[5] IDENTICAL-ROW CONTRACT (baseline and challenger score the same keys)")
    for (pos, lab), p in sorted(panels.items()):
        ev = EVAL_A if lab == "A" else EVAL_B
        d = p[p.season.isin(ev)]
        keys = d[["player_id", "season"]]
        assert not keys.duplicated().any(), f"{pos}/{lab}: duplicate (player_id, season) keys"
        k = POSITIONS[pos]["top_k"]
        t = top_cohort(d, k)
        assert len(t) == k * len(ev), f"{pos}/{lab}: top cohort {len(t)} != {k}x{len(ev)}"
    print(f"    all {len(panels)} panels: unique (player_id, season) keys; top cohorts exactly "
          f"k x n_seasons; both arms will be evaluated on these frozen keys")

    print("\n[6] SLEEPER / ADP FENCE")
    for (pos, lab), p in sorted(panels.items()):
        assert "sleeper" not in p.columns and "adp" not in " ".join(p.columns), \
            f"{pos}/{lab}: a market column reached the calibration panel"
    print("    no Sleeper/ADP column exists on any calibration panel; the design matrix is "
          "[intercept, raw prediction] and is asserted at fit time")

    print("\n[7] BASELINE ARM (already disclosed in prereg §3.5 — NOT a challenger metric)")
    rows = []
    for (pos, lab), p in sorted(panels.items()):
        ev = EVAL_A if lab == "A" else EVAL_B
        d = p[p.season.isin(ev)]
        k = POSITIONS[pos]["top_k"]
        rows.append(dict(pos=pos, analysis=lab, panel="full", **block(d, "pred")))
        rows.append(dict(pos=pos, analysis=lab, panel=f"top{k}", **block(top_cohort(d, k), "pred")))
    print(pd.DataFrame(rows).round(3).to_string(index=False))

    after = snapshot()
    assert before == after, "PROTECTED ARTIFACTS CHANGED DURING CHECK"
    print(f"\n[8] PROTECTED ARTIFACTS UNCHANGED: True ({len(after)} files)")
    print(f"\nSCRIPT SHA256: {_self_sha256()}")
    print("CODE IS FROZEN. --fire runs this exact code once.")
    print("NO calibration coefficient, calibrated prediction, or challenger metric was computed.")
    return panels


# ---------------------------------------------------------------------------------------- FIRE
def run_fire():
    panels = run_check()
    print("\n" + "=" * 100)
    print("FIRE — one shot, frozen challenger: calibrated = max(0, a_pos + b_pos * raw_prediction)")
    print("=" * 100)
    before = snapshot()
    verdicts = []
    for lab, ev, oof_min in (("A", EVAL_A, min(OOF_SEASONS)), ("B", EVAL_B, 2021)):
        for pos in POSITIONS:
            p = panels[(pos, lab)].copy()
            k = POSITIONS[pos]["top_k"]
            coefs, parts = [], []
            for Y in ev:
                fit = p[(p.season >= oof_min) & (p.season < Y)]
                assert fit.season.max() < Y, "CALIBRATION LEAK"
                a, b = fit_affine(fit, "pred")
                te = p[p.season == Y].copy()
                te["cal"] = apply_affine(te["pred"], a, b)
                coefs.append(dict(season=Y, a=a, b=b, fit_n=len(fit),
                                  fit_seasons=f"{fit.season.min()}-{fit.season.max()}"))
                parts.append(te)
            d = pd.concat(parts, ignore_index=True)
            print(f"\n--- {pos} / Analysis {lab} — fitted coefficients ---")
            print(pd.DataFrame(coefs).round(4).to_string(index=False))

            res = {}
            for panel_name, sub in (("full", d), (f"top{k}", top_cohort(d, k))):
                bb, cb = block(sub, "pred"), block(sub, "cal")
                lo, hi, sd = cluster_bootstrap_delta(sub, "pred", "cal")
                per = sub.groupby("season").apply(
                    lambda g: _mae(g.y, g.cal) - _mae(g.y, g.pred), include_groups=False)
                tt = ttest_1samp(per.values, 0.0)
                res[panel_name] = dict(base=bb, cal=cb, dMAE=cb["MAE"] - bb["MAE"],
                                       dRMSE=cb["RMSE"] - bb["RMSE"], lo=lo, hi=hi,
                                       per=per, wins=int((per < 0).sum()), p=float(tt.pvalue),
                                       clipped=int((sub["cal"] <= 0).sum()))
                print(f"  [{panel_name}] n={bb['n']} cl={bb['clusters']} | "
                      f"MAE {bb['MAE']:.3f} -> {cb['MAE']:.3f} ({cb['MAE']-bb['MAE']:+.3f}) | "
                      f"RMSE {bb['RMSE']:.3f} -> {cb['RMSE']:.3f} | "
                      f"bias {bb['bias']:+.3f} -> {cb['bias']:+.3f} | "
                      f"med {bb['med_bias']:+.3f} -> {cb['med_bias']:+.3f} | "
                      f"SD {bb['predSD']:.2f} -> {cb['predSD']:.2f} (actual {bb['actSD']:.2f}) | "
                      f"rho {bb['rho']:.5f} -> {cb['rho']:.5f}")
                print(f"           boot95 [{lo:+.3f}, {hi:+.3f}] | seasons won {res[panel_name]['wins']}/{len(per)} | "
                      f"t p={tt.pvalue:.4f} | clipped-to-0 rows {res[panel_name]['clipped']}")
                print("           per-season dMAE: " + "  ".join(f"{s}:{v:+.3f}" for s, v in per.items()))

            prim, full = res[f"top{k}"], res["full"]
            g1 = prim["dMAE"] <= -G1_REL * prim["base"]["MAE"]
            g2 = prim["hi"] < 0
            g3 = prim["wins"] >= G3_MIN_SEASONS
            g4 = prim["p"] <= G4_ALPHA and prim["dMAE"] < 0
            g5 = full["dMAE"] <= G5_ABS
            g6 = full["dRMSE"] <= G6_REL * full["base"]["RMSE"]
            bmin = min(c["b"] for c in coefs)
            unclipped = d[d["cal"] > 0]
            g7 = bmin > 0 and abs(_rho(unclipped.y, unclipped.pred) - _rho(unclipped.y, unclipped.cal)) < 1e-9
            gates = dict(G1=g1, G2=g2, G3=g3, G4=g4, G5=g5, G6=g6, G7=g7)
            print(f"  GATES {pos}/{lab}: " + "  ".join(f"{k2}={'PASS' if v else 'FAIL'}" for k2, v in gates.items())
                  + f"  ->  {'PASS' if all(gates.values()) else 'FAIL'}"
                  + ("" if lab == "A" else "   (Analysis B is REPORT-ONLY and promotes nothing)"))
            verdicts.append(dict(pos=pos, analysis=lab, **gates, verdict=all(gates.values())))

    print("\n" + "=" * 100)
    print("VERDICT TABLE")
    print(pd.DataFrame(verdicts).to_string(index=False))
    assert snapshot() == before, "PROTECTED ARTIFACTS CHANGED DURING FIRE"
    print(f"\nPROTECTED ARTIFACTS UNCHANGED: True\nSCRIPT SHA256: {_self_sha256()}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--fire", action="store_true")
    a = ap.parse_args()
    if a.fire:
        run_fire()
    elif a.check:
        run_check()
    else:
        raise SystemExit("pass --check or --fire")
