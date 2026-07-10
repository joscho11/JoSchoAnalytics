"""A4 extension gate (PREREGISTRATION.md Amendments 1-3): SEEN panels only.

Compares corrected-only (2014+) vs corrected+extended (2002+) walk-forward
Model A (frozen A1/A3 config, RB/WR/TE) on the 2020-2025 and 2016-2019 panels,
then applies the D2 rule verbatim:
  PASS iff (a) delta pooled rho 2020-2025 >= +0.010
       AND (b) delta pooled rho 2016-2019 >= -0.010
       AND (c) no position's delta on 2020-2025 < -0.030.

HARD FENCE: asserts no evaluation season precedes 2016. The pre-registered TE
gate seasons (2010-2015) are never predicted or scored here. Training folds may
consume 2002+ rows as history; that reveals nothing about 2010-2015 skill.

Also prints the pre-declared NON-GATING diagnostic: importance of era-bound
features (snap share / air yards / adot / target share) in the earliest fold.

Run:  python fantasy/seasonal_projections/extension_gate.py
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase0_benchmark as pb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
POS  = ["RB", "WR", "TE"]                       # QB dropped (Amendment 2)
OUT  = HERE / "extension_gate_results.json"

for _title, _seasons in pb.PANELS.items():      # hard fence
    assert min(_seasons) >= 2016, f"panel {_title} would touch pre-2016 seasons"


def run(csv_name):
    pb.DATA = HERE / csv_name
    df = pb.assemble()
    df["model_wf"]   = pb.walk_forward_model(df) * 17
    df["finish_all"] = pb.finish_ranks(df)
    pool = df[df["adp"].notna()].copy()
    pool["adp_overall"] = pool.groupby("season")["adp"].rank(method="first")
    pool = pool[pool["adp_overall"] <= pb.POOL_SIZE]
    assert pool[pool.model_wf.notna()].season.min() >= 2016, "predicted a fenced season"
    res = {}
    for title, seasons in pb.PANELS.items():
        res[title] = pb.eval_source(pool[pool["season"].isin(seasons)],
                                    "model_wf", False, positions=POS)
    return res, df


def diagnostic(df):
    """Non-gating: era-bound feature importance in the earliest fold (t=2016)."""
    from lightgbm import LGBMRegressor
    harness_cols = {"actual_pts", "adp", "ffc_adp", "ecr", "naive_pts", "naive_ppg17",
                    "age_curve", "model_wf", "finish_all", "adp_overall"}
    feats = [c for c in df.columns if c not in pb.EXCLUDE and c not in harness_cols]
    era_feats = ["prior_snap_share_pg", "prior_air_yards_share", "prior_adot", "prior_target_share"]
    print("\n-- DIAGNOSTIC (non-gating): era-bound feature importance, fold t=2016 "
          "(train 2002-2015) --")
    print(f"  {'pos':4} " + " ".join(f"{f.replace('prior_',''):>16}" for f in era_feats)
          + "   (split-importance rank / total feats)")
    for pos in POS:
        tr = df[(df.season < 2016) & df.target_ppg.notna() & (df.position == pos)]
        m = LGBMRegressor(**pb.LGBM_PARAMS)
        m.fit(tr[feats], tr.target_ppg, sample_weight=tr.sample_weight)
        imp = pd.Series(m.feature_importances_, index=feats).rank(ascending=False, method="min")
        print(f"  {pos:4} " + " ".join(f"{int(imp[f]):>13d}/{len(feats)}" for f in era_feats))


def main():
    print("=== corrected+extended (2002+) ===")
    ext, df_ext = run("season_dataset_2002_2025.csv")

    base = json.load(open(HERE / "phase0_benchmark_results.json"))  # corrected-only, commit 5b846fd
    rows, deltas = [], {}
    for title in pb.PANELS:
        for pos in POS:
            b = base[title]["model_wf"][pos]["rho"]
            e = ext[title][pos]["rho"]
            rows.append((title, pos, b, e, e - b))
        bp = np.mean([base[title]["model_wf"][p]["rho"] for p in POS])
        ep = np.mean([ext[title][p]["rho"] for p in POS])
        deltas[title] = {"pooled_base": bp, "pooled_ext": ep, "pooled_delta": ep - bp}

    print(f"\n{'panel':26} {'pos':4} {'corrected':>10} {'extended':>9} {'delta':>8}")
    for title, pos, b, e, d in rows:
        print(f"{title:26} {pos:4} {b:10.3f} {e:9.3f} {d:+8.3f}")
    for title, d in deltas.items():
        print(f"{title:26} POOLED {d['pooled_base']:8.3f} {d['pooled_ext']:9.3f} "
              f"{d['pooled_delta']:+8.3f}")

    d2025 = round(deltas["2020-2025 (all sources)"]["pooled_delta"], 3)
    d1619 = round(deltas["2016-2019 (FFC ADP era)"]["pooled_delta"], 3)
    worst = round(min(e - b for t, p, b, e, _ in rows if t.startswith("2020")), 3)
    a = d2025 >= 0.010
    b_ = d1619 >= -0.010
    c = worst >= -0.030
    verdict = "PASS" if (a and b_ and c) else "FAIL"
    print(f"\nD2 rule: (a) d2020-25 {d2025:+.3f} >= +0.010: {a} | "
          f"(b) d2016-19 {d1619:+.3f} >= -0.010: {b_} | "
          f"(c) worst pos {worst:+.3f} >= -0.030: {c}")
    print(f"A4 EXTENSION GATE: {verdict}")

    OUT.write_text(json.dumps({"extended": ext, "deltas": deltas,
                               "rule": {"a": bool(a), "b": bool(b_), "c": bool(c)},
                               "verdict": verdict}, indent=2, default=float))
    print(f"wrote {OUT.name}")
    diagnostic(df_ext)
    return verdict


if __name__ == "__main__":
    main()
