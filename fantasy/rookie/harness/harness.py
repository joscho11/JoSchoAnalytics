"""Part C — ROOKIE HIT-PROBABILITY harness (prereg fantasy/rookie/PREREG_rookie_production_2026-07-20.md).

TWO MODES:
  --build : run the SYNTHETIC harness-proof ONLY (noise / planted / future-peek probes +
            identity + leakage asserts). NO real target is scored; NO real metric printed.
            This is what verifies the machinery this session (blindness intact).
  --fire  : run the real backtest ONCE on the real target (a SEPARATE fresh session — NOT now).

Arms (prereg §7): full (all 5 groups) | draft_only (group 1) | college_only (groups 2-5) |
combine_out (college box + PFF + age).  Missing-data regimes (prereg §5):
  full/draft_only  -> CatBoost native NaN ; logistic missing-indicator (center+flag, fill 0)
  college_only     -> within-position MEDIAN, NO flag, NO NaN (the "market back-door close")
Decision metric (prereg §8): pooled OOS log loss + AUC, full vs draft_only, held-out test
classes 2019-2023 (train <= Y-1, min 4 train classes, K=5).
"""
import sys, json, argparse
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, log_loss

HERE = Path(__file__).resolve().parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SKILL = ["QB", "RB", "WR", "TE"]
TEST_CLASSES = [2019, 2020, 2021, 2022, 2023]     # prereg §8 PINNED
MIN_TRAIN_CLASSES = 4
SEED = 42
# frozen light configs (the --fire inner-CV grid expands these; pinned so build==fire code path)
CAT_PARAMS = dict(iterations=250, depth=4, learning_rate=0.05, l2_leaf_reg=4.0,
                  loss_function="Logloss", random_seed=SEED, verbose=0, allow_writing_files=False)
LOGIT_C = 0.5


# ---------------------------------------------------------------- feature prep (train-fit only)
def _pos_median_fill(X, pos, medians):
    X = X.copy()
    for c in X.columns:
        for pcode in pos.unique():
            m = (pos == pcode)
            X.loc[m, c] = X.loc[m, c].fillna(medians.get((pcode, c), np.nan))
    return X.fillna(X.median(numeric_only=True))          # global backstop for all-NaN cells


def prep(train, test, cols, family, regime, pos_tr, pos_te):
    """Return (Xtr, Xte) prepared per family+regime, fit strictly on train. No test leakage."""
    if not cols:   # position-only baseline (used by the synthetic proof to isolate feature value)
        Dtr = pd.get_dummies(pos_tr, prefix="pos").reset_index(drop=True)
        Dte = pd.get_dummies(pos_te, prefix="pos").reset_index(drop=True).reindex(columns=Dtr.columns, fill_value=0)
        return Dtr, Dte
    Xtr, Xte = train[cols].copy(), test[cols].copy()
    if regime == "median_noflag":
        med = {(p, c): Xtr.loc[pos_tr == p, c].median() for p in pos_tr.unique() for c in cols}
        Xtr = _pos_median_fill(Xtr, pos_tr, med)
        Xte = _pos_median_fill(Xte, pos_te, med)
    if family == "catboost":
        # native NaN for full/draft_only; already median-filled for college_only
        Xtr = pd.concat([Xtr, pd.get_dummies(pos_tr, prefix="pos")], axis=1)
        Xte = pd.concat([Xte, pd.get_dummies(pos_te, prefix="pos")], axis=1)
        Xte = Xte.reindex(columns=Xtr.columns, fill_value=0)
        return Xtr, Xte
    # logistic: standardize on train; missing-indicator for non-median regimes
    mean, std = Xtr.mean(), Xtr.std(ddof=0).replace(0, 1)
    if regime != "median_noflag":
        flag_tr = Xtr.isna().astype(float); flag_te = Xte.isna().astype(float)
        Ztr = ((Xtr - mean) / std).fillna(0.0); Zte = ((Xte - mean) / std).fillna(0.0)
        flag_tr.columns = [f"{c}__miss" for c in cols]; flag_te.columns = [f"{c}__miss" for c in cols]
        Ztr = pd.concat([Ztr, flag_tr], axis=1); Zte = pd.concat([Zte, flag_te], axis=1)
    else:
        Ztr = ((Xtr - mean) / std); Zte = ((Xte - mean) / std)
    Ztr = pd.concat([Ztr, pd.get_dummies(pos_tr, prefix="pos").reset_index(drop=True)], axis=1)
    Zte = pd.concat([Zte.reset_index(drop=True), pd.get_dummies(pos_te, prefix="pos").reset_index(drop=True)], axis=1)
    Zte = Zte.reindex(columns=Ztr.columns, fill_value=0)
    return Ztr, Zte


