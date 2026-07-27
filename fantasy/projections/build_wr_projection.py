"""WR SEASON-TOTAL half-PPR PROJECTION — BUILD under committed prereg
PREREG_wr_projection_2026-07-21.md.

REUSES the position-agnostic RB engine by IMPORT (build_rb_projection) — season_total_target,
nested_select, walk_forward, fit_final_model, _prep, _grid, _score_bundle, metrics, FAMILIES, the 32-col
veteran pool, and the rookie draft/age/combine/landing lists. Defines only WR-specific assembly: a WR
frozen-matrix twin (position=='WR' + pff_receiving) and the WR feature pools. **build_rb_projection.py is
NOT modified.** NO depth_rank in either bucket. (The carry-forward lesson was originally recorded as
"nflreadpy depth charts end at 2024"; that premise was FALSE — corrected 2026-07-26, the 2025+ data exists
under a new ESPN schema. The exclusion stands on deploy-realism evidence, not on data absence. This build
never joined depth charts at all, so nothing here changes.)

MODES  --assemble | --walk-forward | --ship  (mirror the RB build).

Interpreter: AI_hedge_fund venv. rookie_ppg_model.pkl untouched. NO parquet / raw-PFF in the repo
(PFF-derived WR matrix regenerated in TEMP scratch; only derived CSVs written to results/).
"""
import sys, os, argparse, shutil, subprocess, tempfile
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_rb_projection as B                       # the RB engine (reused by import; NOT modified)
from rookie_deploy_recovery import recover_missing_deploy_profiles, assert_drafted_deploy_profiles
from build_rb_projection import (                     # position-agnostic engine + shared constants/lists
    season_total_target, nested_select, walk_forward, fit_final_model, _prep, _score_bundle,
    metrics_block, _mae, _rmse, _rank, VET_FEATS, ROOK_DRAFT, ROOK_AGE, ROOK_COMBINE, ROOK_LAND,
    SEED, TEST_SEASONS, DEPLOY, MAXOBS, norm_name, SEAS, HARNESS, MODELS_DIR, RESULTS_DIR,
    ROOKIE_PPG_MD5, _md5, report_walkforward, report_sleeper)

WR_SCRATCH = Path(os.environ.get("WR_SCRATCH",
    r"C:/Users/josep/AppData/Local/Temp/claude/c--Users-josep-Desktop-random-stuff-cowork-OS/"
    r"a0db9953-ac7c-4009-99e9-0c070fb2e7da/scratchpad/wr_projection"))
WR_SCRATCH.mkdir(parents=True, exist_ok=True)

# ---- WR feature pools (prereg §3) — NO depth_rank ----
WR_VET_ALL = list(VET_FEATS)                           # the same 32-col season_dataset pool as RB veterans
WR_CFB = ["cfb_final_dom", "cfb_best_dom", "cfb_scrim_ypg", "cfb_rec_ypg", "cfb_rec_pg", "cfb_ypr",
          "cfb_final_recshare", "cfb_career_scrim_yds", "cfb_career_scrim_td", "cfb_seasons",
          "cfb_breakout_class"]                        # receiving-oriented cfb slice (excludes id/metadata + rushing)
WR_PFF = ["pff_receiving_grades_offense", "pff_receiving_grades_pass_route", "pff_receiving_yprr",
          "pff_receiving_avg_depth_of_target", "pff_receiving_contested_catch_rate",
          "pff_receiving_drop_rate", "pff_receiving_yards_after_catch_per_reception",
          "pff_receiving_targeted_qb_rating", "pff_receiving_routes", "pff_receiving_receptions",
          "pff_receiving_yards", "pff_receiving_touchdowns", "pff_receiving_avoided_tackles"]
FROZEN_JOIN_WR = ROOK_COMBINE + WR_CFB + WR_PFF        # cols sourced from the frozen matrix (WR slice)
WR_ROOK_ALL = ROOK_DRAFT + ROOK_AGE + ROOK_COMBINE + WR_CFB + WR_PFF + ROOK_LAND


