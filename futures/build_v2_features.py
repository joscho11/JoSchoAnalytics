"""Build the v2 feature families from the 2026-08-05 point-in-time snapshots.

Governed by PREREGISTRATION Amendment 4. Features are open; the one rule that survives is that a
feature must be buildable point-in-time for BOTH history and the deploy season. Every family below
is computed from information that exists before the target season's first kickoff:

  * prior-season player statistics (settled the previous January)
  * the target season's OPENING roster (set at cutdown, before week 1)
  * All-Pro honors awarded for prior seasons

Writes `futures/data/team_season_panel_v2.parquet`, the v1 panel plus the new columns. The v1 panel
is not modified.

WHAT EACH FAMILY IS, AND THE TRAP IT AVOIDS
-------------------------------------------
`qb_*`      Last season's primary starter, identified by pass attempts, NOT by who starts in the
            target season. The schedule's QB fields are populated post-game and are 272/272 null for
            2026, so anything keyed on the target season's actual starter is a leak in history and
            absent at deploy. `qb_returning` asks only whether that same gsis_id appears on the
            target season's opening roster, which is knowable in August.

`allpro_*`  All-Pro honors from the three prior seasons, mapped to gsis_id through the honoring
            season's roster, then counted on the TARGET season's opening roster. This is the join
            the feasibility audit said the repo did not own. It does. Prior-team All-Pro counts are
            never described as current-roster talent; this IS current-roster, by construction.

`roster_continuity`  Share of last season's offensive and defensive snaps played by players who are
            on this season's opening roster. Undefined before 2014 because snap coverage starts 2013.

`reserve_count`  Players carrying a reserve or inactive status on the opening roster. This is a
            reserve-list count, NOT an injury report. The weekly injury feed is in-season only and
            is excluded by section 2.3.

Run:  python futures/build_v2_features.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import nflreadpy as nfl
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "futures" / "data"
ART = REPO / "futures" / "artifacts"

PANEL_V1 = DATA / "team_season_panel.parquet"
ROSTER_HIST = DATA / "roster_snapshot_opening_2002_2025.parquet"
ROSTER_2026 = DATA / "roster_snapshot_2026.parquet"
SNAPS = DATA / "snap_counts_2012_2025.parquet"
ALLPRO = REPO / "betting" / "nfl_allpro_1997_2025.csv"
OUT = DATA / "team_season_panel_v2.parquet"

PREDICT_SEASON = 2026
# One canonical map, applied to EVERY source. Three different code sets collide here and the
# mismatch is silent: the All-Pro CSV uses PFR codes (SDG, SFO, KAN, TAM, GNB, NWE, NOR, LVR),
# the roster feed carries its own variants (ARZ, BLT, CLV, HST, SL), and the panel uses nflverse.
# Measured before this map existed: only 60.8% of post-2002 All-Pro honors matched a roster on
# season+team+name, against 97.0% on season+name alone. The entire gap was team codes.
FRANCHISE = {
    "ARZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",          # roster feed variants
    "SL": "LA", "STL": "LA", "LAR": "LA", "RAM": "LA",               # Rams lineage
    "SD": "LAC", "SDG": "LAC",                                        # Chargers lineage
    "OAK": "LV", "LVR": "LV", "RAI": "LV",                            # Raiders lineage
    "GNB": "GB", "KAN": "KC", "NOR": "NO", "NWE": "NE",               # PFR codes
    "SFO": "SF", "TAM": "TB", "JAC": "JAX", "WSH": "WAS",
    "CRD": "ARI", "RAV": "BAL", "OTI": "TEN", "HTX": "HOU", "CLT": "IND",
}
# "2TM" marks a player who played for two teams that season. He cannot be attributed to one roster,
# so those honors are dropped rather than guessed, and the count is recorded.
UNRESOLVABLE_TEAM = {"2TM", "3TM"}
RESERVE_STATUS = {"RES", "INA", "PUP", "NFI", "EXE", "SUS"}
ALLPRO_LOOKBACK = 3          # same 3-year window the spread model's All-Pro block uses
ALLPRO_WEIGHTS = {1: 4, 2: 2, 3: 1}   # most recent honor counts most


def pdf(o):
    return o.to_pandas() if hasattr(o, "to_pandas") else o


def canon(s: pd.Series) -> pd.Series:
    return s.astype(str).str.upper().replace(FRANCHISE)


def sha256_frame(df: pd.DataFrame) -> str:
    return hashlib.sha256(
        pd.util.hash_pandas_object(df.reset_index(drop=True), index=False).values.tobytes()
    ).hexdigest()


# ---------------------------------------------------------------- opening rosters, all seasons
def opening_rosters() -> pd.DataFrame:
    """One frame: every team-season's opening roster, 2002 through the predict season."""
    hist = pd.read_parquet(ROSTER_HIST)[["season", "team", "gsis_id", "position", "status"]]
    cur = pd.read_parquet(ROSTER_2026)[["season", "team", "gsis_id", "position", "status"]]
    r = pd.concat([hist, cur], ignore_index=True)
    r["team"] = canon(r["team"])
    r["season"] = r["season"].astype(int)
    r = r[r["gsis_id"].notna()].drop_duplicates(["season", "team", "gsis_id"])
    return r


