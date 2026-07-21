"""Build the ROOKIE BOARD product (ships regardless — prereg §10; research REJECTED, not re-fired).

The hit-probability research question is ANSWERED (fired 2026-07-20, CLAIM REJECTED: college/athletic
do NOT beat draft capital; full CatBoost pooled OOS AUC 0.843 vs draft-only 0.838, placebo-null). Those
are the ONLY validity numbers this product cites. This script fits the SHIPPED scorer as the fired
model's architecture VERBATIM (CatBoost, full arm, frozen CAT_PARAMS, native-NaN, position dummies),
adds a display Platt/LOCO calibration (AUC is calibration-invariant → the fired 0.843 link holds),
scores the 2024–2026 classes, surfaces the existing rookie-year projection (rookie_ppg_model.pkl —
UNCHANGED, not retrained), joins the read-only talent score, and writes the board CSVs.

NO hyperparameter search, NO feature change, NO family swap, NO re-fire, NO fresh validity metric.
PFF-derived parquets are regenerated in a TEMP scratch dir and never enter the repo; only derived
per-rookie display values land in the public board CSVs (raw PFF season tables never do).

Run:  python fantasy/rookie/build_rookie_board.py
"""
import sys, json, shutil, subprocess, tempfile, hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from catboost import CatBoostClassifier
from sklearn.linear_model import LogisticRegression

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent                    # fantasy/rookie
HARNESS = HERE / "harness"
SEAS = HERE.parent / "seasonal_projections"
sys.path.insert(0, str(SEAS))
import rookie_features as rf                               # existing rookie-projection features
from _utils import norm_name                              # repo-consistent name normalization

MODELS = HERE / "models"; MODELS.mkdir(exist_ok=True)
BOARD = HERE / "board_data"; BOARD.mkdir(exist_ok=True)
ROOKIE_PPG_PKL = SEAS / "models" / "rookie_ppg_model.pkl"
ROOKIE_PPG_MD5 = "872467b2295fce27761f9e04da01b6e8"        # MUST be unchanged (surface, not retrain)
TALENT_CSV = HERE.parent / "talent" / "rookie_score_2026.csv"   # READ-ONLY

SKILL = ["QB", "RB", "WR", "TE"]
TRAIN_CLASSES = list(range(2015, 2024))                   # 2015-2023 (the 9 labeled classes)
SCORE_CLASSES = [2024, 2025, 2026]
SEED = 42
# frozen CAT_PARAMS — VERBATIM from harness.py (the fired architecture; do not change)
CAT_PARAMS = dict(iterations=250, depth=4, learning_rate=0.05, l2_leaf_reg=4.0,
                  loss_function="Logloss", random_seed=SEED, verbose=0, allow_writing_files=False)

DISCLOSURE = (
    "Backtested, not live-validated (2019-2023 hold-out classes). At this sample, college production "
    "and athletic testing added no measured edge beyond draft capital - the hit probability largely "
    "tracks draft position. First live test: end of the 2026 season. "
    "Harness one-shot (2019-2023): full-model AUC 0.843 vs draft-capital-only 0.838 (rejected the "
    "'beats draft capital' claim). QB and TE per-position numbers are underpowered - descriptive only."
)


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def regen_features_in_scratch():
    """Run the FROZEN assemble scripts in a temp dir so PFF-derived parquets never touch the repo."""
    scr = Path(tempfile.mkdtemp(prefix="rookie_board_"))
    for f in ("assemble_panel.py", "assemble_features.py", "feature_groups.json", "feature_cols.csv"):
        shutil.copy2(HARNESS / f, scr / f)
    py = sys.executable
    for script in ("assemble_panel.py", "assemble_features.py"):
        r = subprocess.run([py, str(scr / script)], cwd=scr, capture_output=True, text=True)
        tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-400:]
        print(f"  [{script}] {tail}")
        assert r.returncode == 0, f"{script} failed:\n{r.stderr[-800:]}"
    feat_hit = pd.read_parquet(scr / "feat_hit.parquet")
    feat_score = pd.read_parquet(scr / "feat_scoring.parquet")
    groups = json.loads((scr / "feature_groups.json").read_text())
    assert len(feat_hit) == 712 and int(feat_hit.hit.sum()) == 135, "panel != frozen 712/135"
    assert len(feat_score) == 235, f"scoring panel != 235 (got {len(feat_score)})"
    return feat_hit, feat_score, groups, scr


