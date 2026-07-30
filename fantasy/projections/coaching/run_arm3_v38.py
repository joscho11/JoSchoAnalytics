"""PHASE C/D — end-to-end Arm 3 Stage 1 / Stage 2 orchestration (prereg v3.8).

Calls the tested primitives in `stage_models.py`. This module is what both the synthetic
end-to-end tests and the real build invoke, so a passing synthetic test exercises the same code
path as production.

Writes ONLY versioned v38 artifacts. The preliminary `arm3_residuals.csv` / `arm3_effects.csv`
predate every correction from v3.2 onward and are never touched.

Run:  python run_arm3_v38.py --build
"""
import argparse
import hashlib
import json
import pathlib

import numpy as np
import pandas as pd

import build_reliability as BR
import drive_definitions as DD
import stage_models as SM

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"

STAGE1_TARGETS = list(range(2014, 2026))
STAGE2_TARGETS = list(range(2018, 2027))
RETIRED = set(DD.RETIRED_NAMES)


# ================================================================ inputs
def load_stage1_inputs(panel_path=None, controls_path=None):
    panel = pd.read_csv(panel_path or DATA / "team_offense_panel.csv")
    ctrl = pd.read_csv(controls_path or DATA / "personnel_controls.csv")

    for name, df in [("team_offense_panel", panel), ("personnel_controls", ctrl)]:
        assert not df.duplicated(["season", "team"]).any(), f"{name}: duplicate (season, team)"
        leaked = RETIRED & set(df.columns)
        assert not leaked, f"{name}: retired drive names still present -> {sorted(leaked)}"

    df = panel[["season", "team", "epa_play"]].merge(ctrl, on=["season", "team"], how="inner")
    missing = [c for c in SM.STAGE1_PREDICTORS if c not in df.columns]
    assert not missing, f"missing Stage 1 predictors: {missing}"
    BR.assert_design_matrix_is_clean(SM.STAGE1_PREDICTORS, "stage1")
    return df


# ================================================================ Stage 1
def _fit_predict(train, test, alpha):
    """Preprocess + ridge, refit from scratch. Returns predictions for `test`."""
    pre = SM.Stage1Preprocessor().fit(train)
    Xtr, Xte = pre.transform(train).values, pre.transform(test).values
    ytr = train["relative_epa_play"].values
    block = {j: "s1" for j in range(Xtr.shape[1])}
    c, coef = SM.block_ridge(Xtr, ytr, block, {"s1": float(alpha)})
    return c + Xte @ coef, pre


def run_stage1(df=None, targets=None, verbose=True):
    df = load_stage1_inputs() if df is None else df
    targets = targets or STAGE1_TARGETS

    # Same-season centering, computed WITHIN each completed season.
    df = SM.relative_epa_play(df)

    res_rows, tune_rows, fold_rows, schemas = [], [], [], {}
    for S in targets:
        hist_seasons = sorted(s for s in df.season.unique() if s < S)
        folds = SM.expanding_folds(df.season.unique(), S,
                                   min_train_seasons=SM.STAGE1_MIN_TRAIN_SEASONS,
                                   min_validation_seasons=SM.STAGE1_MIN_VALIDATION_SEASONS)
        if not folds:
            if verbose:
                print(f"  {S}: SKIPPED (frozen Stage 1 minimums not met; "
                      f"{len(hist_seasons)} prior seasons)")
            continue

        def score(alpha, _folds=folds, _S=S):
            errs = []
            for tr_seasons, val_season in _folds:
                tr = df[df.season.isin(tr_seasons)]
                va = df[df.season == val_season]
                pred, _ = _fit_predict(tr, va, alpha)
                errs.append(va["relative_epa_play"].values - pred)
            return SM.season_averaged_mse(errs)

        sel = SM.select_alpha(score)

        # persist every candidate, including boundary extensions
        for h in sel["history"]:
            for a, sc in zip(h["alphas"], h["scores"]):
                tune_rows.append(dict(target_season=S, alpha=a, season_avg_mse=sc,
                                      grid_lo_exp=h["lo_exp"], grid_hi_exp=h["hi_exp"]))
        # per-fold losses at the SELECTED alpha
        for tr_seasons, val_season in folds:
            tr, va = df[df.season.isin(tr_seasons)], df[df.season == val_season]
            pred, _ = _fit_predict(tr, va, sel["alpha"])
            e = va["relative_epa_play"].values - pred
            fold_rows.append(dict(target_season=S, validation_season=val_season,
                                  n_train_seasons=len(tr_seasons), n_train_rows=len(tr),
                                  n_val_rows=len(va), mse=float(np.mean(e ** 2))))

        train = df[df.season < S]
        test = df[df.season == S]
        if not len(test):
            continue
        pred, pre = _fit_predict(train, test, sel["alpha"])
        schemas[str(S)] = dict(
            numeric_columns=SM.STAGE1_NUMERIC, binary_columns=SM.STAGE1_BINARY,
            qb_vocabulary=pre.qb_vocab_, n_qb_levels=len(pre.qb_vocab_),
            medians={k: float(v) for k, v in pre.medians_.items()},
            means={k: float(v) for k, v in pre.mean_.items()},
            stds={k: float(v) for k, v in pre.std_.items()},
            n_train_rows=int(len(train)), first_train_season=int(train.season.min()),
            last_train_season=int(train.season.max()))

        for (_, row), p in zip(test.iterrows(), pred):
            res_rows.append(dict(
                season=int(row.season), team=row.team, epa_play=float(row.epa_play),
                league_mean_epa_play=float(row.league_mean_epa_play),
                relative_epa_play=float(row.relative_epa_play),
                predicted_relative_epa_play=float(p),
                team_offense_residual=float(row.relative_epa_play - p),
                selected_alpha=sel["alpha"], n_train_rows=int(len(train)),
                first_train_season=int(train.season.min()),
                last_train_season=int(train.season.max()), n_inner_folds=len(folds),
                at_lower_boundary=sel["at_lower_boundary"],
                at_upper_boundary=sel["at_upper_boundary"],
                boundary_unresolved=sel["boundary_unresolved"],
                extensions_lo=sel["extensions_lo"], extensions_hi=sel["extensions_hi"]))
        if verbose:
            print(f"  {S}: alpha={sel['alpha']:.4g} folds={len(folds)} "
                  f"train={len(train)} boundary={sel['boundary_unresolved']}")

    return (pd.DataFrame(res_rows), pd.DataFrame(tune_rows), pd.DataFrame(fold_rows), schemas)


