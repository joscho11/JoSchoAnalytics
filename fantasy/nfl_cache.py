"""Tiny on-disk cache for the nflverse pulls used by the fantasy rebuild.

Keeps a staging rebuild reproducible within a session and lets the gates be re-run
without re-downloading. Cache files live under `fantasy/staging/_nflcache/` and are
hashed into the run manifest so the build inputs are pinned.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import polars as _pl

_orig_read_parquet = _pl.read_parquet


def _lenient(source, *args, **kwargs):
    try:
        return _orig_read_parquet(source, *args, **kwargs)
    except Exception:
        kwargs.setdefault("use_pyarrow", True)
        return _orig_read_parquet(source, *args, **kwargs)


_pl.read_parquet = _lenient

import nflreadpy as nfl  # noqa: E402
import pandas as pd  # noqa: E402

CACHE_DIR = Path(__file__).parent / "staging" / "_nflcache"


def _path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{name}.parquet"


def cached(name: str, loader, refresh: bool = False) -> pd.DataFrame:
    p = _path(name)
    if p.exists() and not refresh:
        return pd.read_parquet(p)
    res = loader()
    df = res.to_pandas() if hasattr(res, "to_pandas") else pd.DataFrame(res)
    df.to_parquet(p, index=False)
    return df


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cache_hashes() -> dict:
    if not CACHE_DIR.exists():
        return {}
    return {p.name: sha256(p) for p in sorted(CACHE_DIR.glob("*.parquet"))}


def load_all(seasons, coach_seasons, refresh: bool = False) -> dict:
    s = list(seasons)
    return {
        "player_stats": cached("player_stats", lambda: nfl.load_player_stats(s), refresh),
        "ff_opportunity": cached("ff_opportunity", lambda: nfl.load_ff_opportunity(s), refresh),
        "schedules": cached("schedules", lambda: nfl.load_schedules(s), refresh),
        "injuries": cached("injuries", lambda: nfl.load_injuries(s), refresh),
        "depth_charts": cached("depth_charts", lambda: nfl.load_depth_charts(s), refresh),
        "pbp": cached("pbp", lambda: nfl.load_pbp(s), refresh),
        "snap_counts": cached("snap_counts", lambda: nfl.load_snap_counts(s), refresh),
        "players": cached("players", lambda: nfl.load_players(), refresh),
        "coach_schedules": cached("coach_schedules",
                                  lambda: nfl.load_schedules(list(coach_seasons)), refresh),
    }
