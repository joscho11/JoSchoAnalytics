"""2026 Draft Board tab — season-projection comparison table (2026-07-22 rebuild).

This tab retires the licensed Phase-4 band as its spine. It now lists every player with
a 2026 Sleeper ADP (~245) and shows, side by side, the market's draft price and positional
rank next to Sleeper's season-total projection and a model-based estimate I built — plus the
positional-rank gap for each and descriptive talent scores. Selected named 2026 players use a
disclosed analyst overlay on that model-based estimate.

The frozen artifacts (phase4_band_2026.csv, talent_index_2026.csv) stay on disk, read-only —
the closed H-campaign and the daily ADP refresh still reference them. This module no longer
reads the band.

Compliance — DESCRIPTIVE ONLY.
  • Sleeper ADP + Sleeper Proj are Sleeper's data (attributed).
  • Model Proj + Model Gap use a separate, from-scratch model, BACKTESTED (2021–2025)
    and NOT live-validated. A frozen, disclosed 2026 analyst overlay replaces the displayed
    point estimate for selected players while preserving every raw model output.
  • The gap columns are neutral positional-rank differences, not recommendations.
  • Talent Scores are descriptive context on their own scales, and feed no other column.
  • No buy/sell/fade/steal/reach/target/tier/valued/hit-rate/accuracy language anywhere.
"""
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard_chrome import TABLE_HEIGHT   # shared ~20-row height for long tables

_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")

_HERE = Path(__file__).resolve().parent
SEAS = _HERE / "fantasy" / "seasonal_projections"
# Draft-price universe: every player with a 2026 Sleeper ADP (~245), from the frozen
# season dataset. This defines the table's rows.
DATASET = SEAS / "season_dataset_2014_2026.csv"
# LIVE ADP overlay written by refresh_board_adp.py (regenerable, market data only). It
# freshens the ADP of the ~180 board-overlap players; the rest keep the dataset snapshot.
LIVE_OVERLAY = SEAS / "board_adp_live_2026.csv"
# The two independent season-total projections + the raw Sleeper projection they are
# compared against live here (from-scratch model, read-only).
PROJ_RESULTS = _HERE / "fantasy" / "projections" / "results"
ANALYST_PROJECTION_ADJUSTMENTS = (
    PROJ_RESULTS / "analyst_projection_adjustments_2026.csv"
)
# Descriptive talent artifacts (fantasy/talent/, provenance-stamped). NFL Talent scores
# players with NFL history against NFL players; College Talent scores 2026 rookies (RB/WR/TE)
# against past drafted prospects. Disjoint by construction (artifact membership), different
# scales, and context-only — neither feeds any other column.
TALENT_DIR = _HERE / "fantasy" / "talent"
TALENT_CSV = TALENT_DIR / "talent_score_2026.csv"
ROOKIE_CSV = TALENT_DIR / "rookie_score_2026.csv"
BOARD_SEASON = 2026


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
        out = out.reset_index()
    return out.set_index("player_id")


