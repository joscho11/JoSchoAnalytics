"""2026 Draft Board. CSV-only. No training in this repository.

The page compares market draft price to a published season projection for a frozen
180-player universe. Talent scores are descriptive context. They do not feed any
other column. Public copy must not name the Sleeper mix.
"""
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import page_common
from fantasy_scoring import DEFAULT_SCORING, SCORING_MODES
from dashboard_chrome import TABLE_HEIGHT, dataframe_phone_desktop

_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")

_HERE = Path(__file__).resolve().parent
SEAS = _HERE / "fantasy" / "seasonal_projections"
# Retained only for legacy metadata helpers below; it no longer defines the displayed board.
DATASET = SEAS / "season_dataset_2014_2026.csv"
# Daily, regenerable overlay for live Sleeper ADP and projection points. The frozen V2 source
# remains the authority for the 180-player universe and model values/ranks.
LIVE_OVERLAY = SEAS / "board_adp_live_2026.csv"
LIVE_ESPN_OVERLAY = SEAS / "board_espn_adp_live_2026.csv"
LIVE_YAHOO_OVERLAY = SEAS / "board_yahoo_adp_live_2026.csv"
MARKET_SNAPSHOT_ROOT = SEAS / "market_snapshots" / "2026"
# Legacy per-position files supply only optional Sleeper projection and team metadata.
# The independent model projection is read solely from INDEPENDENT_V2.
PROJ_RESULTS = _HERE / "fantasy" / "projections" / "results"
INDEPENDENT_V2 = PROJ_RESULTS / "independent_half_ppr_points_2026.csv"
ANALYST_PROJECTION_ADJUSTMENTS = (
    PROJ_RESULTS / "analyst_projection_adjustments_2026.csv"
)
# Dated roster corrections for board identity metadata only. These never alter a projection,
# rank, gap, or model input.
TEAM_OVERRIDES_2026 = {
    "MEN516487": "LV",   # Fernando Mendoza, Raiders, 2026-08-12
    "00-0035719": "SF",  # Deebo Samuel, re-signed, live Ourlads RWR1
    "00-0030279": "IND", # Keenan Allen, Colts one-year, 2026-08-17
    "00-0040142": "GB",  # Kaleb Johnson, Packers trade 2026-08-30
}


def _stamp_team_overrides(indexed: pd.DataFrame) -> pd.DataFrame:
    """Identity metadata only. Does not change a projection, rank, or gap."""
    keys = indexed.index.intersection(list(TEAM_OVERRIDES_2026))
    if len(keys):
        indexed = indexed.copy()
        indexed.loc[keys, "team"] = pd.Index(keys).map(TEAM_OVERRIDES_2026)
    return indexed


# Descriptive talent artifacts (fantasy/talent/, provenance-stamped). NFL Talent scores players
# with NFL history against NFL players at their own position; College Talent scores 2026 rookies
# (all four positions) against past prospects who reached the NFL. Disjoint by construction
# (artifact membership), different scales, and context-only — neither feeds any other column.
TALENT_DIR = _HERE / "fantasy" / "talent"
# R29 box-score talent. Since the per-position migration completed 2026-07-27 (R34/R37/R39/R41),
# every board position overwrites this, so it feeds NO rendered column. It is still read as the
# base layer — and still fingerprinted — so a missing per-position artifact degrades to the old
# value instead of blanking the column outright. Kept on disk, unregenerated, pinned md5.
TALENT_CSV = TALENT_DIR / "talent_score_2026.csv"
ROOKIE_CSV = TALENT_DIR / "rookie_score_2026.csv"
# College QB talent (SPEC R35). rookie_score_2026.csv carries NO QB rows, so rookie QBs had a
# blank College Talent cell; this fills them from the college QB build. Disjoint from
# ROOKIE_CSV by position, so the two sources cannot collide.
COLLEGE_QB_CSV = TALENT_DIR / "college_qb_score_2026.csv"
# College RB talent (SPEC R36). DESCRIPTIVE ONLY — the 8-facet charting index fired rc +0.329 (DEAD,
# < .35 band) against the shipped PBP instrument at +0.501, and carries no strength-of-schedule
# adjustment. Joseph directed it to REPLACE the box-score value on every RB row it covers.
COLLEGE_RB_CSV = TALENT_DIR / "college_rb_score_2026.csv"
# College WR talent (SPEC R38). DESCRIPTIVE ONLY — WR is dead across six instrument classes;
# a high score for a future bust is the construct working. REPLACES the box-score value on every
# WR row it covers, matching the RB policy.
COLLEGE_WR_CSV = TALENT_DIR / "college_wr_score_2026.csv"
# College TE talent (SPEC R40). DESCRIPTIVE ONLY — the TE instrument fired dead at +0.294 and
# +0.326, contested is functionally absent at 3.0% effective, and route-craft runs 77% against
# 68.5% nominal. REPLACES the box-score value on every TE row it covers.
COLLEGE_TE_CSV = TALENT_DIR / "college_te_score_2026.csv"
# NFL QB talent (SPEC R34) — supersedes the R29 QB vector inside talent_score_2026.csv, which is
# NOT regenerated and keeps its pinned md5. QB rows prefer this artifact; every other position
# reads talent_score_2026.csv unchanged, so the two can never collide.
NFL_QB_CSV = TALENT_DIR / "nfl_qb_score_2026.csv"
# NFL RB talent (SPEC R37) — dedicated 12-facet rush/receive build on qualified RBs (>=100
# carries in the 3-season window). Replaces the R29 PBP value for RB rows only; an RB below the
# volume floor is left BLANK rather than mixed across two scales.
NFL_RB_CSV = TALENT_DIR / "nfl_rb_score_2026.csv"
# NFL WR talent (SPEC R39) — dedicated 9-facet build on qualified WRs (>=250 routes in the
# 3-season window). Replaces the R29 value for WR rows; a WR below the volume floor is left
# BLANK rather than mixed across two scales.
NFL_WR_CSV = TALENT_DIR / "nfl_wr_score_2026.csv"
# NFL TE talent (SPEC R41) — the last per-position build. Replaces the R29 value for TE rows,
# which completes the migration: talent_score_2026.csv now feeds NO board column.
NFL_TE_CSV = TALENT_DIR / "nfl_te_score_2026.csv"
BOARD_SEASON = 2026


def _name_position_key(frame: pd.DataFrame) -> pd.Series:
    """Conservative fallback identity key for metadata-only legacy joins."""
    name = (frame["player"].astype("string").str.normalize("NFKD")
            .str.encode("ascii", "ignore").str.decode("ascii")
            .str.lower().str.replace(r"[^a-z0-9]", "", regex=True))
    return name + "|" + frame["position"].astype("string")


def _load_projections():
    """player_id -> (model projection, raw Sleeper projection) from the from-scratch
    season-total results. Concatenated across positions, deduped by player_id.

    Raw result CSVs remain model-only artifacts. A frozen explicit analyst overlay can
    replace the displayed point estimate for preselected 2026 player scenarios.
    """
    frames = []
    for p in ("rb", "wr", "te", "qb"):
        f = PROJ_RESULTS / f"{p}_projection_2026.csv"
        if f.exists():
            frames.append(
                pd.read_csv(
                    f,
                    usecols=[
                        "player_id", "player", "position", "team",
                        "projection", "sleeper",
                    ],
                )
            )
    if not frames:
        return pd.DataFrame(
            columns=[
                "player_id", "player", "position", "team",
                "projection", "sleeper",
            ]
        ).set_index("player_id")
    out = pd.concat(frames, ignore_index=True).drop_duplicates("player_id")
    out["model_projection_raw"] = out["projection"]
    out["projection_adjustment"] = pd.NA
    out["projection_adjustment_as_of"] = pd.NA
    if ANALYST_PROJECTION_ADJUSTMENTS.exists():
        adj = pd.read_csv(ANALYST_PROJECTION_ADJUSTMENTS)
        required = {
            "player_id", "player", "position", "raw_projection",
            "adjusted_projection", "method", "as_of",
        }
        missing_columns = required.difference(adj.columns)
        if missing_columns:
            raise ValueError(
                "Analyst projection overlay is missing columns: "
                f"{sorted(missing_columns)}"
            )
        if adj["player_id"].duplicated().any():
            duplicates = adj.loc[
                adj["player_id"].duplicated(keep=False), "player_id"
            ].tolist()
            raise ValueError(
                f"Duplicate analyst projection overlay player_id values: {duplicates}"
            )

        raw = out.set_index("player_id")
        overlay = adj.set_index("player_id")
        orphaned = overlay.index.difference(raw.index)
        if len(orphaned):
            raise ValueError(
                "Analyst projection overlay contains unknown player_id values: "
                f"{orphaned.tolist()}"
            )

        joined = raw.loc[overlay.index]
        identity_mismatch = (
            joined["player"].ne(overlay["player"])
            | joined["position"].ne(overlay["position"])
        )
        if identity_mismatch.any():
            bad = overlay.index[identity_mismatch].tolist()
            raise ValueError(
                "Analyst projection overlay player/position mismatch for: "
                f"{bad}"
            )

        expected_raw = pd.to_numeric(
            overlay["raw_projection"], errors="raise"
        )
        current_raw = pd.to_numeric(joined["projection"], errors="raise")
        stale = current_raw.sub(expected_raw).abs().gt(0.05)
        if stale.any():
            bad = overlay.index[stale].tolist()
            raise ValueError(
                "Analyst projection overlay is stale against raw projection "
                f"artifacts for: {bad}"
            )

        adjusted = pd.to_numeric(
            overlay["adjusted_projection"], errors="raise"
        )
        out = out.set_index("player_id")
        out.loc[overlay.index, "projection"] = adjusted
        out.loc[overlay.index, "projection_adjustment"] = overlay["method"]
        out.loc[overlay.index, "projection_adjustment_as_of"] = overlay["as_of"]

        # Optional dated ROSTER correction, on the same disclosed row as the scenario. The
        # projection artifacts carry each player's team as of the build, so a signing after
        # that date leaves the cell blank and the board renders blank as "not signed". A
        # non-empty code here overwrites the team for that player only. It is identity
        # metadata: it feeds no projection, no rank and no gap, and nothing is re-scored.
        if "team" in overlay.columns:
            team = overlay["team"].astype("string").str.strip()
            corrected = team[team.notna() & team.ne("")]
            malformed = corrected[~corrected.str.fullmatch(r"[A-Z]{2,3}")]
            if len(malformed):
                raise ValueError(
                    "Analyst overlay team corrections must be 2-3 letter uppercase team "
                    f"codes: {malformed.to_dict()}"
                )
            out.loc[corrected.index, "team"] = corrected
        out = out.reset_index()
    indexed = out.set_index("player_id") if "player_id" in out.columns else out
    return _stamp_team_overrides(indexed)