def prep_native(train_df, other_df, cols):
    """Harness native-NaN prep VERBATIM: features kept as-is (NaN), + position dummies, align cols."""
    Xtr = train_df[cols].reset_index(drop=True)
    Xot = other_df[cols].reset_index(drop=True)
    Dtr = pd.get_dummies(train_df["position"], prefix="pos").reset_index(drop=True)
    Dot = pd.get_dummies(other_df["position"], prefix="pos").reset_index(drop=True)
    Xtr = pd.concat([Xtr, Dtr], axis=1)
    Xot = pd.concat([Xot, Dot], axis=1).reindex(columns=Xtr.columns, fill_value=0)
    return Xtr, Xot


def prep_median_noflag(train_df, other_df, cols):
    """Harness COLLEGE-ONLY regime VERBATIM (prereg §5): within-position median fill (fit on
    TRAIN only), NO missingness flag, NO NaN routing, then position dummies. The college arm must
    NOT see informative missingness (missingness proxies draft capital — the §5 back-door close)."""
    Xtr = train_df[cols].reset_index(drop=True)
    Xot = other_df[cols].reset_index(drop=True)
    ptr = train_df["position"].reset_index(drop=True)
    pot = other_df["position"].reset_index(drop=True)
    med = {(p, c): Xtr.loc[ptr == p, c].median() for p in ptr.unique() for c in cols}

    def fill(X, pos):
        X = X.copy()
        for c in cols:
            for pc in pos.unique():
                m = (pos == pc)
                X.loc[m, c] = X.loc[m, c].fillna(med.get((pc, c), np.nan))
        return X.fillna(X.median(numeric_only=True))       # global backstop (harness _pos_median_fill)

    Xtr, Xot = fill(Xtr, ptr), fill(Xot, pot)
    Dtr = pd.get_dummies(ptr, prefix="pos")
    Dot = pd.get_dummies(pot, prefix="pos")
    Xtr = pd.concat([Xtr, Dtr], axis=1)
    Xot = pd.concat([Xot, Dot], axis=1).reindex(columns=Xtr.columns, fill_value=0)
    return Xtr, Xot


def _logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_shipped_scorer(feat_hit, cols, prep_fn=prep_native, arm="full"):
    """One fired ARM as a shipped scorer: CatBoost + frozen CAT_PARAMS + the arm's §5 missing-data
    regime (prep_fn) + Platt/LOCO display calibration. Identical method across arms; only cols +
    prep_fn differ (full/draft = prep_native native-NaN; college = prep_median_noflag)."""
    y = feat_hit["hit"].values
    oof_raw = np.full(len(feat_hit), np.nan)
    idx = feat_hit.reset_index(drop=True)
    for Y in TRAIN_CLASSES:                                  # leave-one-class-out OOF for the Platt fit
        tr = idx[idx.entry_year != Y]; va = idx[idx.entry_year == Y]
        Xtr, Xva = prep_fn(tr, va, cols)
        base = CatBoostClassifier(**CAT_PARAMS)
        base.fit(Xtr.values, tr["hit"].values)
        oof_raw[va.index.values] = base.predict_proba(Xva.values)[:, 1]
    platt = LogisticRegression(C=1e6, solver="lbfgs")
    platt.fit(_logit(oof_raw).reshape(-1, 1), y)
    oof_cal = platt.predict_proba(_logit(oof_raw).reshape(-1, 1))[:, 1]
    Xall, _ = prep_fn(idx, idx.head(1), cols)                # final base refit on ALL 9 classes
    base_all = CatBoostClassifier(**CAT_PARAMS)
    base_all.fit(Xall.values, y)
    bundle = {"base": base_all, "platt": platt, "feature_cols": list(Xall.columns),
              "arm": arm, "arm_cols": cols, "cat_params": CAT_PARAMS, "calibration": "platt_loco",
              "train_classes": TRAIN_CLASSES, "note": f"shipped {arm} scorer = fired {arm} arm arch"}
    oof = pd.DataFrame({"entry_year": idx.entry_year, "position": idx.position,
                        "y": y, "p_raw": oof_raw, "p_cal": oof_cal})
    return bundle, oof