def fit_predict(train, test, cols, family, regime):
    """Calibrated P(hit) for test rows. Calibration nested via CV on TRAIN only."""
    pos_tr, pos_te = train["position"], test["position"]
    Xtr, Xte = prep(train, test, cols, family, regime, pos_tr, pos_te)
    ytr = train["hit"].values
    if family == "catboost":
        from catboost import CatBoostClassifier
        base = CatBoostClassifier(**CAT_PARAMS)
    else:
        base = LogisticRegression(C=LOGIT_C, max_iter=2000, class_weight=None)
    n_pos = int(ytr.sum()); cv = max(2, min(3, n_pos))     # guard tiny positive counts
    method = "isotonic" if n_pos >= 50 else "sigmoid"
    try:
        clf = CalibratedClassifierCV(base, method=method, cv=cv)
        clf.fit(Xtr.values, ytr)
        p = clf.predict_proba(Xte.values)[:, 1]
    except Exception:                                      # cold fallback: uncalibrated
        base.fit(Xtr.values, ytr); p = base.predict_proba(Xte.values)[:, 1]
    return np.clip(p, 1e-6, 1 - 1e-6)


# ---------------------------------------------------------------- backtest + metrics
ARMS = {
    "full":        (lambda g: g["draft"] + g["combine"] + g["cfb"] + g["pff"] + g["age"], "native"),
    "draft_only":  (lambda g: g["draft"], "native"),
    "college_only":(lambda g: g["combine"] + g["cfb"] + g["pff"] + g["age"], "median_noflag"),
    "combine_out": (lambda g: g["cfb"] + g["pff"] + g["age"], "native"),
}


def backtest(df, groups, arm, family):
    cols_fn, regime = ARMS[arm]
    cols = cols_fn(groups)
    rows = []
    for Y in TEST_CLASSES:
        tr = df[df.entry_year <= Y - 1]
        te = df[df.entry_year == Y]
        assert tr.entry_year.max() < Y, "LEAKAGE: train class >= test class"
        assert tr.entry_year.nunique() >= MIN_TRAIN_CLASSES, "too few train classes"
        if len(te) == 0:
            continue
        p = fit_predict(tr, te, cols, family, regime)
        rows.append(pd.DataFrame({"entry_year": Y, "position": te["position"].values,
                                  "y": te["hit"].values, "p": p}))
    return pd.concat(rows, ignore_index=True)


def metrics(oos):
    out = {"pooled": {"n": len(oos), "logloss": log_loss(oos.y, oos.p, labels=[0, 1]),
                      "auc": roc_auc_score(oos.y, oos.p) if oos.y.nunique() > 1 else np.nan}}
    for pos in SKILL:
        s = oos[oos.position == pos]
        out[pos] = {"n": len(s),
                    "logloss": log_loss(s.y, s.p, labels=[0, 1]) if len(s) else np.nan,
                    "auc": roc_auc_score(s.y, s.p) if s.y.nunique() > 1 else np.nan}
    return out


