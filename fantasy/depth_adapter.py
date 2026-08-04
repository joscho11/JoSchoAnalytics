"""Dual-schema nflverse depth-chart adapter — one canonical shape, fail-closed.

WHY (2026-08-03)
----------------
nflverse changed the depth-chart schema. `load_depth_charts` returns a DIAGONAL UNION:

  legacy (<=2024):  season, club_code, week, game_type, depth_team, position, ...
  current (>=2025): dt, team, player_name, gsis_id, pos_grp, pos_abb, pos_rank, ...

`fantasy/data_pipeline.ipynb` filters on the LEGACY columns
(`game_type=="REG" & position.isin(...) & depth_team=="1"`). Against 2025 those columns are
all NULL, so the filter dropped **100% of the season silently** and the downstream fillna
defaults took over. Measured consequence in the shipped `features_dataset.csv`: all 5,328
2025 rows have `depth_chart_position == 3` and all fifteen availability flags == 1.0 —
**16 of 16 constant**, versus zero constant columns in 2022, 2023 and 2024. Those columns
carry 6-16% of each production model's importance, so every published "2025 holdout MAE"
was measured on a feature distribution that cannot occur at serving time.

This adapter normalises both schemas to one set of canonical fields and REFUSES to return
a season it cannot populate. Zero selected rows is an abort, not an empty frame.

Canonical output columns:
    season, week, team, player_name, gsis_id, position, depth_rank, pos_slot, source_schema
`week` is NaN for the current schema (it is a dated snapshot, not a weekly chart) — callers
that need weekly granularity must use `as_of_snapshot`.
"""
from __future__ import annotations

import pandas as pd

__all__ = ["DepthSchemaError", "SKILL_POSITIONS", "detect_schema",
           "normalize_depth_charts", "as_of_snapshot", "assert_season_invariants"]

SKILL_POSITIONS = ("QB", "RB", "WR", "TE")

_LEGACY_REQUIRED = ("season", "club_code", "week", "game_type", "depth_team")
_CURRENT_REQUIRED = ("dt", "team", "pos_abb", "pos_rank")


class DepthSchemaError(RuntimeError):
    """The depth frame cannot be normalised, or a season fails its invariants."""


def detect_schema(df: pd.DataFrame) -> str:
    """'legacy' | 'current' — per ROW GROUP, decided by which key columns are populated."""
    cols = set(df.columns)
    has_legacy = set(_LEGACY_REQUIRED) <= cols
    has_current = set(_CURRENT_REQUIRED) <= cols
    if has_legacy and has_current:
        return "mixed"
    if has_current:
        return "current"
    if has_legacy:
        return "legacy"
    raise DepthSchemaError(
        f"depth frame matches neither schema; columns={sorted(cols)[:12]}")


def _norm_pos(s):
    return s.astype(str).str.upper().str.strip()


def normalize_depth_charts(df: pd.DataFrame) -> pd.DataFrame:
    """Return the canonical frame, taking each row from whichever schema populated it."""
    schema = detect_schema(df)
    out = []

    if schema in ("legacy", "mixed") and "club_code" in df.columns:
        m = df["club_code"].notna() & df["season"].notna()
        leg = df[m].copy()
        if len(leg):
            pos_col = "position" if "position" in leg.columns else "depth_position"
            name = None
            for c in ("football_name", "player_name", "full_name"):
                if c in leg.columns:
                    name = c
                    break
            out.append(pd.DataFrame({
                "season": leg["season"].astype("Int64"),
                "week": leg["week"].astype("Int64") if "week" in leg else pd.NA,
                "team": leg["club_code"].astype(str),
                "player_name": leg[name].astype(str) if name else "",
                "gsis_id": leg["gsis_id"].astype(str) if "gsis_id" in leg else pd.NA,
                "position": _norm_pos(leg[pos_col]) if pos_col in leg else pd.NA,
                "depth_rank": pd.to_numeric(leg["depth_team"], errors="coerce"),
                "game_type": leg["game_type"] if "game_type" in leg else pd.NA,
                "source_schema": "legacy",
            }))

    if schema in ("current", "mixed") and "dt" in df.columns:
        m = df["dt"].notna() & df["team"].notna()
        cur = df[m].copy()
        if len(cur):
            dt = pd.to_datetime(cur["dt"], errors="coerce", utc=True)
            out.append(pd.DataFrame({
                "season": dt.dt.year.astype("Int64"),
                "week": pd.Series([pd.NA] * len(cur), dtype="Int64"),
                "team": cur["team"].astype(str),
                "player_name": cur["player_name"].astype(str)
                if "player_name" in cur else "",
                "gsis_id": cur["gsis_id"].astype(str) if "gsis_id" in cur else pd.NA,
                "position": _norm_pos(cur["pos_abb"]),
                "depth_rank": pd.to_numeric(cur["pos_rank"], errors="coerce"),
                # pos_slot identifies WHICH slot (LWR/RWR/SWR-style) the row belongs to.
                # pos_rank is a single ordering ACROSS the position's slots, so depth
                # within a slot is only recoverable with pos_slot alongside it.
                "pos_slot": pd.to_numeric(cur["pos_slot"], errors="coerce")
                if "pos_slot" in cur.columns else pd.NA,
                "game_type": pd.NA,
                "source_schema": "current",
                "_dt": dt,
            }))

    if not out:
        raise DepthSchemaError("no rows populated under either schema")
    res = pd.concat(out, ignore_index=True)
    if "_dt" not in res.columns:
        res["_dt"] = pd.NaT
    if "pos_slot" not in res.columns:
        res["pos_slot"] = pd.NA
    return res