def score(bundle, feat_hit, feat_score, cols, prep_fn=prep_native):
    _, Xsc = prep_fn(feat_hit, feat_score, cols)
    Xsc = Xsc.reindex(columns=bundle["feature_cols"], fill_value=0)   # align to trained column order
    raw = bundle["base"].predict_proba(Xsc.values)[:, 1]
    cal = bundle["platt"].predict_proba(_logit(raw).reshape(-1, 1))[:, 1]
    return 100.0 * cal


def surface_projection():
    """Surface the EXISTING rookie-year PPG model (no retrain; md5 asserted unchanged).

    Returned keyed by (norm_name, position, season) NOT gsis, because the brand-new 2026 class
    carries placeholder gsis in draft_picks (e.g. 'LOV121782') that don't match the real gsis in
    season_dataset — the name+position+class bridge is vintage-proof. Ambiguous keys are skipped."""
    assert _md5(ROOKIE_PPG_PKL) == ROOKIE_PPG_MD5, "rookie_ppg_model.pkl CHANGED — abort"
    d = joblib.load(ROOKIE_PPG_PKL)
    model, feat_cols = d["model"], d["feature_cols"]
    sd = pd.read_csv(SEAS / "season_dataset_2014_2026.csv")
    rk = sd[(sd.is_rookie == 1) & (sd.season.isin(SCORE_CLASSES))].copy()
    rk = rf.add_rookie_features(rk)                         # joins combine, casts dtypes
    for c in feat_cols:
        if c not in rk.columns:
            rk[c] = np.nan
    rk["proj_ppg"] = np.clip(model.predict(rk[feat_cols]), 0, None)
    rk["norm_name"] = rk["player"].map(norm_name)
    rk["position"] = rk["position"].astype(str)
    return rk[["player_id", "norm_name", "position", "season", "proj_ppg"]]


def unified_pff(df):
    pos = df["position"]
    g = lambda c: df[c] if c in df.columns else pd.Series(np.nan, index=df.index)
    grade = np.where(pos.isin(["WR", "TE"]), g("pff_receiving_grades_offense"),
             np.where(pos == "RB", g("pff_rushing_grades_run"), g("pff_passing_grades_pass")))
    eff = np.where(pos.isin(["WR", "TE"]), g("pff_receiving_yprr"),
           np.where(pos == "RB", g("pff_rushing_elusive_rating"), g("pff_passing_btt_rate")))
    return pd.Series(grade, index=df.index), pd.Series(eff, index=df.index)


DISPLAY = ["draft_pick", "age", "forty", "vertical", "broad_jump", "wt", "bmi", "speed_score",
           "cfb_final_dom", "cfb_scrim_ypg", "pff_grade", "pff_eff"]


def add_percentiles(board, refpop):
    """Within-position percentile of each display stat vs the 2015-2026 drafted-skill panel (refpop)."""
    for c in DISPLAY:
        pct = np.full(len(board), np.nan)
        for pos in SKILL:
            ref = refpop.loc[refpop.position == pos, c].dropna()
            m = (board.position == pos) & board[c].notna()
            if len(ref) and m.any():
                pct[m.values] = board.loc[m, c].map(lambda v: (ref <= v).mean() * 100.0).values
        board[f"pct_{c}"] = np.round(pct, 0)
    return board


