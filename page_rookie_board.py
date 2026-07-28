"""Rookie Board page — the rookie hit-probability product (ships regardless; research REJECTED).

Additive page: reads the pre-built board CSVs in fantasy/rookie/board_data/ (no model runs here,
no network). The hit-probability research was fired 2026-07-20 and REJECTED (college/athletic add no
measured edge beyond draft capital: full AUC 0.843 vs draft-only 0.838, 2019-2023 hold-out). The
disclosure below rides on every surface.

The rookie-year PROJECTION columns are sourced from the RB, WR, and TE season-total models
(`fantasy/projections/results/*_rookie_board_projection.csv`). The old starved per-game
`rookie_ppg` surface is retired from display; its pkl is untouched in-repo. The projections are
shown beside Sleeper's projection when Sleeper has published one, with a descriptive difference;
they make no claim to beat Sleeper.
"""
import sys
from pathlib import Path
import pandas as pd
import streamlit as st

_HERE = Path(__file__).resolve().parent
_BOARD = _HERE / "fantasy" / "rookie" / "board_data"
_PROJ_DIR = _HERE / "fantasy" / "projections" / "results"
_PROJ_FILES = ["rb_rookie_board_projection.csv", "wr_rookie_board_projection.csv",
               "te_rookie_board_projection.csv", "qb_rookie_board_projection.csv"]  # RB+WR+TE rookie;
# QB rookie arm HELD (too thin — file is empty), so QB rookies show no projection. QB non-rookie
# projections ship as a data export only (results/qb_projection_2026.csv), not on this rookie board.
_CLASSES = [2026, 2025, 2024]

sys.path.insert(0, str(_HERE / "fantasy" / "seasonal_projections"))
try:
    from _utils import norm_name
except Exception:                                             # pragma: no cover - defensive
    def norm_name(s):
        return str(s).lower().strip()

DISCLOSURE = (
    "Backtested, not live-validated (2019-2023 hold-out classes). At this sample, college production "
    "and athletic testing added no measured edge beyond draft capital — the hit probability largely "
    "tracks draft position (full-model AUC 0.843 vs draft-capital-only 0.838, one-shot backtest). "
    "First live test: end of the 2026 season. QB and TE per-position numbers are underpowered."
)

HIT_DEF = (
    "Hit % = share of historical players with this profile who had at least one startable season "
    "in their first three years: top-24 for RB/WR or top-12 for QB/TE in season-total half-PPR. "
    "A best-of-three outcome, not a per-year rate."
)
THREE_MODEL = (
    "Three views of the same hit definition — 'Draft-Capital' uses only where a player was picked; "
    "'College' uses only his college production + athletic testing; 'Full' combines both. They land "
    "close together because the college signal, while real, is already reflected in draft position "
    "(see guide)."
)
PCT_HELP = (
    "Percentile rank within this player's position across every drafted QB/RB/WR/TE from the "
    "2015–2026 draft classes — e.g. 80 means higher than 80% of same-position drafted rookies since "
    "2015. Higher = better."
)
PROJ_HELP = (
    "Projected SEASON-TOTAL half-PPR points for the rookie year, from the RB, WR, and TE season-total "
    "models (under fantasy/projections/). They model opportunity (vacated backfield share, drafting-team "
    "context, ADP-implied role) and college/athletic/draft profile — so a rookie drafted into a crowded "
    "room can project lower than his draft slot alone would suggest. "
    "For the 2026 class this is the deploy projection; for 2024/2025 it is the walk-forward "
    "out-of-sample projection. Backtested 2021–2025 (pooled Spearman ~0.69–0.74 vs actual season "
    "totals), NOT live-validated. RB, WR, and TE rookies for now. TE is the thinnest of those (small "
    "rookie sample, zero-heavy scoring) — noisier, disclosed. The QB rookie arm was built but HELD (too "
    "thin — 7–13 QBs/year, and a rookie QB's season hinges on whether he starts, which the features can't "
    "see) — QB rookies show no projection; QB non-rookie projections exist only as a data export."
)
SLEEPER_HELP = (
    "Sleeper's published season-total half-PPR projection (the market), shown for context. The model "
    "does NOT claim to beat Sleeper — on 2021–2025 Sleeper ranks rookies/vets slightly better "
    "(Spearman +0.80 vs the model's +0.69). It is shown side-by-side by design, not as a scoreboard. "
    "Blank means Sleeper has not published a projection for that player."
)
DIFF_HELP = (
    "Projection − Sleeper (season-total half-PPR). Positive = the model is higher than the market on "
    "this player; negative = lower. Descriptive only — it is not a recommendation. Note: the ROOKIE "
    "models are conservative at the very top (they compress the highest projections), so a large "
    "negative Diff on a top-projected rookie reflects that low bias rather than a read. That is a "
    "rookie-model property: the separate non-rookie calibration audit on the Help page finds no "
    "comparable top-end compression. Blank means one or both projections are unavailable."
)

