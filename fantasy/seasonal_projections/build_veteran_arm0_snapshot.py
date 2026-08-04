"""Freeze the Arm 0 VETERAN feature snapshot — 2014-2025, features only (prereg v3.9, activation).

    fantasy/seasonal_projections/snapshots/veteran_arm0_features_2014_2025.parquet

WHY THIS EXISTS
---------------
The authorized experiment used to pin `season_dataset_2014_2026.csv` by md5. That file is a LIVE
production artifact: it carries season 2026, which is refreshed as the deploy season evolves. On
2026-08-03 a concurrent session populated `qb_changed` for 916 rows of season 2026, and the whole-file
md5 moved — correctly refusing activation, but for a reason that had nothing to do with the
experiment's inputs.

Measured on that change, exactly:
  * differences confined to season 2026, every one;
  * nine columns differed only by CSV float round-trip noise, max |diff| 3.5527e-15, no null flips;
  * the only substantive change was `qb_changed` on 916 rows of 2026 (NaN -> 717 zeros, 199 ones);
  * NO 2014-2025 value differed, bitwise, in any of the 47 columns.

So the experiment-consumed data never moved. Pinning a mutable 2014-2026 file to protect an immutable
2014-2025 window was the wrong scope. This snapshot is that window, frozen: the authorized run reads
it and nothing else, and 2026 can be refreshed as often as it likes without touching activation.

DERIVED, NOT INVENTED
---------------------
The schema and the population come from the LIVE contracts, read at build time:
  columns    = assemble_real_panel_v39.VETERAN_FEATURE_COLUMNS
               (IDENTITY_COLUMNS + ARM0_VETERAN_FEATURES; the 32 features are cross-checked against
                the four shipped veteran bundles' own `feature_cols`)
  population = every row of the source with season in ALL_PANEL_SEASONS (2014-2025)
This module hard-codes neither list. If a contract changes, the snapshot changes with it and its hash
moves, which is the point.

WHAT IT MUST NOT CONTAIN
------------------------
No target, outcome, label, sample weight, ADP or market column. `VETERAN_FEATURE_COLUMNS` already
excludes them by construction; it is checked against `FORBIDDEN_IN_FEATURES` before writing.

Run:  python fantasy/seasonal_projections/build_veteran_arm0_snapshot.py
"""
import argparse
import hashlib
import pathlib
import sys

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
COACH = REPO / "fantasy" / "projections" / "coaching"
sys.path.insert(0, str(COACH))

import assemble_real_panel_v39 as ARP                                  # noqa: E402

OUT = HERE / "snapshots" / "veteran_arm0_features_2014_2025.parquet"
SOURCE = HERE / "season_dataset_2014_2026.csv"

# The generator MAY read the live production CSV. The authorized experiment may NOT — it reads only
# the frozen output of this script. That asymmetry is the whole design.
SOURCE_NAME = "season_dataset_2014_2026.csv"


class BuildError(RuntimeError):
    """Any violation of the frozen build contract. Never caught here."""


def frozen_columns():
    """The ordered consumed schema, taken from the LIVE contract."""
    return tuple(ARP.VETERAN_FEATURE_COLUMNS)


def frozen_seasons():
    """The consumed window, taken from the LIVE contract."""
    return tuple(ARP.ALL_PANEL_SEASONS)


def bundle_cross_check(models_dir=None):
    """The 32 Arm 0 veteran features must be exactly what the four shipped veteran bundles expect."""
    problems = []
    for (pos, bucket), row in sorted(
            {k: v for k, v in ARP.SHIPPED_ARM0_BUCKETS.items() if k[1] == "veteran"}.items()):
        fc = ARP.bundle_feature_cols(pos, bucket, models_dir=models_dir)
        missing = [c for c in fc if c not in ARP.VETERAN_FEATURE_COLUMNS]
        if missing:
            problems.append(f"{pos}/{bucket} expects {len(missing)} column(s) the snapshot schema "
                            f"lacks: {missing[:6]}")
    return problems


def build(out=OUT, source=None, verbose=True):
    """Derive the snapshot. Returns the DataFrame that was written."""
    src = SOURCE if source is None else pathlib.Path(source)
    cols, seasons = frozen_columns(), frozen_seasons()

    forbidden = sorted(set(cols) & ARP.FORBIDDEN_IN_FEATURES)
    if forbidden:
        raise BuildError(f"the consumed contract itself names forbidden column(s): {forbidden}")
    problems = bundle_cross_check()
    if problems:
        raise BuildError("bundle cross-check: " + "; ".join(problems))

    header = pd.read_csv(src, nrows=0)
    missing = [c for c in cols if c not in header.columns]
    if missing:
        raise BuildError(f"source is missing consumed column(s): {missing}")

    df = pd.read_csv(src, usecols=list(cols))          # explicit: a market column is never even loaded
    df = df[df[ARP.SEASON_KEY].isin(seasons)].copy()
    df = df[list(cols)]

    # --- deterministic shape --------------------------------------------------------------------
    df = df.sort_values([ARP.SEASON_KEY, ARP.PLAYER_KEY], kind="mergesort").reset_index(drop=True)
    df[ARP.SEASON_KEY] = df[ARP.SEASON_KEY].astype("int32")
    for c in ("reconstructed", "is_rookie"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("int8")
    for c in ("player_id", "player", "norm_name", "position", "team"):
        df[c] = df[c].astype("string")
    for c in ARP.ARM0_VETERAN_FEATURES:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")

    _assert_contract(df, cols, seasons)

    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False, engine="pyarrow", compression="snappy")
    if verbose:
        sha = hashlib.sha256(pathlib.Path(out).read_bytes()).hexdigest()
        print(f"wrote {out}  rows={len(df)} cols={len(df.columns)} "
              f"seasons={seasons[0]}-{seasons[-1]} sha256={sha}")
    return df


def _assert_contract(df, cols, seasons):
    if tuple(df.columns) != tuple(cols):
        raise BuildError("column order does not match the consumed contract")
    if df.duplicated(subset=list(ARP.PANEL_KEYS)).any():
        raise BuildError("duplicate (player_id, season) keys")
    if df[ARP.PLAYER_KEY].isna().any():
        raise BuildError("null player_id")
    got = tuple(sorted(int(s) for s in pd.unique(df[ARP.SEASON_KEY])))
    if got != tuple(seasons):
        raise BuildError(f"season coverage is {got}, must be exactly {seasons}")
    leaked = sorted(set(df.columns) & ARP.FORBIDDEN_IN_FEATURES)
    if leaked:
        raise BuildError(f"forbidden outcome/market column(s): {leaked}")
    # the frame must satisfy the SAME validator the authorized reader applies to its output
    problems = ARP.validate_feature_frame(df)
    if problems:
        raise BuildError("snapshot fails the live feature validator: " + "; ".join(problems))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--source", default=None)
    args = ap.parse_args()
    build(out=args.out, source=args.source)