def _latest_market_scoring():
    """Return optional Sleeper standard/PPR season totals keyed by GSIS id."""
    snapshots = sorted(MARKET_SNAPSHOT_ROOT.glob("*/normalized.csv"))
    if not snapshots:
        return pd.DataFrame(columns=["gsis_id", "pts_half_ppr", "pts_std", "pts_ppr"])
    try:
        frame = pd.read_csv(
            snapshots[-1], usecols=["gsis_id", "pts_half_ppr", "pts_std", "pts_ppr"],
            dtype={"gsis_id": "string"},
        )
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return pd.DataFrame(columns=["gsis_id", "pts_half_ppr", "pts_std", "pts_ppr"])
    return frame.dropna(subset=["gsis_id"]).drop_duplicates("gsis_id")


@st.cache_data
def _load_board_2026_cached(source_fingerprint):
    if not INDEPENDENT_V2.exists():
        raise FileNotFoundError(f"Independent V2 board source is missing: {INDEPENDENT_V2}")
    df = pd.read_csv(INDEPENDENT_V2).copy()
    expected = {"season", "player_id", "player", "position", "adp_half_ppr",
                "adp_pos_rank", "projected_half_ppr", "projected_pos_rank"}
    missing = expected.difference(df.columns)
    if missing:
        raise ValueError(f"Independent V2 source is missing columns: {sorted(missing)}")
    if len(df) != 180 or set(df["position"]) != {"QB", "RB", "WR", "TE"}:
        raise ValueError("Independent V2 board must be the exact 180-player four-position universe")
    if df[["player", "position"]].duplicated().any() or df["projected_half_ppr"].isna().any():
        raise ValueError("Independent V2 board has duplicate player-position rows or blank projections")

    # The independent source is the board spine: its published player set and V2 ranks define the
    # exact evaluated universe. Legacy projection files provide only ancillary Sleeper projection and
    # team metadata; they never supply a fallback model projection.
    df["team"] = pd.NA
    df["model_proj"] = pd.to_numeric(df["projected_half_ppr"], errors="raise")
    df["model_proj_raw"] = df["model_proj"]
    df["projection_adjustment"] = pd.NA
    df["projection_adjustment_as_of"] = pd.NA
    df["pos_rank"] = pd.to_numeric(df["adp_pos_rank"], errors="raise").astype("Int64")
    df["model_proj_pos_rank"] = pd.to_numeric(
        df["projected_pos_rank"], errors="raise").astype("Int64")
    df["sleeper_proj"] = pd.NA
    df["sleeper_proj_half_ppr"] = pd.NA
    df["sleeper_proj_standard"] = pd.NA
    df["sleeper_proj_ppr"] = pd.NA
    live_market_loaded = False
    if LIVE_OVERLAY.exists():
        overlay = pd.read_csv(LIVE_OVERLAY)
        required_overlay = {"player", "position", "adp_half_ppr", "adp_pos_rank",
                            "sleeper_pts_half_ppr", "refreshed_at"}
        if len(overlay) == 180 and required_overlay <= set(overlay.columns):
            overlay["_name_position"] = _name_position_key(overlay)
            if not overlay["_name_position"].duplicated().any():
                overlay = overlay.set_index("_name_position")
                df["_name_position"] = _name_position_key(df)
                matched = df["_name_position"].isin(overlay.index)
                if matched.any():
                    df.loc[matched, "adp_half_ppr"] = df.loc[matched, "_name_position"].map(
                        overlay["adp_half_ppr"]
                    )
                    df.loc[matched, "pos_rank"] = pd.to_numeric(
                        df.loc[matched, "_name_position"].map(overlay["adp_pos_rank"]),
                        errors="raise",
                    ).astype("Int64")
                    df.loc[matched, "sleeper_proj"] = pd.to_numeric(
                        df.loc[matched, "_name_position"].map(overlay["sleeper_pts_half_ppr"]),
                        errors="coerce",
                    )
                    live_market_loaded = bool(matched.all())
                df = df.drop(columns="_name_position")

    df["espn_adp"] = pd.NA
    df["espn_pos_rank"] = pd.Series([pd.NA] * len(df), dtype="Int64")
    if LIVE_ESPN_OVERLAY.exists():
        espn = pd.read_csv(LIVE_ESPN_OVERLAY, dtype={"player_id": "string"})
        required_espn = {"player_id", "espn_adp", "espn_pos_rank", "refreshed_at"}
        if len(espn) == 180 and required_espn <= set(espn.columns):
            espn["player_id"] = espn["player_id"].astype("string")
            if not espn["player_id"].duplicated().any():
                espn_idx = espn.set_index("player_id")
                ids = df["player_id"].astype("string")
                hit = ids.isin(espn_idx.index)
                if hit.any():
                    df.loc[hit.to_numpy(), "espn_adp"] = pd.to_numeric(
                        ids[hit].map(espn_idx["espn_adp"]), errors="coerce"
                    )
                    df.loc[hit.to_numpy(), "espn_pos_rank"] = pd.to_numeric(
                        ids[hit].map(espn_idx["espn_pos_rank"]), errors="coerce"
                    ).astype("Int64")

    df["yahoo_adp"] = pd.NA
    df["yahoo_pos_rank"] = pd.Series([pd.NA] * len(df), dtype="Int64")
    if LIVE_YAHOO_OVERLAY.exists():
        yahoo = pd.read_csv(LIVE_YAHOO_OVERLAY, dtype={"player_id": "string"})
        required_yahoo = {"player_id", "yahoo_adp", "yahoo_pos_rank", "refreshed_at"}
        if len(yahoo) == 180 and required_yahoo <= set(yahoo.columns):
            yahoo["player_id"] = yahoo["player_id"].astype("string")
            if not yahoo["player_id"].duplicated().any():
                yahoo_idx = yahoo.set_index("player_id")
                ids = df["player_id"].astype("string")
                hit = ids.isin(yahoo_idx.index)
                if hit.any():
                    df.loc[hit.to_numpy(), "yahoo_adp"] = pd.to_numeric(
                        ids[hit].map(yahoo_idx["yahoo_adp"]), errors="coerce"
                    )
                    df.loc[hit.to_numpy(), "yahoo_pos_rank"] = pd.to_numeric(
                        ids[hit].map(yahoo_idx["yahoo_pos_rank"]), errors="coerce"
                    ).astype("Int64")

    legacy = _load_projections().reset_index() if any(
        (PROJ_RESULTS / f"{p}_projection_2026.csv").exists() for p in ("rb", "wr", "te", "qb")
    ) else pd.DataFrame(columns=["player_id", "player", "position", "team", "sleeper"])
    if not legacy.empty:
        legacy = legacy.drop_duplicates("player_id", keep=False).copy()
        by_id = legacy.set_index("player_id")
        resolved = df["player_id"].notna()
        df.loc[resolved, "team"] = df.loc[resolved, "player_id"].map(by_id["team"])
        if not live_market_loaded:
            df.loc[resolved, "sleeper_proj"] = df.loc[resolved, "player_id"].map(by_id["sleeper"])
        legacy["_name_position"] = _name_position_key(legacy)
        legacy = legacy[~legacy["_name_position"].duplicated(keep=False)].set_index("_name_position")
        df["_name_position"] = _name_position_key(df)
        unresolved = df["team"].isna() & df["_name_position"].isin(legacy.index)
        df.loc[unresolved, "team"] = df.loc[unresolved, "_name_position"].map(legacy["team"])
        if not live_market_loaded:
            missing_sleeper = df["sleeper_proj"].isna() & df["_name_position"].isin(legacy.index)
            df.loc[missing_sleeper, "sleeper_proj"] = df.loc[
                missing_sleeper, "_name_position"].map(legacy["sleeper"])
        df = df.drop(columns="_name_position")

    scoring_market = _latest_market_scoring().set_index("gsis_id")
    if not scoring_market.empty:
        ids = df["player_id"].astype("string")
        for _source, _target in (("pts_half_ppr", "sleeper_proj_half_ppr"),
                                 ("pts_std", "sleeper_proj_standard"),
                                 ("pts_ppr", "sleeper_proj_ppr")):
            df[_target] = pd.to_numeric(ids.map(scoring_market[_source]), errors="coerce")
    df["sleeper_proj_half_ppr"] = df["sleeper_proj_half_ppr"].where(
        df["sleeper_proj_half_ppr"].notna(), df["sleeper_proj"])

    # Explicit current-team metadata corrections, retained outside model artifacts.
    df.loc[df["player_id"].isin(TEAM_OVERRIDES_2026), "team"] = df["player_id"].map(
        TEAM_OVERRIDES_2026
    )

    # Talent scores — populated ONLY from artifact membership (disjoint by construction).
    df["nfl_talent"] = pd.NA
    df["college_talent"] = pd.NA
    if TALENT_CSV.exists():
        t = pd.read_csv(TALENT_CSV, usecols=["gsis_id", "score"]).set_index("gsis_id")
        df["nfl_talent"] = df["player_id"].map(t["score"])
    if NFL_QB_CSV.exists():
        # R34 REPLACES the R29 value for QBs (different instrument, different pool). A QB below
        # the qualified-starter pool is left BLANK rather than falling back to R29 — mixing two
        # scales in one column would be dishonest.
        nq = pd.read_csv(NFL_QB_CSV, usecols=["gsis_id", "score"]).dropna(subset=["gsis_id"])
        r34 = df["player_id"].map(nq.set_index("gsis_id")["score"])
        is_qb = df["position"].eq("QB")
        df.loc[is_qb, "nfl_talent"] = r34[is_qb]
    if NFL_RB_CSV.exists():
        nr = pd.read_csv(NFL_RB_CSV, usecols=["gsis_id", "score"]).dropna(subset=["gsis_id"])
        r37 = df["player_id"].map(nr.set_index("gsis_id")["score"])
        is_rb = df["position"].eq("RB")
        df.loc[is_rb, "nfl_talent"] = r37[is_rb]
    if NFL_WR_CSV.exists():
        nw = pd.read_csv(NFL_WR_CSV, usecols=["gsis_id", "score"]).dropna(subset=["gsis_id"])
        r39 = df["player_id"].map(nw.set_index("gsis_id")["score"])
        is_wr = df["position"].eq("WR")
        df.loc[is_wr, "nfl_talent"] = r39[is_wr]
    if NFL_TE_CSV.exists():
        nt = pd.read_csv(NFL_TE_CSV, usecols=["gsis_id", "score"]).dropna(subset=["gsis_id"])
        r41 = df["player_id"].map(nt.set_index("gsis_id")["score"])
        is_te = df["position"].eq("TE")
        df.loc[is_te, "nfl_talent"] = r41[is_te]
    if ROOKIE_CSV.exists():
        r = pd.read_csv(ROOKIE_CSV, usecols=["gsis_id", "rookie_score"]).set_index("gsis_id")
        df["college_talent"] = df["player_id"].map(r["rookie_score"])
    if COLLEGE_QB_CSV.exists():
        # 2026 rookie QBs only, keyed on the deploy player_id (brand-new players carry a
        # placeholder id, not a gsis, so the build resolved them by guarded name join).
        cq = pd.read_csv(COLLEGE_QB_CSV,
                         usecols=["nfl_player_id", "score", "is_2026_rookie"])
        cq = cq[cq["is_2026_rookie"].astype(bool) & cq["nfl_player_id"].notna()]
        qb_score = df["player_id"].map(cq.set_index("nfl_player_id")["score"])
        df["college_talent"] = df["college_talent"].where(
            df["college_talent"].notna(), qb_score)
    if COLLEGE_RB_CSV.exists():
        # RB college talent REPLACES the box-score rookie value wherever R36 has one
        # (Joseph's direction 2026-07-27, against the recommendation to fill blanks only —
        # the charting index fired rc +0.329 DEAD vs the PBP instrument's +0.501 CLEAN).
        cr = pd.read_csv(COLLEGE_RB_CSV, usecols=["nfl_player_id", "score", "is_2026_rookie"])
        cr = cr[cr["is_2026_rookie"].astype(bool) & cr["nfl_player_id"].notna()]
        rb_score = df["player_id"].map(cr.set_index("nfl_player_id")["score"])
        is_rb = df["position"].eq("RB")
        df.loc[is_rb, "college_talent"] = rb_score[is_rb].where(
            rb_score[is_rb].notna(), df.loc[is_rb, "college_talent"])
    if COLLEGE_WR_CSV.exists():
        cw = pd.read_csv(COLLEGE_WR_CSV, usecols=["nfl_player_id", "score", "is_2026_rookie"])
        cw = cw[cw["is_2026_rookie"].astype(bool) & cw["nfl_player_id"].notna()]
        wr_score = df["player_id"].map(cw.set_index("nfl_player_id")["score"])
        is_wr = df["position"].eq("WR")
        df.loc[is_wr, "college_talent"] = wr_score[is_wr].where(
            wr_score[is_wr].notna(), df.loc[is_wr, "college_talent"])
    if COLLEGE_TE_CSV.exists():
        ct = pd.read_csv(COLLEGE_TE_CSV, usecols=["nfl_player_id", "score", "is_2026_rookie"])
        ct = ct[ct["is_2026_rookie"].astype(bool) & ct["nfl_player_id"].notna()]
        te_score = df["player_id"].map(ct.set_index("nfl_player_id")["score"])
        is_te = df["position"].eq("TE")
        df.loc[is_te, "college_talent"] = te_score[is_te].where(
            te_score[is_te].notna(), df.loc[is_te, "college_talent"])

    for c in (
        "model_proj", "model_proj_raw", "sleeper_proj",
        "sleeper_proj_half_ppr", "sleeper_proj_standard", "sleeper_proj_ppr",
        "nfl_talent", "college_talent",
    ):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Sleeper ranks are ancillary and computed only across this exact V2 universe. V2 model ranks
    # come directly from the frozen source and are not recomputed.
    df["sleeper_proj_pos_rank"] = df.groupby("position")["sleeper_proj"] \
                       .rank(method="min", ascending=False).astype("Int64")
    df["sleeper_gap"] = (df["pos_rank"] - df["sleeper_proj_pos_rank"]).astype("Int64")
    df["model_gap"] = (df["pos_rank"] - df["model_proj_pos_rank"]).astype("Int64")
    return _attach_model_draft_rank(df)