# ================================================================ Stage 2
def _stage2_fit(resid, expo, train_seasons, alpha_c, alpha_h, vocab=None):
    """Fit on `train_seasons`; returns (intercept, coef, names, blocks, vocab)."""
    tr = resid[resid.season.isin(train_seasons)]
    hi = max(train_seasons) + 1
    if vocab is None:
        e = expo[expo.season.isin(train_seasons)]
        vocab = (sorted(e[e.role == BR.ROLE_CALLER].person_id.dropna().unique()),
                 sorted(e[e.role == BR.ROLE_HC_CTX].person_id.dropna().unique()))
    keys, X, names, blocks = SM.stage2_design(
        expo[expo.season.isin(train_seasons)], hi,
        persons_caller=vocab[0], persons_ctx=vocab[1], row_universe=tr)
    y = keys.merge(tr, on=["season", "team"], how="left")["team_offense_residual"].values
    block_of = {j: blocks[j] for j in range(len(names))}
    c, coef = SM.block_ridge(X, y, block_of, {"caller": alpha_c, "hc_context": alpha_h})
    return c, coef, names, blocks, vocab


def _stage2_predict(resid, expo, seasons, c, coef, names, blocks, vocab):
    tr = resid[resid.season.isin(seasons)]
    keys, X, _n, _b = SM.stage2_design(
        expo[expo.season.isin(seasons)], max(seasons) + 1,
        persons_caller=vocab[0], persons_ctx=vocab[1], row_universe=tr)
    y = keys.merge(tr, on=["season", "team"], how="left")["team_offense_residual"].values
    return y, c + X @ coef