def frozen_wr_matrix():
    """WR twin of build_rb_projection.frozen_rb_matrix: regenerate the FROZEN hit-model matrix in a temp
    dir (PFF-derived parquet never touches the repo), return the WR slice keyed by gsis/norm_name."""
    scr = Path(tempfile.mkdtemp(prefix="wr_frozen_"))
    for f in ("assemble_panel.py", "assemble_features.py", "feature_groups.json", "feature_cols.csv"):
        shutil.copy2(HARNESS / f, scr / f)
    for script in ("assemble_panel.py", "assemble_features.py"):
        r = subprocess.run([sys.executable, str(scr / script)], cwd=scr, capture_output=True, text=True)
        print(f"    [{script}] {(r.stdout.strip().splitlines() or [r.stderr[-300:]])[-1]}")
        assert r.returncode == 0, f"{script} failed:\n{r.stderr[-1200:]}"
    fh = pd.read_parquet(scr / "feat_hit.parquet"); fs = pd.read_parquet(scr / "feat_scoring.parquet")
    assert len(fh) == 712 and int(fh.hit.sum()) == 135, "frozen panel != 712/135"
    frz = pd.concat([fh, fs], ignore_index=True)
    frz = frz[frz["position"].astype(str) == "WR"].copy()
    missing = [c for c in FROZEN_JOIN_WR if c not in frz.columns]
    assert not missing, f"frozen WR matrix missing expected cols: {missing}"
    keep = ["gsis_id", "norm_name", "position", "entry_year"] + FROZEN_JOIN_WR
    frz = frz[[c for c in keep if c in frz.columns]].copy()
    shutil.rmtree(scr, ignore_errors=True)
    return frz


def assemble():
    sd = pd.read_csv(SEAS / "season_dataset_2014_2026.csv")
    wr = sd[sd["position"] == "WR"].copy()
    wr["log_pick"] = np.log(wr["draft_pick"].clip(lower=1))
    tgt = season_total_target()
    wr = wr.merge(tgt, on=["player_id", "season"], how="left")
    pre = wr["season"] <= MAXOBS
    wr.loc[pre, "y"] = wr.loc[pre, "y"].fillna(0.0)               # <=2025 missing => 0; 2026 => NaN
    vet = wr[wr["is_rookie"] == 0].copy()
    rook = wr[wr["is_rookie"] == 1].copy()

    frz = frozen_wr_matrix()
    frz_g = frz.drop(columns=["norm_name", "position", "entry_year"]).drop_duplicates("gsis_id")
    rook = rook.merge(frz_g, left_on="player_id", right_on="gsis_id", how="left")
    rook = rook.drop(columns=[c for c in ["gsis_id"] if c in rook.columns])
    need = rook[FROZEN_JOIN_WR].isna().all(axis=1)                # coalesce 2026 placeholder-gsis by name+pos
    frz_n = (frz.drop(columns=["gsis_id", "entry_year"])
                .drop_duplicates(subset=["norm_name", "position"], keep=False))
    if need.any():
        fill = rook.loc[need, ["norm_name", "position"]].merge(frz_n, on=["norm_name", "position"], how="left")
        fill.index = rook.loc[need].index
        for c in FROZEN_JOIN_WR:
            rook.loc[need, c] = fill[c].values
    rook = recover_missing_deploy_profiles(rook, FROZEN_JOIN_WR, "receiving", deploy_season=DEPLOY)
    assert_drafted_deploy_profiles(rook, FROZEN_JOIN_WR, deploy_season=DEPLOY)
    return vet, rook, wr