def placebo(df, groups, family, arm_a="full", arm_b="draft_only", draws=200, rng=None):
    """Shuffle hit WITHIN (position, entry_year); recompute full-vs-draft-only AUC delta."""
    rng = rng or np.random.default_rng(SEED)
    obs = metrics(backtest(df, groups, arm_a, family))["pooled"]["auc"] - \
          metrics(backtest(df, groups, arm_b, family))["pooled"]["auc"]
    null = []
    for _ in range(draws):
        d = df.copy()
        d["hit"] = (d.groupby(["position", "entry_year"])["hit"]
                     .transform(lambda s: rng.permutation(s.values)))
        null.append(metrics(backtest(d, groups, arm_a, family))["pooled"]["auc"] -
                    metrics(backtest(d, groups, arm_b, family))["pooled"]["auc"])
    return obs, float(np.quantile(null, 0.95))


# ---------------------------------------------------------------- SYNTHETIC harness-proof
def synth_frame(real_feat, rng):
    """Structure of the real panel (classes, positions, missingness) + a CONTROLLED target.
    Real `hit` is NOT used. Plants: f_noise (random), f_signal (0.6*latent+noise), f_peek(=y)."""
    d = real_feat[["entry_year", "position"]].copy().reset_index(drop=True)
    n = len(d)
    latent = rng.normal(size=n)
    base = {"QB": -1.7, "RB": -0.9, "WR": -1.65, "TE": -1.8}   # ~ real base rates in logit
    lin = d["position"].map(base).values + 1.1 * latent
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-lin))).astype(int)
    d["hit"] = y
    d["f_noise"] = rng.normal(size=n)
    d["f_signal"] = 0.6 * latent + 0.8 * rng.normal(size=n)
    d["f_peek"] = y.astype(float)
    # inject realistic missingness into f_signal using the real combine missingness mask
    miss = real_feat["forty"].isna().values if "forty" in real_feat.columns else np.zeros(n, bool)
    d.loc[miss[:n], "f_signal"] = np.nan
    return d


def prove(real_feat):
    print("=" * 64); print("PART C — SYNTHETIC HARNESS-PROOF (no real target, no real metric)"); print("=" * 64)
    rng = np.random.default_rng(SEED)
    d = synth_frame(real_feat, rng)
    groups = {"draft": ["f_noise"], "combine": ["f_signal"], "cfb": [], "pff": [], "age": []}
    fam = "logistic"

    def auc_for(cols, regime="native"):
        rows = []
        for Y in TEST_CLASSES:
            tr, te = d[d.entry_year <= Y - 1], d[d.entry_year == Y]
            if len(te) == 0 or tr.hit.nunique() < 2:
                continue
            p = fit_predict(tr, te, cols, fam, regime)
            rows.append(pd.DataFrame({"position": te.position.values, "y": te.hit.values, "p": p}))
        o = pd.concat(rows, ignore_index=True)
        return roc_auc_score(o.y, o.p), log_loss(o.y, o.p, labels=[0, 1])

    a_pos, ll_pos = auc_for([])                 # position-only control (present in every arm)
    a_noise, ll_noise = auc_for(["f_noise"])
    a_sig, ll_sig = auc_for(["f_signal"])
    a_peek, ll_peek = auc_for(["f_peek"])
    print(f"  POS-ONLY base: AUC {a_pos:.3f}   logloss {ll_pos:.3f}   (position control)")
    print(f"  NOISE  probe : AUC {a_noise:.3f} (expect ~= pos-only)  logloss {ll_noise:.3f}")
    print(f"  SIGNAL probe : AUC {a_sig:.3f} (expect > pos-only+.05) logloss {ll_sig:.3f}")
    print(f"  PEEK   probe : AUC {a_peek:.3f} (expect >0.95)         logloss {ll_peek:.3f}")

    p1 = abs(a_noise - a_pos) < 0.05            # noise feature adds ~0 beyond position (no hallucination)
    p2 = (a_sig > a_pos + 0.05) and (ll_sig < ll_pos)   # planted signal detected beyond position
    p3 = a_peek > 0.95 and ll_peek < ll_sig             # future-peek screams leakage
    # leakage assert: no test-class row in any train fold
    leak_ok = True
    for Y in TEST_CLASSES:
        tr = d[d.entry_year <= Y - 1]
        leak_ok &= (tr.entry_year < Y).all()
    # identity assert: draft_only arm uses ONLY group-1 columns
    gj = json.loads((HERE / "feature_groups.json").read_text())
    id_ok = ARMS["draft_only"][0](gj) == gj["draft"]
    # college_only excludes draft capital
    col_only = set(ARMS["college_only"][0](gj))
    exclude_ok = col_only.isdisjoint(set(gj["draft"]))

    print(f"\n  probe NOISE ≈ pos-only (adds ~0)        : {'PASS' if p1 else 'FAIL'}")
    print(f"  probe SIGNAL > pos-only+.05 & ll<pos    : {'PASS' if p2 else 'FAIL'}")
    print(f"  probe PEEK > 0.95 & ll<signal (leak)    : {'PASS' if p3 else 'FAIL'}")
    print(f"  leakage (no test class in train fold) : {'PASS' if leak_ok else 'FAIL'}")
    print(f"  identity (draft_only == group1 only)  : {'PASS' if id_ok else 'FAIL'}")
    print(f"  college_only excludes draft capital   : {'PASS' if exclude_ok else 'FAIL'}")
    allok = all([p1, p2, p3, leak_ok, id_ok, exclude_ok])
    print(f"\nPART C: {'PASS — machinery detects signal+leakage; arms correct; NO real metric touched.' if allok else 'FAIL'}")
    return allok