_COLS = {
    "name": "Player", "position": "Pos", "team": "Team", "draft_round": "Rd", "draft_pick": "Pick",
    "hit_prob_draft": "Draft-Capital Hit-%", "hit_prob_college": "College Hit-%",
    "hit_prob_full": "Full Hit-%", "projection": "Proj (season ½-PPR)", "sleeper": "Sleeper Proj",
    "diff": "Diff vs Sleeper", "talent_score": "College Talent",
    "pct_speed_score": "Athleticism (Percentile)", "pct_cfb_final_dom": "Production (Percentile)",
}


@st.cache_data(ttl=3600)
def _load(cls: int) -> pd.DataFrame:
    f = _BOARD / f"rookie_board_{cls}.csv"
    return pd.read_csv(f) if f.exists() else pd.DataFrame()


# The rookie board CSVs carry PFR-style team codes (NWE/KAN/LVR/NOR/SFO/TAM/LAR/GNB) while
# every other surface on the site uses the nflverse canonical set. Normalised at DISPLAY time;
# the build artifact is left alone.
_TEAM_DISPLAY = {"NWE": "NE", "KAN": "KC", "LVR": "LV", "NOR": "NO", "SFO": "SF",
                 "TAM": "TB", "LAR": "LA", "GNB": "GB", "JAC": "JAX", "ARZ": "ARI",
                 "BLT": "BAL", "CLV": "CLE", "HST": "HOU", "SDG": "LAC", "OAK": "LV",
                 "STL": "LA", "WSH": "WAS"}


def canon_team(value):
    """Map any feed's team code onto the site-wide canonical convention."""
    return _TEAM_DISPLAY.get(str(value), value)


_COLLEGE_QB = _HERE / "fantasy" / "talent" / "college_qb_score_2026.csv"
_COLLEGE_RB = _HERE / "fantasy" / "talent" / "college_rb_score_2026.csv"
_COLLEGE_WR = _HERE / "fantasy" / "talent" / "college_wr_score_2026.csv"
_COLLEGE_TE = _HERE / "fantasy" / "talent" / "college_te_score_2026.csv"


@st.cache_data(ttl=3600)
def _load_college_qb() -> pd.DataFrame:
    """College QB talent score (SPEC R35) — the PFF-college passing build.

    Covers every FBS QB with a qualifying college career, not just this year's rookies, so it
    also carries QBs still in college. `rookie_score_2026.csv` has no QB rows at all, which is
    why rookie QBs previously showed a blank College Talent cell.
    """
    if not _COLLEGE_QB.exists():
        return pd.DataFrame()
    return pd.read_csv(_COLLEGE_QB)


@st.cache_data(ttl=3600)
def _load_college_rb() -> pd.DataFrame:
    """College RB talent score (SPEC R36) — 8-facet PFF index, DESCRIPTIVE ONLY.

    Fired rc +0.329 (DEAD, below the .35 band) against the shipped PBP instrument at +0.501,
    and carries no strength-of-schedule adjustment. REPLACES the box-score value on every RB
    row it covers (Joseph's direction 2026-07-27).
    """
    if not _COLLEGE_RB.exists():
        return pd.DataFrame()
    return pd.read_csv(_COLLEGE_RB)


@st.cache_data(ttl=3600)
def _load_college_wr() -> pd.DataFrame:
    """College WR talent score (SPEC R38) — DESCRIPTIVE ONLY.

    WR is dead across six instrument classes; this describes college WR talent and makes no
    claim about NFL outcomes. Replaces the box-score value on every WR row it covers.
    """
    if not _COLLEGE_WR.exists():
        return pd.DataFrame()
    return pd.read_csv(_COLLEGE_WR)


@st.cache_data(ttl=3600)
def _load_college_te() -> pd.DataFrame:
    """College TE talent score (SPEC R40) — DESCRIPTIVE ONLY.

    The thinnest of the four college indices, on an instrument that fired dead at +0.294 and
    +0.326. Contested-catch is functionally absent (3.0% effective) and route-craft runs 77%
    against 68.5% nominal. Replaces the box-score value on every TE row it covers.
    """
    if not _COLLEGE_TE.exists():
        return pd.DataFrame()
    return pd.read_csv(_COLLEGE_TE)


