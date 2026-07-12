"""2026-forward talent index — PRODUCT FEATURE, descriptive only. Not a test.

License (H7 OUTCOMES, T6 terms): H7 fired FAIL (pooled r -0.013; a well-powered
null — the market prices public efficiency-over-expectation). Per T6, ONLY the
2026-FORWARD index is unblocked: the frozen T2 metrics computed from 2025
play-level data, displayed as descriptive context beside 2026 board players.
No outcomes exist for 2026 and none may ever be joined. The historical (<=2025)
index remains permanently unauthorized.

Fences (bind structurally):
  * Metric definitions lifted VERBATIM from h7_talent_signal.py T2 — no new
    thresholds, no re-engineering. Vendor week-0 qualification IS the floor.
  * NO composite: this column is never blended, weighted, jointly ranked, or
    combined with the disagreement signal, bands, P(top-N), bust prob, or
    anything else. Separate column, full stop.
  * NO correlation of the index against anything, ever (H7's features are dead
    against every target). This script computes zero correlations.
  * phase4_band_2026.csv is READ-ONLY (hash-verified unchanged at exit).
  * Nulls are honest: rookies/non-qualifiers get null + a coverage flag.
    No imputation, ever.

Output: talent_index_2026.csv — one row per phase4_band_2026.csv board row.
Re-run next July with SEASON bumped for a 2027 board (same license terms).
"""
import hashlib
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
BAND = HERE / "phase4_band_2026.csv"
DATASET = HERE / "season_dataset_2014_2026.csv"
OUT = HERE / "talent_index_2026.csv"
BOARD_SEASON = 2026
FEAT_SEASON = 2025                      # the board's prior season

# frozen T2 metric map, lifted verbatim from h7_talent_signal.py (do not edit)
NGS_METRIC = {"QB": ("passing", "completion_percentage_above_expectation"),
              "RB": ("rushing", "rush_yards_over_expected_per_att"),
              "WR": ("receiving", "avg_yac_above_expectation"),
              "TE": ("receiving", "avg_yac_above_expectation")}
METRIC_LABEL = {"QB": "CPOE", "RB": "RYOE/att", "WR": "xYAC+/-", "TE": "xYAC+/-"}

DISCLOSURE = ("Descriptive 2025 efficiency only (H7 pre-registered null, "
              "2026-07-12: not predictive of market error). Never combined "
              "with other board signals.")
ROOKIE_DISCLOSURE = ("Rookie: college production context (different instrument "
                     "than veteran rows — not directly comparable). Descriptive "
                     "only; not validated; never combined with other board "
                     "signals.")
# rookie college-name aliases (variant -> board-norm), school-guarded below
ROOKIE_ALIAS = {"kevin concepcion": "kc concepcion",
                "michael washington": "mike washington"}
ROOKIE_METRIC = {"RB": "college_scrim_yds_share_2025",
                 "WR": "college_rec_yds_share_2025",
                 "TE": "college_rec_yds_share_2025"}
# QB analog (documented, UNUSED — no QB rookie on the 2026 board):
# college_pass_yds_share_2025 = pass_yds / team receiving yards.

DATASET_COLS = ["player", "player_id", "position", "season", "is_rookie",
                "prior_games"]          # membership allowlist — no outcome columns


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def frame_hash(df):
    return hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()[:16]


def load_ngs_2025():
    """2025 week-0 REG vendor-qualified aggregates, id + metric only (H7's
    load pattern; a name join is structurally impossible on these frames)."""
    import nflreadpy as nfl
    frames, prov = {}, {}
    for st in ("passing", "rushing", "receiving"):
        d = nfl.load_nextgen_stats(seasons=[FEAT_SEASON], stat_type=st).to_pandas()
        d = d[(d.week == 0) & (d.season_type == "REG")].copy()
        metric_cols = sorted({m for _, (s, m) in NGS_METRIC.items() if s == st})
        d = d[["player_gsis_id"] + metric_cols].rename(
            columns={"player_gsis_id": "player_id"})
        d["player_id"] = d["player_id"].astype(str)
        assert not d["player_id"].duplicated().any(), f"{st}: dup gsis at week 0"
        frames[st] = d.sort_values("player_id").reset_index(drop=True)
        prov[st] = {"rows": len(d), "hash": frame_hash(frames[st])}
    return frames, prov


