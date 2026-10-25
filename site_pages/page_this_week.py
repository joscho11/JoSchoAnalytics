"""This Week hub - the in-season landing that gathers the week's spread HIGH card,
weekly fantasy, and anytime TDs into one place, each linking to its full page.

Summary + deep-links by design: it reuses the same release manifest and loaders as
the individual pages (release_default_selection, render_release_status,
row_display_high, season_high_record), so nothing here can drift from what those
pages show. Import-safe: no st.* at import time.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

import dashboard_data
import nav_registry
import page_common
from dashboard_utils import ats_record_parts, format_ats_record
from live_2026 import BREAKEVEN, LIVE_SEASON, row_display_high, season_high_record
from publishing.manifest import release_status as _manifest_release_status
from team_display import public_team_abbr


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


def _friendly_date(value) -> str:
    """'2026-10-21T00:54:34Z' -> 'Wed Oct 21'. Unparseable input is returned as-is."""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return str(value)
    return f"{parsed:%a %b} {parsed.day}"


def _release_status(product: str, season: int, week: int, fallback_caption: str) -> None:
    """Badge + plain-language detail from the release manifest (no raw ISO stamps)."""
    try:
        manifest = page_common.load_release_manifest()
        state = _manifest_release_status(
            product, int(season), int(week), manifest=manifest, root=page_common._HERE
        )
        st.badge(state["status"], icon=state["icon"], color=state["color"])
        if state.get("published_at"):
            st.caption(f"Validated {_friendly_date(state['published_at'])}")
        else:
            st.caption(state["detail"])
        nxt = (manifest.get("products", {}).get(product, {}) or {}).get("next_release") or {}
        try:
            n_season, n_week = int(nxt["season"]), int(nxt["week"])
        except (KeyError, TypeError, ValueError):
            return
        if state["status"] == "Published" and (n_season, n_week) != (int(season), int(week)):
            upcoming = _manifest_release_status(
                product, n_season, n_week, manifest=manifest, root=page_common._HERE
            )
            if upcoming["status"] == "Published":
                st.caption(f"Next: {n_season} Week {n_week} is published.")
            elif upcoming["status"] == "Scheduled":
                st.caption(f"Next: {n_season} Week {n_week} is scheduled.")
            else:
                st.caption(f"Next: {n_season} Week {n_week} projections are not out yet.")
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
            games.append(f"{public_team_abbr(away)} @ {public_team_abbr(home)}")
    return int(mask.sum()), games


def _correct_col(df) -> str:
    if "ens_model_correct" in df.columns and df["ens_model_correct"].notna().any():
        return "ens_model_correct"
    return "model_correct"


def _record_metric(preds) -> None:
    try:
        wins, n, pct = season_high_record(preds)
        losses, pushes = n - wins, 0
        sdf = preds[(preds["season"] == LIVE_SEASON) & preds["actual_margin"].notna()]
        hdf = sdf[sdf.apply(row_display_high, axis=1)]
        _, _, pushes, _ = ats_record_parts(hdf, _correct_col(sdf))
    except Exception:
        return
    if n > 0 and pct is not None:
        st.metric(
            f"{LIVE_SEASON} HIGH picks (ATS)", format_ats_record(wins, losses, pushes), f"{pct}%",
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
            st.caption("HIGH = a 3.0+ point disagreement with the Tuesday number. Open "
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
               "numbers are projections. Touchdown Props has live 2026 Anytime TD, "
               "2+ TD, and First TD markets, plus a 2025 demo. Full method on Help & Guide.")