def _attach_college_qb(df: pd.DataFrame, cls: int) -> pd.DataFrame:
    """Attach `talent_score` from the four dedicated college builds. Named for the QB build it
    started as; it now covers all four positions, each from its own artifact.

    The two policies are DIFFERENT and deliberately so:
      * QB (R35) FILLS BLANKS ONLY — the box-score build carries no QB rows at all, so there is
        nothing to overwrite, and the guard keeps it that way.
      * RB (R36), WR (R38) and TE (R40) REPLACE the box-score value wherever they cover a player
        (Joseph's direction 2026-07-27, against the recommendation to fill blanks only). A row
        the build does not cover keeps whatever was already there.
    Every position's rows are keyed on that position's artifact only, so no two builds can
    collide on one row.
    """
    cq = _load_college_qb()
    if cq.empty or df.empty or cls != 2026:
        return df
    df = df.copy()
    if "talent_score" not in df.columns:
        df["talent_score"] = pd.NA
    # Join on normalized name: the rookie board carries its OWN placeholder ids for brand-new
    # players (GRE361852) which do not always equal the season dataset's (00-0041092), so no id
    # namespace is shared. Names ambiguous on either side are refused rather than mis-joined.
    qbs = cq[cq["is_2026_rookie"].astype(bool)]
    dup_cfb = set(qbs.loc[qbs["norm_name"].duplicated(keep=False), "norm_name"])
    by_name = (qbs[~qbs["norm_name"].isin(dup_cfb)]
               .set_index("norm_name")["score"])
    is_qb = df["position"].eq("QB")
    nn = df.loc[is_qb, "name"].map(norm_name)
    dup_board = set(nn[nn.duplicated(keep=False)])
    filled = nn.map(lambda v: by_name.get(v) if v not in dup_board else None)
    df.loc[is_qb, "talent_score"] = df.loc[is_qb, "talent_score"].where(
        df.loc[is_qb, "talent_score"].notna(), filled)

    cr = _load_college_rb()
    if not cr.empty:
        rbs = cr[cr["is_2026_rookie"].astype(bool)]
        dup_r = set(rbs.loc[rbs["norm_name"].duplicated(keep=False), "norm_name"])
        by_rb = rbs[~rbs["norm_name"].isin(dup_r)].set_index("norm_name")["score"]
        is_rb = df["position"].eq("RB")
        nnr = df.loc[is_rb, "name"].map(norm_name)
        dup_b = set(nnr[nnr.duplicated(keep=False)])
        got = nnr.map(lambda v: by_rb.get(v) if v not in dup_b else None)
        # REPLACES the box-score rookie value wherever R36 covers the player (Joseph's
        # direction 2026-07-27). Rows R36 does not cover keep whatever was already there.
        df.loc[is_rb, "talent_score"] = got.where(got.notna(), df.loc[is_rb, "talent_score"])

    cw = _load_college_wr()
    if not cw.empty:
        wrs = cw[cw["is_2026_rookie"].astype(bool)]
        dup_w = set(wrs.loc[wrs["norm_name"].duplicated(keep=False), "norm_name"])
        by_wr = wrs[~wrs["norm_name"].isin(dup_w)].set_index("norm_name")["score"]
        is_wr = df["position"].eq("WR")
        nnw = df.loc[is_wr, "name"].map(norm_name)
        dup_bw = set(nnw[nnw.duplicated(keep=False)])
        gw = nnw.map(lambda v: by_wr.get(v) if v not in dup_bw else None)
        df.loc[is_wr, "talent_score"] = gw.where(gw.notna(), df.loc[is_wr, "talent_score"])

    ct = _load_college_te()
    if not ct.empty:
        tes = ct[ct["is_2026_rookie"].astype(bool)]
        dup_t = set(tes.loc[tes["norm_name"].duplicated(keep=False), "norm_name"])
        by_te = tes[~tes["norm_name"].isin(dup_t)].set_index("norm_name")["score"]
        is_te = df["position"].eq("TE")
        nnt = df.loc[is_te, "name"].map(norm_name)
        dup_bt = set(nnt[nnt.duplicated(keep=False)])
        gt = nnt.map(lambda v: by_te.get(v) if v not in dup_bt else None)
        df.loc[is_te, "talent_score"] = gt.where(gt.notna(), df.loc[is_te, "talent_score"])
    return df