def main():
    band_hash_before = sha(BAND)
    band = pd.read_csv(BAND)
    assert len(band) == 180 and (band["season"] == BOARD_SEASON).all()

    ds = pd.read_csv(DATASET, usecols=DATASET_COLS)
    ds = ds[ds["season"] == BOARD_SEASON].copy()
    forbidden = {"target_ppg", "target_games", "actual_pts"}
    assert not (set(ds.columns) & forbidden), "outcome column loaded — STOP"

    # name bridge via the campaign norm_name convention (the band was generated
    # from an earlier dataset build; raw strings have suffix drift, e.g.
    # "Kenneth Walker" vs "Kenneth Walker III")
    from _utils import norm_name
    # shared alias table (J1 convention: variant -> dataset-canonical). The
    # J1 three (Gabriel Davis/Robby Anderson/Hollywood Brown) map UD->dataset
    # and are inert here; "kenny gainwell" is NEW (appended this session): the
    # band was built from an older dataset build that used the nickname form.
    ALIAS = {"gabriel davis": "gabe davis", "robby anderson": "robbie chosen",
             "hollywood brown": "marquise brown", "kenny gainwell": "kenneth gainwell"}
    nmz = lambda s: ALIAS.get(norm_name(s), norm_name(s))
    band = band.copy()
    band["nn"] = band["player"].map(nmz)
    ds["nn"] = ds["player"].map(nmz)
    key = ds[["nn", "position", "player_id", "is_rookie", "prior_games"]]
    assert not key.duplicated(["nn", "position"]).any(), "norm-name collision — STOP"
    m = band[["player", "position", "nn"]].merge(key, on=["nn", "position"], how="left")
    m["in_2026_dataset"] = m["player_id"].notna()

    # fallback: band rows absent from the CURRENT 2026 dataset (it was rebuilt
    # after the band was generated — roster-feed drift). Recover the veteran's
    # id from his most recent prior-season dataset row; flag the desync.
    missing = m[~m.in_2026_dataset]
    if len(missing):
        prior = pd.read_csv(HERE / "season_dataset_2014_2025.csv",
                            usecols=["player", "player_id", "position", "season"])
        prior["nn"] = prior["player"].map(norm_name)
        prior = (prior.sort_values("season")
                 .drop_duplicates(["nn", "position"], keep="last"))
        fb = missing[["nn", "position"]].merge(
            prior[["nn", "position", "player_id"]], on=["nn", "position"], how="left")
        m.loc[~m.in_2026_dataset, "player_id"] = fb["player_id"].to_numpy()
        m.loc[~m.in_2026_dataset, "is_rookie"] = 0     # established veterans
        print(f"NOTE — band/dataset desync: {len(missing)} band rows are not in the "
              f"current 2026 dataset (rebuilt after the band was generated): "
              f"{missing.player.tolist()}; ids recovered from prior-season rows.")
    assert m["player_id"].notna().all(), \
        f"id recovery failed for: {m.loc[m.player_id.isna(), 'player'].tolist()}"
    assert len(m) == 180

    ngs, prov = load_ngs_2025()

    rows = []
    for r in m.itertuples():
        st, metric = NGS_METRIC[r.position]
        hit = ngs[st].loc[ngs[st]["player_id"] == str(r.player_id), metric]
        raw = float(hit.iloc[0]) if len(hit) and pd.notna(hit.iloc[0]) else None
        if raw is not None:
            flag = "qualified"
        elif not r.in_2026_dataset:
            flag = "not_in_2026_dataset"       # band/dataset desync, id recovered
        elif r.is_rookie == 1:
            flag = "rookie_no_prior_season"
        elif pd.isna(r.prior_games) or r.prior_games == 0:
            flag = "no_2025_season"
        else:
            flag = "below_vendor_qualifier"
        rows.append({"player_id": r.player_id, "player": r.player,
                     "position": r.position, "metric_name": METRIC_LABEL[r.position],
                     "raw_value": raw, "qualifier_flag": raw is not None,
                     "coverage_flag": flag})
    out = pd.DataFrame(rows)
    # structural sanity: a 2026 rookie cannot have a 2025 NGS row
    assert not ((out.coverage_flag == "rookie_no_prior_season")
                & out.qualifier_flag).any()

    # display normalization (JUDGMENT CALL, flagged for ratification):
    # per-position percentile among ALL 2025 vendor qualifiers at that position
    # (stable, interpretable universe), raw metric kept alongside.
    out["pct_among_2025_qualifiers"] = None
    for pos, (st, metric) in NGS_METRIC.items():
        univ = ngs[st][metric].dropna()
        mask = (out.position == pos) & out.qualifier_flag
        out.loc[mask, "pct_among_2025_qualifiers"] = out.loc[mask, "raw_value"].map(
            lambda v: round(100.0 * (univ < v).mean(), 1))
    out["disclosure"] = DISCLOSURE

    # ── rookie context addendum (v2): the 14 rookie-flagged rows ONLY ───────
    # Headline = final-college-season (2025) production share, lifted from the
    # in-repo cfbfastR aggregation (fetch_college.aggregate_season — key-less
    # public parquet): WR/TE = player rec yards / team rec yards; RB = player
    # scrimmage yards / team scrimmage yards. Capital = display facts only
    # (H8r fence: no -pick signal, nothing folded into any score). Percentile
    # reference = the 2026 DRAFTED class at the same position (college-matched).
    import fetch_college as fc
    import nflreadpy as nfl

    def canon_school(s):
        if not isinstance(s, str):
            return ""
        return s.lower().replace(".", "").replace("st ", "state ").strip() \
                .replace("state", "st")

    rmask = out.coverage_flag == "rookie_no_prior_season"
    out["is_rookie_context"] = rmask
    out["draft_round"] = None
    out["draft_pick"] = None
    out["pct_among_2026_drafted_class"] = None
    if rmask.any():
        dp26 = nfl.load_draft_picks().to_pandas()
        dp26 = dp26[dp26.season == BOARD_SEASON].copy()
        # 2026-class quirk: the draft table's gsis_id column holds ELIAS-format
        # ids (not 00-00xxxxx) — canonical gsis not yet backfilled. Name join.
        dp26["nn"] = dp26["pfr_player_name"].map(norm_name)
        dp26["school_c"] = dp26["college"].map(canon_school)
        dp26["pos_n"] = dp26["position"].replace({"HB": "RB", "FB": "RB"})
        out["nn"] = out["player"].map(norm_name)
        capkey = dp26[["nn", "pos_n", "round", "pick", "school_c"]] \
            .rename(columns={"pos_n": "position"})
        assert not capkey.duplicated(["nn", "position"]).any(), \
            "2026 draft (name, position) collision — STOP"
        cap = out.loc[rmask, ["nn", "position"]].merge(
            capkey, on=["nn", "position"], how="left")
        assert cap["round"].notna().all(), \
            f"capital miss: {out.loc[rmask].iloc[cap['round'].isna().to_numpy()].player.tolist()}"
        out.loc[rmask, "draft_round"] = cap["round"].astype(int).to_numpy()
        out.loc[rmask, "draft_pick"] = cap["pick"].astype(int).to_numpy()
        rk_school = dict(zip(cap["nn"], cap["school_c"]))

        prod = fc.aggregate_season(2025)
        prod["nn"] = prod["name"].map(norm_name).map(lambda n: ROOKIE_ALIAS.get(n, n))
        prod["school_c"] = prod["team"].map(canon_school)
        prod["scrim_share"] = prod["scrim_yds"] / prod["team_scrim_yds"]

        def college_share(nn, pos):
            m = prod[prod.nn == nn]
            if len(m) > 1:
                m = m[m.school_c == rk_school.get(nn, "")]
            if len(m) != 1:
                return None
            r = m.iloc[0]
            if rk_school.get(nn) and r.school_c != rk_school[nn]:
                return None                       # school mismatch — refuse
            v = r.rec_yds_share if pos in ("WR", "TE") else r.scrim_share
            return None if pd.isna(v) else float(v)

        # percentile reference: 2026 drafted class at position, college-matched
        dpos = dp26.copy()
        dpos["pos_n"] = dpos["position"].replace({"HB": "RB", "FB": "RB"})
        ref = {}
        for pos in ("RB", "WR", "TE"):
            cls = dpos[dpos.pos_n == pos].merge(
                prod[["nn", "school_c", "rec_yds_share", "scrim_share"]],
                on=["nn", "school_c"], how="inner")
            vals = (cls["rec_yds_share"] if pos in ("WR", "TE")
                    else cls["scrim_share"]).dropna()
            assert len(vals) >= 8, f"{pos}: 2026 class reference too thin ({len(vals)})"
            ref[pos] = vals

        for i in out.index[rmask]:
            pos, nn = out.at[i, "position"], out.at[i, "nn"]
            v = college_share(nn, pos)
            if v is None:
                out.at[i, "coverage_flag"] = "rookie_college_no_match"
                continue
            out.at[i, "raw_value"] = v
            out.at[i, "metric_name"] = ROOKIE_METRIC[pos]
            out.at[i, "pct_among_2026_drafted_class"] = \
                round(100.0 * (ref[pos] < v).mean(), 1)
            out.at[i, "disclosure"] = ROOKIE_DISCLOSURE
        out = out.drop(columns=["nn"])

    # veteran rows must be value-identical to v1 on the original columns
    if OUT.exists():
        v1 = pd.read_csv(OUT)
        shared = [c for c in v1.columns if c in out.columns]
        a = out.loc[~rmask.to_numpy(), shared].reset_index(drop=True)
        b = v1.loc[v1.coverage_flag != "rookie_no_prior_season", shared] \
              .reset_index(drop=True)
        for c in shared:                       # None (in-memory) == NaN (CSV)
            if pd.api.types.is_numeric_dtype(b[c]):
                a[c] = pd.to_numeric(a[c], errors="coerce")
        pd.testing.assert_frame_equal(a, b, check_dtype=False)
        print("veteran rows verified value-identical to v1 on original columns")
    out.to_csv(OUT, index=False)

    print(f"wrote {OUT.name}: {len(out)} rows (one per board row)")
    print(f"NGS 2025 source: nflreadpy week-0 REG aggregates; provenance: {prov}")
    print("coverage by position (qualified / rookie / no-2025 / below-qualifier):")
    for pos in ["QB", "RB", "WR", "TE"]:
        g = out[out.position == pos]
        c = g.coverage_flag.value_counts()
        print(f"  {pos} (n={len(g)}): qualified {c.get('qualified', 0)}, "
              f"rookie {c.get('rookie_no_prior_season', 0)}, "
              f"no-2025 {c.get('no_2025_season', 0)}, "
              f"below-qualifier {c.get('below_vendor_qualifier', 0)}, "
              f"dataset-desync {c.get('not_in_2026_dataset', 0)}")
    assert sha(BAND) == band_hash_before, "phase4_band_2026.csv was modified — STOP"
    print("attestation: no outcome quantity computed; no correlation computed; "
          "no composite constructed; phase4 artifact unmodified (hash-verified).")


if __name__ == "__main__":
    main()