def _board_source_fingerprint():
    """Cache key for every local artifact that contributes to the board."""
    paths = [
        INDEPENDENT_V2,
        LIVE_OVERLAY,
        LIVE_ESPN_OVERLAY,
        LIVE_YAHOO_OVERLAY,
        *(PROJ_RESULTS / f"{position}_projection_2026.csv"
          for position in ("rb", "wr", "te", "qb")),
        ANALYST_PROJECTION_ADJUSTMENTS,
        *(MARKET_SNAPSHOT_ROOT.glob("*/normalized.csv")),
        TALENT_CSV,
        ROOKIE_CSV,
        COLLEGE_QB_CSV,
        COLLEGE_RB_CSV,
        COLLEGE_WR_CSV,
        COLLEGE_TE_CSV,
        NFL_QB_CSV,
        NFL_RB_CSV,
        NFL_WR_CSV,
        NFL_TE_CSV,
    ]
    return tuple(
        (str(path), path.stat().st_mtime_ns, path.stat().st_size)
        if path.exists() else (str(path), None, None)
        for path in paths
    )


def _load_adjustment_disclosure():
    """Small audit table for the collapsed on-page overlay disclosure."""
    if not ANALYST_PROJECTION_ADJUSTMENTS.exists():
        return pd.DataFrame(
            columns=["Position", "Player", "Team", "Raw model", "Board value", "Basis",
                     "Reason", "As of"]
        )
    adj = pd.read_csv(
        ANALYST_PROJECTION_ADJUSTMENTS,
        usecols=[
            "position", "player", "team", "raw_projection", "adjusted_projection",
            "method", "as_of", "note",
        ],
    )
    adj["method"] = adj["method"].str.replace("_", " ", regex=False)
    return (
        adj.rename(
            columns={
                "position": "Position",
                "player": "Player",
                "team": "Team",
                "raw_projection": "Raw model",
                "adjusted_projection": "Board value",
                "method": "Basis",
                "as_of": "As of",
                "note": "Reason",
            }
        )
        .sort_values(["Position", "Player"], kind="stable")
        .reset_index(drop=True)
    )


# Same cutoffs as the in-house VOR board (phase0_benchmark / model_rankings CSV).
MODEL_DRAFT_REPLACEMENT = {"QB": 14, "RB": 30, "WR": 36, "TE": 14}