@st.cache_data(ttl=3600)
def _load_proj() -> pd.DataFrame:
    """Season-total projection join files (norm_name, position, entry_class, projection, sleeper, diff).
    Concatenates the per-position files (RB + WR + TE); position is in the join key, so each row draws
    its position's model. Missing files are skipped (positions not built yet stay blank)."""
    frames = []
    for name in _PROJ_FILES:
        path = _PROJ_DIR / name
        if path.exists():
            frame = pd.read_csv(path)
            if not frame.empty:  # the intentionally held QB file is header-only
                frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["norm_name", "position", "entry_class", "projection", "sleeper", "diff"])
    return pd.concat(frames, ignore_index=True)


def _attach_projection(df: pd.DataFrame, cls: int) -> pd.DataFrame:
    """Left-join RB/WR/TE season-total projections; QB stays blank by design."""
    proj = _load_proj()
    for c in ("projection", "sleeper", "diff"):
        df[c] = pd.NA
    if proj.empty or df.empty:
        return df
    proj = proj[proj["entry_class"] == cls]
    df = df.copy()
    df["_nn"] = df["name"].map(norm_name)
    key = proj.set_index(["norm_name", "position"])[["projection", "sleeper", "diff"]]
    idx = list(zip(df["_nn"], df["position"]))
    for col in ("projection", "sleeper", "diff"):
        s = key[col]
        df[col] = [s.get(k) if k in s.index else pd.NA for k in idx]
    return df.drop(columns=["_nn"])


_WATCH_COLS = {"player": "Player", "college": "College", "final_season": "Last season",
               "seasons": "Qualifying seasons", "score": "College Talent",
               "rank_final_season": "Rank in that season", "reliability": "Reliability"}


def _render_college_watch(cls: int, position: str, loader, label: str) -> None:
    """Collapsed view of scored college players who are NOT in this year's rookie class.

    Same College Talent instrument, same 0-100 scale — these players are simply not in this
    year's class, so they appear on no rookie board. Most are still in college. Descriptive only.
    """
    cq = loader()
    if cq.empty:
        return
    ret = cq[~cq["is_2026_rookie"].astype(bool)].copy()
    if ret.empty:
        return
    latest = int(ret["final_season"].max())
    current = ret[ret["final_season"] == latest].sort_values("score", ascending=False)
    with st.expander(
        f"College {label} who are not in the {cls} rookie class ({len(current)} from {latest})",
        expanded=False,
    ):
        st.caption(
            "The same College Talent instrument, on the same 0-100 scale as the column above — "
            f"these {label.lower()} simply are not in this year's rookie class, so they appear "
            "on no rookie board. Most are still in college. It is a descriptive read of college "
            "production, not a projection of NFL performance or fantasy value, and it says "
            "nothing about whether or when any of them will be drafted."
        )
        # the QB artifact carries `reliability`; the RB one does not — take what exists
        present = [c for c in _WATCH_COLS if c in current.columns]
        watch = current[present].rename(columns=_WATCH_COLS)
        watch.insert(0, "#", range(1, len(watch) + 1))
        st.dataframe(
            watch,
            hide_index=True, width="stretch",
            height=min(560, 60 + 35 * len(current)),
            column_config={
                "#": st.column_config.NumberColumn(
                    # 50px is the grid minimum; pinned so it keeps that exact width instead of
                # absorbing an even share of the table's leftover space (grow=0 when pinned).
                format="%d", width=50, pinned=True,
                    help="Row number in this list (sorted by College Talent) — a counter to "
                         "keep your place, not a ranking."),
                "College Talent": st.column_config.NumberColumn(
                    format="%.1f", help="Same instrument and scale as the College Talent column "
                                        f"above. Anchored on {label.lower()} who reached the NFL, "
                                        "with no strength-of-schedule adjustment."),
                "Reliability": st.column_config.NumberColumn(
                    format="%.2f", help="How much college volume sits behind the score (0-1). "
                                        "A one-season player is shrunk hard toward the mean."),
                "Rank in that season": st.column_config.NumberColumn(format="%d"),
                "Last season": st.column_config.NumberColumn(format="%d"),
            },
        )
        st.caption(
            f"Showing the {latest} season only; the build covers {len(ret):,} non-rookie college "
            f"{label.lower()} back to 2014."
        )


