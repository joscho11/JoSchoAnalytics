"""Join qb_changed_2026.csv onto the 2026 seasonal dataset. Fail-closed, staged.

`season_dataset_2014_2026.csv` has 923 rows for 2026 and ZERO non-null `qb_changed`,
because `build_2026_board.py` seeds NaN unconditionally. `qb_changed` sits in the saved
`feature_cols` of TWELVE active artifacts (7 in fantasy/projections/models, the four
{qb,rb,wr,te}_ppg models and rookie_ppg in fantasy/seasonal_projections/models), so every
2026 player is currently scored as "his team did not change QB" — false for 7 of 32 teams.

Writes to a STAGING path. Every gate must pass or nothing is written.

    python fantasy/seasonal_projections/join_qb_changed_2026.py [--promote]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DATASET = HERE / "season_dataset_2014_2026.csv"
QBC = HERE / "qb_changed_2026.csv"
PROV = HERE / "qb_changed_2026.provenance.json"
STAGED = HERE / "season_dataset_2014_2026.staged.csv"
MANIFEST = HERE / "qb_changed_join_manifest.json"
SEASON = 2026


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest().upper()


class JoinGateError(RuntimeError):
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--promote", action="store_true")
    args = ap.parse_args()

    for f in (DATASET, QBC, PROV):
        if not f.exists():
            raise JoinGateError(f"required input missing: {f}")

    qbc = pd.read_csv(QBC)
    prov = json.loads(PROV.read_text(encoding="utf-8"))

    # ---- GATE 1: the qb_changed artifact itself -----------------------------
    if len(qbc) != 32:
        raise JoinGateError(f"expected 32 teams, got {len(qbc)}")
    if qbc["team"].duplicated().any():
        dup = sorted(qbc.loc[qbc["team"].duplicated(), "team"])
        raise JoinGateError(f"duplicate team mapping: {dup}")
    if qbc["qb_changed"].isna().any():
        bad = sorted(qbc.loc[qbc["qb_changed"].isna(), "team"])
        raise JoinGateError(f"unresolved team(s) — refusing to write: {bad}")
    if not set(qbc["qb_changed"].unique()) <= {0, 1}:
        raise JoinGateError("qb_changed must be strictly 0/1")
    n_changed = int((qbc["qb_changed"] == 1).sum())
    if n_changed == 0 or n_changed == 32:
        raise JoinGateError(f"degenerate qb_changed ({n_changed}/32 changed)")
    print(f"GATE 1 ok: 32 teams, {n_changed} changed, {32 - n_changed} unchanged, "
          "no duplicates, all resolved")

    # ---- GATE 2: provenance freshness --------------------------------------
    for k in ("created_utc", "snapshot_dt_max", "definition", "sources"):
        if k not in prov or not prov[k]:
            raise JoinGateError(f"provenance missing {k}")
    print(f"GATE 2 ok: provenance snapshot_dt_max={prov['snapshot_dt_max']}")

    # ---- Join ---------------------------------------------------------------
    ds = pd.read_csv(DATASET, low_memory=False)
    if "qb_changed" not in ds.columns:
        raise JoinGateError("dataset has no qb_changed column")
    tgt = ds["season"] == SEASON
    n_2026 = int(tgt.sum())
    before_nonnull = int(ds.loc[tgt, "qb_changed"].notna().sum())

    team_col = "team"
    if team_col not in ds.columns:
        raise JoinGateError("dataset has no team column")
    ds_teams = set(ds.loc[tgt, team_col].dropna().unique())
    missing = sorted(ds_teams - set(qbc["team"]))
    if missing:
        raise JoinGateError(f"2026 teams absent from qb_changed artifact: {missing}")

    m = dict(zip(qbc["team"], qbc["qb_changed"].astype(int)))
    ds.loc[tgt, "qb_changed"] = ds.loc[tgt, team_col].map(m)

    # ---- GATE 3: full coverage of every ROSTERED row ------------------------
    # `qb_changed` is a TEAM feature. A player with no 2026 team has no team QB, so the
    # value is genuinely undefined for him and must stay <NA> — writing 0 there would be
    # the very defect this script exists to remove ("his team did not change QB" is a
    # claim, and there is no team). The contract is therefore: 100% coverage of rostered
    # rows, and EXPLICIT NA for unrostered ones. Measured 2026-08-03: 7 unsigned free
    # agents (Keenan Allen, Stefon Diggs, Tyreek Hill, Joe Mixon, Deebo Samuel Sr.,
    # Brandon Aiyuk, Najee Harris) — all carry an ADP, so they are on the board with a
    # blank team.
    rostered = tgt & ds[team_col].notna()
    unrostered = tgt & ds[team_col].isna()
    n_rostered = int(rostered.sum())
    after_nonnull = int(ds.loc[rostered, "qb_changed"].notna().sum())
    if after_nonnull != n_rostered:
        blanks = ds.loc[rostered & ds["qb_changed"].isna(), team_col].value_counts().to_dict()
        raise JoinGateError(
            f"rostered coverage {after_nonnull}/{n_rostered}; unmapped teams {blanks}")
    if int(ds.loc[unrostered, "qb_changed"].notna().sum()) != 0:
        raise JoinGateError(
            "an unrostered 2026 player was given a numeric qb_changed — 0 is a claim, "
            "not an absence")
    print(f"GATE 3 ok: rostered coverage {before_nonnull} -> {after_nonnull}/{n_rostered}"
          f"  |  {int(unrostered.sum())} unrostered rows deliberately left <NA>")

    # ---- GATE 4: per-team correctness ---------------------------------------
    changed_teams = set(qbc.loc[qbc["qb_changed"] == 1, "team"])
    unchanged_teams = set(qbc.loc[qbc["qb_changed"] == 0, "team"])
    got = ds.loc[rostered].groupby(team_col)["qb_changed"].agg(["min", "max", "size"])
    for t, r in got.iterrows():
        want = 1 if t in changed_teams else 0
        if r["min"] != want or r["max"] != want:
            raise JoinGateError(
                f"team {t}: expected every row = {want}, got min={r['min']} max={r['max']}")
    assert changed_teams and unchanged_teams
    print(f"GATE 4 ok: all {len(changed_teams)} changed teams are 1, "
          f"all {len(unchanged_teams)} unchanged teams are 0, across {len(got)} teams")

    # ---- GATE 5: nothing outside 2026 moved --------------------------------
    old = pd.read_csv(DATASET, low_memory=False)
    hist = old["season"] != SEASON
    if not old.loc[hist, "qb_changed"].equals(ds.loc[hist, "qb_changed"]):
        raise JoinGateError("historical qb_changed values changed — refusing to write")
    if len(old) != len(ds) or list(old.columns) != list(ds.columns):
        raise JoinGateError("row count or schema drifted")
    print(f"GATE 5 ok: {int(hist.sum())} historical rows and the schema are untouched")

    ds.to_csv(STAGED, index=False)
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season": SEASON,
        "rows_2026": n_2026,
        "rows_2026_rostered": n_rostered,
        "rows_2026_unrostered_left_na": int(unrostered.sum()),
        "unrostered_players": sorted(ds.loc[unrostered, "player"].dropna().tolist()),
        "coverage_before": before_nonnull,
        "coverage_after": after_nonnull,
        "n_changed_teams": n_changed,
        "n_unchanged_teams": 32 - n_changed,
        "changed_teams": sorted(changed_teams),
        "qb_changed_source": {"file": QBC.name, "sha256": sha256(QBC),
                              "provenance_sha256": sha256(PROV),
                              "snapshot_dt_max": prov["snapshot_dt_max"]},
        "dataset_before_sha256": sha256(DATASET),
        "dataset_staged_sha256": sha256(STAGED),
        "promoted": False,
    }
    if args.promote:
        shutil.copy2(DATASET, HERE / "season_dataset_2014_2026.pre_qbchanged.csv")
        shutil.copy2(STAGED, DATASET)
        manifest["promoted"] = True
        manifest["dataset_after_sha256"] = sha256(DATASET)
        print(f"PROMOTED (backup: season_dataset_2014_2026.pre_qbchanged.csv)")
    else:
        print("STAGED ONLY — pass --promote to replace the dataset")
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest -> {MANIFEST.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