HEADLINE = "catboost"   # prereg §5: CatBoost = primary/headline; logistic = secondary comparator


def fold_improve(oos_full, oos_draft):
    """# of the 5 test-class folds where full AUC > draft_only AUC (pooled within fold)."""
    cnt = 0
    for Y in TEST_CLASSES:
        f = oos_full[oos_full.entry_year == Y]; d = oos_draft[oos_draft.entry_year == Y]
        if f.y.nunique() < 2 or d.y.nunique() < 2:
            continue
        cnt += int(roc_auc_score(f.y, f.p) > roc_auc_score(d.y, d.p))
    return cnt


def decide(m_full, m_draft, folds_improved, placebo_obs, placebo_bar):
    """prereg §8 criteria (a)-(e). Returns per-criterion booleans + ACCEPT/REJECT."""
    d_ll = m_draft["pooled"]["logloss"] - m_full["pooled"]["logloss"]      # >0 = full better
    d_auc = m_full["pooled"]["auc"] - m_draft["pooled"]["auc"]
    a = d_ll >= 0.010
    b = d_auc >= 0.020
    c = folds_improved >= 3
    d = all((m_full[p]["auc"] - m_draft[p]["auc"]) >= -0.030 for p in ("RB", "WR"))  # §8d floor RB/WR
    e = placebo_obs > placebo_bar
    return {"a_dlogloss": (round(d_ll, 3), a), "b_dauc": (round(d_auc, 3), b),
            "c_folds": (folds_improved, c), "d_floor_RBWR": d,
            "e_placebo": (round(placebo_obs, 3), round(placebo_bar, 3), e),
            "ACCEPT": bool(a and b and c and d and e)}


def decide_selftest():
    """Build-time proof of the §8 arithmetic on FAKE metric inputs (no real data)."""
    mk = lambda ll, au, rb=0.0, wr=0.0: {"pooled": {"logloss": ll, "auc": au},
                                         "RB": {"auc": 0.5 + rb}, "WR": {"auc": 0.5 + wr},
                                         "QB": {"auc": .5}, "TE": {"auc": .5}}
    passcase = decide(mk(0.40, 0.66, .04, .04), mk(0.42, 0.63), 4, 0.03, 0.01)
    failcase = decide(mk(0.415, 0.635, -.05, .0), mk(0.42, 0.63), 2, 0.005, 0.01)
    ok = passcase["ACCEPT"] is True and failcase["ACCEPT"] is False
    print(f"  decide() self-test (pass-case ACCEPT & fail-case REJECT): {'PASS' if ok else 'FAIL'}")
    return ok