def run_asserts(vet, rook):
    print("=" * 74); print("STEP 2 — WR PRE-REGISTERED ASSERTS (no model metric)"); print("=" * 74)
    ok = True
    key_v = set(map(tuple, vet[["player_id", "season"]].to_numpy()))
    key_r = set(map(tuple, rook[["player_id", "season"]].to_numpy()))
    disj = key_v.isdisjoint(key_r)
    a1 = disj and bool((vet.is_rookie == 0).all() and (rook.is_rookie == 1).all())
    ok &= a1
    print(f"1. ROUTING: vet {len(vet)} + rookie {len(rook)} = {len(vet)+len(rook)} | (player,season) disjoint "
          f"{disj} | is_rookie clean -> {'PASS' if a1 else 'FAIL'}")

    talent_leak = [c for c in (WR_VET_ALL + WR_ROOK_ALL) if ("talent" in c or "efficiency" in c or c == "y")]
    # depth-CHART tokens only (carry-forward lesson) — NOT "avg_depth_of_target", which is college aDOT
    depth_leak = [c for c in (WR_VET_ALL + WR_ROOK_ALL) if ("depth_rank" in c or "depth_chart" in c or "depth_team" in c)]
    prior_derived = {"ppg_2yr", "ppg_3yr", "ppg_trend", "career_high_ppg"}
    knowable = {"age", "years_exp", "draft_round", "draft_pick", "vacated_target_share",
                "vacated_rush_share", "coach_changed", "qb_changed", "missed_prior_season"}
    same = [c for c in WR_VET_ALL if not (c.startswith("prior_") or c in prior_derived or c in knowable)]
    a2 = (not talent_leak) and (not same) and (not depth_leak)
    ok &= a2
    print(f"2. <=Y-1 LAG + NO-DEPTH: leak {talent_leak or 'none'} | non-prior {same or 'none'} | "
          f"depth-cols {depth_leak or 'none'}  -> {'PASS' if a2 else 'FAIL'}")

    from sklearn.ensemble import HistGradientBoostingRegressor
    v = vet[vet["season"] <= MAXOBS].dropna(subset=["y"]).copy()
    feats = [c for c in WR_VET_ALL if v[c].notna().sum() >= 30 and v[c].nunique(dropna=True) >= 3]
    tr, te = v[v.season < 2024], v[v.season == 2024]
    m = HistGradientBoostingRegressor(random_state=SEED, max_iter=200)
    m.fit(tr[feats].to_numpy(float), tr["y"].to_numpy(float))
    aligned = _rank(te["y"], m.predict(te[feats].to_numpy(float)))
    rng = np.random.default_rng(SEED)
    trs = tr.copy(); trs["y"] = trs.groupby("season")["y"].transform(lambda s: rng.permutation(s.values))
    ms = HistGradientBoostingRegressor(random_state=SEED, max_iter=200)
    ms.fit(trs[feats].to_numpy(float), trs["y"].to_numpy(float))
    shuf = _rank(te["y"], ms.predict(te[feats].to_numpy(float)))
    a3 = (aligned > 0.20) and (abs(shuf) < 0.15)
    ok &= a3
    print(f"3. SHUFFLE-LEAK probe (veteran, test 2024): aligned {aligned:+.3f} (>.20) | "
          f"within-season-shuffled {shuf:+.3f} (~0)  -> {'PASS' if a3 else 'FAIL'}")

    a4 = all(bool((vet[vet.season < Y].season < Y).all() and (rook[rook.season < Y].season < Y).all())
             for Y in TEST_SEASONS)
    ok &= a4
    print(f"4. WALK-FORWARD guard (train seasons < test, all folds): {'PASS' if a4 else 'FAIL'}")
    assert ok, "WR PRE-REGISTERED ASSERTS FAILED — STOP"
    print("\nSTEP 2 ASSERTS: PASS")


def coverage_report(vet, rook, wr):
    print("\n--- coverage / structure ---")
    print(f"VETERAN: rows {len(vet)} | 2021-2025 {len(vet[vet.season.isin(TEST_SEASONS)])} | 2026 {len(vet[vet.season==DEPLOY])} | features {len(WR_VET_ALL)}")
    print(f"ROOKIE:  rows {len(rook)} | 2021-2025 {len(rook[rook.season.isin(TEST_SEASONS)])} | 2026 {len(rook[rook.season==DEPLOY])} | features {len(WR_ROOK_ALL)}")
    g = wr.groupby("season").apply(lambda d: pd.Series({
        "rows": len(d), "vet": int((d.is_rookie == 0).sum()), "rook": int((d.is_rookie == 1).sum()),
        "y%": f"{d['y'].notna().mean()*100:.0f}", "sleeper%": f"{d['sleeper_pts_half_ppr'].notna().mean()*100:.0f}"}),
        include_groups=False)
    print(g.to_string())
    # DEPLOY-GAP CHECK (the depth_rank lesson generalized): veteran feature 2026 coverage vs 2021-2025
    print("\nDEPLOY-GAP CHECK — veteran features whose 2026 coverage << 2021-2025 (flag >20pp drop):")
    tr = vet[vet.season.isin(TEST_SEASONS)]; d26 = vet[vet.season == DEPLOY]
    flags = 0
    for c in WR_VET_ALL:
        ctr, c26 = tr[c].notna().mean(), d26[c].notna().mean()
        if ctr - c26 > 0.20:
            print(f"  ⚠ {c}: train {100*ctr:.0f}% -> 2026 {100*c26:.0f}%"); flags += 1
    print("  none (no hidden deploy-gap)" if flags == 0 else f"  {flags} flagged")
    print("\n2026 WR opportunity-feature coverage (provisional gap, prereg §6):")
    r26 = wr[(wr.season == DEPLOY)]
    for c in ["vacated_target_share", "prior_team_pass_rate", "coach_changed", "qb_changed", "adp_pos_rank"]:
        if c in r26.columns:
            nz = f" nonzero {100*(r26[c].fillna(0)!=0).mean():.0f}%" if c in ("coach_changed", "qb_changed") else ""
            print(f"  {c:22s}: present {100*r26[c].notna().mean():4.0f}%{nz}")


