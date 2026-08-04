"""Depth-chart derived feature tables — ONE builder for training and for serving.

Built on top of `depth_adapter` (the canonical dual-schema normaliser). This module adds
the two things the adapter deliberately leaves to the caller:

  1. **Snapshot -> week mapping.** Current-schema (>=2025) rows are DATED snapshots, not
     weekly charts. Each team-week is assigned the LATEST snapshot STRICTLY BEFORE that
     team's own kickoff. `assert_no_future_snapshot` proves it after the fact.
  2. **The full 16-column contract.** Skill depth rank + offensive teammate availability
     + opponent defensive starter availability + O-line starter availability, using the
     SAME construction for legacy and current seasons.

The legacy construction is preserved bit-for-bit for <=2024: filter to depth rank 1,
sort by (season, week, team, position, player_id), keep the first row per
(season, week, team, position), join the injury report, blend
0.6*injury + 0.4*practice, pivot to team level. Current-schema seasons run through the
identical code after their side-specific position codes (LCB/RCB/LDE/SLB/LT/...) are
folded onto the legacy vocabulary (CB/DE/OLB/T/...).

Fail-closed: every season requested is put through `assert_season_invariants`, and a
season that yields a constant depth-rank block raises rather than returning defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from depth_adapter import (DepthSchemaError, assert_season_invariants,
                           normalize_depth_charts)

__all__ = [
    "DepthSchemaError", "DEPTH_CONTRACT_COLUMNS", "SKILL_POSITIONS",
    "DEFENSIVE_POSITIONS", "OL_POSITIONS", "DEF_FLAG_COLS", "OL_FLAG_COLS",
    "TEAMMATE_FLAG_COLS", "CURRENT_TO_LEGACY_POSITION", "DepthTables",
    "canonical_depth", "map_snapshots_to_weeks", "assert_no_future_snapshot",
    "build_injury_scores", "build_depth_tables", "build_live_depth_contract",
]

SKILL_POSITIONS = ["QB", "RB", "WR", "TE"]
DEFENSIVE_POSITIONS = ["CB", "OLB", "ILB", "MLB", "DE", "DT", "FS", "SS"]
OL_POSITIONS = ["T", "G", "C"]

TEAMMATE_FLAG_COLS = ["starter_qb_availability", "starter_rb_availability",
                      "starter_wr_availability", "starter_te_availability"]
DEF_FLAG_COLS = ["opp_cb1_availability", "opp_olb1_availability", "opp_ilb1_availability",
                 "opp_mlb1_availability", "opp_de1_availability", "opp_dt1_availability",
                 "opp_fs1_availability", "opp_ss1_availability"]
OL_FLAG_COLS = ["starter_tackle_availability", "starter_guard_availability",
                "starter_center_availability"]

#: the sixteen columns this module is solely responsible for
DEPTH_CONTRACT_COLUMNS = (["depth_chart_position"] + TEAMMATE_FLAG_COLS
                          + DEF_FLAG_COLS + OL_FLAG_COLS)

_TEAMMATE_RENAME = {"QB": "starter_qb_availability", "RB": "starter_rb_availability",
                    "WR": "starter_wr_availability", "TE": "starter_te_availability"}
_DEF_RENAME = {"CB": "opp_cb1_availability", "OLB": "opp_olb1_availability",
               "ILB": "opp_ilb1_availability", "MLB": "opp_mlb1_availability",
               "DE": "opp_de1_availability", "DT": "opp_dt1_availability",
               "FS": "opp_fs1_availability", "SS": "opp_ss1_availability"}
_OL_RENAME = {"T": "starter_tackle_availability", "G": "starter_guard_availability",
              "C": "starter_center_availability"}

#: nflverse's current schema splits positions by field side. Fold them back onto the
#: legacy vocabulary the 2018-2024 feature block was built from. Anything absent here
#: (KR/PR/PK/P/H/LS/NT/FB) was NOT used by the legacy build and stays excluded.
CURRENT_TO_LEGACY_POSITION = {
    "QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE",
    "LT": "T", "RT": "T", "LG": "G", "RG": "G", "C": "C",
    "LCB": "CB", "RCB": "CB", "NB": "CB",
    "LDE": "DE", "RDE": "DE",
    "LDT": "DT", "RDT": "DT",
    "SLB": "OLB", "WLB": "OLB",
    "RILB": "ILB", "LILB": "ILB", "MLB": "MLB",
    "FS": "FS", "SS": "SS",
}

#: legacy depth charts only ever carried tiers 1-3 and the pipeline filled missing with 3.
#: The current schema ranks 1..10+, so clip to keep the 2025 feature on the same support
#: as every training season.
MAX_DEPTH_RANK = 3
UNKNOWN_DEPTH_RANK = 3

_INJURY_MAP = {None: 1.0, "Questionable": 0.5, "Doubtful": 0.25, "Out": 0.0, "Note": 1.0}
_PRACTICE_MAP = {"Full Participation in Practice": 1.0,
                 "Limited Participation in Practice": 0.5,
                 "Did Not Participate In Practice": 0.0,
                 "\n": 1.0, "Note": 1.0}


@dataclass
class DepthTables:
    """The four tables the pipeline joins, plus the provenance of how they were built."""
    player_depth_rank: pd.DataFrame
    teammate_flags: pd.DataFrame
    def_flags: pd.DataFrame
    ol_flags: pd.DataFrame
    canonical: pd.DataFrame
    report: dict = field(default_factory=dict)


# ── canonicalisation ──────────────────────────────────────────────────────────────

def _clean_id(s: pd.Series) -> pd.Series:
    out = s.astype("string")
    return out.where(~out.isin(["nan", "None", "<NA>", ""]), pd.NA)


def canonical_depth(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalise via the adapter, then fold positions onto the legacy vocabulary.

    Returns columns: season, week, team, player_id, position, depth_rank, game_type,
    source_schema, _dt. `season`/`week` are authoritative only for legacy rows; current
    rows get theirs from `map_snapshots_to_weeks`.
    """
    norm = normalize_depth_charts(raw)
    out = pd.DataFrame({
        "season": pd.to_numeric(norm["season"], errors="coerce").astype("Int64"),
        "week": pd.to_numeric(norm["week"], errors="coerce").astype("Int64"),
        "team": norm["team"].astype(str),
        "player_id": _clean_id(norm["gsis_id"]),
        "player_name": norm["player_name"].astype(str),
        "raw_position": norm["position"].astype(str).str.upper().str.strip(),
        "depth_rank": pd.to_numeric(norm["depth_rank"], errors="coerce"),
        "pos_slot": pd.to_numeric(norm["pos_slot"], errors="coerce"),
        "game_type": norm["game_type"],
        "source_schema": norm["source_schema"],
        "_dt": norm["_dt"],
    })
    legacy = out["source_schema"] == "legacy"
    out["position"] = np.where(
        legacy,
        out["raw_position"],
        out["raw_position"].map(CURRENT_TO_LEGACY_POSITION).fillna("__DROP__"),
    )
    out = out[out["position"] != "__DROP__"].copy()
    # the legacy build only ever used REG rows; current-schema snapshots have no game_type
    is_legacy = out["source_schema"] == "legacy"
    out = out[(~is_legacy) | (out["game_type"] == "REG")].copy()

    # Legacy `depth_team` is depth WITHIN a slot: KC 2024 wk1 listed two CB1s, two T1s
    # and two WR1s (LCB/RCB, LT/RT, LWR/RWR). The current schema instead gives ONE
    # pos_rank sequence per pos_abb that CYCLES through pos_slot, so the same Chiefs
    # snapshot ranks its three WR slots 1..8. Re-rank within (team, snapshot, pos_abb,
    # pos_slot) so both schemas mean the same thing before anything downstream reads it.
    cur_mask = ~is_legacy.reindex(out.index, fill_value=False)
    if cur_mask.any():
        cur = out[cur_mask].copy()
        cur["_slot_key"] = cur["pos_slot"].fillna(-1.0)
        cur = cur.sort_values(["team", "_dt", "raw_position", "_slot_key", "depth_rank"])
        cur["depth_rank"] = (
            cur.groupby(["team", "_dt", "raw_position", "_slot_key"], sort=False)
            .cumcount() + 1).astype(float)
        out.loc[cur.index, "depth_rank"] = cur["depth_rank"]

    out["depth_rank"] = out["depth_rank"].clip(upper=MAX_DEPTH_RANK)
    return out.reset_index(drop=True)