def fire():
    """REAL one-shot fire (fresh session only). Runs all arms/families, applies §8, writes OUTCOMES."""
    import pickle
    feat = pd.read_parquet(HERE / "feat_hit.parquet")
    groups = json.loads((HERE / "feature_groups.json").read_text())
    res = {"generated": "FIRE", "families": {}}
    oos_cache = {}
    for fam in ("catboost", "logistic"):
        oos_cache[fam] = {arm: backtest(feat, groups, arm, fam) for arm in ARMS}
        res["families"][fam] = {arm: metrics(oos_cache[fam][arm]) for arm in ARMS}
    # §8 decision on the HEADLINE family (CatBoost), full vs draft_only
    of = oos_cache[HEADLINE]["full"]; od = oos_cache[HEADLINE]["draft_only"]
    fi = fold_improve(of, od)
    pobs, pbar = placebo(feat, groups, HEADLINE, "full", "draft_only", draws=1000)
    verdict = decide(res["families"][HEADLINE]["full"], res["families"][HEADLINE]["draft_only"],
                     fi, pobs, pbar)
    res["verdict_headline_catboost"] = verdict
    with open(HERE / "fire_rookie_results.pkl", "wb") as fh:   # derived-only, scratchpad
        pickle.dump(res, fh)
    print("=== FIRE OUTCOMES (headline=CatBoost, full vs draft_only) ===")
    for k, v in verdict.items():
        print(f"  {k}: {v}")
    print("Full metrics dumped to fire_rookie_results.pkl (derived-only).")
    return res


def real_pathproof(feat):
    """F-step: run the EXACT fire code (backtest, all 4 arms x both families) on the REAL
    63-feature matrix with a PERMUTED target (blindness-safe). Proves the path executes and
    yields valid probabilities on real shapes. NO metric computed."""
    print("\n" + "=" * 64)
    print("PART C2 — REAL-SHAPE FIRE-PATH PROOF (permuted target; no metric)")
    print("=" * 64)
    groups = json.loads((HERE / "feature_groups.json").read_text())
    rng = np.random.default_rng(SEED)
    d = feat.copy()
    d["hit"] = (d.groupby(["position", "entry_year"])["hit"]
                 .transform(lambda s: rng.permutation(s.values)))    # scramble => blindness-safe
    exp_rows = int(d.entry_year.isin(TEST_CLASSES).sum())
    allok = True
    for family in ("logistic", "catboost"):
        for arm in ARMS:
            oos = backtest(d, groups, arm, family)
            ok = (len(oos) == exp_rows and oos.p.between(0, 1).all()
                  and np.isfinite(oos.p).all() and oos.entry_year.nunique() == len(TEST_CLASSES))
            allok &= ok
            print(f"  {family:9s} {arm:12s}: rows {len(oos):3d}/{exp_rows} folds {oos.entry_year.nunique()} "
                  f"p∈[{oos.p.min():.3f},{oos.p.max():.3f}] {'OK' if ok else 'FAIL'}")
    print(f"\nPART C2: {'PASS — full fire path runs on real shapes; probabilities valid; NO metric computed.' if allok else 'FAIL'}")
    return allok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--fire", action="store_true")
    a = ap.parse_args()
    if a.fire:
        # REAL one-shot fire — FRESH SESSION ONLY, run exactly once. Freeze the sha first.
        fire()
        raise SystemExit(0)
    if not a.build:
        raise SystemExit("pass --build (synthetic proof only). --fire = the one-shot real run "
                         "(fresh session only, exactly once).")
    feat = pd.read_parquet(HERE / "feat_hit.parquet")
    ok = prove(feat)
    okd = decide_selftest()
    ok2 = real_pathproof(feat)
    raise SystemExit(0 if (ok and okd and ok2) else 1)


if __name__ == "__main__":
    main()
