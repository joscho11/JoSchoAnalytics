"""Retained, provenance-bearing depth-chart snapshot for the serving path.

Serving must never fall back to "last known values" or to all-default features — that is
exactly how the 2025 season shipped sixteen constant columns. The only permitted fallback
when the live nflverse fetch fails is a snapshot this repo deliberately RETAINED, whose
provenance is recorded and whose freshness is checked against the slate being served.

    save_snapshot(df, season)     write parquet + <name>.provenance.json
    load_snapshot(season, cutoff, max_age_days)
                                  load it, or raise if it is stale / absent / not
                                  strictly older than the slate's first kickoff
    fetch_or_retained(...)        live fetch, retain on success, fall back on failure
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SNAPSHOT_DIR = Path(__file__).parent / "live_snapshots"
DEFAULT_MAX_AGE_DAYS = 10


class SnapshotError(RuntimeError):
    """No usable depth snapshot — serving must abort rather than guess."""


def _paths(season: int):
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    base = SNAPSHOT_DIR / f"depth_charts_{season}"
    return base.with_suffix(".parquet"), base.with_suffix(".provenance.json")


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _max_dt(df: pd.DataFrame):
    if "dt" not in df.columns or df["dt"].isna().all():
        return None
    return pd.to_datetime(df["dt"], utc=True, format="mixed").max()


def save_snapshot(df: pd.DataFrame, season: int) -> dict:
    parquet, prov = _paths(season)
    df.to_parquet(parquet, index=False)
    mx = _max_dt(df)
    meta = {
        "season": int(season),
        "retained_utc": datetime.now(timezone.utc).isoformat(),
        "source": "nflreadpy.load_depth_charts",
        "rows": int(len(df)),
        "columns": list(df.columns),
        "max_snapshot_dt": None if mx is None else str(mx),
        "sha256": _sha256(parquet),
        "purpose": "explicit serving fallback; never a substitute for a fresh fetch",
    }
    prov.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def load_snapshot(season: int, cutoff_utc, max_age_days: int = DEFAULT_MAX_AGE_DAYS):
    parquet, prov = _paths(season)
    if not parquet.exists() or not prov.exists():
        raise SnapshotError(
            f"no retained depth snapshot for {season} — refusing to serve on last-known "
            "or default features")
    meta = json.loads(prov.read_text(encoding="utf-8"))
    actual = _sha256(parquet)
    if actual != meta.get("sha256"):
        raise SnapshotError(f"retained snapshot {parquet.name} does not match its "
                            f"recorded sha256 ({actual[:12]} vs "
                            f"{str(meta.get('sha256'))[:12]})")
    df = pd.read_parquet(parquet)
    mx = _max_dt(df)
    cutoff = pd.Timestamp(cutoff_utc)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    if mx is None:
        raise SnapshotError("retained snapshot carries no dated rows — freshness "
                            "cannot be checked")
    if mx >= cutoff:
        raise SnapshotError(f"retained snapshot's newest row {mx} is not strictly before "
                            f"kickoff {cutoff}")
    age_days = (cutoff - mx).total_seconds() / 86400.0
    if age_days > max_age_days:
        raise SnapshotError(f"retained snapshot is {age_days:.1f} days older than the "
                            f"slate (limit {max_age_days}) — refusing to serve stale "
                            "depth charts")
    meta["age_days_vs_slate"] = round(age_days, 2)
    meta["verified_sha256"] = actual
    return df, meta


def fetch_or_retained(loader, season: int, cutoff_utc,
                      max_age_days: int = DEFAULT_MAX_AGE_DAYS):
    """Try the live fetch; retain it on success, fall back to the retained copy on failure.

    Returns (frame, provenance dict). Raises SnapshotError if neither path yields a
    usable, freshness-checked frame.
    """
    try:
        df = loader()
        df = df.to_pandas() if hasattr(df, "to_pandas") else pd.DataFrame(df)
        if not len(df):
            raise RuntimeError("live depth fetch returned zero rows")
        meta = save_snapshot(df, season)
        meta["provenance"] = "live fetch"
        return df, meta
    except Exception as live_err:  # noqa: BLE001 — fallback path is the point
        try:
            df, meta = load_snapshot(season, cutoff_utc, max_age_days)
        except SnapshotError as snap_err:
            raise SnapshotError(
                f"live depth fetch failed ({live_err}) AND no usable retained snapshot "
                f"({snap_err}) — aborting rather than serving default features"
            ) from live_err
        meta["provenance"] = f"retained snapshot (live fetch failed: {live_err})"
        return df, meta