# ── snapshot -> week mapping ──────────────────────────────────────────────────────

def team_week_cutoffs(schedules: pd.DataFrame) -> pd.DataFrame:
    """One row per (season, week, team) with that team's own kickoff instant (UTC).

    `gametime` is local Eastern in nflverse; a missing one falls back to midnight ET,
    which is strictly conservative (an earlier cutoff can only reject snapshots).
    """
    reg = schedules[schedules["game_type"] == "REG"].copy()
    day = pd.to_datetime(reg["gameday"], errors="coerce")
    tod = pd.to_timedelta(reg.get("gametime", pd.Series(index=reg.index, dtype=object))
                          .fillna("00:00") + ":00", errors="coerce").fillna(pd.Timedelta(0))
    local = (day + tod).dt.tz_localize("America/New_York",
                                       ambiguous=True, nonexistent="shift_forward")
    reg["cutoff_utc"] = local.dt.tz_convert("UTC")
    rows = []
    for side in ("home_team", "away_team"):
        t = reg[["season", "week", side, "cutoff_utc"]].rename(columns={side: "team"})
        rows.append(t)
    out = pd.concat(rows, ignore_index=True)
    out["season"] = out["season"].astype(int)
    out["week"] = out["week"].astype(int)
    if out["cutoff_utc"].isna().any():
        raise DepthSchemaError("schedule rows with no usable kickoff time — cannot prove "
                               "a snapshot predates the game")
    return out.sort_values(["team", "cutoff_utc"]).reset_index(drop=True)


