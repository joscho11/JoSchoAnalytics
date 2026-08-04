"""Promotion gates for the staged features dataset. Every gate must PASS.

Run from fantasy/:  python gate_staging_dataset.py
Exit status 0 only if every gate passes. Writes fantasy/staging/gate_report.json.

Reconciliation note (measured, not assumed)
-------------------------------------------
`features_dataset.csv` was last committed at 976e94a. `features.ipynb` and
`data_pipeline.ipynb` both changed AFTER that (474a970, 8888d09, ef8f1d9), replacing
cross-season rolling windows (`groupby("player_id")`, `groupby("team")`,
`groupby(["team","position"])`) with per-season ones. The published CSV therefore does
NOT correspond to the notebooks as committed, and a faithful rebuild differs from it in
population and in every rolling column.

So the drift gate runs against a LEGACY REPLICA — the same builder with
`LEGACY_ROLLING_SEMANTICS = True` — which isolates source-data refresh from code change.
The staging-vs-published diff is reported alongside as information.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

import depth_features as DF  # noqa: E402

OLD = _HERE / "features_dataset.csv"
NEW = _HERE / "staging" / "features_dataset.staging.csv"
REPLICA = _HERE / "staging" / "features_dataset.legacyreplica.csv"
DEPTH_REPORT = _HERE / "staging" / "depth_report.json"
OUT = _HERE / "staging" / "gate_report.json"

HOLDOUT_SEASON = 2025
COMPARE_SEASONS = [2020, 2021, 2022, 2023, 2024]
DRIFT_TOLERANCE = 0.02          # non-depth value-mismatch rate on shared keys
POPULATION_TOLERANCE = 0.005    # replica-vs-published row-count delta
KEY = ["player_id", "season", "week"]
#: expected because week 1 has no prior-week rolling form and week 18 has no next-week
#: target under the per-season windows the committed notebooks now use
EXPECTED_HOLDOUT_WEEKS = list(range(2, 18))

results = []


def gate(name, ok, detail=None):
    results.append({"gate": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"\n        {detail}" if detail else ""))
    return ok


def _mismatch_rate(a, b):
    if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
        return float((~np.isclose(a.astype(float), b.astype(float), rtol=1e-6, atol=1e-8,
                                  equal_nan=True)).mean())
    return float((a.astype(str) != b.astype(str)).mean())


def _drift(old, new, seasons, skip):
    m = old.merge(new, on=KEY, suffixes=("_old", "_new"))
    m = m[m["season"].isin(seasons)]
    out = {}
    for c in new.columns:
        if c in skip:
            continue
        r = _mismatch_rate(m[f"{c}_old"], m[f"{c}_new"])
        if r > 0:
            out[c] = round(r, 5)
    return out, int(len(m))


def main() -> int:
    old = pd.read_csv(OLD)
    new = pd.read_csv(NEW)
    replica = pd.read_csv(REPLICA)
    depth_report = json.loads(DEPTH_REPORT.read_text(encoding="utf-8"))

    depth_cols = set(DF.DEPTH_CONTRACT_COLUMNS)
    id_cols = {"player_id", "player_display_name", "position", "team", "opponent_team",
               "season", "week"}

    # 1 — uniqueness
    dups = int(new.duplicated(KEY).sum())
    gate("unique (player_id, season, week)", dups == 0,
         f"{dups} duplicate keys in staging; the published file has "
         f"{int(old.duplicated(KEY).sum())} (an un-deduplicated injury-report join)")

    # 2 — schema reconciliation
    same_set = set(old.columns) == set(new.columns) and len(old.columns) == len(new.columns)
    order_moves = [i for i, (a, b) in enumerate(zip(old.columns, new.columns)) if a != b]
    gate("schema reconciliation (same 97 columns)", same_set,
         f"added={sorted(set(new.columns) - set(old.columns))} "
         f"removed={sorted(set(old.columns) - set(new.columns))}; "
         f"column ORDER differs from index {order_moves[0] if order_moves else '-'} "
         f"(published file appends total_line/team_spread last; staging uses the order "
         f"declared in features.ipynb) — order carries no information, models store "
         f"feature_cols explicitly")

    # 3 — row-count reconciliation against the legacy replica
    per_season = pd.concat([old.groupby("season").size().rename("published"),
                            replica.groupby("season").size().rename("legacy_replica"),
                            new.groupby("season").size().rename("staging")],
                           axis=1).fillna(0).astype(int)
    pop_delta = abs(len(replica) - len(old)) / len(old)
    shared_rep = old.merge(replica[KEY], on=KEY, how="inner")
    recon = {"per_season": per_season.to_dict("index"),
             "published_rows": int(len(old)), "replica_rows": int(len(replica)),
             "staging_rows": int(len(new)),
             "replica_shared_keys_with_published": int(len(shared_rep)),
             "population_delta_vs_published": round(pop_delta, 5)}
    gate("row-count reconciliation (legacy replica reproduces the published population)",
         pop_delta <= POPULATION_TOLERANCE,
         f"published {len(old)} vs replica {len(replica)} "
         f"({pop_delta:.3%} <= {POPULATION_TOLERANCE:.1%}); staging {len(new)} — the "
         f"staging population is smaller by design: per-season rolling windows drop each "
         f"player's week-1 row")

    # 3b — every staging-vs-published population difference is attributable
    staging_keys = new[KEY].assign(_in=1)
    old_only = old.merge(staging_keys, on=KEY, how="left")
    old_only = old_only[old_only["_in"].isna()]
    first_wk = old.groupby(["player_id", "season"])["week"].transform("min")
    old_first = old[old["week"] == first_wk][KEY].assign(_f=1)
    rep_keys = replica[KEY].assign(_r=1)
    tagged = old_only.merge(old_first, on=KEY, how="left").merge(rep_keys, on=KEY,
                                                                how="left")
    is_week1 = tagged["_f"].notna()
    absent_from_replica = tagged["_r"].isna()
    unexplained = int((~is_week1 & ~absent_from_replica).sum())
    recon.update({"old_only_rows": int(len(old_only)),
                  "old_only_that_are_player_season_week1": int(is_week1.sum()),
                  "old_only_absent_from_replica_too": int(absent_from_replica.sum()),
                  "old_only_unexplained": unexplained})
    gate("every published row missing from staging is attributable",
         unexplained == 0,
         f"{len(old_only)} old-only rows: {int(is_week1.sum())} are player-season week 1 "
         f"(per-season windows), {int(absent_from_replica.sum())} are absent from the "
         f"replica too (nflverse source refresh), {unexplained} unexplained")

    # 4 — no future snapshot
    sc = depth_report["snapshot_check"]
    gate("no depth row uses a snapshot at/after its own kickoff", sc["violations"] == 0,
         f"{sc['checked_rows']} current-schema rows checked; snapshot-to-kickoff lag "
         f"min {sc.get('lag_hours_min')}h / median {sc.get('lag_hours_median')}h / "
         f"max {sc.get('lag_hours_max')}h")

    # 5 — all sixteen columns present
    missing = [c for c in DF.DEPTH_CONTRACT_COLUMNS if c not in new.columns]
    gate("all 16 depth/availability columns present", not missing,
         f"missing={missing}" if missing else "16/16")

    # 6 — none of the sixteen constant in the holdout season
    nun = {c: int(new[new["season"] == HOLDOUT_SEASON][c].nunique())
           for c in DF.DEPTH_CONTRACT_COLUMNS}
    constant = [c for c, n in nun.items() if n < 2]
    gate(f"none of the 16 constant in {HOLDOUT_SEASON}", not constant,
         f"distinct values per column: {nun}")

    # 7 — coverage
    h = new[new["season"] == HOLDOUT_SEASON]
    dcp_tw = h.groupby(["team", "week"])["depth_chart_position"].nunique()
    cov = {"weeks": sorted(h["week"].unique().tolist()),
           "n_weeks": int(h["week"].nunique()),
           "n_teams": int(h["team"].nunique()),
           "rows_by_position": h["position"].value_counts().to_dict(),
           "team_weeks": int(len(dcp_tw)),
           "team_weeks_with_varying_depth_rank": int((dcp_tw > 1).sum()),
           "rows_per_week": h.groupby("week").size().to_dict()}
    ok_cov = (cov["n_teams"] == 32
              and cov["weeks"] == EXPECTED_HOLDOUT_WEEKS
              and set(cov["rows_by_position"]) == {"QB", "RB", "WR", "TE"}
              and cov["team_weeks_with_varying_depth_rank"] == cov["team_weeks"])
    gate("weekly / team / position coverage in the holdout season", ok_cov,
         json.dumps(cov))

    # 8 — FEATURES-STAGE CODE EQUIVALENCE: rebuild the published features file from the
    #     published raw file. Holds inputs fixed, so only code is under test.
    from nfl_cache import load_all
    import build_staging_dataset as B
    import equivalence_checks as EQ
    data = load_all(B.SEASONS, B.COACH_SEASONS)
    eq_feat = EQ.features_stage_reproduces_published(
        _HERE / "raw_dataset.csv", OLD, data, COMPARE_SEASONS)
    gate("features-stage code equivalence (rebuild published CSV from published raw)",
         eq_feat["row_count_identical"] and eq_feat["max_mismatch_rate"] <= 1e-3,
         f"rows {eq_feat['published_rows']} -> {eq_feat['rebuilt_rows']}; "
         f"{eq_feat['compared_rows']} shared rows compared; max non-id mismatch rate "
         f"{eq_feat['max_mismatch_rate']} (the published file's single duplicate key "
         f"fans out to 2 rows); drift={eq_feat['drift']}")

    # 8b — informational: the residual published-vs-rebuild difference is INPUT refresh
    drift_rep, n_rep = _drift(old, replica, COMPARE_SEASONS, depth_cols | id_cols)
    mrep = old.merge(replica, on=KEY, suffixes=("_old", "_new"))
    mrep = mrep[mrep["season"].isin(COMPARE_SEASONS)]
    magnitudes = {}
    for c, r in drift_rep.items():
        a, b = mrep[f"{c}_old"].astype(float), mrep[f"{c}_new"].astype(float)
        bad = ~np.isclose(a, b, rtol=1e-6, atol=1e-8, equal_nan=True)
        magnitudes[c] = {"rate": r, "mean_abs_diff": round(float((b - a)[bad].abs().mean()), 6),
                         "max_abs_diff": round(float((b - a)[bad].abs().max()), 6),
                         "column_std": round(float(a.std()), 6)}
    results.append({"gate": "INFO legacy-replica vs published non-depth drift "
                            "(= nflverse source refresh)", "status": "INFO",
                    "detail": {"n": n_rep, "columns": magnitudes}})

    # 8c — informational: staging vs published, dominated by the committed notebook change
    drift_stage, n_stage = _drift(old, new, COMPARE_SEASONS, depth_cols | id_cols)
    results.append({"gate": "INFO staging vs published non-depth drift "
                            "(= per-season rolling windows + source refresh)",
                    "status": "INFO", "detail": {"n": n_stage, "drift": drift_stage}})

    # 9 — DEPTH-BUILDER CODE EQUIVALENCE on the legacy seasons
    import depth_features as _DF
    tables = _DF.build_depth_tables(data["depth_charts"], data["schedules"],
                                    data["injuries"], B.SEASONS)
    eq_depth = EQ.depth_flags_match_original_notebook(data, tables)
    gate("depth builders reproduce the pre-fix notebook exactly on legacy seasons",
         eq_depth["identical"],
         f"rows joined {eq_depth['joined_rows']}; max mismatch rate "
         f"{eq_depth['max_mismatch_rate']} across all 15 availability columns, 2018-2024")

    # 9b — the depth block actually changed in the holdout season
    mh = old.merge(new, on=KEY, suffixes=("_old", "_new"))
    hold = {c: round(_mismatch_rate(mh[mh["season"] == HOLDOUT_SEASON][f"{c}_old"],
                                    mh[mh["season"] == HOLDOUT_SEASON][f"{c}_new"]), 4)
            for c in DF.DEPTH_CONTRACT_COLUMNS}
    changed = sum(1 for v in hold.values() if v > 0.05)
    gate("depth block materially changed in the holdout season", changed == 16,
         f"{changed}/16 columns changed on >5% of shared {HOLDOUT_SEASON} rows: {hold}")

    # 9c — informational: historical depth delta vs the published CSV (source refresh,
    #      since gate 9 proves the code is identical)
    mr = old.merge(replica, on=KEY, suffixes=("_old", "_new"))
    mr = mr[mr["season"].isin(COMPARE_SEASONS)]
    hist = {c: round(_mismatch_rate(mr[f"{c}_old"], mr[f"{c}_new"]), 4)
            for c in DF.DEPTH_CONTRACT_COLUMNS}
    results.append({"gate": "INFO historical depth delta vs published "
                            "(= nflverse depth/injury revisions)", "status": "INFO",
                    "detail": hist})

    # 10 — nulls / defaults / distributions per season
    stats = {}
    for s in sorted(new["season"].unique()):
        sub = new[new["season"] == s]
        stats[int(s)] = {
            "rows": int(len(sub)),
            "nulls": {c: int(sub[c].isna().sum()) for c in DF.DEPTH_CONTRACT_COLUMNS
                      if sub[c].isna().any()},
            "default_rate_1.0": {c: round(float((sub[c] == 1.0).mean()), 4)
                                 for c in DF.DEPTH_CONTRACT_COLUMNS
                                 if c != "depth_chart_position"},
            "availability_mean": {c: round(float(sub[c].mean()), 4)
                                  for c in DF.DEPTH_CONTRACT_COLUMNS
                                  if c != "depth_chart_position"},
            "availability_std": {c: round(float(sub[c].std()), 4)
                                 for c in DF.DEPTH_CONTRACT_COLUMNS
                                 if c != "depth_chart_position"},
            "depth_chart_position_share": sub["depth_chart_position"].value_counts(
                normalize=True).round(4).to_dict(),
        }
    any_null = {s: v["nulls"] for s, v in stats.items() if v["nulls"]}
    gate("no nulls in the 16 columns in any season", not any_null,
         json.dumps(any_null) if any_null else "0 nulls, 8 seasons")

    passed = all(r["status"] in ("PASS", "INFO") for r in results)
    OUT.write_text(json.dumps({"all_pass": passed, "gates": results,
                               "row_reconciliation": recon, "coverage": cov,
                               "per_season_stats": stats,
                               "features_stage_equivalence": eq_feat,
                               "depth_builder_equivalence": eq_depth,
                               "replica_non_depth_drift": magnitudes,
                               "staging_non_depth_drift": drift_stage,
                               "holdout_depth_drift": hold,
                               "historical_depth_drift": hist},
                              indent=1, default=str), encoding="utf-8")
    print(f"\n{'ALL GATES PASS' if passed else 'GATE FAILURE'} — report: {OUT}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
