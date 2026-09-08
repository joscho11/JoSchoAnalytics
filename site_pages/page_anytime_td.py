"""Anytime TDs demo page. 2025 weeks 10-17 CSVs from td_count_model_beta.

Rushing and receiving TDs only. Passing TDs are out. CSV only. No model code.
A priced comparison board: our P(TD) next to the book, not a pick list.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

import page_common
from dashboard_chrome import TABLE_HEIGHT, dataframe_phone_desktop

_HERE = Path(__file__).resolve().parents[1]
_DIR = _HERE / "betting" / "anytime_td"
DEMO_SEASON = 2025
DEFAULT_WEEK = 10
POS_TABS = ("All", "QB", "RB", "WR", "TE")
DESKTOP_COLS = [
    "#", "Player", "Pos", "Opp", "Our P(TD)", "Book", "vs book",
    "Our fair", "P(2+)", "Hit",
]
PHONE_COLS = ["#", "Player", "Our P(TD)", "Book", "Hit"]
PHONE_LABELS = {
    "Our P(TD)": "Ours",
}
PHONE_WIDTHS = {
    "#": 50,
    "Player": 148,
    "Our P(TD)": 58,
    "Book": 54,
    "Hit": 50,
}


def _parse_week(name: str) -> int | None:
    stem = name.replace(".csv", "")
    parts = stem.split("_")
    try:
        if parts[0] != "anytime" or parts[2] != f"{DEMO_SEASON}":
            return None
        return int(parts[3].replace("week", ""))
    except (IndexError, ValueError):
        return None


def available_weeks() -> dict[int, Path]:
    found: dict[int, Path] = {}
    if not _DIR.is_dir():
        return found
    for path in sorted(_DIR.glob(f"anytime_td_{DEMO_SEASON}_week*.csv")):
        week = _parse_week(path.name)
        if week is not None:
            found[week] = path
    return found


def priced_rows(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["p_book"] = pd.to_numeric(out["p_book"], errors="coerce")
    out["p_ge1"] = pd.to_numeric(out["p_ge1"], errors="coerce")
    out["p_ge2"] = pd.to_numeric(out.get("p_ge2"), errors="coerce")
    return out[out.p_book.notna() & out.p_ge1.notna()].copy()


def by_position(df: pd.DataFrame, position: str) -> pd.DataFrame:
    if position == "All":
        return df
    if position == "RB":
        return df[df.position.isin(["RB", "FB"])]
    return df[df.position.eq(position)]


def week_summary(df: pd.DataFrame) -> dict:
    n = int(len(df))
    hits = int(pd.to_numeric(df["scored_anytime"], errors="coerce").fillna(0).eq(1).sum())
    return {
        "n": n,
        "hits": hits,
        "hit_rate": (hits / n) if n else None,
        "mean_p": float(df.p_ge1.mean()) if n else None,
        "mean_book": float(df.p_book.mean()) if n else None,
    }


@st.cache_data(ttl=3600)
def _load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


@st.cache_data(ttl=3600)
def _load_meta(path: str) -> dict:
    raw = Path(path)
    if not raw.is_file():
        return {}
    try:
        return json.loads(raw.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _amer(value) -> str:
    if pd.isna(value):
        return ""
    n = int(round(float(value)))
    return f"+{n}" if n > 0 else str(n)


def _p_color(val, lo: float = 0.08, hi: float = 0.55) -> str:
    if pd.isna(val):
        return ""
    ratio = max(0.0, min(1.0, (float(val) - lo) / (hi - lo)))
    r = int(255 * (1 - ratio))
    g = int(82 + 118 * ratio)
    return f"color: rgb({r},{g},82); font-weight: 600"


def _display(df: pd.DataFrame) -> pd.DataFrame:
    ranked = df.sort_values("p_ge1", ascending=False).reset_index(drop=True)
    vs = 100 * (ranked.p_ge1 - ranked.p_book)
    hit = pd.to_numeric(ranked.scored_anytime, errors="coerce").fillna(0).eq(1)
    return pd.DataFrame({
        "#": range(1, len(ranked) + 1),
        "Player": ranked.player_display_name + " · " + ranked.team.astype(str),
        "Pos": ranked.position,
        "Opp": ranked.opponent_team,
        "Our P(TD)": ranked.p_ge1.astype(float),
        "Book": ranked.p_book.astype(float),
        "vs book": vs.round(1),
        "Our fair": ranked.fair_amer.map(_amer),
        "P(2+)": ranked.p_ge2.astype(float),
        "Hit": hit.map(lambda ok: "Yes" if ok else "No"),
        "_p": ranked.p_ge1.astype(float),
    })


def _style(view: pd.DataFrame):
    def _apply(df: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        if "Our P(TD)" in df.columns:
            for i, val in enumerate(view["_p"]):
                styles.iloc[i, df.columns.get_loc("Our P(TD)")] = _p_color(val)
        if "Hit" in df.columns:
            for i, mark in enumerate(view["Hit"]):
                if mark == "Yes":
                    styles.iloc[i, df.columns.get_loc("Hit")] = (
                        "color: #35D08A; font-weight: 700"
                    )
        return styles
    return _apply


def _desktop_column_config() -> dict:
    return {
        "#": st.column_config.NumberColumn("#", format="%d", width=50, pinned=True,
                                           help="Row number in this list as currently sorted."),
        "Player": st.column_config.TextColumn("Player", help="Name and NFL team."),
        "Opp": st.column_config.TextColumn("Opp", help="Opponent this week."),
        "Our P(TD)": st.column_config.NumberColumn(
            "Our P(TD)", format="percent",
            help="Our chance the player scores a rushing or receiving TD.",
        ),
        "Book": st.column_config.NumberColumn(
            "Book", format="percent",
            help="Median implied Yes from at least 3 US books, T-2h close.",
        ),
        "vs book": st.column_config.NumberColumn(
            "vs book", format="%+.1f",
            help="Our probability minus the book, in percentage points. Not a bet.",
        ),
        "Our fair": st.column_config.TextColumn(
            "Our fair", help="American odds implied by our P(TD).",
        ),
        "P(2+)": st.column_config.NumberColumn(
            "P(2+)", format="percent",
            help="Chance of two or more rushing or receiving TDs.",
        ),
        "Hit": st.column_config.TextColumn(
            "Hit", help="Did they score a rushing or receiving TD?",
        ),
    }


def _phone_column_config() -> dict:
    cfg = _desktop_column_config()
    cfg["#"] = st.column_config.NumberColumn(
        "#", format="%d", width=PHONE_WIDTHS["#"], pinned=True,
        help="Row number in this list as currently sorted.",
    )
    cfg["Player"] = st.column_config.TextColumn(
        "Player", width=PHONE_WIDTHS["Player"], pinned=True,
        help="Name and NFL team.",
    )
    cfg["Our P(TD)"] = st.column_config.NumberColumn(
        PHONE_LABELS["Our P(TD)"], format="percent",
        width=PHONE_WIDTHS["Our P(TD)"], pinned=True,
        help="Our chance the player scores a rushing or receiving TD.",
    )
    cfg["Book"] = st.column_config.NumberColumn(
        "Book", format="percent", width=PHONE_WIDTHS["Book"], pinned=True,
        help="Median implied Yes from at least 3 US books, T-2h close.",
    )
    cfg["Hit"] = st.column_config.TextColumn(
        "Hit", width=PHONE_WIDTHS["Hit"], pinned=True,
        help="Did they score a rushing or receiving TD?",
    )
    return cfg


def _board(view: pd.DataFrame, slug: str, search: str) -> None:
    table = _display(view)
    style_fn = _style(table)
    show = table[DESKTOP_COLS]
    phone = table[PHONE_COLS]
    dataframe_phone_desktop(
        show.style.apply(style_fn, axis=None),
        phone.style.apply(style_fn, axis=None),
        slug=slug,
        hide_index=True,
        width="stretch",
        height=TABLE_HEIGHT,
        column_config=_desktop_column_config(),
        phone_column_config=_phone_column_config(),
        key=f"atd_grid_{slug}_{search}_{len(table)}",
    )


def _reading_guide() -> None:
    with st.expander("How to read this board"):
        st.markdown("""
