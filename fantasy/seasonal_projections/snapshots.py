"""Deterministic snapshot layer for nflreadpy pulls.

nflreadpy's upstream data drifts between pulls, which makes rebuilds
unreproducible and confounds any logic-change A/B (a leakage-fix delta would be
tangled with data drift). This module pins every raw pull:

  - First request for a key fetches live, converts to pandas, and writes
    snapshots/{key}.parquet plus a manifest entry (sha256 of the parquet bytes,
    row/col counts, fetch timestamp, nflreadpy version).
  - Every later request reads the parquet. Same bytes in, same dataset out.
  - Delete a parquet (or pass refresh=True) to deliberately re-fetch; the
    manifest records the new hash + date so the drift is visible in git.

Usage:
    from snapshots import snap
    ps = snap("player_stats_2011_2025", nfl.load_player_stats, list(range(2011, 2026)))
"""
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE     = Path(__file__).resolve().parent
SNAP_DIR = HERE / "snapshots"
MANIFEST = SNAP_DIR / "manifest.json"


def _load_manifest():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {}


def _sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def snap(key, loader, *args, refresh=False, **kwargs):
    """Return the pinned DataFrame for `key`, fetching + snapshotting on first use."""
    SNAP_DIR.mkdir(exist_ok=True)
    path = SNAP_DIR / f"{key}.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)

    df = loader(*args, **kwargs)
    if hasattr(df, "to_pandas"):          # polars -> pandas
        df = df.to_pandas()
    df.to_parquet(path, index=False)

    import nflreadpy
    manifest = _load_manifest()
    manifest[key] = {
        "sha256": _sha256(path),
        "rows": int(len(df)),
        "cols": int(df.shape[1]),
        "fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nflreadpy": nflreadpy.__version__,
        "loader": getattr(loader, "__name__", str(loader)),
        "args": repr(args)[:200],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"  [snapshot] fetched + pinned {key}: {len(df):,} rows "
          f"(sha256 {manifest[key]['sha256'][:12]}...)")
    return df


def verify(key):
    """Re-hash a snapshot and check it against the manifest. Returns True/False."""
    manifest = _load_manifest()
    path = SNAP_DIR / f"{key}.parquet"
    if key not in manifest or not path.exists():
        return False
    return _sha256(path) == manifest[key]["sha256"]
