"""Stable, season-aware landing page for JoScho Analytics."""

import streamlit as st

import nav_registry
from seasonal_config import app_today, board_refresh_season_start
import dashboard_data
import email_signup
import live_2026


def _page_link(slug: str, label: str, icon: str) -> None:
    page = nav_registry.PAGES.get(slug)
    if page is not None:
        st.page_link(page, label=label, icon=icon, width="stretch")
    else:
        # Standalone AppTest harnesses do not populate the navigation registry.
        st.markdown(f"**{label}**")


def _live_record_line() -> str:
    """Compact 2026 HIGH record for the Track Record card - blends into the card
    and never claims a figure the tracker does not have. Empty on any load error."""
    try:
        wins, n, pct = live_2026.season_high_record(dashboard_data.load_predictions())
    except Exception:
        return ""
    if n > 0 and pct is not None:
        return f"**{live_2026.LIVE_SEASON} HIGH:** {wins}/{n} ({pct}%)"
    return f"**{live_2026.LIVE_SEASON} HIGH:** first graded card after Week 1"


def render() -> None:
    st.title("JoScho Analytics")
    st.caption(
        "Independent NFL betting and fantasy models, published with their assumptions, "
        "limits, results, and source code."
    )

    with st.container(horizontal=True, vertical_alignment="center"):
        st.badge("2026 preseason", icon=":material/calendar_today:", color="orange")
        st.badge("Public methodology", icon=":material/code:", color="green")
        st.badge("No paid picks", icon=":material/verified:", color="blue")

    st.subheader("Start here")
    with st.container(key="jsa-home-start"):
        with st.container(horizontal=True, gap="medium"):
            with st.container(border=True, height="stretch"):
                st.markdown("### Build a draft plan")
                st.caption(
                    "Compare the frozen independent projection with daily Sleeper, ESPN, or Yahoo ADP "
                    "across the 180-player board."
                )
                _page_link("draft-board", "Open the Draft Board", ":material/list_alt:")

            with st.container(border=True, height="stretch"):
                st.markdown("### Check the NFL slate")
                st.caption(
                    "Review every matchup and the Tuesday HIGH betting card. Week 1 "
                    "matchups are already published."
                )
                _page_link(
                    "weekly-predictions",
                    "Open Weekly Predictions",
                    ":material/query_stats:",
                )

        with st.container(horizontal=True, gap="medium"):
            with st.container(border=True, height="stretch"):
                st.markdown("### Audit the evidence")
                st.caption(
                    "See the graded record, confidence definitions, break-even line, and "
                    "where live 2026 differs from the 2025 demo."
                )
                _page_link("track-record", "Open the Track Record", ":material/monitoring:")

            with st.container(border=True, height="stretch"):
                st.markdown("### Compare anytime TDs")
                st.caption(
                    "2025 demo of rushing and receiving TD chances next to the book. "
                    "Not even money. For fun. Not a proven edge."
                )
                _page_link("anytime-tds", "Open Anytime TDs", ":material/sports_score:")

    _rec = _live_record_line()
    if _rec:
        st.markdown(_rec)

    season_start = board_refresh_season_start()
    if app_today() < season_start:
        st.info(
            "The site is in preseason mode. The Draft Board, Week 1 matchups, weekly fantasy rankings, and DFS projections are live. "
            "The DFS Optimizer still needs the DraftKings salary CSV for the contest. "
            "Anytime TDs is a 2025 demo. "
            f"The next planned Draft Board model snapshot is before {season_start:%B %d}."
        )
    else:
        st.info(
            "The regular season is underway. Weekly products publish on their stated "
            "cadence; use each page's freshness note before acting on a number."
        )

    st.subheader("Explore the rest")
    with st.container(horizontal=True, gap="small", key="jsa-home-explore"):
        _page_link("rookie-board", "Rookie Board", ":material/biotech:")
        _page_link("weekly-fantasy", "Weekly Fantasy", ":material/trophy:")
        _page_link("dfs-optimizer", "DFS Optimizer", ":material/target:")
        _page_link("season-totals", "Season Totals", ":material/bar_chart:")
        _page_link("league-history", "League History", ":material/history:")
        _page_link("film-room", "Film Room", ":material/movie:")

    email_signup.render_card()

    with st.container(border=True):
        st.markdown("**How to read the site**")
        st.caption(
            "Green highlights identify a documented threshold, not certainty. Live 2026 "
            "and historical demo outputs are labeled separately. When a market or result "
            "source is unavailable, the site says so instead of filling the gap with an "
            "estimate."
        )
        _page_link("help", "Read Help & Guide", ":material/help:")