def map_snapshots_to_weeks(canon: pd.DataFrame, schedules: pd.DataFrame) -> pd.DataFrame:
    """Give every current-schema row the (season, week) whose kickoff it precedes.

    For each (team, week) the LATEST snapshot strictly before that team's kickoff is
    selected; the whole of that snapshot's rows for that team become the week's chart.
    Legacy rows already carry a week and pass through unchanged.
    """
    legacy = canon[canon["source_schema"] == "legacy"].copy()
    current = canon[canon["source_schema"] == "current"].copy()
    if not len(current):
        return legacy.assign(snapshot_dt=pd.NaT)

    cutoffs = team_week_cutoffs(schedules)
    snaps = (current[["team", "_dt"]].drop_duplicates()
             .rename(columns={"_dt": "snapshot_dt"})
             .sort_values(["team", "snapshot_dt"]).reset_index(drop=True))

    chosen = pd.merge_asof(
        cutoffs.sort_values("cutoff_utc"),
        snaps.sort_values("snapshot_dt"),
        left_on="cutoff_utc", right_on="snapshot_dt", by="team",
        direction="backward", allow_exact_matches=False,
    )
    unresolved = chosen[chosen["snapshot_dt"].isna()]
    resolved = chosen.dropna(subset=["snapshot_dt"]).copy()

    mapped = current.drop(columns=["season", "week"]).merge(
        resolved[["season", "week", "team", "snapshot_dt", "cutoff_utc"]],
        left_on=["team", "_dt"], right_on=["team", "snapshot_dt"], how="inner",
    )
    mapped["season"] = mapped["season"].astype("Int64")
    mapped["week"] = mapped["week"].astype("Int64")
    legacy = legacy.assign(snapshot_dt=pd.NaT, cutoff_utc=pd.NaT)
    out = pd.concat([legacy, mapped], ignore_index=True)
    out.attrs["unresolved_team_weeks"] = int(len(unresolved))
    out.attrs["unresolved_detail"] = unresolved[["season", "week", "team"]].to_dict("records")
    return out


def assert_no_future_snapshot(mapped: pd.DataFrame) -> dict:
    """Prove no mapped row uses a snapshot at or after its own game's kickoff."""
    cur = mapped[mapped["source_schema"] == "current"].copy()
    if not len(cur):
        return {"checked_rows": 0, "violations": 0}
    for c in ("snapshot_dt", "cutoff_utc"):
        cur[c] = pd.to_datetime(cur[c], utc=True)
    bad = cur[~(cur["snapshot_dt"] < cur["cutoff_utc"])]
    if len(bad):
        raise DepthSchemaError(
            f"{len(bad)} depth rows use a snapshot at or after kickoff — "
            f"first: {bad.iloc[0][['season', 'week', 'team']].to_dict()}")
    lag = (cur["cutoff_utc"] - cur["snapshot_dt"]).dt.total_seconds() / 3600.0
    return {"checked_rows": int(len(cur)), "violations": 0,
            "lag_hours_min": round(float(lag.min()), 2),
            "lag_hours_median": round(float(lag.median()), 2),
            "lag_hours_max": round(float(lag.max()), 2)}


# ── injuries ──────────────────────────────────────────────────────────────────────

