"""Season Win Totals page.

READ-ONLY over files published from season_totals_v2_prod:

    futures/published/season_totals_2026.csv
    futures/published/evidence.json

No model runs here. pandas and streamlit only.

Hero is the high-confidence win record. Copy is checked against
futures/language_fence.py.
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

_HERE = Path(__file__).resolve().parents[1]
_CSV = _HERE / "futures" / "published" / "season_totals_2026.csv"
_EVIDENCE = _HERE / "futures" / "published" / "evidence.json"

HIGH_COL = "High Confidence"
HIGH_YES = "\u2705"
HIGH_NO = "\u274c"
BAR_PCT = 52.4
# Phone grid: same columns as desktop, shorter headers, every column pinned
# so Glide cannot shunt Team to the right. 50px is Glide's hard minimum.
_PHONE_LABELS = {
    "Proj Wins": "Proj",
    "vs posted": "vs",
    HIGH_COL: "HIGH",
}
_PHONE_WIDTHS = {
    # Measured 2026-09-29: these six pinned widths summed to 316px against a
    # ~362px phone grid, and Streamlit's dataframe grid stretches to fill the
    # container, so the leftover ~46px rendered as a blank trailing column
    # (same header-row background, no header text, no cell content). Widened
    # to sum to ~362px; no column added or removed.
    "#": 54,
    "Team": 64,
    "Proj Wins": 62,
    "Posted": 62,
    "vs posted": 62,
    HIGH_COL: 58,
}

PROJ_HELP = (
    "Projected regular-season wins. Ties count as half a win. The 32 projections "
    "sum to 272 scheduled games."
)
POSTED_HELP = "The posted regular-season win total. Also an input to the ridge fit."
VS_HELP = "Projection minus posted. Positive means the model is above the number."
HIGH_HELP = (
    f"{HIGH_YES} means high confidence: the projection is at least 1 full win off the "
    f"posted number. {HIGH_NO} means we still show a projection but it is not a "
    "high-confidence call."
)
METHOD = """
**Model.** Fifteen structural inputs plus the posted win total in a ridge fit.
2026 projections are recentered so league wins sum to 272.

**High confidence.** A call fires when `|projection - posted| >= 1` win, same rule
as the held-out book above.