def as_of_snapshot(norm: pd.DataFrame, season: int, position: str = "QB",
                   depth_rank: int = 1, on_or_before=None) -> pd.DataFrame:
    """The latest starter chart at or before `on_or_before`, one row per team.

    For the current schema this is a genuine dated snapshot; for legacy it takes the
    lowest available week. Ambiguity (two players tied at the same rank on the same team
    in the same snapshot) is returned, NOT resolved — the caller decides.
    """
    d = norm[(norm["season"] == season)
             & (norm["position"] == position.upper())
             & (norm["depth_rank"] == depth_rank)].copy()
    if not len(d):
        raise DepthSchemaError(
            f"no {position} depth_rank={depth_rank} rows for season {season}")
    if d["_dt"].notna().any():
        if on_or_before is not None:
            cutoff = pd.Timestamp(on_or_before, tz="UTC")
            d = d[d["_dt"] <= cutoff]
            if not len(d):
                raise DepthSchemaError(
                    f"no {position}1 snapshot on or before {on_or_before} for {season}")
        latest = d.groupby("team")["_dt"].transform("max")
        d = d[d["_dt"] == latest]
    elif d["week"].notna().any():
        first = d.groupby("team")["week"].transform("min")
        d = d[d["week"] == first]
    return d.drop_duplicates(["team", "player_name"]).reset_index(drop=True)


def assert_season_invariants(norm: pd.DataFrame, season: int, *,
                             min_rows: int = 100, min_teams: int = 28,
                             max_null_rate: float = 0.5,
                             require_rank_variance: bool = True) -> dict:
    """Fail closed on a season the adapter could not really populate.

    Catches exactly the 2025 failure: a filter that silently selects zero rows and lets
    downstream defaults manufacture a constant feature block.
    """
    d = norm[norm["season"] == season]
    report = {"season": season, "rows": int(len(d))}
    if len(d) < min_rows:
        raise DepthSchemaError(
            f"season {season}: only {len(d)} normalised depth rows (< {min_rows}). "
            "This is the 2025 failure mode — a schema mismatch selecting nothing.")
    teams = d["team"].nunique()
    report["teams"] = int(teams)
    if teams < min_teams:
        raise DepthSchemaError(f"season {season}: only {teams} teams (< {min_teams})")
    null_rate = float(d["depth_rank"].isna().mean())
    report["depth_rank_null_rate"] = round(null_rate, 4)
    if null_rate > max_null_rate:
        raise DepthSchemaError(
            f"season {season}: depth_rank null rate {null_rate:.2%} > {max_null_rate:.0%}")
    nunique = int(d["depth_rank"].dropna().nunique())
    report["depth_rank_distinct"] = nunique
    if require_rank_variance and nunique < 2:
        raise DepthSchemaError(
            f"season {season}: depth_rank has {nunique} distinct value(s) — a constant "
            "default-filled feature block, which is what shipped for 2025")
    report["positions"] = sorted(set(d["position"].dropna()) & set(SKILL_POSITIONS))
    report["source_schemas"] = sorted(d["source_schema"].unique())
    return report