# ---------------------------------------------------------------- QB family
def qb_features(rosters: pd.DataFrame, seasons: list[int]) -> pd.DataFrame:
    """Prior season's primary passer, his production, and whether he is still here."""
    need = [s - 1 for s in seasons if s - 1 >= 2002]
    ps = pdf(nfl.load_player_stats(sorted(set(need))))
    ps = ps[(ps.get("season_type", "REG") == "REG")]
    agg = (ps.groupby(["season", "team", "player_id"], as_index=False)
             .agg(attempts=("attempts", "sum"),
                  passing_epa=("passing_epa", "sum"),
                  passing_cpoe=("passing_cpoe", "mean")))
    agg = agg[agg["attempts"] > 0].copy()
    agg["team"] = canon(agg["team"])
    # primary passer = most attempts for that team that season; ties broken by epa then id so the
    # result never depends on row order
    agg = agg.sort_values(["season", "team", "attempts", "passing_epa", "player_id"],
                          ascending=[True, True, False, False, True])
    prim = agg.groupby(["season", "team"], as_index=False).first()
    prim["qb_prior_epa_per_att"] = prim["passing_epa"] / prim["attempts"]
    prim = prim.rename(columns={"player_id": "prior_qb_id", "attempts": "qb_prior_attempts",
                                "passing_cpoe": "qb_prior_cpoe"})
    prim["season"] = prim["season"] + 1            # attach last season's QB to THIS season's row
    prim = prim[["season", "team", "prior_qb_id", "qb_prior_attempts",
                 "qb_prior_epa_per_att", "qb_prior_cpoe"]]

    on_roster = set(zip(rosters["season"], rosters["team"], rosters["gsis_id"]))
    prim["qb_returning"] = [
        float((s, t, q) in on_roster) if isinstance(q, str) else np.nan
        for s, t, q in zip(prim["season"], prim["team"], prim["prior_qb_id"])
    ]
    return prim