Chance a skill player scores a rushing or receiving touchdown. Passing TDs are
out. This is not even money: a typical quote is around one in five, so misses
will outnumber hits. Over full 2025 the sportsbooks were still about 0.08% more
accurate. On these eight demo weeks our numbers were closer in 5; that is not a
betting record. For fun, not a proven edge. Bet responsibly.

**Desktop columns.** #, Player (name and team), Pos, Opp, Our P(TD), Book,
vs book (percentage points, not a pick), Our fair, P(2+), Hit.

**Phone columns.** #, Player, Ours, Book, Hit. Swipe the position tabs.
        """)


def render() -> None:
    st.title("Anytime TDs")
    st.caption(
        "Chance a skill player scores a rushing or receiving touchdown. "
        "Passing TDs are out. Demo. For fun. Bet responsibly."
    )
    st.info(
        "2026 Week 1 is not on this board yet. It lands later this week, because "
        "the book Yes prices are posted about three hours before kickoff. "
        "Everything below is the 2025 weeks 10 to 17 demo."
    )
    available = available_weeks()
    if not available:
        st.error("Anytime TD demo files are missing.")
        st.stop()
    weeks = sorted(available)
    with st.container(key="jsa-filter-bar"):
        controls = st.columns([1, 2])
        seeded = page_common.seed_widget_from_query("atd_week", "atd_week", weeks)
        week_kwargs = {"key": "atd_week"}
        if not seeded and "atd_week" not in st.session_state:
            week_kwargs["index"] = weeks.index(DEFAULT_WEEK) if DEFAULT_WEEK in weeks else 0
        week = int(controls[0].selectbox("Week", weeks, **week_kwargs))
        page_common.sync_query_value("atd_week", week)
        search = controls[1].text_input(
            "Search player", placeholder="Barkley, Jefferson", key="atd_search",
        )

    with st.container(horizontal=True, vertical_alignment="center"):
        st.badge("Demo", icon=":material/science:", color="orange")
        st.caption("Priced players only. Sorted by our P(TD). 2025 weeks 10-17 demo.")
    _reading_guide()

    raw = _load_csv(str(available[week]))
    need = [
        "player_display_name", "position", "team", "opponent_team",
        "p_ge1", "p_ge2", "p_book", "fair_amer", "scored_anytime",
    ]
    missing = [c for c in need if c not in raw.columns]
    if missing:
        st.error(f"Demo CSV is missing columns: {missing}")
        st.stop()

    priced = priced_rows(raw)
    if priced.empty:
        st.warning("No book Yes prices for this week.")
        st.stop()
    summary = week_summary(priced)
    hit_pct = 100 * summary["hit_rate"] if summary["hit_rate"] is not None else 0
    with st.container(horizontal=True, key="jsa-metric-even-atd"):
        st.metric("Priced", summary["n"], border=True)
        st.metric("Scored", f"{summary['hits']}/{summary['n']}", f"{hit_pct:.0f}%",
                  delta_arrow="off", border=True)
        st.metric("Our P", f"{100 * summary['mean_p']:.0f}%", border=True)
        st.metric("Book P", f"{100 * summary['mean_book']:.0f}%", border=True)

    if search:
        priced = priced[priced.player_display_name.str.contains(
            search, case=False, na=False, regex=False,
        )]

    tabs = st.tabs(list(POS_TABS), key="atd_position_tabs", on_change="rerun")
    for tab, pos in zip(tabs, POS_TABS):
        if not tab.open:
            continue
        with tab:
            view = by_position(priced, pos)
            if view.empty:
                st.info("No priced players in this filter.")
                continue
            st.caption(f"{len(view)} priced · {pos}")
            _board(view, f"atd-{pos.lower()}", search or "")