def report_2026(vp, rp):
    print("\n" + "=" * 74); print("STEP 3 — 2026 WR PROJECTIONS (face-validity; not integrated)"); print("=" * 74)
    both = pd.concat([vp.assign(grp="vet"), rp.assign(grp="rook")], ignore_index=True)
    both = both.sort_values("proj_2026", ascending=False).reset_index(drop=True)
    show = both[["player", "grp", "proj_2026", "sleeper_pts_half_ppr", "draft_pick"]].copy()
    show.columns = ["player", "grp", "proj", "sleeper", "pick"]
    print("\nTOP-15 projected WRs (2026):"); print(show.head(15).to_string(index=False))
    print("\nTOP-15 ROOKIE WRs (2026):")
    print(show[show.grp == "rook"].head(15).to_string(index=False))


def do_assemble():
    print("=" * 74); print("WR PROJECTION BUILD — ASSEMBLE (prereg PREREG_wr_projection_2026-07-21.md)"); print("=" * 74)
    vet, rook, wr = assemble()
    run_asserts(vet, rook)
    coverage_report(vet, rook, wr)
    vet.to_parquet(WR_SCRATCH / "vet.parquet", index=False)
    rook.to_parquet(WR_SCRATCH / "rook.parquet", index=False)
    print(f"\nwrote {WR_SCRATCH/'vet.parquet'} ({len(vet)}) + rook.parquet ({len(rook)}) [scratch only]")


def do_walk_forward():
    vet = pd.read_parquet(WR_SCRATCH / "vet.parquet"); rook = pd.read_parquet(WR_SCRATCH / "rook.parquet")
    print("=" * 74); print("WR PROJECTION BUILD — WALK-FORWARD + SLEEPER + 2026"); print("=" * 74)
    print("\nVETERAN nested-CV walk-forward:")
    vout, _ = walk_forward(vet, WR_VET_ALL, "vet")
    print("\nROOKIE nested-CV walk-forward:")
    rout, _ = walk_forward(rook, WR_ROOK_ALL, "rook")
    merged = pd.concat([vout.assign(grp="vet"), rout.assign(grp="rook")], ignore_index=True)
    merged.to_parquet(WR_SCRATCH / "walkforward_preds.parquet", index=False)
    report_walkforward(merged); report_sleeper(merged)
    print("\nfitting final models on all training data (<=2025) and scoring 2026...")
    v26 = vet[vet.season == DEPLOY].copy(); r26 = rook[rook.season == DEPLOY].copy()
    vb = fit_final_model(vet, WR_VET_ALL); rb_ = fit_final_model(rook, WR_ROOK_ALL)
    v26["proj_2026"] = np.round(_score_bundle(vb, v26), 1); r26["proj_2026"] = np.round(_score_bundle(rb_, r26), 1)
    print(f"  veteran final: {vb['family']} {vb['params']} (inner-MAE {vb['inner_cv_mae']:.3f})")
    print(f"  rookie  final: {rb_['family']} {rb_['params']} (inner-MAE {rb_['inner_cv_mae']:.3f})")
    pd.concat([v26.assign(grp="vet"), r26.assign(grp="rook")], ignore_index=True).to_parquet(
        WR_SCRATCH / "proj_2026.parquet", index=False)
    report_2026(v26, r26)
    print("\n" + "=" * 74); print("STOP 2 (HARD) — readout complete. NO board integration. Awaiting Joseph."); print("=" * 74)