# ---------------------------------------------------------------- All-Pro family
def allpro_features(rosters: pd.DataFrame, seasons: list[int]) -> pd.DataFrame:
    """All-Pro honors from the prior 3 seasons, counted on the TARGET season's opening roster."""
    ap = pd.read_csv(ALLPRO)
    ap.columns = [c.strip().lower() for c in ap.columns]
    n_before = len(ap)
    ap = ap[~ap["team"].astype(str).str.upper().isin(UNRESOLVABLE_TEAM)].copy()
    n_multi = n_before - len(ap)
    ap["team"] = canon(ap["team"])
    ap["year"] = ap["year"].astype(int)
    ap["side"] = ap["side"].astype(str).str.strip().str.lower()
    unmapped = sorted(set(ap["team"]) - set(canon(pd.Series(sorted(rosters["team"].unique())))))
    assert not unmapped, f"All-Pro team codes with no franchise mapping: {unmapped}"

    # Resolve each honor to a gsis_id using the roster of the season it was awarded in.
    names = rosters.merge(
        pd.read_parquet(ROSTER_HIST)[["season", "team", "gsis_id", "full_name"]]
          .assign(team=lambda d: canon(d["team"])),
        on=["season", "team", "gsis_id"], how="left")
    names["key"] = names["full_name"].astype(str).str.lower().str.replace(r"[^a-z]", "", regex=True)
    lut = (names.dropna(subset=["full_name"])
                .drop_duplicates(["season", "team", "key"])
                .set_index(["season", "team", "key"])["gsis_id"])

    ap["key"] = ap["player"].astype(str).str.lower().str.replace(r"[^a-z]", "", regex=True)
    ap["gsis_id"] = [lut.get((y, t, k), None) for y, t, k in zip(ap["year"], ap["team"], ap["key"])]
    resolved = float(ap["gsis_id"].notna().mean())
    ap_all = ap.copy()

    ap = ap.dropna(subset=["gsis_id"])
    rows = []
    for s in seasons:
        window = ap[(ap["year"] >= s - ALLPRO_LOOKBACK) & (ap["year"] <= s - 1)].copy()
        window["w"] = window["year"].map(lambda y: ALLPRO_WEIGHTS.get(s - y, 0))
        # one row per player: his best weighted honor in the window, by side
        pw = (window.groupby(["gsis_id", "side"], as_index=False)["w"].sum())
        cur = rosters[rosters["season"] == s][["team", "gsis_id"]]
        j = cur.merge(pw, on="gsis_id", how="inner")
        g = j.groupby("team")
        out = pd.DataFrame({
            "allpro_weighted": g["w"].sum(),
            "allpro_offense": j[j["side"] == "offense"].groupby("team")["w"].sum(),
            "allpro_defense": j[j["side"] == "defense"].groupby("team")["w"].sum(),
        })
        out = out.reindex(sorted(rosters[rosters["season"] == s]["team"].unique())).fillna(0.0)
        out["season"] = s
        rows.append(out.reset_index().rename(columns={"index": "team"}))
    res = pd.concat(rows, ignore_index=True)
    res.attrs["name_resolution_rate"] = resolved
    res.attrs["multi_team_honors_dropped"] = n_multi
    res.attrs["resolution_2002plus"] = float(
        ap_all.loc[ap_all["year"] >= 2002, "gsis_id"].notna().mean())
    return res


# ---------------------------------------------------------------- continuity and reserve list
def continuity_features(rosters: pd.DataFrame, seasons: list[int]) -> pd.DataFrame:
    snaps = pd.read_parquet(SNAPS)
    cols = [c for c in ("offense_snaps", "defense_snaps") if c in snaps.columns]
    snaps["team"] = canon(snaps["team"])
    snaps["snaps"] = snaps[cols].fillna(0).sum(axis=1)
    idc = "pfr_player_id" if "pfr_player_id" in snaps.columns else "player"
    per = (snaps.groupby(["season", "team", idc], as_index=False)["snaps"].sum())

    # snap counts key on PFR ids, so map them onto gsis via the roster's pfr_id column
    rh = pd.read_parquet(ROSTER_HIST)
    if "pfr_id" in rh.columns:
        xw = (rh[["season", "team", "gsis_id", "pfr_id"]].dropna()
                .assign(team=lambda d: canon(d["team"]))
                .drop_duplicates(["season", "team", "pfr_id"]))
        per = per.merge(xw, left_on=["season", "team", idc],
                        right_on=["season", "team", "pfr_id"], how="left")
    else:
        per["gsis_id"] = None

    rows = []
    for s in seasons:
        prev = per[per["season"] == s - 1]
        if prev.empty or prev["gsis_id"].notna().sum() == 0:
            continue
        keep = set(zip(rosters.loc[rosters["season"] == s, "team"],
                       rosters.loc[rosters["season"] == s, "gsis_id"]))
        p = prev.dropna(subset=["gsis_id"]).copy()
        p["retained"] = [float((t, g) in keep) for t, g in zip(p["team"], p["gsis_id"])]
        g = p.groupby("team")
        rows.append(pd.DataFrame({
            "season": s,
            "roster_continuity": g.apply(
                lambda d: float((d["snaps"] * d["retained"]).sum() / d["snaps"].sum())
                if d["snaps"].sum() > 0 else np.nan, include_groups=False),
        }).reset_index())
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["team", "season", "roster_continuity"])