def _attach_model_draft_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Overall snake-draft order from Model Proj minus a replacement starter.

    Rank 1 is the largest points-over-replacement. Frozen with Model Proj; ADP
    is not an input. Ties keep source order.
    """
    out = df.copy()
    pts = pd.to_numeric(out["model_proj"], errors="raise")
    repl = {}
    for pos, n in MODEL_DRAFT_REPLACEMENT.items():
        pool = pts[out["position"].eq(pos)].nlargest(n)
        if len(pool) < n:
            raise ValueError(f"{pos} board has {len(pool)} projections, need {n}")
        repl[pos] = float(pool.iloc[-1])
    vor = pts - out["position"].map(repl)
    order = vor.sort_values(ascending=False, kind="mergesort")
    out["model_draft_rank"] = pd.Series(
        range(1, len(out) + 1), index=order.index,
    ).astype("Int64")
    return out


def _load_board_2026():
    return _load_board_2026_cached(_board_source_fingerprint())


def apply_scoring_mode(df: pd.DataFrame, scoring: str) -> pd.DataFrame:
    """Recalculate board point estimates and their positional ranks."""
    out = df.copy()
    if scoring == DEFAULT_SCORING:
        return out
    source_col = {
        "Standard": "sleeper_proj_standard",
        "PPR": "sleeper_proj_ppr",
    }[scoring]
    current = pd.to_numeric(out["sleeper_proj"], errors="coerce")
    selected = pd.to_numeric(out[source_col], errors="coerce").where(
        pd.to_numeric(out[source_col], errors="coerce").notna(), current
    )
    delta = selected - current
    out["sleeper_proj"] = selected
    out["model_proj"] = pd.to_numeric(out["model_proj"], errors="coerce") + delta.fillna(0)
    out["model_proj_pos_rank"] = out.groupby("position")["model_proj"].rank(
        method="min", ascending=False
    ).astype("Int64")
    out["sleeper_proj_pos_rank"] = out.groupby("position")["sleeper_proj"].rank(
        method="min", ascending=False
    ).astype("Int64")
    out["model_gap"] = (out["pos_rank"] - out["model_proj_pos_rank"]).astype("Int64")
    out["sleeper_gap"] = (out["pos_rank"] - out["sleeper_proj_pos_rank"]).astype("Int64")
    return _attach_model_draft_rank(out)


# Preserve the existing test/maintenance API while the cached implementation
# receives a real source-dependent key.
_load_board_2026.clear = _load_board_2026_cached.clear


# ---------------------------------------------------------------------------
# Players outside the current Sleeper draft market (2026-07-28)
# ---------------------------------------------------------------------------
# The board above is the DRAFT-PRICE universe: every player carrying a 2026 Sleeper half-PPR
# ADP. The projection artifacts cover many more players than that. Everyone the model projects
# who has NO current Sleeper ADP is listed in a separate collapsed explorer instead, with no
# price columns at all — there is no draft price for them, and none is invented. Sleeper ADP,
# Sleeper Proj, Position Rank and both gap columns are structurally absent there.
_NFL_TALENT_BY_POSITION = {
    "QB": NFL_QB_CSV, "RB": NFL_RB_CSV, "WR": NFL_WR_CSV, "TE": NFL_TE_CSV,
}
_COLLEGE_TALENT_BY_POSITION = {
    "QB": COLLEGE_QB_CSV, "RB": COLLEGE_RB_CSV,
    "WR": COLLEGE_WR_CSV, "TE": COLLEGE_TE_CSV,
}
_OUTSIDE_IDENTITY = ["player_id", "player", "position", "team"]
_OUTSIDE_COLS = _OUTSIDE_IDENTITY + [
    "model_proj", "model_proj_pos_rank_full", "nfl_talent", "college_talent",
]


def _nfl_talent_by_gsis(path):
    """gsis_id -> NFL Talent score from one per-position NFL artifact.

    Same instrument and same artifact the board above reads. An id resolving to more than one
    row is AMBIGUOUS and dropped, so a bad artifact leaves a blank cell instead of an
    arbitrary pick.
    """
    nfl = pd.read_csv(path, usecols=["gsis_id", "score"], dtype={"gsis_id": str})
    keep = nfl["gsis_id"].notna() & nfl["score"].notna()
    nfl = nfl[keep]
    nfl = nfl[~nfl["gsis_id"].duplicated(keep=False)]
    return nfl.set_index("gsis_id")["score"]


def _college_talent_by_join_id(path):
    """Coalesced NFL id -> College Talent score from one per-position college artifact.

    ID seam (verified 2026-07-28 against the shipped artifacts): a veteran's college row
    carries his NFL id in `gsis_id` and leaves `nfl_player_id` blank, while a brand-new
    deploy row carries it in `nfl_player_id`. Coalescing nfl_player_id OVER gsis_id resolves
    both without ever falling back to a name join — an unguarded name join across ~2,900
    college rows would silently collide on common names. Any coalesced id resolving to more
    than one college row is AMBIGUOUS and dropped outright; that player keeps a blank cell.
    """
    college = pd.read_csv(
        path,
        usecols=["gsis_id", "nfl_player_id", "score"],
        dtype={"gsis_id": str, "nfl_player_id": str},
    )
    join_id = college["nfl_player_id"].combine_first(college["gsis_id"])
    keep = join_id.notna() & college["score"].notna()
    join_id, scores = join_id[keep], college.loc[keep, "score"]
    ambiguous = join_id.duplicated(keep=False)
    return pd.Series(
        scores[~ambiguous].to_numpy(), index=pd.Index(join_id[~ambiguous].to_numpy())
    )


@st.cache_data
def _load_outside_market_players_cached(source_fingerprint):
    """Every projected 2026 player who is NOT on the 245-row draft-price board.

    Starts from `_load_projections()`, so the analyst overlay and every other projection rule
    that governs the board above governs this view too. Identity fields come from the
    projection artifacts (current 2026 team included).
    """
    proj = _load_projections().reset_index()
    proj["model_proj"] = pd.to_numeric(proj["projection"], errors="coerce")
    # Positional rank across the COMPLETE projection pool, computed BEFORE the board rows are
    # removed — so "WR105" here means the same thing it would mean on the board above, not a
    # rank within this leftover subset.
    proj["model_proj_pos_rank_full"] = (
        proj.groupby("position")["model_proj"]
            .rank(method="min", ascending=False).astype("Int64")
    )
    board_ids = set(_load_board_2026_cached(source_fingerprint)["player_id"])
    out = proj[~proj["player_id"].isin(board_ids)].copy()

    # Talent scores. Unlike the board above — where the two columns are disjoint by artifact
    # membership — this explorer lets both coexist on one row: a veteran outside the draft
    # market can have an NFL Talent score AND a college row from his prospect years. They stay
    # two separate columns on two separate scales and neither feeds anything else.
    out["nfl_talent"] = pd.NA
    out["college_talent"] = pd.NA
    for position, path in _NFL_TALENT_BY_POSITION.items():
        if not path.exists():
            continue
        rows = out["position"].eq(position)
        out.loc[rows, "nfl_talent"] = out.loc[rows, "player_id"].map(
            _nfl_talent_by_gsis(path))
    for position, path in _COLLEGE_TALENT_BY_POSITION.items():
        if not path.exists():
            continue
        rows = out["position"].eq(position)
        out.loc[rows, "college_talent"] = out.loc[rows, "player_id"].map(
            _college_talent_by_join_id(path))
    for column in ("model_proj", "nfl_talent", "college_talent"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    return out[_OUTSIDE_COLS].reset_index(drop=True)


@st.cache_data
def _projection_pool_size_cached(source_fingerprint):
    """Size of the complete model-projection pool the positional rank is taken against."""
    return int(len(_load_projections()))


def _load_outside_market_players():
    return _load_outside_market_players_cached(_board_source_fingerprint())


def _projection_pool_size():
    return _projection_pool_size_cached(_board_source_fingerprint())


# Same maintenance API as the board loader, keyed on the same fingerprint, so a changed
# projection or talent artifact invalidates BOTH views together.
_load_outside_market_players.clear = _load_outside_market_players_cached.clear
_projection_pool_size.clear = _projection_pool_size_cached.clear


@st.cache_data
def _refresh_date():
    """The valid V2-universe live-market overlay date, or None if absent/stale-schema."""
    if not LIVE_OVERLAY.exists():
        return None
    try:
        overlay = pd.read_csv(LIVE_OVERLAY)
        required = {"player", "position", "adp_half_ppr", "adp_pos_rank",
                    "sleeper_pts_half_ppr", "refreshed_at"}
        if len(overlay) != 180 or not required <= set(overlay.columns):
            return None
        return str(overlay["refreshed_at"].iloc[0])
    except (KeyError, ValueError, pd.errors.EmptyDataError):
        return None


def _pretty_iso_date(iso) -> str:
    try:
        stamp = date.fromisoformat(str(iso)[:10])
        return f"{_MONTHS[stamp.month - 1]} {stamp.day}, {stamp.year}"
    except (ValueError, TypeError):
        return str(iso)


def _overlay_refresh_date(path: Path, adp_col: str, rank_col: str):
    """The valid 180-row overlay date, or None if absent/stale-schema."""
    if not path.exists():
        return None
    try:
        overlay = pd.read_csv(path, dtype={"player_id": "string"})
        required = {"player_id", adp_col, rank_col, "refreshed_at"}
        if len(overlay) != 180 or not required <= set(overlay.columns):
            return None
        return str(overlay["refreshed_at"].iloc[0])
    except (KeyError, ValueError, pd.errors.EmptyDataError):
        return None


@st.cache_data
def _espn_refresh_date():
    return _overlay_refresh_date(LIVE_ESPN_OVERLAY, "espn_adp", "espn_pos_rank")


@st.cache_data
def _yahoo_refresh_date():
    return _overlay_refresh_date(LIVE_YAHOO_OVERLAY, "yahoo_adp", "yahoo_pos_rank")


def _adp_caption(market: str = "Sleeper ADP"):
    if market == MODEL_DRAFT_MARKET:
        iso = _refresh_date()
        if not iso:
            return ("The draft-price column is Model Draft Rank (1.0 = first). "
                    "Position Rank, Sleeper Gap, and Model Gap stay on Sleeper ADP. "
                    "Model Proj is frozen. Live Sleeper ADP will appear after the next "
                    "successful daily market pull.")
        pretty = _pretty_iso_date(iso)
        return (f"The draft-price column is Model Draft Rank (1.0 = first). "
                f"Position Rank, Sleeper Gap, and Model Gap stay on Sleeper ADP "
                f"(live refresh {pretty}). Model Proj points and ranks remain frozen until "
                "the early-September snapshot.")
    if market == ESPN_ADP_MARKET:
        iso = _espn_refresh_date()
        if not iso:
            return ("Model Proj is frozen. "
                    "ESPN ADP will appear after the next successful ESPN market pull. "
                    "Sleeper prices stay on the Sleeper view.")
        pretty = _pretty_iso_date(iso)
        return (f"Live ESPN ADP refresh: {pretty}. Draft-price ranks, Sleeper Gap, "
                "and Model Gap update from this pull; Model Proj points and ranks remain "
                "frozen until the early-September snapshot. ESPN publishes one ADP, "
                "not a half-PPR-specific ranking.")
    if market == YAHOO_ADP_MARKET:
        iso = _yahoo_refresh_date()
        if not iso:
            return ("Model Proj is frozen. "
                    "Yahoo ADP will appear after the next successful Yahoo market pull. "
                    "Sleeper prices stay on the Sleeper view.")
        pretty = _pretty_iso_date(iso)
        return (f"Live Yahoo ADP refresh: {pretty}. Draft-price ranks, Sleeper Gap, "
                "and Model Gap update from this pull; Model Proj points and ranks remain "
                "frozen until the early-September snapshot. Yahoo publishes one ADP, "
                "not a half-PPR-specific ranking. Players Yahoo has not priced stay blank.")
    iso = _refresh_date()
    if not iso:
        return ("Model Proj is frozen. "
                "Live Sleeper ADP and Sleeper projection refreshes will appear after the next "
                "successful daily market pull.")
    pretty = _pretty_iso_date(iso)
    return (f"Live Sleeper ADP and Sleeper projection refresh: {pretty}. Draft-price ranks, "
            "Sleeper ranks, Sleeper Gap, and Model Gap update from this pull; Model Proj "
            "points and ranks remain frozen until the early-September snapshot.")


# Sortable display column -> the underlying NUMERIC field it sorts on. Every sentinel
# (a rookie QB with no projection = NaN gap/rank/proj, a player with no talent score) is
# NaN in its numeric key, so na_position="last" sinks it to the BOTTOM in BOTH directions.
# Insertion order sets the selector order; "Sleeper ADP" is first, so it is the default.
SORT_KEYS = {
    "Sleeper ADP": "adp_half_ppr",
    "Position Rank": "pos_rank",
    "Sleeper Proj Position Rank": "sleeper_proj_pos_rank",
    "Sleeper Gap": "sleeper_gap",
    "Model Proj Position Rank": "model_proj_pos_rank",
    "Model Draft Rank": "model_draft_rank",
    "Model Gap": "model_gap",
    "Sleeper Proj": "sleeper_proj",
    "Model Proj": "model_proj",
    "NFL Talent Score": "nfl_talent",
    "College Talent Score": "college_talent",
}

ADP_MARKETS = ("Sleeper ADP", "ESPN ADP", "Yahoo ADP")
DEFAULT_ADP_MARKET = "Sleeper ADP"
ESPN_ADP_MARKET = "ESPN ADP"
YAHOO_ADP_MARKET = "Yahoo ADP"
MODEL_DRAFT_MARKET = "Model Draft Rank"
BOARD_VIEWS = ADP_MARKETS + (MODEL_DRAFT_MARKET,)
_MARKET_PRICE_COLS = {
    ESPN_ADP_MARKET: ("espn_adp", "espn_pos_rank"),
    YAHOO_ADP_MARKET: ("yahoo_adp", "yahoo_pos_rank"),
}


def sort_keys_for(market: str) -> dict:
    """Sort labels for the selected board view. The view's own order is first."""
    if market not in BOARD_VIEWS:
        market = DEFAULT_ADP_MARKET
    keys = {market: "adp_half_ppr"}
    for label, column in SORT_KEYS.items():
        if label == "Sleeper ADP" or label == market:
            continue
        keys[label] = column
    return keys