def main():
    print("=" * 66); print("ROOKIE BOARD BUILD (product; research REJECTED, not re-fired)"); print("=" * 66)
    feat_hit, feat_score, groups, scr = regen_features_in_scratch()
    full_cols = groups["draft"] + groups["combine"] + groups["cfb"] + groups["pff"] + groups["age"]

    draft_cols = groups["draft"]
    college_cols = groups["combine"] + groups["cfb"] + groups["pff"] + groups["age"]
    # three fired arms as shipped scorers — identical method; only feature set + §5 regime differ
    ARMS_SPEC = [("full", full_cols, prep_native), ("draft", draft_cols, prep_native),
                 ("college", college_cols, prep_median_noflag)]
    md5s = {}
    feat_score = feat_score.copy()
    for arm, cols, pf in ARMS_SPEC:
        regime = "median-noflag(§5)" if pf is prep_median_noflag else "native-NaN"
        print(f"\nfitting {arm:7s} arm — CatBoost + frozen CAT_PARAMS + Platt/LOCO, regime {regime}, {len(cols)} feats...")
        b, oof = fit_shipped_scorer(feat_hit, cols, pf, arm)
        joblib.dump(b, MODELS / f"rookie_hit_model_{arm}.pkl")
        md5s[arm] = _md5(MODELS / f"rookie_hit_model_{arm}.pkl")
        feat_score[f"hit_prob_{arm}"] = np.round(score(b, feat_hit, feat_score, cols, pf), 1)
        if arm == "full":
            oof.to_csv(BOARD / "oof_predictions.csv", index=False)   # derived (y,p) only
    (MODELS / "rookie_hit_model.pkl").unlink(missing_ok=True)        # superseded by the 3 arm files
    feat_score["pff_grade"], feat_score["pff_eff"] = unified_pff(feat_score)

    # projection surface — COALESCE: real-gsis join (reliable for 2024/25), then name+position+class
    # bridge fallback only for still-missing rows (the placeholder-gsis 2026 seam). Skip ambiguous.
    feat_score = feat_score.copy()
    feat_score["position"] = feat_score["position"].astype(str)
    proj = surface_projection()
    pg = (proj[["player_id", "proj_ppg"]].dropna(subset=["player_id"])
              .drop_duplicates("player_id", keep=False).rename(columns={"player_id": "gsis_id"}))
    feat_score = feat_score.merge(pg, on="gsis_id", how="left")
    pn = (proj[["norm_name", "position", "season", "proj_ppg"]]
              .drop_duplicates(subset=["norm_name", "position", "season"], keep=False)
              .rename(columns={"proj_ppg": "proj_ppg_n"}))
    feat_score = feat_score.merge(pn, left_on=["norm_name", "position", "entry_year"],
                                  right_on=["norm_name", "position", "season"], how="left").drop(columns=["season"])
    feat_score["proj_ppg"] = feat_score["proj_ppg"].fillna(feat_score["proj_ppg_n"])
    feat_score = feat_score.drop(columns=["proj_ppg_n"])
    # talent (2026-only, READ-ONLY): same name+position bridge; skip ambiguous; never backfill
    tal = pd.read_csv(TALENT_CSV).copy()
    tal["norm_name"] = tal["display_name"].map(norm_name)
    tal["position"] = tal["position"].astype(str)
    tal = (tal[["norm_name", "position", "rookie_score"]].rename(columns={"rookie_score": "talent_score"})
              .drop_duplicates(subset=["norm_name", "position"], keep=False))       # skip ambiguous
    feat_score = feat_score.merge(tal, on=["norm_name", "position"], how="left")
    feat_score.loc[feat_score.entry_year != 2026, "talent_score"] = np.nan          # talent file is 2026-only

    # team/name from draft_picks
    import nflreadpy as nfl
    dp = nfl.load_draft_picks().to_pandas().dropna(subset=["gsis_id"]).drop_duplicates("gsis_id")
    dp = dp[["gsis_id", "pfr_player_name", "team"]].rename(columns={"pfr_player_name": "name"})
    feat_score = feat_score.merge(dp, on="gsis_id", how="left")

    # reference population for percentiles = 2015-2026 drafted-skill panel
    refpop = pd.concat([feat_hit, feat_score], ignore_index=True)
    refpop["pff_grade"], refpop["pff_eff"] = unified_pff(refpop)
    feat_score = add_percentiles(feat_score, refpop)

    hitcols = ["hit_prob_draft", "hit_prob_college", "hit_prob_full"]
    idcols = (["gsis_id", "name", "position", "team", "entry_year", "draft_round", "draft_pick"]
              + hitcols + ["proj_ppg", "talent_score"])
    board = feat_score[idcols + DISPLAY + [f"pct_{c}" for c in DISPLAY]].copy()
    board = board.rename(columns={"entry_year": "entry_class"})

    # structural asserts
    for h in hitcols:
        assert board[h].between(0, 100).all() and board[h].notna().all(), f"{h} out of [0,100] or NaN"
    assert len(board) == 235, f"board rows != 235 ({len(board)})"
    assert board.entry_class.isin(SCORE_CLASSES).all(), "non-scoring class in board"
    assert set(board.gsis_id).isdisjoint(set(feat_hit.gsis_id)), "training-class player leaked into board"
    assert _md5(ROOKIE_PPG_PKL) == ROOKIE_PPG_MD5, "rookie_ppg_model.pkl md5 changed"
    # the FULL arm must reproduce the already-shipped values (else the full arm wasn't reproduced -> HALT)
    ANCH = {"ashton jeanty": 88.4, "brock bowers": 78.9, "travis hunter": 78.5, "caleb williams": 28.2}
    bn = board.assign(nn=board.name.map(norm_name))
    for nm, ev in ANCH.items():
        g = bn.loc[bn.nn == nm, "hit_prob_full"]
        assert len(g) == 1 and abs(float(g.iloc[0]) - ev) < 0.05, \
            f"FULL ARM NOT REPRODUCED: {nm} got {float(g.iloc[0]) if len(g) else 'NA'} != shipped {ev}"

    for cls in SCORE_CLASSES:
        sub = board[board.entry_class == cls].sort_values("hit_prob_full", ascending=False)
        sub.to_csv(BOARD / f"rookie_board_{cls}.csv", index=False)
    (BOARD / "DISCLOSURE.md").write_text("# Rookie board disclosure (ships on every surface)\n\n" +
                                         DISCLOSURE + "\n")
    shutil.rmtree(scr, ignore_errors=True)

    print("\nmodel md5s: " + " | ".join(f"{a}={m}" for a, m in md5s.items()))
    print("wrote models/rookie_hit_model_{full,draft,college}.pkl, board_data/rookie_board_{2024,2025,2026}.csv,"
          " oof_predictions.csv, DISCLOSURE.md")
    print(f"rookie_ppg_model.pkl md5 UNCHANGED: {_md5(ROOKIE_PPG_PKL)}")
    print("STRUCTURAL ASSERTS PASS (full arm reproduces shipped anchors). No re-fire, no fresh validity metric.")
    # 3-column anchor readout
    print("\n=== 3-ARM ANCHOR READOUT (hit prob: Draft | College | Full) ===")
    show = pd.concat([pd.read_csv(BOARD / f"rookie_board_{c}.csv") for c in SCORE_CLASSES], ignore_index=True)
    show["nn"] = show["name"].map(norm_name)
    for nm in ("ashton jeanty", "brock bowers", "travis hunter", "jayden daniels", "jeremiyah love",
               "fernando mendoza", "caleb williams"):
        r = show[show.nn == nm]
        if len(r):
            x = r.iloc[0]
            print(f"  {x['name']:20s} [{int(x.entry_class)}] {x.position} pk{int(x.draft_pick):>3}  "
                  f"Draft {x.hit_prob_draft:5.1f} | College {x.hit_prob_college:5.1f} | Full {x.hit_prob_full:5.1f}")


if __name__ == "__main__":
    main()