@st.cache_data
def _load_board_2026_cached(source_fingerprint):
    ds = pd.read_csv(DATASET, usecols=["player_id", "season", "player", "position",
                                       "team", "adp_half_ppr"])
    df = ds[(ds.season == BOARD_SEASON) & ds.adp_half_ppr.notna()].copy()
    df = df.drop_duplicates("player_id").reset_index(drop=True)

    # LIVE ADP overlay: prefer the freshly-refreshed price where present (the ~180
    # board-overlap players), else keep the frozen-dataset snapshot (so a fresh clone and
    # the hermetic AppTest still render, and the deeper ~65 have a price).
    if LIVE_OVERLAY.exists():
        ov = pd.read_csv(LIVE_OVERLAY).set_index("player_id")
        if "adp_half_ppr" in ov.columns:
            fresh = df["player_id"].map(ov["adp_half_ppr"])
            df["adp_half_ppr"] = fresh.where(fresh.notna(), df["adp_half_ppr"])

    # The two projections + the raw Sleeper projection, joined read-only by player_id.
    proj = _load_projections()
    df["model_proj"] = df["player_id"].map(proj["projection"]) if len(proj) else pd.NA
    df["model_proj_raw"] = (
        df["player_id"].map(proj["model_projection_raw"])
        if len(proj) else pd.NA
    )
    df["projection_adjustment"] = (
        df["player_id"].map(proj["projection_adjustment"])
        if len(proj) else pd.NA
    )
    df["sleeper_proj"] = df["player_id"].map(proj["sleeper"]) if len(proj) else pd.NA
    # Team from the projection roster where present (current 2026 team), else the dataset.
    if len(proj) and "team" in proj.columns:
        pteam = df["player_id"].map(proj["team"])
        df["team"] = pteam.where(pteam.notna(), df["team"])

    # Talent scores — populated ONLY from artifact membership (disjoint by construction).
    df["nfl_talent"] = pd.NA
    df["college_talent"] = pd.NA
    if TALENT_CSV.exists():
        t = pd.read_csv(TALENT_CSV, usecols=["gsis_id", "score"]).set_index("gsis_id")
        df["nfl_talent"] = df["player_id"].map(t["score"])
    if ROOKIE_CSV.exists():
        r = pd.read_csv(ROOKIE_CSV, usecols=["gsis_id", "rookie_score"]).set_index("gsis_id")
        df["college_talent"] = df["player_id"].map(r["rookie_score"])

    for c in (
        "model_proj", "model_proj_raw", "sleeper_proj",
        "nfl_talent", "college_talent",
    ):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Positional ranks. ADP ascending (1 = earliest pick at the position); projection ranks
    # descending (1 = highest projected points). NaN keys (rookie QBs with no projection)
    # stay <NA> and sink last on any sort.
    df["pos_rank"] = df.groupby("position")["adp_half_ppr"] \
                       .rank(method="min", ascending=True).astype("Int64")
    df["sleeper_proj_pos_rank"] = df.groupby("position")["sleeper_proj"] \
                       .rank(method="min", ascending=False).astype("Int64")
    df["model_proj_pos_rank"] = df.groupby("position")["model_proj"] \
                       .rank(method="min", ascending=False).astype("Int64")
    # Gap = draft-price rank minus projection rank. Positive = the projection ranks him
    # higher than his draft cost; negative = lower. Descriptive difference, not advice.
    df["sleeper_gap"] = (df["pos_rank"] - df["sleeper_proj_pos_rank"]).astype("Int64")
    df["model_gap"] = (df["pos_rank"] - df["model_proj_pos_rank"]).astype("Int64")
    return df


def _board_source_fingerprint():
    """Cache key for every local artifact that contributes to the board."""
    paths = [
        DATASET,
        LIVE_OVERLAY,
        *(PROJ_RESULTS / f"{position}_projection_2026.csv"
          for position in ("rb", "wr", "te", "qb")),
        ANALYST_PROJECTION_ADJUSTMENTS,
        TALENT_CSV,
        ROOKIE_CSV,
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
            columns=["Position", "Player", "Raw model", "Board value", "Basis", "As of"]
        )
    adj = pd.read_csv(
        ANALYST_PROJECTION_ADJUSTMENTS,
        usecols=[
            "position", "player", "raw_projection", "adjusted_projection",
            "method", "as_of",
        ],
    )
    adj["method"] = adj["method"].str.replace("_", " ", regex=False)
    return (
        adj.rename(
            columns={
                "position": "Position",
                "player": "Player",
                "raw_projection": "Raw model",
                "adjusted_projection": "Board value",
                "method": "Basis",
                "as_of": "As of",
            }
        )
        .sort_values(["Position", "Player"], kind="stable")
        .reset_index(drop=True)
    )


def _load_board_2026():
    return _load_board_2026_cached(_board_source_fingerprint())


# Preserve the existing test/maintenance API while the cached implementation
# receives a real source-dependent key.
_load_board_2026.clear = _load_board_2026_cached.clear


@st.cache_data
def _refresh_date():
    """The ADP snapshot date from the live overlay (ISO string), or None if absent."""
    if not LIVE_OVERLAY.exists():
        return None
    try:
        s = pd.read_csv(LIVE_OVERLAY, usecols=["refreshed_at"])["refreshed_at"]
        return str(s.iloc[0]) if len(s) else None
    except (KeyError, ValueError, pd.errors.EmptyDataError):
        return None


def _adp_caption():
    """Auto-stamped, first-person ADP caption. Flags a snapshot older than 7 days."""
    iso = _refresh_date()
    if not iso:
        return ("I refresh these draft prices from Sleeper ADP; prices move as real "
                "drafts happen.")
    try:
        stamp = date.fromisoformat(str(iso)[:10])
        pretty = f"{_MONTHS[stamp.month - 1]} {stamp.day}, {stamp.year}"
        stale = (date.today() - stamp).days > 7
    except (ValueError, TypeError):
        pretty, stale = str(iso), False
    note = (" These prices are more than a week old, so they may be behind the market."
            if stale else " Prices move as real drafts happen.")
    return f"I refresh these draft prices from Sleeper ADP — latest pull {pretty}.{note}"


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
    "Model Gap": "model_gap",
    "Sleeper Proj": "sleeper_proj",
    "Model Proj": "model_proj",
    "NFL Talent Score": "nfl_talent",
    "College Talent Score": "college_talent",
}


