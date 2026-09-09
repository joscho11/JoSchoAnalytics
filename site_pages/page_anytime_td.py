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
LIVE_SEASON = 2026
DEFAULT_RELEASE = (LIVE_SEASON, 1)
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


def _parse_release(name: str) -> tuple[int, int] | None:
    stem = name.removesuffix(".csv")
    parts = stem.split("_")
    if len(parts) < 4 or parts[0] != "anytime" or parts[1] != "td":
        return None
    try:
        return int(parts[2]), int(parts[3].removeprefix("week"))
    except ValueError:
        return None


def available_releases() -> dict[tuple[int, int], Path]:
    found: dict[tuple[int, int], Path] = {}
    if not _DIR.is_dir():
        return found
    for path in sorted(_DIR.glob("anytime_td_*_week*.csv")):
        key = _parse_release(path.name)
        if key is not None:
            found[key] = path
    return found


def default_release(options: list[tuple[int, int]]) -> tuple[int, int]:
    """Prefer the live 2026 Week 1 board whenever it has been published."""
    if DEFAULT_RELEASE in options:
        return DEFAULT_RELEASE
    live = [key for key in options if key[0] == LIVE_SEASON]
    return live[0] if live else options[0]


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
    outcomes = pd.to_numeric(df["scored_anytime"], errors="coerce")
    hits = int(outcomes.eq(1).sum())
    graded = int(outcomes.notna().sum())
    return {
        "n": n,
        "hits": hits,
        "graded": graded,
        "hit_rate": (hits / graded) if graded else None,
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


def _live_metadata() -> dict:
    files = sorted(_DIR.glob("anytime_td_2026_week01_*.json"))
    if not files:
        return {}
    # The newest slate metadata describes the most recent cumulative append.
    return _load_meta(str(files[-1]))
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
    outcome = pd.to_numeric(ranked.scored_anytime, errors="coerce")
    hit = outcome.map(lambda value: "Yes" if value == 1 else ("No" if pd.notna(value) else ""))
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
        "Hit": hit,
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
    graded = pd.to_numeric(view.scored_anytime, errors="coerce").notna().any()
    desktop_cols = DESKTOP_COLS if graded else [c for c in DESKTOP_COLS if c != "Hit"]
    phone_cols = PHONE_COLS if graded else [c for c in PHONE_COLS if c != "Hit"]
    show = table[desktop_cols]
    phone = table[phone_cols]
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
        "Passing TDs are out. Live 2026 releases plus a 2025 demo. For fun. Bet responsibly."
    )
    releases = available_releases()
    if not releases:
        st.error("Anytime TD demo files are missing.")
        st.stop()
    live_keys = sorted((key for key in releases if key[0] == LIVE_SEASON), reverse=True)
    demo = available_weeks()
    if live_keys:
        options = live_keys + sorted(((DEMO_SEASON, w) for w in demo), reverse=True)
        labels = {key: f"{key[0]} Week {key[1]}" for key in options}
        seeded = page_common.seed_widget_from_query("atd_release", "atd_release", options)
        with st.container(key="jsa-filter-bar"):
            controls = st.columns([1, 2])
            kwargs = {"key": "atd_release", "format_func": lambda key: labels[key]}
            if not seeded and "atd_release" not in st.session_state:
                kwargs["index"] = options.index(default_release(options))
            release = controls[0].selectbox("Week", options, **kwargs)
            page_common.sync_query_value("atd_release", release)
            search = controls[1].text_input("Search player", placeholder="Barkley, Jefferson", key="atd_search")
        available = releases
        season, week = release
        if season == LIVE_SEASON:
            st.info("Live 2026 prices are copied manually from the sportsbook when available (preferably near T-3h). "
                    "Early preparation captures are labeled; additional games appear as they are frozen. No odds API is used.")
            meta = _live_metadata()
            if meta:
                books = ", ".join(meta.get("book", []))
                st.caption(f"Book: {books or 'manual paste'} · Last capture: {meta.get('capture_max', 'unknown')}")
    else:
        weeks = sorted(demo)
        with st.container(key="jsa-filter-bar"):
            controls = st.columns([1, 2])
            seeded = page_common.seed_widget_from_query("atd_week", "atd_week", weeks)
            week_kwargs = {"key": "atd_week"}
            if not seeded and "atd_week" not in st.session_state:
                week_kwargs["index"] = weeks.index(DEFAULT_WEEK) if DEFAULT_WEEK in weeks else 0
            week = int(controls[0].selectbox("Week", weeks, **week_kwargs))
            page_common.sync_query_value("atd_week", week)
            search = controls[1].text_input("Search player", placeholder="Barkley, Jefferson", key="atd_search")
        available = {(DEMO_SEASON, w): p for w, p in demo.items()}
        season = DEMO_SEASON
    with st.container(horizontal=True, vertical_alignment="center"):
        is_live = season == LIVE_SEASON
        st.badge("Live" if is_live else "Demo", icon=":material/live_tv:" if is_live else ":material/science:",
                 color="green" if is_live else "orange")
        st.caption("Priced players only. Sorted by our P(TD). " +
                   ("Cumulative 2026 Week 1 release." if is_live else "2025 weeks 10-17 demo."))
    _reading_guide()

    raw = _load_csv(str(available[(season, week)]))
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
        if summary["graded"]:
            st.metric("Scored", f"{summary['hits']}/{summary['graded']}", f"{hit_pct:.0f}%",
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
