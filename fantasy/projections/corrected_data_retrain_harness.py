"""CORRECTED-DATA RETRAIN EVALUATION — harness for
PREREG_corrected_data_retrain_2026-07-26.md.

Three frozen arms per position (prereg §2):
  OLD  = pre-fix dataset (git 3b4cde0) + inherited nested_select   -> must reproduce the shipped panels
  MID  = corrected dataset + OLD's per-fold (family, params)       -> isolates the DATA effect
  NEW  = corrected dataset + inherited nested_select               -> total effect
Attribution: data = MID-OLD, selection = NEW-MID, total = NEW-OLD.

MODES
  --check  STRUCTURAL ONLY. Extracts the pre-fix dataset, assembles all four positions on BOTH data
           versions, asserts keys/intersections/time-boundaries/pool-purity/fences, runs the synthetic
           probes and ONE cheap reproduction probe, prints the runtime estimate and all protected
           hashes. Computes NO corrected-model nested selection, NO corrected-model metric and NO
           rescored 2026 projection.
  --fire   The one shot.

Writes nothing into the repo. Scratch goes to $RETRAIN_SCRATCH.
Interpreter: BettingEdgeContinued/.venv-test/Scripts/python.exe
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
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
SEAS_DIR = REPO / "fantasy" / "seasonal_projections"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SEAS_DIR))

SCRATCH = Path(os.environ.get(
    "RETRAIN_SCRATCH",
    r"C:/Users/josep/AppData/Local/Temp/claude/c--Users-josep-Desktop-random-stuff-cowork-OS/"
    r"19483edc-3155-4194-8790-1ec4281ff28f/scratchpad/retrain_eval"))
SCRATCH.mkdir(parents=True, exist_ok=True)
PREFIX_SEAS = SCRATCH / "prefix_seas"
PREFIX_COMMIT = "3b4cde0"
DATASET = "season_dataset_2014_2026.csv"

# ------------------------------------------------------------------------- FROZEN CONSTANTS (§3-§6)
SEED = 42
BOOT_DRAWS = 2000
EVAL_SEASONS = [2021, 2022, 2023, 2024, 2025]
DEPLOY = 2026
SEALED_FLOOR = 2016
NOISE_FLOOR = 0.26          # measured junk-column MAE cost (RB session)
R2_UPPER = 0.50
R3_RHO_TOL = -0.005
R4_MIN_SEASONS = 4
R6_RMSE_REL = 0.010
R5_BIAS_TOL = 2.0
R8_SLATE_PCT = 0.10
R8_PLAYER_PTS = 25.0
BLOCK_DEPLOY_MISS = 0.50    # §6.4 blocking condition
BLOCK_TRAIN_MISS = 0.05

POSITIONS = {
    "QB": dict(module="build_qb_projection", vet="QB_VET_ALL", rook="QB_ROOK_ALL", top_k=12,
               wf="qb_walkforward_predictions.csv"),
    "RB": dict(module="build_rb_projection", vet="VET_ALL", rook="ROOK_ALL", top_k=24,
               wf="walkforward_predictions.csv"),
    "WR": dict(module="build_wr_projection", vet="WR_VET_ALL", rook="WR_ROOK_ALL", top_k=24,
               wf="wr_walkforward_predictions.csv"),
    "TE": dict(module="build_te_projection", vet="TE_VET_ALL", rook="TE_ROOK_ALL", top_k=12,
               wf="te_walkforward_predictions.csv"),
}

PROTECTED = {
    "fantasy/projections/models/qb_veteran_model.pkl": "7632549f95995b9702baefdf016d7271",
    "fantasy/projections/models/rb_rookie_model.pkl": "da230ee66575ca574f02cbc2139e1a80",
    "fantasy/projections/models/rb_veteran_model.pkl": "167aca71a8511afcced37c0abc846004",
    "fantasy/projections/models/te_rookie_model.pkl": "f79dad0ab26af5cb4e06a9f1723328cd",
    "fantasy/projections/models/te_veteran_model.pkl": "5a2f0b504d4cc6fc9a2e04453fd76a44",
    "fantasy/projections/models/wr_rookie_model.pkl": "6c9a3f3ed02ce32c53594f383aade882",
    "fantasy/projections/models/wr_veteran_model.pkl": "17dfbcf01054bdd5ce032f2b55df9ad2",
    "fantasy/seasonal_projections/models/rookie_ppg_model.pkl": "872467b2295fce27761f9e04da01b6e8",
    "fantasy/seasonal_projections/season_dataset_2014_2025.csv": "d9f06a2fd77adae6b5b58158650fc7ea",
    "fantasy/seasonal_projections/season_dataset_2014_2026.csv": "8322a59e43251820cb393d40787f60e6",
}

# runtime model, calibrated 2026-07-26 on this machine (prereg §10):
#   full-grid cost per inner season ~= 18.7 + 0.0041 * train_rows  seconds
#   validated against a measured nested_select (481 rows, 4 seasons) = 1.3 min
_RT_A, _RT_B = 18.7, 0.0041


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _self_sha256() -> str:
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def snapshot() -> dict:
    out = {k: _md5(REPO / k) for k in PROTECTED if (REPO / k).exists()}
    for f in sorted(RESULTS_DIR.glob("*.csv")):
        out[str(f.relative_to(REPO))] = _md5(f)
    for f in (HERE / "wr_player_scenarios_2026.csv",):
        if f.exists():
            out[str(f.relative_to(REPO))] = _md5(f)
    return out


def assert_protected(snap: dict):
    bad = [f"{k}: {snap[k]} != {v}" for k, v in PROTECTED.items() if k in snap and snap[k] != v]
    assert not bad, f"PROTECTED ARTIFACT MISMATCH: {bad}"


# ------------------------------------------------------------------------------------- METRICS
def _mae(y, p):
    return float(np.mean(np.abs(np.asarray(y, float) - np.asarray(p, float))))


def _rmse(y, p):
    return float(np.sqrt(np.mean((np.asarray(y, float) - np.asarray(p, float)) ** 2)))


def _rho(y, p):
    return float(spearmanr(y, p).statistic)


def block(df, col):
    y, p = df["y"].to_numpy(float), df[col].to_numpy(float)
    return dict(n=len(df), MAE=_mae(y, p), RMSE=_rmse(y, p), bias=float(np.mean(y - p)),
                med_bias=float(np.median(y - p)), predSD=float(np.std(p, ddof=1)),
                actSD=float(np.std(y, ddof=1)), rho=_rho(y, p))


def paired_bootstrap(df, a_col, b_col, seed=SEED, draws=BOOT_DRAWS):
    """95% interval for MAE(b) - MAE(a), resampling player_id clusters."""
    rng = np.random.default_rng(seed)
    ids = df.player_id.unique()
    pos = {i: np.where(df.player_id.values == i)[0] for i in ids}
    ae_a = np.abs(df["y"].values - df[a_col].values)
    ae_b = np.abs(df["y"].values - df[b_col].values)
    out = np.empty(draws)
    for k in range(draws):
        sel = np.concatenate([pos[i] for i in rng.choice(ids, size=len(ids), replace=True)])
        out[k] = ae_b[sel].mean() - ae_a[sel].mean()
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


# --------------------------------------------------------------------------------- DATA VERSIONS
def materialise_prefix_dataset() -> Path:
    """Extract the pre-fix dataset from git into scratch (read-only; never into the repo)."""
    PREFIX_SEAS.mkdir(parents=True, exist_ok=True)
    dst = PREFIX_SEAS / DATASET
    if not dst.exists():
        with open(dst, "wb") as fh:
            r = subprocess.run(["git", "show", f"{PREFIX_COMMIT}:fantasy/seasonal_projections/{DATASET}"],
                               cwd=REPO, stdout=fh)
        assert r.returncode == 0, "git show of the pre-fix dataset failed"
    blob = subprocess.run(["git", "rev-parse", f"{PREFIX_COMMIT}:fantasy/seasonal_projections/{DATASET}"],
                          cwd=REPO, capture_output=True, text=True).stdout.strip()
    return dst, blob


def assemble_for(pos: str, version: str):
    """assemble() for a position against a chosen data version. Patches only that module's SEAS,
    which is the sole path through which assemble() reads the dataset."""
    cache = SCRATCH / f"assembled_{pos}_{version}.parquet"
    cache_r = SCRATCH / f"assembled_{pos}_{version}_rook.parquet"
    if cache.exists() and cache_r.exists():
        return pd.read_parquet(cache), pd.read_parquet(cache_r)
    mod = __import__(POSITIONS[pos]["module"])
    orig = mod.SEAS
    try:
        mod.SEAS = PREFIX_SEAS if version == "old" else SEAS_DIR
        vet, rook, _ = mod.assemble()
    finally:
        mod.SEAS = orig
    vet.to_parquet(cache, index=False)
    rook.to_parquet(cache_r, index=False)
    return vet, rook


# ------------------------------------------------------------------------------- WALK-FORWARD ARMS
def walk_arm(df, feats, tag, frozen=None, verbose=True):
    """One arm's walk-forward. frozen=None -> inherited nested_select; frozen={season:(fam,params)}
    -> apply that exact configuration (the MID arm). Returns (predictions, chosen)."""
    import build_rb_projection as B
    rows, chosen = [], {}
    for Y in EVAL_SEASONS:
        tr = df[df.season < Y].dropna(subset=["y"])
        te = df[df.season == Y].dropna(subset=["y"])
        if len(tr) < 60 or len(te) == 0:
            if verbose:
                print(f"      [{tag}] {Y}: SKIPPED (train={len(tr)}, test={len(te)})")
            continue
        assert tr.season.max() < Y, f"WALK-FORWARD LEAK ({tag}, {Y})"
        assert tr.season.min() >= 2014, "dataset floor moved"
        if frozen is None:
            (fam, params, _imae), _ = B.nested_select(tr, feats)
        else:
            if Y not in frozen:
                continue
            fam, params = frozen[Y]
        Xtr, Xte = B._prep(fam, tr, te, feats)
        p = B._fit_predict(fam, params, Xtr, tr["y"].to_numpy(float), Xte)
        chosen[Y] = (fam, params)
        rows.append(pd.DataFrame({"season": Y, "grp": tag, "player_id": te.player_id.values,
                                  "player": te.player.values, "y": te.y.values, "pred": p}))
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["season", "grp", "player_id", "player", "y", "pred"])
    return out, chosen


def top_cohort_keys(df, k):
    d = df.copy()
    d["_rk"] = d.groupby("season")["pred"].rank(ascending=False, method="first")
    return set(map(tuple, d.loc[d._rk <= k, ["player_id", "season"]].to_numpy()))


# ------------------------------------------------------------------------------------- PROBES
def probe_noise():
    rng = np.random.default_rng(11)
    y = rng.gamma(2, 30, 400)
    p = rng.normal(60, 25, 400)
    r = abs(_rho(y, p))
    return r < 0.15, f"|rho(noise pred, y)| = {r:.4f} (< .15)"


def probe_planted():
    rng = np.random.default_rng(12)
    y = rng.gamma(2, 30, 400)
    p = 0.9 * y + rng.normal(0, 5, 400)
    r = _rho(y, p)
    return r > 0.90, f"rho(planted pred, y) = {r:.4f} (> .90)"


def probe_future_peek():
    """A model trained on its own test season must score far better than a walk-forward one.

    The synthetic target must carry a SEASON-SPECIFIC effect, otherwise a walk-forward model
    already sits on the irreducible noise floor and a peeking model has nothing left to win —
    which would make the probe blind to leakage rather than sensitive to it. Here f0's
    coefficient flips sign in the test season: only a model that has seen 2021 can get it right.
    """
    import build_rb_projection as B
    rng = np.random.default_rng(13)
    n = 900
    d = pd.DataFrame({"season": np.repeat([2019, 2020, 2021], n // 3),
                      "player_id": [f"p{i}" for i in range(n)],
                      "player": [f"P{i}" for i in range(n)]})
    for j in range(3):
        d[f"f{j}"] = rng.normal(0, 1, n)
    coef = d.season.map({2019: 30.0, 2020: 30.0, 2021: -30.0})
    d["y"] = 40 + coef * d.f0 + 10 * d.f1 + rng.normal(0, 6, n)
    feats = ["f0", "f1", "f2"]
    tr, te = d[d.season < 2021], d[d.season == 2021]
    cfg = dict(num_leaves=15, learning_rate=0.03, n_estimators=400)
    Xtr, Xte = B._prep("lightgbm", tr, te, feats)
    honest = _mae(te.y, B._fit_predict("lightgbm", cfg, Xtr, tr.y.to_numpy(float), Xte))
    Xp, Xte2 = B._prep("lightgbm", te, te, feats)
    peek = _mae(te.y, B._fit_predict("lightgbm", cfg, Xp, te.y.to_numpy(float), Xte2))
    return peek < honest * 0.5, f"walk-forward {honest:.2f} vs FUTURE-PEEK {peek:.2f} (peek must scream)"


def runtime_estimate(rows_by_fold):
    """Sum of (a + b*train_rows) * inner_seasons over every nested_select the fire will run."""
    return sum((_RT_A + _RT_B * r) * s for r, s in rows_by_fold)


# --------------------------------------------------------------------------------------- CHECK
def run_check():
    print("=" * 100)
    print("CORRECTED-DATA RETRAIN — STRUCTURAL CHECK (no corrected-model selection, metric or 2026 score)")
    print("=" * 100)
    before = snapshot()
    assert_protected(before)
    print(f"\n[1] PROTECTED ARTIFACTS: {len(before)} files snapshotted; all 10 pinned hashes match")

    dst, blob = materialise_prefix_dataset()
    print(f"\n[2] PRE-FIX DATASET  git {PREFIX_COMMIT}:{DATASET}")
    print(f"    blob {blob}  -> {dst}  (md5 {_md5(dst)}, {dst.stat().st_size:,} bytes)")
    print(f"    corrected on disk md5 {_md5(SEAS_DIR / DATASET)}")
    assert _md5(dst) != _md5(SEAS_DIR / DATASET), "the two data versions are identical — nothing to test"

    print("\n[3] SYNTHETIC PROBES")
    probes = [("noise carries no signal", probe_noise()),
              ("planted signal detected", probe_planted()),
              ("future-peek screams", probe_future_peek())]
    for name, (ok, msg) in probes:
        print(f"    {'PASS' if ok else 'FAIL'}  {name}: {msg}")
    assert all(ok for _, (ok, _) in probes), "SYNTHETIC PROBE FAILED — STOP"

    print("\n[4] POOL PURITY (R7) — depth columns absent from every pool, all four positions")
    import build_rb_projection as B
    banned = {B.DEPTH, B.DEPTH_SRC}
    for pos, cfg in POSITIONS.items():
        mod = __import__(cfg["module"])
        for which in ("vet", "rook"):
            pool = list(getattr(mod, cfg[which]))
            leak = [c for c in pool if c in banned or "depth_rank" in c or "depth_chart" in c
                    or "depth_team" in c]
            assert not leak, f"{pos}/{which}: depth column in pool: {leak}"
    print(f"    clean: no {sorted(banned)} and no depth_* token in any of the 8 pools")

    print("\n[5] PANELS — assembling all four positions on BOTH data versions")
    rows_by_fold, summary = [], []
    for pos, cfg in POSITIONS.items():
        t0 = time.time()
        keys = {}
        for ver in ("old", "new"):
            vet, rook = assemble_for(pos, ver)
            for tag, df, which in (("vet", vet, "vet"), ("rook", rook, "rook")):
                ev = df[df.season.isin(EVAL_SEASONS)].dropna(subset=["y"])
                k = set(map(tuple, ev[["player_id", "season"]].to_numpy()))
                assert len(k) == len(ev), f"{pos}/{ver}/{tag}: duplicate (player_id, season)"
                keys[(ver, tag)] = k
                if ver == "new":
                    for Y in EVAL_SEASONS:
                        tr = df[df.season < Y].dropna(subset=["y"])
                        if len(tr) >= 60:
                            # OLD + NEW nested passes, plus one deploy fit each
                            rows_by_fold += [(len(tr), tr.season.nunique())] * 2
                    trd = df[df.season <= 2025].dropna(subset=["y"])
                    rows_by_fold += [(len(trd), trd.season.nunique())] * 2
            assert df.season.min() >= 2014
        old_all = keys[("old", "vet")] | keys[("old", "rook")]
        new_all = keys[("new", "vet")] | keys[("new", "rook")]
        inter = old_all & new_all
        summary.append(dict(pos=pos, old_n=len(old_all), new_n=len(new_all), matched=len(inter),
                            old_only=len(old_all - new_all), new_only=len(new_all - old_all),
                            arm_moved=len((keys[("old", "vet")] & keys[("new", "rook")]) |
                                          (keys[("old", "rook")] & keys[("new", "vet")])),
                            secs=round(time.time() - t0, 1)))
    print(pd.DataFrame(summary).to_string(index=False))
    print("    (arm_moved = rows that changed veteran/rookie routing between data versions)")

    print("\n[6] TIME BOUNDARY + SEALED FENCE")
    for Y in EVAL_SEASONS:
        assert Y >= SEALED_FLOOR
    print(f"    eval seasons {EVAL_SEASONS}; every fold trains strictly on seasons < Y (asserted per "
          f"fold at fire time); no season < {SEALED_FLOOR} is ever scored; 2020 is not an eval season")

    print("\n[7] SLEEPER / ADP FENCE")
    print("    arms carry only [season, grp, player_id, player, y, pred]; Sleeper/ADP enter no fit, "
          "gate, selection or cohort definition")

    print("\n[8] REPRODUCTION PROBE — cheapest arm, OLD data (proves the OLD arm can reproduce)")
    vet, rook = assemble_for("QB", "old")
    mod = __import__(POSITIONS["QB"]["module"])
    feats = list(getattr(mod, POSITIONS["QB"]["rook"]))
    t0 = time.time()
    got, chosen = walk_arm(rook[rook.season <= 2021], feats, "rook", verbose=False)
    stored = pd.read_csv(RESULTS_DIR / POSITIONS["QB"]["wf"])
    s21 = stored[(stored.season == 2021) & (stored.grp == "rook")][["player_id", "pred"]]
    j = s21.merge(got[["player_id", "pred"]], on="player_id", how="inner", suffixes=("_stored", "_repro"))
    # the shipped builders write np.round(pred, 1); compare AFTER the stored rounding (prereg §2)
    dmax = float((j.pred_stored - j.pred_repro.round(1)).abs().max()) if len(j) else float("nan")
    raw = float((j.pred_stored - j.pred_repro).abs().max()) if len(j) else float("nan")
    print(f"    QB rookie 2021: chose {chosen.get(2021)} | matched {len(j)}/{len(s21)} rows")
    print(f"    max |stored - reproduced| AFTER stored 1dp rounding = {dmax:.6g}  "
          f"(unrounded {raw:.6g}, bounded by the 0.05 rounding half-step)  ({time.time()-t0:.0f}s)")
    assert dmax < 1e-9, "OLD arm does not reproduce the shipped panel even after rounding"
    print("    (the fire's R0 gate requires this to hold for every position and fold)")

    est = runtime_estimate(rows_by_fold)
    print(f"\n[9] EXPECTED RUNTIME  {len(rows_by_fold)} nested_select calls "
          f"(OLD + NEW passes, all positions/arms/folds + deploy fits)")
    print(f"    model: (18.7 + 0.0041 x train_rows) s per inner season, calibrated on this machine "
          f"and validated against a measured 1.3 min nested_select (481 rows, 4 seasons)")
    print(f"    ESTIMATE: {est/60:.0f} min ({est/3600:.1f} h) for the two nested passes; "
          f"the MID arm and all scoring add ~2 min; assembles are cached")

    after = snapshot()
    assert before == after, "PROTECTED ARTIFACTS CHANGED DURING CHECK"
    print(f"\n[10] PROTECTED ARTIFACTS UNCHANGED: True ({len(after)} files)")
    print(f"\nSCRIPT SHA256: {_self_sha256()}")
    print("CODE IS FROZEN. --fire runs this exact code once.")
    print("NO corrected-model selection, corrected-model metric, or rescored 2026 projection was computed.")


# ---------------------------------------------------------------------------------------- FIRE
def run_fire():
    run_check()
    print("\n" + "=" * 100)
    print("FIRE — OLD / MID / NEW arms, one shot")
    print("=" * 100)
    before = snapshot()
    import build_rb_projection as B
    verdicts = []

    for pos, cfg in POSITIONS.items():
        print(f"\n{'='*40} {pos} {'='*40}")
        mod = __import__(cfg["module"])
        fv, fr = list(getattr(mod, cfg["vet"])), list(getattr(mod, cfg["rook"]))
        arms, chosen_all = {}, {}
        for ver, arm, frozen_src in (("old", "OLD", None), ("new", "MID", "OLD"), ("new", "NEW", None)):
            vet, rook = assemble_for(pos, ver)
            parts, ch = [], {}
            for tag, df, feats in (("vet", vet, fv), ("rook", rook, fr)):
                frozen = chosen_all.get((frozen_src, tag)) if frozen_src else None
                p, c = walk_arm(df, feats, tag, frozen=frozen, verbose=False)
                parts.append(p)
                ch[tag] = c
                chosen_all[(arm, tag)] = c
            arms[arm] = pd.concat(parts, ignore_index=True)
            print(f"  {arm}: {len(arms[arm])} rows")

        # R0 reproduction gate
        stored = pd.read_csv(RESULTS_DIR / cfg["wf"]).dropna(subset=["y", "pred"])
        old_r = arms["OLD"][["player_id", "season", "pred"]].copy()
        old_r["pred"] = old_r["pred"].round(1)          # the shipped builders write np.round(pred, 1)
        j = stored[["player_id", "season", "pred"]].merge(
            old_r, on=["player_id", "season"], how="outer", suffixes=("_s", "_o"), indicator=True)
        dmax = float((j.pred_s - j.pred_o).abs().max())
        r0 = bool((j._merge == "both").all()) and dmax < 1e-9
        print(f"  R0 reproduction (after the stored 1dp rounding): keys aligned "
              f"{int((j._merge=='both').sum())}/{len(j)} | max |delta| {dmax:.3g} "
              f"-> {'PASS' if r0 else 'FAIL'}")
        if not r0:
            print(f"  {pos} STOPPED: OLD arm does not reproduce the shipped panel; attribution not identified.")
            verdicts.append(dict(pos=pos, R0=False, verdict=False))
            continue

        # matched intersection
        key = ["player_id", "season"]
        m = arms["OLD"][key + ["y", "pred"]].rename(columns={"pred": "OLD"})
        for a in ("MID", "NEW"):
            m = m.merge(arms[a][key + ["pred"]].rename(columns={"pred": a}), on=key, how="inner")
        print(f"  matched intersection n={len(m)}  (OLD {len(arms['OLD'])}, NEW {len(arms['NEW'])}, "
              f"OLD-only {len(arms['OLD'])-len(m)}, NEW-only {len(arms['NEW'])-len(m)})")
        for lbl, extra in (("OLD-only", arms["OLD"].merge(m[key], on=key, how="left", indicator=True)
                            .query("_merge=='left_only'")),
                           ("NEW-only", arms["NEW"].merge(m[key], on=key, how="left", indicator=True)
                            .query("_merge=='left_only'"))):
            if len(extra):
                print(f"    {lbl} n={len(extra)} actual mean {extra.y.mean():.1f} "
                      f"MAE {_mae(extra.y, extra.pred):.2f}")

        tk = top_cohort_keys(arms["OLD"], cfg["top_k"])
        m["_top"] = [tuple(r) in tk for r in m[key].to_numpy()]

        for panel, sub in (("full", m), (f"top{cfg['top_k']}", m[m._top])):
            print(f"  --- {panel} (n={len(sub)}) ---")
            for a in ("OLD", "MID", "NEW"):
                b = block(sub, a)
                print(f"    {a}: MAE {b['MAE']:8.3f}  RMSE {b['RMSE']:8.3f}  rho {b['rho']:.5f}  "
                      f"bias {b['bias']:+8.3f}  med {b['med_bias']:+8.3f}  predSD {b['predSD']:7.2f} "
                      f"(actual {b['actSD']:.2f})")
            bo, bm, bn = (block(sub, a) for a in ("OLD", "MID", "NEW"))
            lo, hi = paired_bootstrap(sub, "OLD", "NEW")
            per = sub.groupby("season").apply(
                lambda g: _mae(g.y, g.NEW) - _mae(g.y, g.OLD), include_groups=False)
            tt = ttest_1samp(per.values, 0.0)
            print(f"    ATTRIBUTION dMAE:  data (MID-OLD) {bm['MAE']-bo['MAE']:+.3f} | "
                  f"selection (NEW-MID) {bn['MAE']-bm['MAE']:+.3f} | total (NEW-OLD) {bn['MAE']-bo['MAE']:+.3f}")
            print(f"    NEW-OLD boot95 [{lo:+.3f}, {hi:+.3f}] | per-season " +
                  "  ".join(f"{s}:{v:+.3f}" for s, v in per.items()) + f" | t p={tt.pvalue:.4f}")
            if panel == "full":
                full = dict(bo=bo, bn=bn, lo=lo, hi=hi, per=per)
            else:
                topp = dict(bo=bo, bn=bn)

        print("  MODEL SELECTION (OLD -> NEW):")
        for tag in ("vet", "rook"):
            o, n = chosen_all.get(("OLD", tag), {}), chosen_all.get(("NEW", tag), {})
            famc = sum(1 for Y in o if Y in n and o[Y][0] != n[Y][0])
            parc = sum(1 for Y in o if Y in n and o[Y][0] == n[Y][0] and o[Y][1] != n[Y][1])
            print(f"    {tag}: {len(o)} folds | family changed {famc} | params changed {parc}")
            for Y in sorted(o):
                if Y in n and o[Y] != n[Y]:
                    print(f"      {Y}: {o[Y][0]}{o[Y][1]}  ->  {n[Y][0]}{n[Y][1]}")

        r1 = (full["bn"]["MAE"] - full["bo"]["MAE"]) <= NOISE_FLOOR
        r2 = full["hi"] < R2_UPPER
        r3 = (full["bn"]["rho"] - full["bo"]["rho"]) >= R3_RHO_TOL
        r4 = int((full["per"] <= NOISE_FLOOR).sum()) >= R4_MIN_SEASONS
        r5 = ((topp["bn"]["MAE"] - topp["bo"]["MAE"]) <= NOISE_FLOOR and
              (abs(topp["bn"]["bias"]) - abs(topp["bo"]["bias"])) <= R5_BIAS_TOL)
        r6 = (full["bn"]["RMSE"] - full["bo"]["RMSE"]) <= R6_RMSE_REL * full["bo"]["RMSE"]
        g = dict(R0=r0, R1=r1, R2=r2, R3=r3, R4=r4, R5=r5, R6=r6, R7=True)
        print("  GATES: " + "  ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in g.items())
              + f"  ->  {'PASS' if all(g.values()) else 'FAIL'}")
        verdicts.append(dict(pos=pos, **g, verdict=all(g.values())))

        # --- 2026 deploy movement (R8) + qb_changed diagnostics (§6.4), scratch only
        vetN, rookN = assemble_for(pos, "new")
        dep = []
        for tag, df, feats in (("vet", vetN, fv), ("rook", rookN, fr)):
            tr = df[(df.season <= 2025)].dropna(subset=["y"])
            sc = df[df.season == DEPLOY]
            if len(tr) < 60 or not len(sc):
                continue
            (fam, params, _), _ = B.nested_select(tr, feats)
            Xtr, Xsc = B._prep(fam, tr, sc, feats)
            pr = np.clip(B._fit_predict(fam, params, Xtr, tr["y"].to_numpy(float), Xsc), 0, None)
            dep.append(sc.assign(new_proj=np.round(pr, 1))[["player_id", "player", "new_proj"]])
            if tag == "vet":
                miss_tr = tr[feats].isna().mean()
                miss_dp = sc[feats].isna().mean()
                flag = [c for c in feats if miss_dp[c] >= BLOCK_DEPLOY_MISS and miss_tr[c] <= BLOCK_TRAIN_MISS]
                print(f"  §6.4 BLOCKING CONDITION: features with deploy-missing >= {BLOCK_DEPLOY_MISS:.0%} "
                      f"and train-missing <= {BLOCK_TRAIN_MISS:.0%}: {flag or 'none'}")
                for c in flag:
                    print(f"      {c}: train {miss_tr[c]*100:.1f}% missing, deploy {miss_dp[c]*100:.1f}%")
                if "qb_changed" in feats:
                    sens = {}
                    for val in (np.nan, 0.0, 1.0):
                        s2 = sc.copy(); s2["qb_changed"] = val
                        _, X2 = B._prep(fam, tr, s2, feats)
                        sens[str(val)] = float(np.clip(B._fit_predict(
                            fam, params, Xtr, tr["y"].to_numpy(float), X2), 0, None).mean())
                    print(f"      qb_changed deploy sensitivity (mean projection): "
                          f"NaN {sens['nan']:.2f} | 0 {sens['0.0']:.2f} | 1 {sens['1.0']:.2f}")
        if dep:
            d26 = pd.concat(dep, ignore_index=True)
            old26 = pd.read_csv(RESULTS_DIR / f"{pos.lower()}_projection_2026.csv")[
                ["player_id", "player", "projection"]]
            cmp26 = old26.merge(d26[["player_id", "new_proj"]], on="player_id", how="inner")
            cmp26["move"] = cmp26.new_proj - cmp26.projection
            pct = (cmp26.new_proj.mean() - cmp26.projection.mean()) / max(cmp26.projection.mean(), 1e-9)
            big = cmp26[cmp26.move.abs() > R8_PLAYER_PTS]
            print(f"  R8 2026 DEPLOY: n={len(cmp26)} slate mean {cmp26.projection.mean():.1f} -> "
                  f"{cmp26.new_proj.mean():.1f} ({pct*100:+.1f}%) | movers >|{R8_PLAYER_PTS:.0f}|: {len(big)}"
                  f"  -> {'WITHIN' if abs(pct) <= R8_SLATE_PCT else 'BREACH — STOP AND REPORT'}")
            print(cmp26.reindex(cmp26.move.abs().sort_values(ascending=False).index)
                  .head(15)[["player", "projection", "new_proj", "move"]].to_string(index=False))
            cmp26.to_csv(SCRATCH / f"deploy_move_{pos}.csv", index=False)

    print("\n" + "=" * 100)
    print("VERDICT TABLE")
    print(pd.DataFrame(verdicts).to_string(index=False))
    print("\nA PASS is a RECOMMENDATION only, and is additionally blocked by §6.4 until the "
          "qb_changed question is settled in its own preregistration.")
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
