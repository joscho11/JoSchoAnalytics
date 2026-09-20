"""College Basketball daily spread card (public, Beta)."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import cbb_daily_data


ET = ZoneInfo("America/New_York")


def _date_options(manifest: dict) -> list[str]:
    dates = sorted(str(value) for value in manifest.get("dates", {}) if str(value))
    return dates


def _format_tip(value: object) -> str:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return "Tip time unavailable"
    return parsed.tz_convert(ET).strftime("%a %b %-d · %-I:%M %p ET")


def _history(result_frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [frame for frame in result_frames if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame()
    result = pd.concat(frames, ignore_index=True)
    result["ats_result"] = result["ats_result"].astype(str)
    return result


def _render_card_row(row: pd.Series, result_map: dict[str, str]) -> None:
    with st.container(border=True):
        home = str(row.get("home_team") or row.get("home_team_id"))
        away = str(row.get("away_team") or row.get("away_team_id"))
        pick = str(row.get("ats_pick") or "no_play_line_unavailable")
        status = str(row.get("market_status") or "missing_line")
        st.markdown(f"**{away} at {home}**")
        st.caption(f"{_format_tip(row.get('tipoff_utc'))} · {'Neutral site' if bool(row.get('neutral_site')) else 'Home court'}")
        cols = st.columns(4)
        cols[0].metric("Predicted score", f"{float(row['predicted_away_score']):.1f}–{float(row['predicted_home_score']):.1f}")
        cols[1].metric("Margin / total", f"{float(row['predicted_margin']):+.1f} / {float(row['predicted_total']):.1f}")
        if status == "available" and pd.notna(row.get("market_home_spread")):
            spread = float(row["market_home_spread"])
            line_text = f"{home} {spread:+.1f} · {away} {-spread:+.1f}"
            edge_text = f"{float(row['model_edge']):+.1f}"
        else:
            line_text, edge_text = "Line unavailable", "—"
        cols[2].metric("Median spread", line_text)
        cols[3].metric("Model edge", edge_text)
        if pick in {"home", "away"}:
            st.success(f"8.5-point play: **{pick.upper()}**")
        elif status != "available":
            st.info("No usable CBBD line was available for this game; score prediction remains visible.")
        else:
            st.caption("Below the locked 8.5-point ATS threshold — no play.")
        graded = result_map.get(str(row.get("game_id")))
        if graded:
            st.caption(f"Result: **{graded.upper()}**")


def render():
    st.title("College basketball daily spreads")
    st.badge("Beta", icon=":material/science:", color="blue")
    st.caption("Exploratory shadow card for men’s Division I games. Data provided by CollegeBasketballData.com.")
    st.info("The score model does **not** consume the spread. The CBBD median spread is joined after prediction to calculate model edge and identify the locked 8.5-point ATS policy.")

    try:
        manifest = cbb_daily_data.load_manifest()
    except Exception as exc:
        st.error(f"The CBB release manifest could not be verified: {exc}")
        return
    dates = _date_options(manifest)
    if not dates:
        st.warning("No official College Basketball daily card has been published yet.")
        st.caption("The page will populate after the 2027 season begins and a validated release is available.")
        return
    today = datetime.now(ET).date().isoformat()
    latest = str(manifest.get("latest_date") or dates[-1])
    default = today if today in dates else latest
    if default != today:
        st.warning(f"Showing the latest official card from {latest}; today’s card has not been published.")
    selected = st.selectbox("Card date", dates, index=dates.index(default), key="cbb_card_date")
    state = manifest.get("dates", {}).get(selected, {})
    if state.get("status") == "no_games_scheduled":
        st.success(f"No D1-vs-D1 games were scheduled for {selected}.")
        return
    try:
        card, metadata, entry = cbb_daily_data.load_card(selected)
    except Exception as exc:
        st.error(f"The selected card failed verification: {exc}")
        return
    results = cbb_daily_data.load_results(selected)
    result_map = {}
    if results is not None and not results.empty:
        result_map = dict(zip(results["game_id"].astype(str), results["ats_result"].astype(str)))
    history_frames = []
    for history_day in dates:
        try:
            prior = cbb_daily_data.load_results(history_day)
        except Exception:
            prior = None
        if prior is not None:
            history_frames.append(prior)
    graded_history = _history(history_frames)

    st.caption(f"Official release · {metadata.get('prediction_at_utc', 'time unavailable')} · threshold {float(metadata.get('threshold', 8.5)):.1f} points · policy is exploratory shadow-only")
    st.badge(str(metadata.get("status", state.get("status", "published"))).replace("_", " ").title(), icon=":material/verified:", color="green")
    available = card["market_status"].astype(str).eq("available") if not card.empty else pd.Series(dtype=bool)
    qualified = card["ats_pick"].astype(str).isin({"home", "away"}) if not card.empty else pd.Series(dtype=bool)
    metric_cols = st.columns(4)
    metric_cols[0].metric("Games modeled", int(len(card)))
    metric_cols[1].metric("Market lines", int(available.sum()))
    metric_cols[2].metric("8.5-point selections", int(qualified.sum()))
    if graded_history.empty:
        metric_cols[3].metric("Live ATS record", "No graded games")
    else:
        wins = int((graded_history["ats_result"] == "win").sum())
        losses = int((graded_history["ats_result"] == "loss").sum())
        pushes = int((graded_history["ats_result"] == "push").sum())
        metric_cols[3].metric("Live ATS record", f"{wins}-{losses}-{pushes}")

    view = st.segmented_control("Show", ["All games", "Qualified plays"], default="All games", key="cbb_view")
    shown = card.copy()
    if view == "Qualified plays":
        shown = shown[shown["ats_pick"].astype(str).isin({"home", "away"})].copy()
    if shown.empty:
        st.info("No games match this view.")
    else:
        shown["_qualified"] = shown["ats_pick"].astype(str).isin({"home", "away"})
        shown["_abs_edge"] = pd.to_numeric(shown["model_edge"], errors="coerce").abs().fillna(-1)
        shown = shown.sort_values(["_qualified", "_abs_edge", "tipoff_utc"], ascending=[False, False, True])
        for _, row in shown.iterrows():
            _render_card_row(row, result_map)

    if graded_history.empty:
        st.subheader("Season-to-date record")
        st.caption("Results will appear here after finalized games are reconciled from genuine timestamped 2027 cards.")
    else:
        st.subheader("Season-to-date ATS record")
        graded = graded_history[graded_history["ats_result"].isin({"win", "loss", "push"})].copy()
        wins = int((graded["ats_result"] == "win").sum())
        losses = int((graded["ats_result"] == "loss").sum())
        pushes = int((graded["ats_result"] == "push").sum())
        denominator = wins + losses
        rate = wins / denominator if denominator else None
        st.write(f"{wins} wins · {losses} losses · {pushes} pushes · ATS rate {rate:.1%}" if rate is not None else "No graded wins/losses yet.")
        if denominator:
            timeline = graded.assign(win=(graded["ats_result"] == "win").astype(int)).sort_values("game_date_et")
            timeline["ats_rate"] = timeline["win"].cumsum() / timeline["win"].where(timeline["ats_result"].ne("push")).notna().cumsum()
            chart = timeline.set_index("game_date_et")[["ats_rate"]].rename(columns={"ats_rate": "ATS win rate"})
            st.line_chart(chart, y="ATS win rate")
            st.caption("The horizontal reference is the illustrative 52.38% -110 break-even rate; no ROI, CLV, or guaranteed-success claim is made.")


__all__ = ["render"]