def build_injury_scores(injuries: pd.DataFrame) -> pd.DataFrame:
    """(season, week, player_id, injury_status_score, practice_status_score) for REG."""
    inj = injuries[injuries["game_type"] == "REG"].copy()
    inj["season"] = inj["season"].astype(int)
    inj["week"] = inj["week"].astype(int)
    inj["injury_status_score"] = inj["report_status"].map(_INJURY_MAP).fillna(1.0)
    inj["practice_status_score"] = inj["practice_status"].map(_PRACTICE_MAP).fillna(1.0)
    inj = inj[["season", "week", "team", "gsis_id", "position", "full_name",
               "injury_status_score", "practice_status_score"]].rename(
        columns={"gsis_id": "player_id"})
    inj["player_id"] = _clean_id(inj["player_id"])
    return inj


# ── the four tables ───────────────────────────────────────────────────────────────

def _starter_slice(mapped: pd.DataFrame, positions) -> pd.DataFrame:
    d = mapped[mapped["position"].isin(positions) & (mapped["depth_rank"] == 1)].copy()
    d["season"] = d["season"].astype(int)
    d["week"] = d["week"].astype(int)
    d = d[["season", "week", "team", "player_id", "position"]]
    return (d.sort_values(["season", "week", "team", "position", "player_id"])
             .drop_duplicates(subset=["season", "week", "team", "position"]))


def _availability_pivot(starters: pd.DataFrame, inj: pd.DataFrame,
                        rename: dict, cols: list) -> pd.DataFrame:
    health = starters.merge(
        inj[["season", "week", "player_id", "injury_status_score", "practice_status_score"]],
        on=["season", "week", "player_id"], how="left")
    health["injury_status_score"] = health["injury_status_score"].fillna(1.0)
    health["practice_status_score"] = health["practice_status_score"].fillna(1.0)
    health["availability"] = (health["injury_status_score"] * 0.6
                              + health["practice_status_score"] * 0.4)
    flags = health.pivot_table(index=["season", "week", "team"], columns="position",
                               values="availability", aggfunc="mean",
                               observed=True).reset_index()
    flags.columns.name = None
    flags = flags.rename(columns=rename)
    for c in cols:
        if c not in flags.columns:
            flags[c] = 1.0
        flags[c] = flags[c].fillna(1.0)
    return flags[["season", "week", "team"] + cols]


def build_depth_tables(depth_raw: pd.DataFrame, schedules: pd.DataFrame,
                       injuries: pd.DataFrame, seasons) -> DepthTables:
    """Everything the pipeline needs for the sixteen depth/availability columns."""
    canon = canonical_depth(depth_raw)
    mapped = map_snapshots_to_weeks(canon, schedules)
    snapshot_report = assert_no_future_snapshot(mapped)

    mapped = mapped[mapped["season"].notna() & mapped["week"].notna()].copy()
    mapped = mapped[mapped["season"].astype(int).isin(list(seasons))].copy()

    invariants = {}
    for s in sorted(seasons):
        sub = mapped[mapped["season"].astype(int) == int(s)]
        if not len(sub):
            raise DepthSchemaError(f"season {s}: no depth rows survived week mapping")
        invariants[int(s)] = assert_season_invariants(
            sub.assign(season=sub["season"].astype("Int64")), int(s))

    inj = build_injury_scores(injuries)

    skill = mapped[mapped["position"].isin(SKILL_POSITIONS)].copy()
    skill["season"] = skill["season"].astype(int)
    skill["week"] = skill["week"].astype(int)
    player_depth_rank = (
        skill[["season", "week", "team", "player_id", "position", "depth_rank"]]
        .dropna(subset=["player_id"])
        .rename(columns={"depth_rank": "depth_chart_position"})
        .sort_values(["season", "week", "team", "position", "player_id"])
        .drop_duplicates(subset=["season", "week", "team", "player_id", "position"])
    )
    player_depth_rank["depth_chart_position"] = (
        player_depth_rank["depth_chart_position"].clip(1, MAX_DEPTH_RANK).astype("Int64"))

    teammate_flags = _availability_pivot(_starter_slice(mapped, SKILL_POSITIONS), inj,
                                         _TEAMMATE_RENAME, TEAMMATE_FLAG_COLS)
    def_flags = _availability_pivot(_starter_slice(mapped, DEFENSIVE_POSITIONS), inj,
                                    _DEF_RENAME, DEF_FLAG_COLS)
    ol_flags = _availability_pivot(_starter_slice(mapped, OL_POSITIONS), inj,
                                   _OL_RENAME, OL_FLAG_COLS)

    report = {
        "snapshot_check": snapshot_report,
        "season_invariants": invariants,
        "rows_by_schema": mapped["source_schema"].value_counts().to_dict(),
        "unresolved_team_weeks": mapped.attrs.get("unresolved_team_weeks", 0),
        "player_depth_rank_rows": int(len(player_depth_rank)),
        "teammate_flag_rows": int(len(teammate_flags)),
        "def_flag_rows": int(len(def_flags)),
        "ol_flag_rows": int(len(ol_flags)),
    }
    return DepthTables(player_depth_rank, teammate_flags, def_flags, ol_flags,
                       mapped, report)


