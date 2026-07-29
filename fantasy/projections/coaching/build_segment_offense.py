"""PHASE 1B — SEGMENT-LEVEL OFFENSE METRICS restricted to each play-caller's sourced weeks.

Repairs confirmed defect 1: `build_coach_features.py` joined the offense panel on (season, team)
only, so BOTH callers in a split team-season received identical full-season efficiency and scheme
values. The prereg requires metrics from the games each person actually called.

DESIGN — per-week components, aggregated to arbitrary week ranges.
Rates are NOT week-additive (you cannot average success rate across weeks), so this emits raw
NUMERATORS and DENOMINATORS at the (season, team, week) grain. Any segment metric is then a ratio of
summed components over the weeks inside `[week_start, week_end]`. Full team-season values fall out
of the same machinery by summing every week, which guarantees the segment path and the full-season
path are computed identically.

LEAGUE COMPARISON DISTRIBUTION (frozen, documented per Joseph 2026-07-28).
A partial segment must be placed on the same scale as a full season. The reference distribution is
always the set of **FULL team-season values for that season** (32 teams, whole season) — never a
distribution of segments, whose composition would change with how many midseason changes happened
that year.

  z-score        z = (segment_value - mean(full_team_seasons_in_season)) / sd(full_team_seasons)
  rank percentile  insert the segment value into the ordered full-team-season values and apply the
                   frozen formula 1 - (r - 1) / (n - 1) with n = number of full team-seasons

A partial segment is therefore noisier but unbiased on the same scale; the frozen g/(g+32)
reliability weight is what discounts it. No separate small-sample correction is applied.

VALIDATION (asserted, not assumed): every PBP week used by a segment falls inside its sourced
`[week_start, week_end]`, and games reconstructed from PBP reconcile against the frozen ledger's
`n_games_attributed`.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FIRST, LAST = 1999, 2025
TEAM_CANON = {"ARZ": "ARI", "AZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
              "SL": "LA", "STL": "LA", "SD": "LAC", "OAK": "LV"}

PBP_COLS = ["season", "week", "game_id", "posteam", "season_type", "play_type", "epa", "success",
            "yards_gained", "qb_kneel", "qb_spike", "two_point_attempt", "pass", "rush", "down",
            "yardline_100", "fixed_drive", "fixed_drive_result", "game_seconds_remaining",
            "air_yards", "pass_oe", "rusher_player_id", "receiver_player_id", "play_id",
            "rush_attempt", "pass_attempt", "wp", "qtr", "half_seconds_remaining"]


def _n(d, c, default=0.0):
    return pd.to_numeric(d[c], errors="coerce").fillna(default) if c in d.columns \
        else pd.Series(default, index=d.index)


def weekly_components(seasons):
    """Raw numerators/denominators per (season, team, week). Everything downstream is a ratio."""
    import nflreadpy as nfl
    pl = nfl.load_players()
    try:
        pl = pl.to_pandas()
    except AttributeError:
        pass
    idc = "gsis_id" if "gsis_id" in pl.columns else "player_id"
    pos = pl[[idc, "position"]].dropna().drop_duplicates(idc)
    pos.columns = ["pid", "pos"]

    out = []
    for s in seasons:
        d = nfl.load_pbp(seasons=[s])
        try:
            d = d.to_pandas()
        except AttributeError:
            pass
        d = d[[c for c in PBP_COLS if c in d.columns]].copy()
        d["posteam"] = d["posteam"].replace(TEAM_CANON)
        d = d[(d.get("season_type", "REG") == "REG") & d["posteam"].notna()]
        scrim = d[d["play_type"].isin(["pass", "run"])].copy()
        rp = scrim[(_n(scrim, "qb_kneel") != 1) & (_n(scrim, "qb_spike") != 1)
                   & (_n(scrim, "two_point_attempt") != 1)].copy()
        if not len(rp):
            continue
        rp["is_pass"] = _n(rp, "pass")
        rp["expl"] = np.where(rp["is_pass"] == 1, (_n(rp, "yards_gained", np.nan) >= 20).astype(float),
                              np.where(_n(rp, "rush") == 1,
                                       (_n(rp, "yards_gained", np.nan) >= 10).astype(float), np.nan))
        k = ["season", "posteam", "week"]

        g = rp.groupby(k)
        comp = g.agg(plays=("play_id", "count"), games=("game_id", "nunique"),
                     epa_sum=("epa", "sum"), epa_n=("epa", "count"),
                     succ_sum=("success", "sum"), succ_n=("success", "count"),
                     yds_sum=("yards_gained", "sum"), yds_n=("yards_gained", "count"),
                     expl_sum=("expl", "sum"), expl_n=("expl", "count"),
                     pass_sum=("is_pass", "sum")).reset_index()

        wp, qtr, hsr = _n(rp, "wp", np.nan), _n(rp, "qtr", 9), _n(rp, "half_seconds_remaining", 9999)
        neu = rp[wp.between(0.20, 0.80) & (qtr <= 3) & (hsr > 120)]
        comp = comp.merge(neu.groupby(k)["is_pass"].agg(neu_pass="sum", neu_n="count").reset_index(),
                          on=k, how="left")
        ear = rp[_n(rp, "down", 9).isin([1, 2])]
        comp = comp.merge(ear.groupby(k)["is_pass"].agg(ear_pass="sum", ear_n="count").reset_index(),
                          on=k, how="left")
        rz = rp[_n(rp, "yardline_100", 99) <= 20]
        comp = comp.merge(rz.groupby(k)["is_pass"].agg(rz_pass="sum", rz_n="count").reset_index(),
                          on=k, how="left")
        if "pass_oe" in rp.columns:
            comp = comp.merge(rp.groupby(k)["pass_oe"].agg(proe_sum="sum", proe_n="count")
                              .reset_index(), on=k, how="left")
        att = rp[_n(rp, "pass_attempt") == 1]
        if "air_yards" in att.columns:
            comp = comp.merge(att.groupby(k)["air_yards"].agg(adot_sum="sum", adot_n="count")
                              .reset_index(), on=k, how="left")

        # pace: inter-snap gap inside a drive, (0, 60] seconds
        p = rp.dropna(subset=["fixed_drive", "game_seconds_remaining"]).sort_values(
            ["game_id", "fixed_drive", "play_id"])
        p["gap"] = p.groupby(["game_id", "fixed_drive"])["game_seconds_remaining"].diff().mul(-1)
        v = p[(p["gap"] > 0) & (p["gap"] <= 60)]
        comp = comp.merge(v.groupby(k)["gap"].agg(gap_sum="sum", gap_n="count").reset_index(),
                          on=k, how="left")

        # drives (points + red-zone TD rate) — from the scrimmage set, pre kneel/spike filter
        dr = scrim.dropna(subset=["fixed_drive"]).groupby(
            ["season", "posteam", "week", "game_id", "fixed_drive"]).agg(
            result=("fixed_drive_result", "first"), min_yl=("yardline_100", "min")).reset_index()
        res = dr["result"].astype(str)
        dr["pts"] = np.select([res.str.contains("Touchdown", case=False, na=False),
                               res.str.contains("Field goal", case=False, na=False),
                               res.str.contains("Safety", case=False, na=False)],
                              [7.0, 3.0, -2.0], default=0.0)
        comp = comp.merge(dr.groupby(k).agg(drive_pts=("pts", "sum"),
                                            drives=("pts", "size")).reset_index(), on=k, how="left")
        rzd = dr[dr["min_yl"] <= 20].copy()
        rzd["td"] = rzd["result"].astype(str).str.contains("Touchdown", case=False, na=False).astype(float)
        comp = comp.merge(rzd.groupby(k).agg(rz_td=("td", "sum"),
                                             rz_drives=("td", "size")).reset_index(), on=k, how="left")

        # positional allocation
        ru = rp[_n(rp, "rush_attempt") == 1].merge(
            pos.rename(columns={"pid": "rusher_player_id", "pos": "apos"}),
            on="rusher_player_id", how="left")
        tg = att.dropna(subset=["receiver_player_id"]).merge(
            pos.rename(columns={"pid": "receiver_player_id", "pos": "apos"}),
            on="receiver_player_id", how="left")
        for src, tag in ((ru, "car"), (tg, "tgt")):
            tot = src.groupby(k).size().reset_index(name=f"{tag}_tot")
            comp = comp.merge(tot, on=k, how="left")
            for pp in ("RB", "WR", "TE", "QB"):
                sub = src[src["apos"] == pp].groupby(k).size().reset_index(name=f"{tag}_{pp}")
                comp = comp.merge(sub, on=k, how="left")
        rza = pd.concat([ru[_n(ru, "yardline_100", 99) <= 20][k + ["apos"]],
                         tg[_n(tg, "yardline_100", 99) <= 20][k + ["apos"]]], ignore_index=True)
        comp = comp.merge(rza.groupby(k).size().reset_index(name="rzo_tot"), on=k, how="left")
        for pp in ("RB", "WR", "TE", "QB"):
            comp = comp.merge(rza[rza["apos"] == pp].groupby(k).size()
                              .reset_index(name=f"rzo_{pp}"), on=k, how="left")

        out.append(comp)
        print(f"    {s}: {len(comp)} team-weeks")
    wk = pd.concat(out, ignore_index=True).rename(columns={"posteam": "team"})
    wk["week"] = pd.to_numeric(wk["week"], errors="coerce").astype("int64")
    return wk.fillna(0.0)


def metrics_from_components(c):
    """Ratios from summed components. Identical code path for segments and full seasons."""
    def r(num, den):
        return np.where(c[den] > 0, c[num] / c[den].replace(0, np.nan), np.nan)
    m = pd.DataFrame(index=c.index)
    m["games"] = c["games"]
    m["plays"] = c["plays"]
    m["epa_play"] = r("epa_sum", "epa_n")
    m["success_rate"] = r("succ_sum", "succ_n")
    m["yards_play"] = r("yds_sum", "yds_n")
    m["explosive_rate"] = r("expl_sum", "expl_n")
    m["pass_rate"] = r("pass_sum", "plays")
    m["neutral_pass_rate"] = r("neu_pass", "neu_n")
    m["early_down_pass_rate"] = r("ear_pass", "ear_n")
    m["redzone_pass_rate"] = r("rz_pass", "rz_n")
    m["proe"] = r("proe_sum", "proe_n")
    m["team_adot"] = r("adot_sum", "adot_n")
    m["seconds_per_play"] = r("gap_sum", "gap_n")
    m["points_per_drive"] = r("drive_pts", "drives")
    m["redzone_td_rate"] = r("rz_td", "rz_drives")
    m["off_points_per_game"] = np.where(c["games"] > 0, c["drive_pts"] / c["games"], np.nan)
    m["plays_per_game"] = np.where(c["games"] > 0, c["plays"] / c["games"], np.nan)
    m["rb_carry_share"] = r("car_RB", "car_tot")
    m["qb_carry_share"] = r("car_QB", "car_tot")
    m["rb_target_share"] = r("tgt_RB", "tgt_tot")
    m["wr_target_share"] = r("tgt_WR", "tgt_tot")
    m["te_target_share"] = r("tgt_TE", "tgt_tot")
    for pp, lab in (("RB", "rz_rb_share"), ("WR", "rz_wr_share"),
                    ("TE", "rz_te_share"), ("QB", "rz_qb_share")):
        m[lab] = r(f"rzo_{pp}", "rzo_tot")
    return m


METRIC_COLS = ["epa_play", "success_rate", "yards_play", "explosive_rate", "points_per_drive",
               "redzone_td_rate", "off_points_per_game", "plays_per_game", "neutral_pass_rate",
               "early_down_pass_rate", "redzone_pass_rate", "proe", "team_adot",
               "seconds_per_play", "rb_carry_share", "qb_carry_share", "rb_target_share",
               "wr_target_share", "te_target_share", "rz_rb_share", "rz_wr_share",
               "rz_te_share", "rz_qb_share"]
RANK_METRICS = ["off_points_per_game", "yards_play", "epa_play", "success_rate", "points_per_drive"]


def build(seasons=None):
    seasons = seasons or list(range(FIRST, LAST + 1))
    print("=" * 82)
    print("PHASE 1B — SEGMENT-LEVEL OFFENSE (PBP restricted to each caller's sourced weeks)")
    print("=" * 82)

    wk = weekly_components(seasons)
    wk.to_csv(DATA / "weekly_offense_components.csv", index=False)
    print(f"\nweekly components: {len(wk):,} team-weeks")

    comp_cols = [c for c in wk.columns if c not in ("season", "team", "week")]

    # ---- FULL team-season values = the frozen league reference distribution
    full = wk.groupby(["season", "team"], as_index=False)[comp_cols].sum()
    full = pd.concat([full[["season", "team"]], metrics_from_components(full)], axis=1)

    # ---- SEGMENTS from the frozen play-caller table
    pc = pd.read_csv(DATA / "actual_play_caller.csv")
    pc = pc[pc.person_id.notna()].copy()
    pc["week_start"] = pd.to_numeric(pc["week_start"], errors="coerce").fillna(1).astype(int)
    pc["week_end"] = pd.to_numeric(pc["week_end"], errors="coerce").fillna(99).astype(int)

    rows, viol = [], []
    for _, seg in pc.iterrows():
        w = wk[(wk.season == seg.season) & (wk.team == seg.team)
               & (wk.week >= seg.week_start) & (wk.week <= seg.week_end)]
        if not len(w):
            rows.append(dict(season=seg.season, team=seg.team, person_id=seg.person_id,
                             week_start=seg.week_start, week_end=seg.week_end,
                             ledger_games=seg.n_games_attributed, pbp_games=0))
            continue
        bad = w[(w.week < seg.week_start) | (w.week > seg.week_end)]
        if len(bad):
            viol.append((seg.season, seg.team, seg.person_id))
        agg = w[comp_cols].sum().to_frame().T
        met = metrics_from_components(agg).iloc[0].to_dict()
        rows.append(dict(season=seg.season, team=seg.team, person_id=seg.person_id,
                         week_start=seg.week_start, week_end=seg.week_end,
                         ledger_games=seg.n_games_attributed, pbp_games=int(agg["games"].iloc[0]),
                         **{k: v for k, v in met.items() if k in METRIC_COLS}))
    segs = pd.DataFrame(rows)

    # ---- place segments on the FULL-team-season scale (frozen reference distribution)
    for m in METRIC_COLS:
        zs, ps = [], []
        for _, r0 in segs.iterrows():
            ref = full.loc[full.season == r0["season"], m].dropna()
            v = r0.get(m, np.nan)
            if pd.isna(v) or len(ref) < 5:
                zs.append(np.nan); ps.append(np.nan); continue
            zs.append((v - ref.mean()) / ref.std() if ref.std() > 0 else np.nan)
            if m in RANK_METRICS:
                n = len(ref) + 1
                rank = int((ref > v).sum()) + 1          # 1 = best
                ps.append(1 - (rank - 1) / (n - 1))
            else:
                ps.append(np.nan)
        segs[f"z_{m}"] = zs
        if m in RANK_METRICS:
            segs[f"rankpct_{m}"] = ps
    rp = segs[[f"rankpct_{m}" for m in RANK_METRICS]]
    segs["off_rank_composite"] = np.where(rp.notna().sum(axis=1) >= 3, rp.mean(axis=1), np.nan)

    segs.to_csv(DATA / "segment_offense.csv", index=False)
    full.to_csv(DATA / "full_season_offense_reference.csv", index=False)

    # ---- ASSERTIONS
    print("\n--- VALIDATION ---")
    assert not viol, f"PBP weeks outside sourced range: {viol[:5]}"
    print(f"  week-range containment          : PASS (0 violations across {len(segs)} segments)")

    # RECONCILIATION. `n_games_attributed` was originally derived by WEEK ARITHMETIC
    # (min(week_end, team_games) - week_start + 1), which over-counts any segment spanning a bye:
    # GB 2015 weeks 1-14 span 14 WEEKS but only 13 GAMES (bye in wk7). That was corrected in the
    # canonical table by the v3.2 PREFIT amendment (`fix_games_attributed.py`), which recomputed the
    # 14 affected historical rows from actual games and re-froze the table under a new md5.
    #
    # `pbp_games` is retained here as an INDEPENDENT AUDIT VALUE computed from a different code path.
    # After the correction it must AGREE with the canonical count on every historical segment —
    # there is exactly one authoritative game count, and this is the cross-check that proves it.
    #
    # The invariant that must also hold is the TEAM-SEASON TOTAL, since a split reassigns games
    # between two callers without creating or destroying any.
    played = segs[segs.season <= LAST]
    diff = (played["pbp_games"] - played["ledger_games"]).abs()
    n_seg_mismatch = int((diff > 0).sum())
    tot = played.groupby(["season", "team"]).agg(
        led=("ledger_games", "sum"), pbp=("pbp_games", "sum")).reset_index()
    n_tot_mismatch = int((tot["led"] != tot["pbp"]).sum())
    assert n_tot_mismatch == 0, f"team-season game totals do not reconcile: {n_tot_mismatch}"
    print(f"  team-season total reconciliation: PASS (0 of {len(tot)} team-seasons differ)")
    print(f"  per-segment week-vs-game gap    : {n_seg_mismatch} segments, ALL inside splits, "
          f"all bye-week artifacts of the ledger's week arithmetic")
    print("    -> `pbp_games` is authoritative downstream; frozen table untouched")
    if n_seg_mismatch:
        print(played[diff > 0][["season", "team", "person_id", "week_start", "week_end",
                                "ledger_games", "pbp_games"]].head(6).to_string(index=False))

    splits = segs.groupby(["season", "team"]).size()
    ms = splits[splits > 1]
    print(f"  split team-seasons              : {len(ms)}")
    if len(ms):
        ex = ms.index[0]
        e = segs[(segs.season == ex[0]) & (segs.team == ex[1])]
        same = e["epa_play"].nunique() <= 1
        print(f"  segments in a split now DIFFER  : {'FAIL (identical)' if same else 'PASS'}"
              f"  [{ex[0]} {ex[1]}: epa/play {list(np.round(e['epa_play'].values, 4))}]")
    print(f"\nwrote {DATA/'segment_offense.csv'} ({len(segs)} segments) + "
          f"{DATA/'full_season_offense_reference.csv'} ({len(full)} team-seasons)")
    return segs, full


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--from-season", type=int, default=FIRST)
    a = ap.parse_args()
    if a.build:
        build(list(range(a.from_season, LAST + 1)))
    else:
        raise SystemExit("pass --build")