def do_ship():
    import joblib
    print("=" * 74); print("WR PROJECTION BUILD — SHIP (final models + derived board artifacts)"); print("=" * 74)
    vet = pd.read_parquet(WR_SCRATCH / "vet.parquet"); rook = pd.read_parquet(WR_SCRATCH / "rook.parquet")
    wf = pd.read_parquet(WR_SCRATCH / "walkforward_preds.parquet")
    vb = fit_final_model(vet, WR_VET_ALL); rb_ = fit_final_model(rook, WR_ROOK_ALL)
    joblib.dump(vb, MODELS_DIR / "wr_veteran_model.pkl"); joblib.dump(rb_, MODELS_DIR / "wr_rookie_model.pkl")
    md5s = {"wr_veteran_model.pkl": _md5(MODELS_DIR / "wr_veteran_model.pkl"),
            "wr_rookie_model.pkl": _md5(MODELS_DIR / "wr_rookie_model.pkl")}
    print(f"  veteran deploy: {vb['family']} {vb['params']} (inner-MAE {vb['inner_cv_mae']:.3f})")
    print(f"  rookie  deploy: {rb_['family']} {rb_['params']} (inner-MAE {rb_['inner_cv_mae']:.3f})")

    v26 = vet[vet.season == DEPLOY].copy(); r26 = rook[rook.season == DEPLOY].copy()
    v26["projection"] = np.round(_score_bundle(vb, v26), 1); r26["projection"] = np.round(_score_bundle(rb_, r26), 1)
    merged = pd.concat([v26, r26], ignore_index=True)
    merged["sleeper"] = merged["sleeper_pts_half_ppr"]
    merged["diff"] = np.round(merged["projection"] - merged["sleeper"], 1)
    cols = ["player_id", "player", "position", "team", "is_rookie", "draft_pick", "adp_pos_rank",
            "projection", "sleeper", "diff"]
    merged[cols].sort_values("projection", ascending=False).to_csv(RESULTS_DIR / "wr_projection_2026.csv", index=False)

    wfr = wf[(wf.grp == "rook") & (wf.season.isin([2024, 2025]))].copy()
    wfr["projection"] = np.round(wfr["pred"], 1)
    wfr = wfr.rename(columns={"season": "entry_class"})[["player", "entry_class", "projection", "sleeper"]]
    r26b = r26.rename(columns={"season": "entry_class"})[["player", "entry_class", "projection",
                                                          "sleeper_pts_half_ppr"]].rename(
        columns={"sleeper_pts_half_ppr": "sleeper"})
    bp = pd.concat([wfr, r26b], ignore_index=True)
    bp["norm_name"] = bp["player"].map(norm_name); bp["position"] = "WR"
    bp["diff"] = np.round(bp["projection"] - bp["sleeper"], 1)
    bp = bp[["norm_name", "position", "entry_class", "projection", "sleeper", "diff"]].drop_duplicates(
        ["norm_name", "position", "entry_class"])
    bp.to_csv(RESULTS_DIR / "wr_rookie_board_projection.csv", index=False)

    wf_out = wf[["season", "grp", "player_id", "player", "y", "pred", "sleeper", "model"]].copy()
    wf_out["pred"] = np.round(wf_out["pred"], 1)
    wf_out.to_csv(RESULTS_DIR / "wr_walkforward_predictions.csv", index=False)
    m = wf.dropna(subset=["y", "pred"]); both = m.dropna(subset=["sleeper"])
    rows = [dict(scope="projection_all", n=len(m), MAE=round(_mae(m.y, m.pred), 2), RMSE=round(_rmse(m.y, m.pred), 2), spearman=round(_rank(m.y, m.pred), 3)),
            dict(scope="projection_vs_sleeper_rows", n=len(both), MAE=round(_mae(both.y, both.pred), 2), RMSE=round(_rmse(both.y, both.pred), 2), spearman=round(_rank(both.y, both.pred), 3)),
            dict(scope="sleeper_vs_actual", n=len(both), MAE=round(_mae(both.y, both.sleeper), 2), RMSE=round(_rmse(both.y, both.sleeper), 2), spearman=round(_rank(both.y, both.sleeper), 3))]
    pd.DataFrame(rows).to_csv(RESULTS_DIR / "wr_sleeper_comparison.csv", index=False)

    assert _md5(SEAS / "models" / "rookie_ppg_model.pkl") == ROOKIE_PPG_MD5, "rookie_ppg_model.pkl CHANGED"
    for f in list(MODELS_DIR.glob("*")) + list(RESULTS_DIR.glob("*")):
        assert f.suffix != ".parquet", f"parquet written to repo: {f}"
    print(f"\nmodel md5s: " + " | ".join(f"{k}={v}" for k, v in md5s.items()))
    print("wrote models/wr_{veteran,rookie}_model.pkl + results/wr_{projection_2026,rookie_board_projection,"
          "walkforward_predictions,sleeper_comparison}.csv")
    print(f"rookie_ppg_model.pkl md5 UNCHANGED: {ROOKIE_PPG_MD5}")
    print(f"\n2026 WR rookie-board projections ({len(bp[bp.entry_class==2026])} class 2026):")
    print(bp[bp.entry_class == 2026].sort_values("projection", ascending=False).head(20).to_string(index=False))
    print("SHIP ARTIFACTS WRITTEN (derived only; no parquet / no raw PFF in repo).")