# ── serving ───────────────────────────────────────────────────────────────────────

def build_live_depth_contract(depth_raw: pd.DataFrame, injuries: pd.DataFrame,
                              season: int, week: int, cutoff_utc,
                              teams=None) -> dict:
    """The SAME sixteen columns for one upcoming slate.

    `cutoff_utc` is the slate's first kickoff; every snapshot used is strictly before it.
    Returns {'player_depth_rank', 'teammate_flags', 'def_flags', 'ol_flags', 'report'}
    where the flag frames are keyed on `team` only (one slate).
    """
    canon = canonical_depth(depth_raw)
    cur = canon[canon["source_schema"] == "current"].copy()
    frame = cur if len(cur) else canon.copy()
    cutoff = pd.Timestamp(cutoff_utc)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")

    if len(cur):
        before = frame[frame["_dt"] < cutoff]
        if not len(before):
            raise DepthSchemaError(
                f"no depth snapshot strictly before {cutoff} — refusing to serve on a "
                "future or absent chart")
        chosen = before.groupby("team")["_dt"].transform("max")
        frame = before[before["_dt"] == chosen].copy()
        snapshot_dt = before["_dt"].max()
    else:
        frame = frame[(frame["season"] == season) & (frame["week"] <= week)].copy()
        if not len(frame):
            raise DepthSchemaError(f"no legacy depth rows for {season} wk<={week}")
        latest = frame.groupby("team")["week"].transform("max")
        frame = frame[frame["week"] == latest].copy()
        snapshot_dt = pd.NaT

    frame["season"] = int(season)
    frame["week"] = int(week)
    if teams is not None:
        frame = frame[frame["team"].isin(list(teams))].copy()

    inv = assert_season_invariants(frame.assign(season=pd.array([season] * len(frame),
                                                               dtype="Int64")), season)

    inj = build_injury_scores(injuries)
    inj_wk = inj[(inj["season"] == int(season)) & (inj["week"] == int(week))]

    pdr = (frame[frame["position"].isin(SKILL_POSITIONS)]
           [["team", "player_id", "position", "depth_rank"]]
           .dropna(subset=["player_id"])
           .rename(columns={"depth_rank": "depth_chart_position"})
           .sort_values(["team", "position", "player_id"])
           .drop_duplicates(subset=["team", "player_id", "position"]))
    pdr["depth_chart_position"] = pdr["depth_chart_position"].clip(1, MAX_DEPTH_RANK)

    def _flags(positions, rename, cols):
        f = _availability_pivot(_starter_slice(frame, positions), inj_wk, rename, cols)
        return f.drop(columns=["season", "week"])

    report = {
        "season": int(season), "week": int(week),
        "cutoff_utc": str(cutoff),
        "snapshot_dt": str(snapshot_dt),
        "snapshot_strictly_before_cutoff": bool(pd.isna(snapshot_dt)
                                                or snapshot_dt < cutoff),
        "season_invariants": inv,
        "teams": int(frame["team"].nunique()),
        "injury_rows_for_week": int(len(inj_wk)),
    }
    if not report["snapshot_strictly_before_cutoff"]:
        raise DepthSchemaError("selected snapshot is not strictly before kickoff")
    return {"player_depth_rank": pdr,
            "teammate_flags": _flags(SKILL_POSITIONS, _TEAMMATE_RENAME, TEAMMATE_FLAG_COLS),
            "def_flags": _flags(DEFENSIVE_POSITIONS, _DEF_RENAME, DEF_FLAG_COLS),
            "ol_flags": _flags(OL_POSITIONS, _OL_RENAME, OL_FLAG_COLS),
            "report": report}