def run_stage2(resid=None, expo=None, targets=None, verbose=True):
    resid = resid if resid is not None else pd.read_csv(DATA / "arm3_stage1_residuals_v38.csv")
    if expo is None:
        expo = pd.read_csv(DATA / "coach_exposure.csv")
    targets = targets or STAGE2_TARGETS

    eff_rows, tune_rows, fold_rows = [], [], []
    for Y in targets:
        folds = SM.expanding_folds(resid.season.unique(), Y,
                                   min_train_seasons=SM.STAGE2_MIN_TRAIN_SEASONS,
                                   min_validation_seasons=SM.STAGE2_MIN_VALIDATION_SEASONS)
        if not folds:
            if verbose:
                print(f"  {Y}: SKIPPED (frozen Stage 2 minimums not met)")
            continue

        # Build each fold's design ONCE and reuse it across all 625 alpha candidates. The
        # design does not depend on the penalties, so rebuilding it per candidate multiplied the
        # cost of the joint search by ~625 for no benefit.
        cache = []
        for tr_seasons, val_season in folds:
            tr = resid[resid.season.isin(tr_seasons)]
            e_tr = expo[expo.season.isin(tr_seasons)]
            vocab = (sorted(e_tr[e_tr.role == BR.ROLE_CALLER].person_id.dropna().unique()),
                     sorted(e_tr[e_tr.role == BR.ROLE_HC_CTX].person_id.dropna().unique()))
            ktr, Xtr, names, blocks = SM.stage2_design(
                e_tr, max(tr_seasons) + 1, persons_caller=vocab[0], persons_ctx=vocab[1],
                row_universe=tr)
            ytr = ktr.merge(tr, on=["season", "team"], how="left")[
                "team_offense_residual"].values
            va = resid[resid.season == val_season]
            kva, Xva, _n, _b = SM.stage2_design(
                expo[expo.season == val_season], val_season + 1,
                persons_caller=vocab[0], persons_ctx=vocab[1], row_universe=va)
            yva = kva.merge(va, on=["season", "team"], how="left")[
                "team_offense_residual"].values
            cache.append((Xtr, ytr, {j: blocks[j] for j in range(len(names))}, Xva, yva))

        def score(ac, ah, _cache=cache):
            errs = []
            for Xtr, ytr, block_of, Xva, yva in _cache:
                c, coef = SM.block_ridge(Xtr, ytr, block_of,
                                         {"caller": ac, "hc_context": ah})
                errs.append(yva - (c + Xva @ coef))
            return SM.season_averaged_mse(errs)

        sel = SM.select_alpha_pair(score)
        for h in sel["history"]:
            for cand in h["candidates"]:
                tune_rows.append(dict(target_season=Y, **cand,
                                      caller_lo=h["caller_lo"], caller_hi=h["caller_hi"],
                                      hc_lo=h["hc_lo"], hc_hi=h["hc_hi"]))
        for (tr_seasons, val_season), (Xtr, ytr, block_of, Xva, yva) in zip(folds, cache):
            c, coef = SM.block_ridge(Xtr, ytr, block_of,
                                     {"caller": sel["alpha_caller"],
                                      "hc_context": sel["alpha_hc_context"]})
            e = yva - (c + Xva @ coef)
            fold_rows.append(dict(target_season=Y, validation_season=val_season,
                                  n_train_seasons=len(tr_seasons), n_val_rows=len(yva),
                                  mse=float(np.mean(e ** 2))))

        train_seasons = sorted(s for s in resid.season.unique() if s < Y)
        c, coef, names, blocks, vocab = _stage2_fit(
            resid, expo, train_seasons, sel["alpha_caller"], sel["alpha_hc_context"])

        e_hist = expo[expo.season.isin(train_seasons)]
        supp = e_hist.groupby(["role", "person_id"]).agg(
            observed_exposure=("exposure", "sum"),
            n_observed_team_seasons=("exposure", "size")).reset_index()
        supp_map = {(r.role, r.person_id): (r.observed_exposure, r.n_observed_team_seasons)
                    for r in supp.itertuples()}

        n_tr = len(resid[resid.season.isin(train_seasons)])
        for name, blk, v in zip(names, blocks, coef):
            pid = name.split("__", 1)[1]
            role = BR.ROLE_CALLER if blk == "caller" else BR.ROLE_HC_CTX
            ex, nts = supp_map.get((role, pid), (0.0, 0))
            eff_rows.append(dict(
                target_season=Y, person_id=pid, role=role, effect=float(v),
                selected_alpha_caller=sel["alpha_caller"],
                selected_alpha_hc_context=sel["alpha_hc_context"],
                first_train_season=int(min(train_seasons)),
                last_train_season=int(max(train_seasons)),
                n_train_team_seasons=n_tr, n_inner_folds=len(folds),
                observed_exposure=float(ex), n_observed_team_seasons=int(nts),
                block_boundary_status=("upper" if (
                    sel["caller_at_upper"] if blk == "caller" else sel["hc_at_upper"])
                    else "lower" if (
                    sel["caller_at_lower"] if blk == "caller" else sel["hc_at_lower"])
                    else "interior"),
                intercept=float(c)))
        if verbose:
            print(f"  {Y}: a_caller={sel['alpha_caller']:.4g} a_hc={sel['alpha_hc_context']:.4g} "
                  f"folds={len(folds)} ids={len(names)}")

    return pd.DataFrame(eff_rows), pd.DataFrame(tune_rows), pd.DataFrame(fold_rows)


def md5(p):
    return hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()


def build():
    print("=" * 84)
    print("ARM 3 v3.8 — STAGE 1")
    print("=" * 84)
    res, tune, folds, schemas = run_stage1()
    res.to_csv(DATA / "arm3_stage1_residuals_v38.csv", index=False)
    tune.to_csv(DATA / "arm3_stage1_tuning_v38.csv", index=False)
    folds.to_csv(DATA / "arm3_stage1_fold_losses_v38.csv", index=False)
    (DATA / "arm3_stage1_feature_schemas_v38.json").write_text(
        json.dumps(schemas, indent=2, sort_keys=True), encoding="utf-8")

    print("=" * 84)
    print("ARM 3 v3.8 — STAGE 2")
    print("=" * 84)
    eff, t2, f2 = run_stage2(resid=res)
    eff.to_csv(DATA / "arm3_stage2_effects_v38.csv", index=False)
    t2.to_csv(DATA / "arm3_stage2_tuning_v38.csv", index=False)
    f2.to_csv(DATA / "arm3_stage2_fold_losses_v38.csv", index=False)

    for f in ["arm3_stage1_residuals_v38.csv", "arm3_stage1_tuning_v38.csv",
              "arm3_stage1_fold_losses_v38.csv", "arm3_stage1_feature_schemas_v38.json",
              "arm3_stage2_effects_v38.csv", "arm3_stage2_tuning_v38.csv",
              "arm3_stage2_fold_losses_v38.csv"]:
        print(f"  {f:42s} {md5(DATA / f)}")
    return res, eff


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    if a.build:
        build()
    else:
        print("pass --build")