def reserve_features(rosters: pd.DataFrame) -> pd.DataFrame:
    r = rosters.copy()
    r["is_res"] = r["status"].astype(str).str.upper().isin(RESERVE_STATUS).astype(float)
    g = r.groupby(["season", "team"], as_index=False).agg(reserve_count=("is_res", "sum"))
    return g


# ---------------------------------------------------------------- assemble
def main() -> None:
    panel = pd.read_parquet(PANEL_V1)
    panel["franchise"] = canon(panel["franchise"])
    seasons = sorted(panel["season"].unique().tolist())
    rosters = opening_rosters()

    qb = qb_features(rosters, seasons)
    ap = allpro_features(rosters, seasons)
    co = continuity_features(rosters, seasons)
    rv = reserve_features(rosters)

    out = panel.copy()
    for name, frame, keys in (("qb", qb, ["season", "team"]),
                              ("allpro", ap, ["season", "team"]),
                              ("continuity", co, ["season", "team"]),
                              ("reserve", rv, ["season", "team"])):
        f = frame.rename(columns={"team": "franchise"})
        out = out.merge(f, left_on=["season", "franchise"],
                        right_on=["season", "franchise"], how="left")

    NEW = ["qb_returning", "qb_prior_epa_per_att", "qb_prior_cpoe", "qb_prior_attempts",
           "allpro_weighted", "allpro_offense", "allpro_defense",
           "roster_continuity", "reserve_count"]
    out = out.drop(columns=[c for c in ("prior_qb_id",) if c in out.columns])

    print(f"panel {out.shape[0]} rows | {len(NEW)} new features")
    print(f"All-Pro name resolution to gsis_id: {ap.attrs.get('name_resolution_rate', float('nan')):.1%}")
    print(f"\n{'feature':<24}{'non-null all':>14}{'non-null 2026':>15}{'mean':>10}{'sd':>9}")
    print("-" * 72)
    p26 = out["season"] == PREDICT_SEASON
    gaps = []
    for c in NEW:
        cov_all = out[c].notna().mean()
        cov_26 = out.loc[p26, c].notna().mean()
        print(f"{c:<24}{cov_all:>13.1%}{cov_26:>15.1%}{out[c].mean():>10.3f}{out[c].std():>9.3f}")
        if cov_all > 0.5 and cov_26 < 0.5:
            gaps.append(c)
    if gaps:
        print(f"\nDEPLOY GAP (train-present, 2026-absent): {gaps}")
        print("These would collapse at deploy and must not be used. See the fantasy depth_rank lesson.")
    else:
        print("\nno deploy gap: every feature present in training is present for 2026")

    out.to_parquet(OUT, index=False)
    meta = {
        "script": "futures/build_v2_features.py",
        "governed_by": "PREREGISTRATION Amendment 4 (A4.3)",
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
        "new_features": NEW,
        "rows": int(len(out)),
        "allpro_name_resolution_rate": round(float(ap.attrs.get("name_resolution_rate", 0)), 4),
        "coverage_all": {c: round(float(out[c].notna().mean()), 4) for c in NEW},
        "coverage_predict_season": {c: round(float(out.loc[p26, c].notna().mean()), 4) for c in NEW},
        "deploy_gaps": gaps,
        "frame_sha256": sha256_frame(out),
    }
    (ART / "v2_feature_build.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(REPO).as_posix()}  sha256 {meta['frame_sha256'][:16]}")


if __name__ == "__main__":
    sys.exit(main())