def _sort_board(view, sort_label, ascending):
    """Sort by the numeric field behind a display column. Sentinels (NaN sort keys) always
    sink to the bottom, in both directions (na_position='last'). Stable so ties keep order."""
    key = SORT_KEYS.get(sort_label, "adp_half_ppr")
    return view.sort_values(key, ascending=ascending, na_position="last", kind="stable")


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
     "Average draft position from Sleeper (half-PPR) — where drafters are actually taking "
     "him. Lower = earlier.", {"format": "%.1f"}),
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
     "His rank at his position by my from-scratch model's season projection "
     "(1 = highest projected).", {"format": "%d", "width": "small"}),
    ("model_gap", _NUM, "Model Gap",
     "Position Rank minus Model Proj Position Rank. Positive = my model ranks him higher "
     "than his draft cost; negative = lower. From a model backtested on 2021–2025, NOT "
     "live-validated — a descriptive difference, not advice. Blank = not in the projection "
     "set (e.g. rookie QBs are not projected).", {"format": "%d", "width": "small"}),
    ("sleeper_proj", _NUM, "Sleeper Proj",
     "Sleeper's projected season-total half-PPR points (raw).",
     {"format": "%d", "width": "small"}),
    ("model_proj", _NUM, "Model Proj",
     "Season-total half-PPR points based on a separate, from-scratch model I built (RB/WR/TE "
     "plus non-rookie QBs; rookie QBs are not projected). Selected 2026 players use the "
     "disclosed analyst overlay below; every raw model output remains preserved. The model "
     "was built independently of the market, backtested on 2021–2025, and is NOT "
     "live-validated. Blank = not in the projection set.",
     {"format": "%d", "width": "small"}),
    ("nfl_talent", _NUM, "NFL Talent Score",
     "My model-based per-opportunity talent estimate for players with NFL history, net of "
     "situation where identifiable. It ranks NFL players against NFL players — a different "
     "scale from College Talent Score. Descriptive context only; feeds no other column. "
     "Blank = no NFL history (see College Talent Score).",
     {"format": "%d", "width": "small"}),
    ("college_talent", _NUM, "College Talent Score",
     "A college-production read for 2026 rookies (RB/WR/TE), scaled against past drafted "
     "prospects — a different scale from NFL Talent Score, and not shipped for rookie QBs. "
     "Descriptive context only; feeds no other column. Blank = has NFL history, or college "
     "data unavailable.", {"format": "%d", "width": "small"}),
]
_DISPLAY_COLS = [m[0] for m in COLUMN_META]
_EXPORT_NAMES = {m[0]: m[2] for m in COLUMN_META}       # colkey -> on-screen label


def _column_config(active_sort_key: str | None = None, ascending: bool = True):
    """Build the table config and visibly mark the active numeric sort key."""
    cfg = {}
    for key, kind, label, help_, extra in COLUMN_META:
        col = st.column_config.NumberColumn if kind == _NUM else st.column_config.TextColumn
        if key == active_sort_key:
            arrow = "↑" if ascending else "↓"
            label = f"{arrow} {label}"
            help_ = f"Current sort field ({'low to high' if ascending else 'high to low'}). {help_}"
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
            styles.loc[:, active_sort_key] = "background-color: #1b5e3a"

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


