"""This Week hub - the in-season landing that gathers the week's spread HIGH card,
weekly fantasy, and anytime TDs into one place, each linking to its full page.

Summary + deep-links by design: it reuses the same release manifest and loaders as
the individual pages (release_default_selection, render_release_status,
row_display_high, season_high_record), so nothing here can drift from what those
pages show. Import-safe: no st.* at import time.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import dashboard_data
import nav_registry
import page_common
from live_2026 import BREAKEVEN, LIVE_SEASON, row_display_high, season_high_record


def _page_link(slug: str, label: str, icon: str) -> None:
    page = nav_registry.PAGES.get(slug)
    if page is not None:
        st.page_link(page, label=label, icon=icon, width="stretch")
    else:
        st.markdown(f"**{label}**")


def _current_week() -> tuple[int, int]:
    try:
        season, week = page_common.release_default_selection("predictions", (LIVE_SEASON, 1))
        return int(season), int(week)
    except Exception:
        return LIVE_SEASON, 1


def _release_status(product: str, season: int, week: int, fallback_caption: str) -> None:
    try:
        page_common.render_release_status(product, int(season), int(week))
    except Exception:
        st.caption(fallback_caption)


def _high_this_week(preds, season: int, week: int):
    if preds is None or getattr(preds, "empty", True):
        return 0, []
    if "season" not in preds.columns or "week" not in preds.columns:
        return 0, []
    wk = preds[(preds["season"] == season) & (preds["week"] == week)]
    if wk.empty:
        return 0, []
    mask = wk.apply(row_display_high, axis=1)
    games = []
    for _, r in wk[mask].iterrows():
        home, away = r.get("home_team"), r.get("away_team")
        if pd.notna(home) and pd.notna(away):
            games.append(f"{away} @ {home}")
    return int(mask.sum()), games


def _record_metric(preds) -> None:
    try:
        wins, n, pct = season_high_record(preds)
    except Exception:
        return
    if n > 0 and pct is not None:
        st.metric(
            f"{LIVE_SEASON} HIGH picks (ATS)", f"{wins}/{n}", f"{pct}%",
            delta_color="green" if pct >= BREAKEVEN * 100 else "red",
            delta_arrow="off", border=True,
        )
    else:
        st.metric(
            f"{LIVE_SEASON} HIGH picks (ATS)", "0/0", "first card after Week 1",
            delta_color="gray", delta_arrow="off", border=True,
        )


def render() -> None:
    st.title("This week")
    season, week = _current_week()
    st.caption(
        f"{season} Week {week} in one place - the HIGH spread card, weekly fantasy, and "
        "anytime TDs, each linking to the full page."
    )

    try:
        preds = dashboard_data.load_predictions()
    except Exception:
        preds = None

    _record_metric(preds)

    with st.container(border=True):
        st.markdown(f"### The HIGH card - Week {week}")
        _release_status("predictions", season, week,
                        "NFL spread projections and the Tuesday HIGH picks.")
        n_high, games = _high_this_week(preds, season, week)
        if n_high > 0:
            plural = "s" if n_high != 1 else ""
            st.markdown(f"**{n_high} HIGH pick{plural} this week:** " + ", ".join(games))
            st.caption("HIGH = a 2.5+ point disagreement with the Tuesday number. Open "
                       "Weekly Predictions for each pick and the full slate.")
        else:
            st.caption("No HIGH picks flagged yet this week - the full slate and every "
                       "pick are on Weekly Predictions.")
        _page_link("weekly-predictions", "Open Weekly Predictions", ":material/query_stats:")

    with st.container(border=True):
        st.markdown("### Weekly fantasy")
        try:
            f_season, f_week = page_common.release_default_selection("fantasy", (season, week))
            _release_status("fantasy", int(f_season), int(f_week),
                            "Half-PPR and per-stat projections for QB, RB, WR, and TE.")
        except Exception:
            st.caption("Half-PPR and per-stat projections for QB, RB, WR, and TE.")
        _page_link("weekly-fantasy", "Open Weekly Fantasy", ":material/trophy:")

    with st.container(border=True):
        st.markdown("### Touchdown Props")
        st.caption("Anytime, 2+, and First TD scorer chances next to the book. "
                   "Not even money, for fun, not a proven edge.")
        _page_link("anytime-tds", "Open Touchdown Props", ":material/sports_score:")

    st.caption("Spread numbers are Tuesday line value, not closing-line value. Fantasy "
               "numbers are projections. Touchdown Props' Anytime TD market is a 2025 demo; "
               "2+ TD and First TD are live 2026. Full method on Help & Guide.")