def do_refresh_deploy():
    """Re-score the deploy season with the existing final models; never retrain or rewrite pkls."""
    import joblib
    print("=" * 74); print("WR DEPLOY REFRESH — existing models only (no retrain)"); print("=" * 74)
    vet = pd.read_parquet(WR_SCRATCH / "vet.parquet"); rook = pd.read_parquet(WR_SCRATCH / "rook.parquet")
    paths = [MODELS_DIR / "wr_veteran_model.pkl", MODELS_DIR / "wr_rookie_model.pkl"]
    before = {p.name: _md5(p) for p in paths}
    vb, rb_ = (joblib.load(p) for p in paths)
    v26 = vet[vet.season == DEPLOY].copy(); r26 = rook[rook.season == DEPLOY].copy()
    v26["projection"] = np.round(_score_bundle(vb, v26), 1)
    r26["projection"] = np.round(_score_bundle(rb_, r26), 1)
    merged = pd.concat([v26, r26], ignore_index=True)
    merged["sleeper"] = merged["sleeper_pts_half_ppr"]
    merged["diff"] = np.round(merged["projection"] - merged["sleeper"], 1)
    cols = ["player_id", "player", "position", "team", "is_rookie", "draft_pick", "adp_pos_rank",
            "projection", "sleeper", "diff"]
    merged[cols].sort_values("projection", ascending=False).to_csv(RESULTS_DIR / "wr_projection_2026.csv", index=False)

    board_path = RESULTS_DIR / "wr_rookie_board_projection.csv"
    prior = pd.read_csv(board_path)
    prior = prior[pd.to_numeric(prior["entry_class"], errors="coerce") != DEPLOY]
    r26b = r26.rename(columns={"season": "entry_class"})[["player", "entry_class", "projection",
                                                              "sleeper_pts_half_ppr"]].rename(
        columns={"sleeper_pts_half_ppr": "sleeper"})
    r26b["norm_name"] = r26b["player"].map(norm_name); r26b["position"] = "WR"
    r26b["diff"] = np.round(r26b["projection"] - r26b["sleeper"], 1)
    board = pd.concat([prior, r26b[["norm_name", "position", "entry_class", "projection", "sleeper", "diff"]]],
                      ignore_index=True).drop_duplicates(["norm_name", "position", "entry_class"], keep="last")
    board.to_csv(board_path, index=False)
    assert before == {p.name: _md5(p) for p in paths}, "deploy refresh changed a model pkl"
    print(f"refreshed {len(r26)} 2026 rookie rows; model pkls unchanged: {before}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assemble", action="store_true")
    ap.add_argument("--walk-forward", dest="wf", action="store_true")
    ap.add_argument("--ship", action="store_true")
    ap.add_argument("--refresh-deploy", action="store_true")
    a = ap.parse_args()
    if a.assemble: do_assemble()
    elif a.wf: do_walk_forward()
    elif a.ship: do_ship()
    elif a.refresh_deploy: do_refresh_deploy()
    else: raise SystemExit("pass --assemble, --walk-forward, or --ship")


if __name__ == "__main__":
    main()