def render():
    df = _load_board_2026()

    with st.expander("How to read this board", expanded=False):
        st.markdown(
            "This board lists every player with a 2026 Sleeper ADP. For each, it shows "
            "where the market is drafting him and **two independent season-total "
            "projections** — Sleeper's and a from-scratch model I built — plus, for each "
            "projection, the gap between his draft-price rank and his projected rank at "
            "his position.\n\n"
            "- **Sleeper ADP** is his average draft position; **Position Rank** turns that "
            "into his rank at his position (1 = first off the board there).\n"
            "- **Sleeper Proj** and **Model Proj** are two separate estimates of his "
            "season-total half-PPR points. Sleeper's is the market's; the **Model Proj** is "
            "mine, built independently of the market — backtested on 2021–2025, not yet "
            "live-validated, and not presented as a better number than the market.\n"
            "- **Sleeper Gap** and **Model Gap** are each Position Rank minus that "
            "projection's position rank: positive means the projection ranks him higher than "
            "his draft cost, negative means lower. They are descriptive differences, not "
            "recommendations.\n"
            "- **NFL Talent Score** and **College Talent Score** are descriptive context on "
            "different scales (NFL players vs. 2026 rookies) — neither feeds any other "
            "column.\n\n"
            "Everything here is descriptive information for your own judgment — not betting "
            "or draft advice — and none of it guarantees what any player will do.")
        st.markdown("**What each column means:**")
        for _key, _kind, _label, _help, _extra in COLUMN_META:
            st.markdown(f"- **{_label}** — {_help}")
        st.caption("Sort with the controls below — they order the whole board numerically, "
                   "with no-data rows (blank projection / talent) always at the bottom.")
        st.caption("Visual cues: positive gaps are green and negative gaps red; rank 1 is green "
                   "and later ranks fade toward red. Color shows direction or magnitude only, "
                   "never a recommendation. The active sort column receives an arrow and a "
                   "subtle surface tint.")

    # Filter + sort toolbar. Explicit numeric sort (st.dataframe's header-click sorts the
    # display strings lexicographically); this routes every sortable column through one
    # numeric path with sentinels pinned to the bottom. Default: Sleeper ADP, ascending.
    with st.container(border=True):
        fc1, fc2, fc3, fc4 = st.columns([1.4, 1.3, 1.6, 1.15])
        with fc1:
            pos = st.multiselect("Position", ["QB", "RB", "WR", "TE"],
                                 default=["QB", "RB", "WR", "TE"], key="db26_pos")
        with fc2:
            name = st.text_input("Player search", "", key="db26_search")
        with fc3:
            sort_label = st.selectbox("Sort by", list(SORT_KEYS), index=0, key="db26_sortby")
        with fc4:
            order = st.radio("Order", ["Ascending", "Descending"], index=0,
                             horizontal=True, key="db26_sortdir")
        st.caption("Note: clicking a column header also sorts, but a few columns won't sort "
                   "correctly that way — a Streamlit limitation. Use the controls above.")

    view = df[df.position.isin(pos)]
    if name.strip():
        view = view[view.player.str.contains(name.strip(), case=False, na=False)]
    ascending = order == "Ascending"
    view = _sort_board(view, sort_label, ascending=ascending)
    active_sort_key = SORT_KEYS[sort_label]

    cols = _DISPLAY_COLS
    st.caption(_adp_caption())
    direction = "low to high" if ascending else "high to low"
    st.caption(f"Sorted by **{sort_label}** ({direction}). The arrow and soft green tint mark "
               "the active sort column.")
    st.caption("Model Proj and Model Gap use a separate, from-scratch model, backtested "
               "on 2021–2025 and not yet live-validated. Selected 2026 players use the "
               "disclosed analyst overlay; every raw model output remains preserved.")
    disclosure = _load_adjustment_disclosure()
    with st.expander(
        f"2026 analyst projection overlays ({len(disclosure)})",
        expanded=False,
    ):
        st.caption(
            "These named-player scenarios replace only the single displayed Model Proj. "
            "They do not retrain a model or rewrite a raw projection file, and Sleeper "
            "values did not determine selection or size."
        )
        st.dataframe(
            disclosure,
            width="stretch",
            hide_index=True,
            column_config={
                "Raw model": st.column_config.NumberColumn(format="%.1f"),
                "Board value": st.column_config.NumberColumn(format="%.1f"),
            },
        )
    st.caption("NFL Talent Score ranks NFL players against NFL players; College Talent Score "
               "ranks 2026 rookies against past drafted prospects — different instruments on "
               "different scales, and neither feeds any other column.")
    # Fixed-height scroll box holds all rows (TABLE_HEIGHT ≈ 20 visible). The key encodes the
    # current sort AND the filter state so the grid REMOUNTS on any change — this discards
    # st.dataframe's sticky client-side header-sort so the Sort-by control always wins.
    st.dataframe(
        view[cols].style.apply(_style_board(view, df, active_sort_key), axis=None),
        width="stretch", height=TABLE_HEIGHT, hide_index=True,
        key=("db26_grid_"
             f"{SORT_KEYS[sort_label]}_{order}_"
             f"{'-'.join(sorted(pos))}_{name.strip().lower()}_{len(view)}"),
        column_config=_column_config(active_sort_key, ascending))

    st.download_button(
        "Download board (CSV)",
        data=view[cols].rename(columns=_EXPORT_NAMES)
                       .to_csv(index=False).encode("utf-8"),
        file_name="draft_board_2026.csv", mime="text/csv",
        key="db26_dl")

    st.markdown("---")
    st.caption(
        "**About these numbers.** Sleeper ADP and Sleeper Proj are Sleeper's; the Model Proj "
        "is based on my own independently built model, with the named 2026 analyst overlays "
        "disclosed above. The model was backtested on 2021–2025 and is not live-validated "
        "(the first live test is the 2026 season). The gap columns are simple positional-rank "
        "differences shown for context. All of this is descriptive information for your own "
        "judgment — not a recommendation about any player.")