def render():
    st.title("🧬 Rookie Board")
    st.caption("A per-position hit-probability score for drafted rookies — plus season-total "
               "projections for RB/WR/TE, a college talent score covering all four positions, "
               "and college/athletic percentiles.")
    st.warning("**Backtested, not live-validated.** " + DISCLOSURE)

    avail = [c for c in _CLASSES if not _load(c).empty]
    if not avail:
        st.info("Rookie board data not built yet — run `python fantasy/rookie/build_rookie_board.py`.")
        return

    c1, c2 = st.columns([1, 1])
    cls = c1.selectbox("Draft class", avail, index=0)
    df = _load(cls)
    df = _attach_projection(df, cls)
    df = _attach_college_qb(df, cls)
    pos = c2.selectbox("Position", ["All", "QB", "RB", "WR", "TE"], index=0)
    if pos != "All":
        df = df[df["position"] == pos]

    df = df.sort_values("hit_prob_full", ascending=False)
    df = df.copy()
    df["team"] = df["team"].map(canon_team)
    show = df[[c for c in _COLS if c in df.columns]].rename(columns=_COLS)
    # Row counter for the table as currently sorted and filtered — a reading aid only.
    show.insert(0, "#", range(1, len(show) + 1))

    st.caption("**Three hit-% columns.** " + THREE_MODEL)
    st.dataframe(
        show, hide_index=True, width="stretch", height=min(720, 60 + 35 * len(show)),
        column_config={
            "#": st.column_config.NumberColumn(
                # 50px is the grid minimum; pinned so it keeps that exact width instead of
                # absorbing an even share of the table's leftover space (grow=0 when pinned).
                format="%d", width=50, pinned=True,
                help="Row number in this table as currently sorted and filtered — a counter "
                     "to keep your place, not a ranking."),
            "Draft-Capital Hit-%": st.column_config.NumberColumn(
                format="%.0f", help="Hit % from draft position ONLY (the market). " + THREE_MODEL),
            "College Hit-%": st.column_config.NumberColumn(
                format="%.0f", help="Hit % from college production + athletic testing ONLY — no draft "
                                    "capital. " + THREE_MODEL),
            "Full Hit-%": st.column_config.NumberColumn(
                format="%.0f", help="Hit % from all features (draft + college + athletic). " + HIT_DEF
                                    + " " + DISCLOSURE),
            "Proj (season ½-PPR)": st.column_config.NumberColumn(format="%.0f", help=PROJ_HELP),
            "Sleeper Proj": st.column_config.NumberColumn(format="%.0f", help=SLEEPER_HELP),
            "Diff vs Sleeper": st.column_config.NumberColumn(format="%+.0f", help=DIFF_HELP),
            "College Talent": st.column_config.NumberColumn(
                format="%.1f", help="Descriptive college talent score, read-only from the talent library. "
                                    "Every position has its own dedicated college charting build (QB from "
                                    "college passing, RB/WR/TE from their own builds), each anchored on "
                                    "players at that position who reached the NFL and each with its own "
                                    "volume floor; a rookie a build does not cover keeps the older college "
                                    "box-score value where one exists. No strength-of-schedule adjustment, "
                                    "so production against weaker and stronger opponents counts the same. "
                                    "2026 class only, and only a subset of it — players outside FBS can "
                                    "never be covered. Blank elsewhere by design; never backfilled."),
            "Athleticism (Percentile)": st.column_config.NumberColumn(format="%.0f", help=PCT_HELP),
            "Production (Percentile)": st.column_config.NumberColumn(format="%.0f", help=PCT_HELP),
        },
    )
    model_available = int(show["Proj (season ½-PPR)"].notna().sum())
    sleeper_available = int(show["Sleeper Proj"].notna().sum())
    st.caption(
        f"Projection availability in this view — Model: {model_available}/{len(show)}; Sleeper: "
        f"{sleeper_available}/{len(show)}. A blank Sleeper Proj means Sleeper has not published one for "
        "that player; Diff stays blank unless both projections are available. Rookie QB model projections "
        "are intentionally withheld."
    )
    _render_college_watch(cls, "QB", _load_college_qb, "QBs")
    _render_college_watch(cls, "RB", _load_college_rb, "RBs")
    _render_college_watch(cls, "WR", _load_college_wr, "WRs")
    _render_college_watch(cls, "TE", _load_college_te, "TEs")

    st.caption(
        f"Class of {cls} · {len(show)} rookies · {HIT_DEF} **Proj (season ½-PPR)** is the projected "
        "season-total half-PPR from the RB, WR, and TE season-total models — RB/WR/TE rookies (the QB "
        "rookie arm was held as too thin), shown beside Sleeper's projection with the difference; no claim "
        "to beat Sleeper. College "
        "Talent covers the 2026 class only, and each position reads its own dedicated college "
        "charting build, anchored on players at that position who reached the NFL and carrying no "
        "strength-of-schedule adjustment. Percentiles are within-position "
        "across the 2015–2026 drafted-skill panel. Hit "
        "probability and projection are backtested, not live-validated."
    )