**Caveats.** 2026 reserve counts are withheld (camp roster vs post-cutdown
history). A few QB identities are roster fallbacks, not week-1 depth charts.
"""


def _file_stamp(path: Path) -> float:
    try:
        return float(path.stat().st_mtime)
    except OSError:
        return 0.0


@st.cache_data(ttl=60)
def _load(stamp: float) -> pd.DataFrame:
    del stamp
    return pd.read_csv(_CSV) if _CSV.exists() else pd.DataFrame()


@st.cache_data(ttl=60)
def _read_json(path_str: str, stamp: float) -> dict:
    del stamp
    p = Path(path_str)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


def _high_flag(certified: str) -> str:
    return HIGH_YES if str(certified).strip().lower() == "yes" else HIGH_NO


def _format_delta(value: float) -> str:
    if pd.isna(value):
        return ""
    if value > 0:
        return f"+{value:.1f}"
    if value < 0:
        return f"{value:.1f}"
    return "0.0"


def _rg_color(ratio: float) -> str:
    ratio = max(0.0, min(1.0, float(ratio)))
    r = int(round(255 * (1 - ratio)))
    g = int(round(82 + 118 * ratio))
    return f"rgb({r},{g},82)"


def _style(view: pd.DataFrame):
    wins = pd.to_numeric(view["Proj Wins"], errors="coerce")
    deltas = pd.to_numeric(view["vs posted"], errors="coerce")
    lo, hi = float(wins.min()), float(wins.max())
    span = hi - lo
    high_flags = view[HIGH_COL].astype(str) if HIGH_COL in view.columns else None

    def _apply(df: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        if "Proj Wins" in df.columns and span > 0:
            col = df.columns.get_loc("Proj Wins")
            for row, w in enumerate(wins.to_numpy()):
                if not pd.isna(w):
                    styles.iat[row, col] = (
                        f"color: {_rg_color((w - lo) / span)}; "
                        "font-weight: 700; font-size: 15px"
                    )
        if "vs posted" in df.columns:
            col = df.columns.get_loc("vs posted")
            for row, delta in enumerate(deltas.to_numpy()):
                if pd.isna(delta):
                    continue
                if abs(delta) >= 1.0:
                    color = "rgb(82,200,82)" if delta > 0 else "rgb(242,139,130)"
                    styles.iat[row, col] = f"font-weight: 700; color: {color}"
                elif abs(delta) >= 0.25:
                    styles.iat[row, col] = "font-weight: 600"
        if high_flags is not None and HIGH_COL in df.columns:
            col = df.columns.get_loc(HIGH_COL)
            for row, flag in enumerate(high_flags.to_numpy()):
                if flag == HIGH_YES:
                    styles.iat[row, col] = "font-weight: 700; font-size: 18px"
        return styles

    return _apply


def _totals_column_config() -> dict:
    return {
        "#": st.column_config.NumberColumn(
            format="%d", width=50, pinned=True,
            help="Row number in this table as currently sorted.",
        ),
        "Proj Wins": st.column_config.NumberColumn(format="%.1f", help=PROJ_HELP),
        "Posted": st.column_config.NumberColumn(format="%.1f", help=POSTED_HELP),
        "vs posted": st.column_config.NumberColumn(format="%+.1f", help=VS_HELP),
        HIGH_COL: st.column_config.TextColumn(help=HIGH_HELP, width="medium"),
    }


def _phone_column_config() -> dict:
    """Phone grid: same help/format as desktop, shorter labels, pinned widths."""
    cfg = _totals_column_config()
    cfg["#"] = st.column_config.NumberColumn(
        "#", format="%d", width=_PHONE_WIDTHS["#"], pinned=True,
        help="Row number in this table as currently sorted.",
    )
    cfg["Team"] = st.column_config.TextColumn(
        "Team", width=_PHONE_WIDTHS["Team"], pinned=True,
    )
    cfg["Proj Wins"] = st.column_config.NumberColumn(
        _PHONE_LABELS["Proj Wins"], format="%.1f",
        width=_PHONE_WIDTHS["Proj Wins"], pinned=True, help=PROJ_HELP,
    )
    cfg["Posted"] = st.column_config.NumberColumn(
        "Posted", format="%.1f",
        width=_PHONE_WIDTHS["Posted"], pinned=True, help=POSTED_HELP,
    )
    cfg["vs posted"] = st.column_config.NumberColumn(
        _PHONE_LABELS["vs posted"], format="%+.1f",
        width=_PHONE_WIDTHS["vs posted"], pinned=True, help=VS_HELP,
    )
    cfg[HIGH_COL] = st.column_config.TextColumn(
        _PHONE_LABELS[HIGH_COL], help=HIGH_HELP,
        width=_PHONE_WIDTHS[HIGH_COL], pinned=True,
    )
    return cfg


def _render_hero(high: dict) -> None:
    wins = int(high["wins"])
    n = int(high["n"])
    pct = 100.0 * float(high["ats"])
    wilson = 100.0 * float(high["wilson_lower"])
    gap = float(high["gap"])
    n_fwd = int(high.get("forward_n") or 0)

    st.markdown(
        f"### High-confidence held-out record\n"
        f"Held-out record when the model disagrees with the posted number by "
        f"**{gap:.0f}+ wins**: **{wins}/{n} correct ({pct:.2f}%)** on "
        f"2015-2025 walk-forward. The one-sided 95% Wilson lower bound is "
        f"**{wilson:.2f}%**, under the {BAR_PCT:.1f}% bar."
    )

    with st.container(key="jsa-st-hero"):
        c1, c2, c3 = st.columns(3)
        c1.metric("High confidence record", f"{wins}/{n}", f"{pct:.2f}% correct")
        c2.metric("2026 high confidence calls", str(n_fwd), f"{gap:.0f}+ win gap rule")
        c3.metric(
            "One-sided 95% Wilson lower",
            f"{wilson:.2f}%",
            f"below the {BAR_PCT:.1f}% bar",
        )


def _high_picks(view: pd.DataFrame) -> pd.DataFrame:
    return view[view[HIGH_COL].eq(HIGH_YES)].copy()


def _render_2026_high_cards(picks: pd.DataFrame) -> None:
    st.markdown("#### 2026 high confidence calls")
    cols = st.columns(min(len(picks), 5))
    for col, (_, row) in zip(cols, picks.iterrows()):
        delta = float(row["vs posted"])
        direction = "Above" if delta > 0 else "Below"
        with col:
            st.markdown(
                f"**{row['Team']}** {HIGH_YES}\n\n"
                f"{row['Proj Wins']:.1f} proj vs {row['Posted']:.1f} posted\n\n"
                f"{direction} by {_format_delta(delta)}"
            )


def _render_2026_high_phone(picks: pd.DataFrame) -> None:
    st.markdown("#### 2026 high confidence calls")
    for _, row in picks.iterrows():
        delta = float(row["vs posted"])
        st.markdown(
            f"**{row['Team']}** {HIGH_YES} · "
            f"{row['Proj Wins']:.1f} vs {row['Posted']:.1f} · "
            f"{_format_delta(delta)}"
        )


def _render_footnote(ev: dict, label: str) -> None:
    high = ev.get("ou_high") or {}
    wilson = 100.0 * float(high.get("wilson_lower") or 0.0)
    mae_gap = float(ev["mae_model"]) - float(ev["mae_market"])
    st.caption(
        f"{label} The all-team projection does not beat the posted win total on "
        f"average (+{mae_gap:.4f} wins vs the posted number on held-out seasons, "
        f"backtested, not live-validated). High-confidence one-sided 95% Wilson "
        f"lower: {wilson:.2f}% (under the {BAR_PCT:.1f}% bar)."
    )


def _render_backtest_expander(ev: dict) -> None:
    with st.expander("Full projection accuracy (not the high-confidence book)"):
        st.markdown(
            "Average miss per team in wins on held-out seasons. Lower is better. "
            "This is the all-teams projection sheet, not the high-confidence slice."
        )
        if ev.get("ladder"):
            ladder = pd.DataFrame(ev["ladder"]).rename(
                columns={"name": "Approach", "mae": "Average miss (wins)", "n": "n"}
            )
            with st.container(key="jsa-st-ladder"):
                st.dataframe(
                    ladder,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Average miss (wins)": st.column_config.NumberColumn(
                            format="%.4f"
                        ),
                        "n": st.column_config.NumberColumn(format="%d"),
                    },
                )
        c1, c2, c3 = st.columns(3)
        c1.metric("This model (all teams)", f"{ev['mae_model']:.4f} wins")
        c2.metric("Posted win total", f"{ev['mae_market']:.4f} wins")
        c3.metric(
            "Seasons beating posted",
            f"{ev['seasons_model_better']}/{ev['seasons_total']}",
        )


def _posted_stamp(df: pd.DataFrame, ev: dict) -> str:
    if "posted_as_of" in df.columns and pd.notna(df["posted_as_of"].iloc[0]):
        as_of = str(df["posted_as_of"].iloc[0])[:10]
    else:
        as_of = str(ev.get("posted_as_of", ""))[:10]
    source = ""
    if "posted_source" in df.columns and pd.notna(df["posted_source"].iloc[0]):
        source = str(df["posted_source"].iloc[0])
    elif ev.get("posted_source"):
        source = str(ev["posted_source"])
    if source.lower().startswith("draftkings"):
        book = "DraftKings"
    elif source:
        book = source.split("(")[0].strip()
    else:
        book = "posted sportsbook"
    if as_of:
        return f"Posted win totals: {book}, as of {as_of}."
    return f"Posted win totals: {book}."


def render():
    st.title("Season Totals")
    st.caption(
        "Pre-season win projections for all 32 teams. High-confidence calls are "
        "the only picks this page highlights."
    )

    csv_stamp = _file_stamp(_CSV)
    df = _load(csv_stamp)
    if df.empty:
        st.info(
            "Season win-total projections are not published yet. From "
            "season_totals_v2_prod run `python src/publish_site.py`."
        )
        return

    ev = _read_json(str(_EVIDENCE), _file_stamp(_EVIDENCE))
    season = int(df["season"].iloc[0])
    label = str(df["claim"].iloc[0])
    high = ev.get("ou_high") or {}
    st.caption(_posted_stamp(df, ev))

    if high.get("n"):
        with st.container(border=True):
            _render_hero(high)

    certified = (
        df["certified"].fillna("").astype(str)
        if "certified" in df.columns
        else pd.Series([""] * len(df))
    )
    view = pd.DataFrame({
        "Team": df["team"],
        "Proj Wins": pd.to_numeric(df["proj_wins"], errors="coerce"),
        "Posted": pd.to_numeric(df["posted"], errors="coerce"),
        "vs posted": pd.to_numeric(df["vs_posted"], errors="coerce"),
        HIGH_COL: certified.map(_high_flag),
    })
    view["_high_sort"] = view[HIGH_COL].eq(HIGH_YES).astype(int)
    view = view.sort_values(
        ["_high_sort", "Proj Wins"], ascending=[False, False]
    ).reset_index(drop=True)
    view = view.drop(columns="_high_sort")
    view.insert(0, "#", range(1, len(view) + 1))

    picks = _high_picks(view)
    if picks.empty:
        st.info("No high-confidence calls for 2026 yet.")
    else:
        with st.container(key="jsa-st-high-desktop"):
            _render_2026_high_cards(picks)
        with st.container(key="jsa-st-high-phone"):
            _render_2026_high_phone(picks)

    st.markdown("#### All 32 team projections")
    totals_cfg = _totals_column_config()
    totals_height = min(720, 60 + 35 * len(view))
    phone_cols = ["#", "Team", "Proj Wins", "Posted", "vs posted", HIGH_COL]
    with st.container(key="jsa-table-desktop-season-totals"):
        st.dataframe(
            view.style.apply(_style(view), axis=None),
            hide_index=True, width="stretch", height=totals_height,
            column_config=totals_cfg,
        )
    with st.container(key="jsa-table-phone-season-totals"):
        st.dataframe(
            view[phone_cols].style.apply(_style(view), axis=None),
            hide_index=True, width="stretch", height=totals_height,
            column_config=_phone_column_config(),
        )

    if ev:
        _render_footnote(ev, label)
        _render_backtest_expander(ev)

    with st.expander("How this is built"):
        st.markdown(METHOD)
        stamp = str(df["generated_at"].iloc[0])[:19].replace("T", " ")
        st.caption(
            f"line_in · {season} season · generated {stamp} UTC · "
            "season_totals_v2_prod"
        )