def apply_board_market(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """Reprice the 180 from the selected ADP source. Model Proj ranks and
    Model Draft Rank stay frozen.

    Sleeper remains the stored default. ESPN and Yahoo copy their overlay price
    and position rank onto the displayed columns and recompute both gaps.
    Unmatched rows stay blank. Sleeper prices are never used as a fill.
    Model Draft Rank fills the draft-price column with the overall order
    (1.0 = first). Position Rank and both gaps stay on Sleeper ADP.
    """
    out = df.copy()
    if market == MODEL_DRAFT_MARKET:
        out["adp_half_ppr"] = pd.to_numeric(
            out["model_draft_rank"], errors="raise"
        ).astype(float)
        return out
    spec = _MARKET_PRICE_COLS.get(market)
    if spec is None:
        return out
    adp_col, rank_col = spec
    out["adp_half_ppr"] = pd.to_numeric(out[adp_col], errors="coerce")
    out["pos_rank"] = pd.to_numeric(out[rank_col], errors="coerce").astype("Int64")
    out["sleeper_gap"] = (out["pos_rank"] - out["sleeper_proj_pos_rank"]).astype("Int64")
    out["model_gap"] = (out["pos_rank"] - out["model_proj_pos_rank"]).astype("Int64")
    return out

# Columns whose direction defaults to DESCENDING when you select them. These four are MAGNITUDE
# columns — more points, more talent — so the interesting end is the top, and ascending-first made
# you flip the toggle every time. Everything else stays ascending-first because it is a RANK or a
# draft price, where 1 / earliest is the interesting end. The toggle is never removed, only
# re-defaulted, and each sort column remembers the direction you last set for it.
DESCENDING_FIRST = {"Sleeper Proj", "Model Proj", "NFL Talent Score", "College Talent Score"}


def _sort_board(view, sort_label, ascending, sort_keys=None):
    """Sort by the numeric field behind a display column. Sentinels (NaN sort keys) always
    sink to the bottom, in both directions (na_position='last'). Stable so ties keep order."""
    keys = sort_keys if sort_keys is not None else SORT_KEYS
    key = keys.get(sort_label, "adp_half_ppr")
    return view.sort_values(key, ascending=ascending, na_position="last", kind="stable")


# Surface tint marking the ACTIVE SORT column. A green surface rather than a neutral one, so
# the column you are sorting on reads at a glance. Deliberately darker and less saturated than
# the value greens in `_rg_color`: the gap and rank numbers render ON TOP of this cell in their
# own red-to-green scale, so a vivid green here would both wash them out and blur "this column
# is sorted" (interaction state) into "this number is positive" (meaning).
# Tuning history — BOTH earlier values were rejected by Joseph for reading GREY on the deployed
# dark skin: #1b5e3a (2026-07-27) and then #16703a (2026-07-29). Both were green by hex but too
# dark (HSL lightness 24% and 26%) to read as green against the near-black table surface. This
# one lifts lightness to 33% and keeps the hue, so it reads green at a glance while staying well
# below the value greens rendered on top of it (rgb(0,200,82) at full ratio).
# DO NOT darken it back below the floor pinned in tests/test_board_page.py
# (`test_semantic_gap_colors_and_active_sort_tint`): green channel >= 120 and green dominant over
# red/blue by >= 60. A change that trips those is the grey regression coming back.
_SORT_TINT = "#1a8f45"


def _rg_color(ratio: float) -> str:
    """Shared Weekly Fantasy red-to-green semantic ramp.

    ``ratio=0`` is the established red, ``ratio=.5`` amber, and ``ratio=1``
    the established green. Color encodes only the underlying number's direction
    or magnitude; it is never a recommendation.
    """
    ratio = max(0.0, min(1.0, float(ratio)))
    r = int(round(255 * (1 - ratio)))
    g = int(round(82 + 118 * ratio))
    return f"rgb({r},{g},82)"


def _gap_color(value: float, cap: float) -> str:
    """A true diverging gap ramp: red below zero, amber at zero, green above."""
    value = max(-cap, min(cap, float(value)))
    if value <= 0:
        # Red -> amber. Retaining red at the negative end prevents a small
        # negative gap from accidentally reading as green on the sequential ramp.
        ratio = (value + cap) / cap
        r, g = 255, int(round(82 + (193 - 82) * ratio))
    else:
        # Amber -> the same established Weekly Fantasy green.
        ratio = value / cap
        r, g = int(round(255 * (1 - ratio))), int(round(193 + (200 - 193) * ratio))
    return f"rgb({r},{g},82)"


def _gap_cap(universe: pd.DataFrame) -> float:
    """Robust symmetric color cap so one extreme gap cannot wash out the table."""
    values = pd.concat(
        [pd.to_numeric(universe.get("sleeper_gap"), errors="coerce"),
         pd.to_numeric(universe.get("model_gap"), errors="coerce")],
        ignore_index=True,
    ).dropna().abs()
    if values.empty:
        return 1.0
    # Full saturation at the 95th percentile keeps ordinary differences legible
    # while still making the most extreme disagreements visibly distinct.
    return max(1.0, float(values.quantile(0.95)))


# Single source of truth for each display column's label + tooltip, shared by the
# st.dataframe column_config AND the visible "what each column means" guide, so the strings
# are byte-identical in both places. Labels are the exact on-screen headers.
_TXT, _NUM = "text", "number"
COLUMN_META = [
    ("player", _TXT, "Player", "Player name.", {}),
    ("position", _TXT, "Position", "His position.", {"width": "small"}),
    ("team", _TXT, "Team", "His 2026 team. Blank = not signed / unavailable.", {"width": "small"}),
    ("adp_half_ppr", _NUM, "Sleeper ADP",
     "Average draft position from the selected source (Sleeper half-PPR, ESPN, or Yahoo). "
     "ESPN and Yahoo each publish one ADP, not a half-PPR-specific ranking. Lower = earlier.",
     {"format": "%.1f"}),
    ("pos_rank", _NUM, "Position Rank",
     "His rank at his position by draft price (1 = first off the board at the position).",
     {"format": "%d", "width": "small"}),
    ("sleeper_proj_pos_rank", _NUM, "Sleeper Proj Position Rank",
     "His rank at his position by Sleeper's season projection (1 = highest projected).",
     {"format": "%d", "width": "small"}),
    ("sleeper_gap", _NUM, "Sleeper Gap",
     "Position Rank minus Sleeper Proj Position Rank. Positive = Sleeper's projection ranks "
     "him higher than his draft cost; negative = lower. A descriptive difference, not advice. "
     "Blank = no Sleeper projection.", {"format": "%d", "width": "small"}),
    ("model_proj_pos_rank", _NUM, "Model Proj Position Rank",
     "His published rank at his position in the 180-player Model Proj universe "
     "(1 = highest projected).", {"format": "%d", "width": "small"}),
    ("model_gap", _NUM, "Model Gap",
     "Position Rank minus Model Proj Position Rank. Positive = Model Proj ranks him higher "
     "than his draft cost; negative = lower. Backtested on 2021-2025 and not live-validated. "
     "A descriptive difference, not advice.",
     {"format": "%d", "width": "small"}),
    ("sleeper_proj", _NUM, "Sleeper Proj",
     "Sleeper's projected season-total half-PPR points (raw).",
     {"format": "%d", "width": "small"}),
    ("model_proj", _NUM, "Model Proj",
     "Published season-total half-PPR points on this board. Frozen until the "
     "early-September snapshot. ADP is not a model input. Backtested on 2021-2025 "
     "and not live-validated.",
     {"format": "%d", "width": "small"}),
    ("nfl_talent", _NUM, "NFL Talent Score",
     "My model-based per-opportunity talent estimate for players with NFL history, net of "
     "situation where identifiable. It ranks NFL players against NFL players — a different "
     "scale from College Talent Score. Every position uses a dedicated per-position build "
     "scored against qualified starters at that position. "
     "Descriptive context only; feeds no other column. Blank = no NFL history, or below "
     "the qualified-starter volume floor.",
     {"format": "%d", "width": "small"}),
    ("college_talent", _NUM, "College Talent Score",
     "A college-production read for 2026 rookies, scaled against past prospects who reached the "
     "NFL — a different scale from NFL Talent Score. Every position now has its own dedicated "
     "college build (QB from college passing; RB, WR and TE from their own college charting "
     "builds), each with its own volume floor; a rookie the build does not cover falls back to "
     "the older college box-score value where one exists. It carries no strength-of-schedule "
     "adjustment, so a big number against weaker opponents reads the same as one against "
     "stronger. Descriptive context only; feeds no other column. Blank = has NFL history, or "
     "college data unavailable (players outside FBS can never be covered).",
     {"format": "%d", "width": "small"}),
]
_DISPLAY_COLS = [m[0] for m in COLUMN_META]
_EXPORT_NAMES = {m[0]: m[2] for m in COLUMN_META}       # colkey -> on-screen label


_ADP_COLUMN_HELP = {
    ESPN_ADP_MARKET: (
        "Average draft position from ESPN. ESPN publishes one ADP, not a "
        "half-PPR-specific ranking. Lower = earlier."
    ),
    YAHOO_ADP_MARKET: (
        "Average draft position from Yahoo. Yahoo publishes one ADP, not a "
        "half-PPR-specific ranking. Players Yahoo has not priced stay blank. "
        "Lower = earlier."
    ),
    MODEL_DRAFT_MARKET: (
        "Overall snake-draft order from Model Proj after subtracting a "
        "replacement starter at each position. 1.0 = first. One decimal, same "
        "as ADP. Not a market price."
    ),
}


def column_meta_for(market: str = DEFAULT_ADP_MARKET):
    """Display metadata for the selected draft-price source."""
    help_ = _ADP_COLUMN_HELP.get(market)
    if help_ is None:
        return COLUMN_META
    rows = []
    for item in COLUMN_META:
        if item[0] != "adp_half_ppr":
            rows.append(item)
            continue
        rows.append((
            "adp_half_ppr", _NUM, market, help_, {"format": "%.1f"},
        ))
    return rows


def export_names_for(market: str = DEFAULT_ADP_MARKET) -> dict:
    return {m[0]: m[2] for m in column_meta_for(market)}

# Optional compact view. The board's spine is the price-vs-projection COMPARISON (ranks and
# gaps); these four are the raw point estimates and the two descriptive talent scores. They ship
# VISIBLE by default (Joseph's call 2026-07-27) and the toggle drops them for a narrower table.
# This is a DISPLAY split only: _DISPLAY_COLS is unchanged, so the CSV download always carries all
# thirteen columns in either mode, and model_proj_raw stays out of both.
_DETAIL_ONLY = ("sleeper_proj", "model_proj", "nfl_talent", "college_talent")
_COMPACT_COLS = [c for c in _DISPLAY_COLS if c not in _DETAIL_ONLY]
# Phone spine: who, draft price, both gaps, and NFL Talent. Raw points and
# College Talent stay on desktop. Phone is its own layout, not a subset of
# compact, so NFL Talent stays on the phone board even when the compact
# toggle hides it on desktop.
_PHONE_COLS = [
    "player", "position", "adp_half_ppr", "pos_rank", "sleeper_gap", "model_gap",
    "nfl_talent",
]
# Short headers + pinned pixel widths so the extra talent column fits. 50px is
# the grid's hard minimum. Player stays unpinned and takes leftover space.
_PHONE_LABELS = {
    "position": "Pos",
    "adp_half_ppr": "ADP",
    "pos_rank": "Rank",
    "sleeper_gap": "S Gap",
    "model_gap": "M Gap",
    "nfl_talent": "NFL",
}
_PHONE_WIDTHS = {
    "position": 50,
    "adp_half_ppr": 54,
    "pos_rank": 50,
    "sleeper_gap": 54,
    "model_gap": 54,
    "nfl_talent": 50,
}

# Row counter for the rendered view only — it numbers the rows as currently sorted and
# filtered, so a long scroll stays easy to follow. Deliberately NOT part of COLUMN_META /
# _DISPLAY_COLS: it is not board data, carries no meaning, and stays out of the CSV export.
_ROW_NO = "row_no"
_ROW_NO_HELP = ("Row number in the board as currently sorted and filtered — a counter to keep "
                "your place, not a ranking.")
# 50px is the grid's hard minimum column width — three digits plus padding, nothing more.
# It must ALSO be pinned: in a stretch-width table every unpinned column carries grow=1 and
# absorbs an equal share of the leftover space, which is what made a "small" (75px) counter
# render far wider than its contents. Pinned columns get grow=0, so this width is exact
# (and the counter stays put when the wide board scrolls sideways).
_ROW_NO_WIDTH = 50
_TALENT_KEYS = ("nfl_talent", "college_talent")


def _blank_missing_talent(series: pd.Series, decimals: int) -> pd.Series:
    """Display blanks for missing talent so Streamlit does not print the word None."""
    def _one(v):
        if pd.isna(v):
            return ""
        x = float(v)
        if decimals == 0:
            return str(int(round(x)))
        return f"{x:.{decimals}f}"
    return series.map(_one)


def _column_config(active_sort_key: str | None = None, ascending: bool = True,
                   market: str = DEFAULT_ADP_MARKET):
    """Build the table config and visibly mark the active numeric sort key."""
    cfg = {_ROW_NO: st.column_config.NumberColumn("#", help=_ROW_NO_HELP, format="%d",
                                                  width=_ROW_NO_WIDTH, pinned=True)}
    for key, kind, label, help_, extra in column_meta_for(market):
        if key == active_sort_key:
            arrow = "↑" if ascending else "↓"
            label = f"{arrow} {label}"
            help_ = f"Current sort field ({'low to high' if ascending else 'high to low'}). {help_}"
        if key in _TALENT_KEYS:
            extra = {k: v for k, v in extra.items() if k != "format"}
            # Displayed as text so missing scores stay blank, not the word None.
            # Right-align so they sit with the other numeric columns.
            cfg[key] = st.column_config.TextColumn(
                label, help=help_, alignment="right", **extra)
            continue
        col = st.column_config.NumberColumn if kind == _NUM else st.column_config.TextColumn
        cfg[key] = col(label, help=help_, **extra)
    return cfg


def _phone_column_config(active_sort_key: str | None = None, ascending: bool = True,
                         market: str = DEFAULT_ADP_MARKET):
    """Phone grid: same help/format as desktop, shorter labels, pinned widths."""
    meta = {m[0]: m for m in column_meta_for(market)}
    cfg = {_ROW_NO: st.column_config.NumberColumn("#", help=_ROW_NO_HELP, format="%d",
                                                  width=_ROW_NO_WIDTH, pinned=True)}
    for key in _PHONE_COLS:
        _kind, label, help_, extra = meta[key][1], meta[key][2], meta[key][3], dict(meta[key][4])
        label = _PHONE_LABELS.get(key, label)
        if market == MODEL_DRAFT_MARKET and key == "adp_half_ppr":
            label = "Drft"
        if key == active_sort_key:
            arrow = "↑" if ascending else "↓"
            label = f"{arrow} {label}"
            help_ = f"Current sort field ({'low to high' if ascending else 'high to low'}). {help_}"
        if key in _PHONE_WIDTHS:
            extra["width"] = _PHONE_WIDTHS[key]
            extra["pinned"] = True
        if key in _TALENT_KEYS:
            extra.pop("format", None)
            cfg[key] = st.column_config.TextColumn(
                label, help=help_, alignment="right", **extra)
            continue
        col = st.column_config.NumberColumn if _kind == _NUM else st.column_config.TextColumn
        cfg[key] = col(label, help=help_, **extra)
    return cfg


def _style_board(view: pd.DataFrame, universe: pd.DataFrame, active_sort_key: str):
    """Return a semantic table style aligned with Weekly Fantasy.

    Gap columns are diverging: negative is red, zero amber, positive green.
    Rank columns are sequential: rank 1 is green and the last rank is red.
    The selected sort column receives a quiet green surface tint plus the arrow
    in its header, so sorting remains understandable even after horizontal scroll.
    """
    gap_cap = _gap_cap(universe)
    rank_caps = universe.groupby("position")["pos_rank"].max().to_dict()
    gap_values = {
        "sleeper_gap": pd.to_numeric(view["sleeper_gap"], errors="coerce").to_numpy(),
        "model_gap": pd.to_numeric(view["model_gap"], errors="coerce").to_numpy(),
    }
    rank_values = {
        key: pd.to_numeric(view[key], errors="coerce").to_numpy()
        for key in ("pos_rank", "sleeper_proj_pos_rank", "model_proj_pos_rank")
    }
    positions = view["position"].to_numpy()

    def _append(styles: pd.DataFrame, row: int, col: int, declaration: str) -> None:
        existing = styles.iat[row, col]
        styles.iat[row, col] = f"{existing}; {declaration}" if existing else declaration

    def _style(df: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=df.index, columns=df.columns)

        # A visible green surface tint is deliberately separate from the red/green value
        # encoding. It marks interaction state, not player direction or quality.
        if active_sort_key in df.columns:
            styles.loc[:, active_sort_key] = f"background-color: {_SORT_TINT}"

        for key, values in gap_values.items():
            if key not in df.columns:
                continue
            col = df.columns.get_loc(key)
            for row, value in enumerate(values):
                if not pd.isna(value):
                    _append(styles, row, col,
                            f"color: {_gap_color(value, gap_cap)}; font-weight: 700; font-size: 15px")

        for key, values in rank_values.items():
            if key not in df.columns:
                continue
            col = df.columns.get_loc(key)
            for row, value in enumerate(values):
                cap = rank_caps.get(positions[row])
                if not pd.isna(value) and cap and cap > 1:
                    ratio = (cap - value) / (cap - 1)
                    _append(styles, row, col, f"color: {_rg_color(ratio)}; font-weight: 600")
        return styles

    return _style


# --- outside-market explorer: display layer ---------------------------------------------
# Deliberately its own COLUMN_META. It shares no column with the board's price spine — no
# Sleeper ADP, no Sleeper Proj, no Position Rank, no gap of either kind — because none of
# those exist for a player the market has not priced.
#
# The point estimates render to one decimal here, where the board above renders whole points.
# The board compresses three numeric columns plus two gap columns into one wide table and
# rounds for legibility; this table has three numerics and room to show them exactly.
_OUTSIDE_COLUMN_META = [
    ("player", _TXT, "Player", "Player name.", {}),
    ("position", _TXT, "Pos", "His position.", {"width": "small"}),
    ("team", _TXT, "Team", "His 2026 team. Blank = not signed / unavailable.",
     {"width": "small"}),
    ("model_proj", _NUM, "Model Proj",
     "Season-total half-PPR points from the separate from-scratch seasonal projection "
     "artifacts, not the Draft Board Model Proj. Backtested on 2021-2025 and NOT "
     "live-validated. There is no Sleeper projection or draft price to compare it against "
     "for these players, so none is shown.", {"format": "%.1f", "width": "small"}),
    ("model_proj_pos_rank_full", _NUM, "Model Proj Position Rank",
     "His rank at his position across the COMPLETE model-projection pool — every projected "
     "player, including the ones on the draft-price board above — not a rank within this "
     "list. 1 = highest projected at the position.", {"format": "%d", "width": "small"}),
    ("nfl_talent", _NUM, "NFL Talent",
     "The same descriptive per-position NFL Talent instrument the board above uses, scored "
     "against qualified NFL starters at his position. Descriptive context only; feeds no "
     "other column. Blank = no NFL history, or below that build's volume floor.",
     {"format": "%.1f", "width": "small"}),
    ("college_talent", _NUM, "College Talent",
     "The same descriptive per-position college charting instrument the board above uses, "
     "scored against past prospects who reached the NFL and carrying no strength-of-schedule "
     "adjustment. A different reference pool and a different scale from NFL Talent — the two "
     "cannot be compared directly or combined. Descriptive context only; feeds no other "
     "column. Blank = the college build does not cover him (players outside FBS never are).",
     {"format": "%.1f", "width": "small"}),
]
_OUTSIDE_DISPLAY_COLS = [m[0] for m in _OUTSIDE_COLUMN_META]
_OUTSIDE_PHONE_COLS = ["player", "position", "model_proj", "model_proj_pos_rank_full"]
_OUTSIDE_EXPORT_NAMES = {m[0]: m[2] for m in _OUTSIDE_COLUMN_META}
_OUTSIDE_ROW_NO_HELP = ("Row number in this list as currently filtered and sorted — a counter "
                        "to keep your place, not a ranking.")

# Sortable display column -> underlying field. Insertion order sets the selector order, so
# "Model Proj" is the default; the render pass defaults its direction to descending.
OUTSIDE_SORT_KEYS = {
    "Model Proj": "model_proj",
    "Model Proj Position Rank": "model_proj_pos_rank_full",
    "NFL Talent": "nfl_talent",
    "College Talent": "college_talent",
    "Player": "player",
}


def _sort_outside_market(view, sort_label, ascending):
    """Same discipline as the board sort: one explicit numeric path, blanks pinned to the
    BOTTOM in both directions (na_position='last'), stable so ties keep their order."""
    key = OUTSIDE_SORT_KEYS.get(sort_label, "model_proj")
    return view.sort_values(key, ascending=ascending, na_position="last", kind="stable")


def _outside_column_config():
    cfg = {_ROW_NO: st.column_config.NumberColumn("#", help=_OUTSIDE_ROW_NO_HELP, format="%d",
                                                  width=_ROW_NO_WIDTH, pinned=True)}
    for key, kind, label, help_, extra in _OUTSIDE_COLUMN_META:
        if key in _TALENT_KEYS:
            extra = {k: v for k, v in extra.items() if k != "format"}
            # Displayed as text so missing scores stay blank, not the word None.
            # Right-align so they sit with the other numeric columns.
            cfg[key] = st.column_config.TextColumn(
                label, help=help_, alignment="right", **extra)
            continue
        col = st.column_config.NumberColumn if kind == _NUM else st.column_config.TextColumn
        cfg[key] = col(label, help=help_, **extra)
    return cfg


def _render_outside_market(board_size: int):
    """Collapsed explorer for projected players the draft market has not priced.

    Mirrors the rookie board's collapsed college-player explorer: same instruments, same
    artifacts, a population that simply does not belong in the table above.
    """
    outside = _load_outside_market_players()
    if outside.empty:
        return
    pool = _projection_pool_size()
    with st.expander(
        f"Players outside Sleeper's current {board_size}-player draft market ({len(outside)})",
        expanded=False,
    ):
        st.caption(
            "These players carry no current Sleeper half-PPR ADP, so there is no draft price "
            "to set a projection beside — which is why they are not on the price-comparison "
            "board above rather than being ranked below it. No draft price, Sleeper "
            "projection or rank difference is shown here, because none exists for them.")
        st.caption(
            "The talent scores are read from the same underlying artifacts the board above "
            "reads. The projections are the separate from-scratch seasonal artifacts, not "
            "the Draft Board Model Proj, with nothing recomputed for this list. A blank "
            "talent cell means the player did not meet that instrument's qualification or "
            "coverage rules.")
        st.caption(
            "NFL Talent ranks NFL players against NFL players; College Talent ranks college "
            "players against past prospects who reached the NFL. Different reference pools on "
            "different scales — read each on its own, and never compare or blend them. Unlike "
            "the board above, a player here can carry both: a veteran outside the draft market "
            "can have an NFL score and a college score from his prospect years, and those two "
            "numbers still say nothing about each other.")
        st.caption(
            f"**Model Proj Position Rank** is his rank at his position across all {pool:,} "
            "projected players — the board's rows included — not a rank within these "
            f"{len(outside):,}. All of it is descriptive information for your own judgment.")

        with st.container(key="jsa-filter-bar-outside"):
            fc1, fc2, fc3, fc4 = st.columns([1.4, 1.3, 1.6, 1.15])
            with fc1:
                pos = st.multiselect("Position", ["QB", "RB", "WR", "TE"],
                                     default=["QB", "RB", "WR", "TE"], key="db26_out_pos")
            with fc2:
                name = st.text_input("Player search", "", key="db26_out_search")
            with fc3:
                sort_label = st.selectbox("Sort by", list(OUTSIDE_SORT_KEYS), index=0,
                                          key="db26_out_sortby")
            with fc4:
                order = st.segmented_control(
                    "Order", ["Descending", "Ascending"], default="Descending",
                    required=True, key="db26_out_sortdir",
                )

        view = outside[outside.position.isin(pos)]
        if name.strip():
            view = view[view.player.str.contains(name.strip(), case=False, na=False)]
        view = _sort_outside_market(view, sort_label, ascending=order == "Ascending")

        display_view = view.copy()
        display_view.insert(0, _ROW_NO, range(1, len(display_view) + 1))
        for _k in _TALENT_KEYS:
            if _k in display_view.columns:
                display_view[_k] = _blank_missing_talent(display_view[_k], decimals=1)
        outside_cols = [_ROW_NO] + _OUTSIDE_DISPLAY_COLS
        outside_phone = [_ROW_NO] + [
            c for c in _OUTSIDE_PHONE_COLS if c in display_view.columns
        ]
        dataframe_phone_desktop(
            display_view[outside_cols],
            display_view[outside_phone],
            slug="draft-outside",
            width="stretch", height=TABLE_HEIGHT, hide_index=True,
            key=(f"db26_outside_grid_{OUTSIDE_SORT_KEYS[sort_label]}_{order}_"
                 f"{'-'.join(sorted(pos))}_{name.strip().lower()}_{len(view)}"),
            column_config=_outside_column_config(),
        )
        st.caption(f"Showing {len(view):,} of {len(outside):,} — blank projection or talent "
                   "cells sort to the bottom in either direction.")
        st.download_button(
            "Download players outside the draft market (CSV)",
            data=view[_OUTSIDE_DISPLAY_COLS].rename(columns=_OUTSIDE_EXPORT_NAMES)
                     .to_csv(index=False).encode("utf-8"),
            file_name="draft_board_2026_outside_market.csv", mime="text/csv",
            key="db26_outside_dl")


def render():
    df = _load_board_2026()

    with st.expander("How to read this board", expanded=False):
        st.markdown(
            "This board lists the independent model's exact 180-player 2026 universe: "
            "24 QB, 60 RB, 72 WR and 24 TE. For each, it shows the current draft "
            "price and **Model Proj**, plus Sleeper's projection when its record "
            "matches. Use **Draft price** to switch Sleeper ADP (the default), ESPN ADP, "
            "Yahoo ADP, or **Model Draft Rank** for the same 180 players. Sleeper ADP, ESPN ADP, Yahoo ADP, "
            "Sleeper Proj, and both gap "
            "columns refresh daily; Model Proj points and ranks stay frozen. For each "
            "available projection, the gap between his draft-price rank and his projected "
            "rank at his position.\n\n"
            "- **Sleeper ADP / ESPN ADP / Yahoo ADP / Model Draft Rank** fills the draft-price "
            "column. The three ADP sources are average draft position; Model Draft Rank is "
            "the model's overall order (1.0 = first). **Position Rank** is his rank at his "
            "position by Sleeper, ESPN, or Yahoo draft price "
            "(1 = first off the board there).\n"
            "- **Sleeper Proj** and **Model Proj** are two estimates of his "
            "season-total half-PPR points. Sleeper's is shown only when its record can be "
            "matched; **Model Proj** is the published season-total half-PPR number on "
            "this board, built without ADP as a model input, backtested on 2021-2025 and not yet "
            "live-validated.\n"
            "- **Sleeper Gap** and **Model Gap** are each Position Rank minus that "
            "projection's position rank: positive means the projection ranks him higher than "
            "his draft cost, negative means lower. They are descriptive differences, not "
            "recommendations.\n"
            "- **Model Draft Rank** (on Draft price) puts that overall order in the "
            "draft-price column (1.0 = first). Position Rank and both gaps stay on "
            "Sleeper ADP. It is not a recommendation.\n"
            "- **NFL Talent Score** and **College Talent Score** are descriptive context on "
            "different scales (NFL players vs. 2026 rookies). Neither feeds any other "
            "column.\n\n"
            "Everything here is descriptive information for your own judgment, not betting "
            "or draft advice, and none of it guarantees what any player will do.")
        st.markdown("**What each column means:**")
        for _key, _kind, _label, _help, _extra in COLUMN_META:
            _detail = " *(hidden in the compact view)*" if _key in _DETAIL_ONLY else ""
            if _key == "adp_half_ppr":
                _label = "Sleeper ADP / ESPN ADP / Yahoo ADP / Model Draft Rank"
            st.markdown(f"- **{_label}**{_detail} — {_help}")
        st.caption("The board opens on the full view. Turn off **Show projection and talent "
                   "detail** for a compact comparison view that drops the raw Sleeper and model "
                   "point estimates and the two talent scores; the CSV download always contains "
                   "every column either way. On a phone the board shows player, position, ADP, "
                   "rank, both gaps, and NFL Talent Score.")
        st.caption("Sort with the controls below — they order the whole board numerically, "
                   "with no-data rows (blank projection / talent) always at the bottom.")
        st.caption("Visual cues: positive gaps are green and negative gaps red; rank 1 is green "
                   "and later ranks fade toward red. Color shows direction or magnitude only, "
                   "never a recommendation. The active sort column receives an arrow and a "
                   "subtle surface tint.")

    # Filter + sort toolbar. Explicit numeric sort (st.dataframe's header-click sorts the
    # display strings lexicographically); this routes every sortable column through one
    # numeric path with sentinels pinned to the bottom. Default: Sleeper ADP, ascending.
    with st.container(border=True, key="jsa-filter-bar-draft"):
        page_common.seed_widget_from_query(
            "db26_adp_src", "db26_adp_src", BOARD_VIEWS,
        )
        if "db26_adp_src" not in st.session_state:
            st.session_state["db26_adp_src"] = DEFAULT_ADP_MARKET
        market = st.segmented_control(
            "Draft price", list(BOARD_VIEWS), key="db26_adp_src", required=True,
            help="Sleeper ADP is the default market this board was built against. "
                 "ESPN ADP and Yahoo ADP are each platform's published average draft "
                 "position for the same 180 players. Model Draft Rank fills the "
                 "draft-price column with the model's overall order (1.0 = first).",
        )
        if market not in BOARD_VIEWS:
            market = DEFAULT_ADP_MARKET
        page_common.seed_widget_from_query("db26_scoring", "db26_scoring", SCORING_MODES)
        scoring = st.segmented_control(
            "Scoring format", list(SCORING_MODES), default=DEFAULT_SCORING,
            key="db26_scoring", required=True,
            help="The board's published model is half-PPR; Standard/PPR labels are available "
                 "for the scoring context while the source artifact remains half-PPR.",
        ) or DEFAULT_SCORING
        sort_keys = sort_keys_for(market)
        prev_sort = st.session_state.get("db26_sortby")
        if market == MODEL_DRAFT_MARKET and prev_sort in ADP_MARKETS:
            st.session_state["db26_sortby"] = MODEL_DRAFT_MARKET
        elif prev_sort == MODEL_DRAFT_MARKET and market in ADP_MARKETS:
            st.session_state["db26_sortby"] = market
        elif prev_sort not in sort_keys:
            if prev_sort in ADP_MARKETS:
                st.session_state["db26_sortby"] = market
        fc1, fc2, fc3, fc4 = st.columns([1.4, 1.3, 1.6, 1.15])
        with fc1:
            if "db26_pos" not in st.session_state:
                _query_pos = str(page_common.query_value("db26_pos") or "")
                _valid_pos = [p for p in _query_pos.split(",") if p in {"QB", "RB", "WR", "TE"}]
                st.session_state["db26_pos"] = _valid_pos or ["QB", "RB", "WR", "TE"]
            pos = st.multiselect(
                "Position", ["QB", "RB", "WR", "TE"], key="db26_pos",
            )
        with fc2:
            _query_search = page_common.query_value("db26_search")
            if "db26_search" not in st.session_state:
                st.session_state["db26_search"] = str(_query_search or "")
            name = st.text_input("Player search", key="db26_search")
        with fc3:
            _sort_seeded = page_common.seed_widget_from_query(
                "db26_sortby", "db26_sortby", list(sort_keys),
            )
            sort_label = st.selectbox("Sort by", list(sort_keys), key="db26_sortby")
        with fc4:
            # Key is per sort column, so each column carries its own default AND remembers a
            # direction you set on it. A single shared key would let Streamlit's stored value
            # override the per-column default the moment you touched the toggle once.
            _order_key = f"db26_sortdir_{sort_keys[sort_label]}"
            _order_options = ["Ascending", "Descending"]
            _order_seeded = page_common.seed_widget_from_query(
                _order_key, "db26_order", _order_options,
            )
            _order_kwargs = {"required": True, "key": _order_key}
            if not _order_seeded and _order_key not in st.session_state:
                _order_kwargs["default"] = (
                    "Descending" if sort_label in DESCENDING_FIRST else "Ascending"
                )
            order = st.segmented_control("Order", _order_options, **_order_kwargs)
        detail = st.toggle(
            "Show projection and talent detail", value=True, key="db26_detail",
            help="On: the full board, including the raw Sleeper and model season-point estimates "
                 "and the two descriptive talent scores. Off: a compact view keeping the "
                 "price-vs-projection comparison only.")
        st.caption("Note: clicking a column header also sorts, but a few columns won't sort "
                   "correctly that way — a Streamlit limitation. Use the controls above.")

    page_common.sync_query_value("db26_adp_src", market)
    page_common.sync_query_value("db26_scoring", scoring)
    page_common.sync_query_value("db26_pos", ",".join(pos))
    page_common.sync_query_value("db26_search", name.strip())
    page_common.sync_query_value("db26_sortby", sort_label)
    page_common.sync_query_value("db26_order", order)

    df = apply_board_market(df, market)
    df = apply_scoring_mode(df, scoring)
    view = df[df.position.isin(pos)]
    if name.strip():
        view = view[view.player.str.contains(name.strip(), case=False, na=False)]
    ascending = order == "Ascending"
    view = _sort_board(view, sort_label, ascending=ascending, sort_keys=sort_keys)
    active_sort_key = sort_keys[sort_label]

    visible_cols = _DISPLAY_COLS if detail else _COMPACT_COLS
    cols = [_ROW_NO] + visible_cols
    # Numbered in the CURRENT sort/filter order — a reading aid, recomputed on every render.
    display_view = view.copy()
    display_view.insert(0, _ROW_NO, range(1, len(display_view) + 1))
    for _k in _TALENT_KEYS:
        if _k in display_view.columns:
            display_view[_k] = _blank_missing_talent(display_view[_k], decimals=0)
    st.caption(_adp_caption(market))
    st.caption(
        f"Scoring format: **{scoring}**. Sleeper Proj uses the selected scoring totals from "
        "the latest market snapshot; Model Proj is translated by the same reception-point "
        "delta, and positional ranks/gaps update with the displayed points."
    )
    direction = "low to high" if ascending else "high to low"
    sort_note = (f"Sorted by **{sort_label}** ({direction}). The arrow and soft green tint mark "
                 "the active sort column.")
    if active_sort_key not in visible_cols:
        # The sort is still applied to every row — the column it keys on just is not on screen.
        sort_note += (f" **{sort_label}** is hidden in the compact view, so the ordering is "
                      "applied but its values are off-screen; turn the detail toggle back on to "
                      "see them.")
    st.caption(sort_note)
    if market == MODEL_DRAFT_MARKET:
        st.caption("Model Proj and Model Gap are the published season-total projection "
                   "for this board. ADP is not a "
                   "model input. Backtested on 2021-2025 and not live-validated. On that "
                   "backtest Model Proj beat ADP ordering in 5 of 6 seasons. "
                   "2026-09-02 availability adjustment: Josh Jacobs 6 games after "
                   "the commissioner's exempt list, MarShawn Lloyd added to the 180.")
    elif market == DEFAULT_ADP_MARKET:
        st.caption("Model Proj and Model Gap are the published season-total projection "
                   "for this board. ADP is not a "
                   "model input. Backtested on 2021-2025 and not live-validated. On that "
                   "backtest Model Proj beat ADP ordering in 5 of 6 seasons. "
                   "2026-09-02 availability adjustment: Josh Jacobs 6 games after "
                   "the commissioner's exempt list, MarShawn Lloyd added to the 180.")
    else:
        st.caption(f"Model Proj and Model Gap in this view use {market} draft prices. ADP is not a "
                   "model input. The 5-of-6 ADP-ordering backtest is vs Sleeper ADP and does "
                   f"not apply to {market}. 2026-09-02 availability adjustment: Josh Jacobs "
                   "6 games after the commissioner's exempt list, MarShawn Lloyd added "
                   "to the 180.")
    st.caption("NFL Talent Score ranks NFL players against NFL players; College Talent Score "
               "ranks 2026 rookies against past drafted prospects — different instruments on "
               "different scales, and neither feeds any other column.")
    # Fixed-height scroll box holds all rows (TABLE_HEIGHT ≈ 20 visible). The key encodes the
    # current sort AND the filter state so the grid REMOUNTS on any change — this discards
    # st.dataframe's sticky client-side header-sort so the Sort-by control always wins.
    phone_cols = [_ROW_NO] + [c for c in _PHONE_COLS if c in display_view.columns]
    style_fn = _style_board(view, df, active_sort_key)
    grid_kwargs = dict(
        width="stretch", height=TABLE_HEIGHT, hide_index=True,
        key=("db26_grid_"
             f"{market.replace(' ', '_')}_{scoring.replace('-', '_')}_{sort_keys[sort_label]}_{order}_"
             f"{'detail' if detail else 'compact'}_"
             f"{'-'.join(sorted(pos))}_{name.strip().lower()}_{len(view)}"),
        column_config=_column_config(active_sort_key, ascending, market),
    )
    dataframe_phone_desktop(
        display_view[cols].style.apply(style_fn, axis=None),
        display_view[phone_cols].style.apply(style_fn, axis=None),
        slug="draft-board",
        phone_column_config=_phone_column_config(active_sort_key, ascending, market),
        **grid_kwargs,
    )

    st.download_button(
        "Download board (CSV)",
        data=view[_DISPLAY_COLS].rename(columns=export_names_for(market))
                       .to_csv(index=False).encode("utf-8"),
        file_name={
            MODEL_DRAFT_MARKET: "draft_board_2026_model_rank.csv",
            ESPN_ADP_MARKET: "draft_board_2026_espn.csv",
            YAHOO_ADP_MARKET: "draft_board_2026_yahoo.csv",
        }.get(market, "draft_board_2026.csv"), mime="text/csv",
        key="db26_dl")
    st.caption("The download carries every column, including any the compact view hides, for the "
               "rows currently filtered and in the current sort order.")

    st.markdown("---")
    st.caption(
        "**About these numbers.** Sleeper ADP and Sleeper Proj are Sleeper's. ESPN ADP is "
        "ESPN's. Yahoo ADP is Yahoo's. Model Proj is "
        "the published v6 projection, evaluated historically on 2021-2025 and not "
        "live-validated (the first live test is 2026). The gap columns are simple "
        "positional-rank differences shown for context. All of this is descriptive "
        "information for your own judgment, not a recommendation about any player.")
