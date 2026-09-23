"""Weekly Predictions page (site revamp Batch 3b).

The page owns its Season/Week/Min-edge controls, while shared stats/helpers come
from dashboard_data and page_common. The 2026 card reads the active published
spread release directly; the 2025 demo remains the older walkthrough.
"""
import glob
import html as _html
import itertools as _it
import json
import os
from datetime import datetime as dt

import pandas as pd
import streamlit as st

import dashboard_data
import page_common
from dashboard_utils import get_confidence, _md_to_html
from live_2026 import (
    HIGH_GAP,
    LIVE_HIGH_N,
    LIVE_HIGH_WILSON_LOWER,
    LIVE_HIGH_WINS,
    has_pick,
    live_high_bar_sentence,
    is_live_season,
    row_display_high,
    row_high_dropped,
    row_qualifying_edge,
    row_qualifying_spread,
)
from page_common import load_agent_analysis


def _public_high(row) -> bool:
    return row_display_high(row)


def _demo_2025_notice():
    """2025 weeks 10-end stay on the old consensus model. Not live 2026."""
    st.info(
        "**Demo test.** 2025 weeks 10 through the end of the season are a "
        "historical walkthrough of the old three-model consensus. They are "
        "unchanged. Live 2026 uses a different Tuesday model."
    )


def _live_notice():
    st.success(
        "**Live 2026 · Tuesday model.** Every game gets a pick. "
        f"**HIGH** (green) is a {HIGH_GAP:g}+ point disagreement with the Tuesday US median. "
        f"If the line moves and that gap falls under {HIGH_GAP:g}, HIGH is dropped. "
        "A market move alone cannot add a HIGH label; an explicitly published model-version "
        "correction may change predictions and HIGH labels while keeping the frozen Tuesday "
        "line. The named best-available quote is used for execution and grading."
    )
    with st.expander("Tuesday model rules and historical benchmark", expanded=False):
        st.markdown(
            "No medium tier. No totals on this season. "
            f"The QB-retaining model's 2021–2025 walk-forward benchmark is {LIVE_HIGH_WINS}/{LIVE_HIGH_N} = "
            f"{LIVE_HIGH_WINS / LIVE_HIGH_N * 100:.2f}% ATS, with a one-sided 95% "
            f"Wilson lower bound of {LIVE_HIGH_WILSON_LOWER * 100:.2f}% (7 pushes among 397 HIGH labels). Median-triggered "
            "tickets are graded at the best US Tuesday number and the last regular-season "
            f"week is skipped. {live_high_bar_sentence()} The Tuesday line, pick, edge, "
            "and HIGH flag use the median; the named best-available quote is execution "
            "and grading. Picks use the first valid Tuesday capture from 09:00–15:30 ET."
        )


def _live_model_context(release_state: dict) -> None:
    """Show the selected immutable release's model ID and material QB assumptions."""
    build_id = release_state.get("build_id")
    if not build_id:
        return
    manifest = page_common.load_release_manifest()
    state = manifest.get("products", {}).get("predictions", {})
    build = state.get("builds", {}).get(str(build_id), {})
    model_version = build.get("model_version")
    if model_version:
        st.caption(f"Prediction model: `{model_version}`")

    correction = build.get("correction") or {}
    if correction.get("model_update") is not True:
        return
    current_qbs = correction.get("qb_selection_details") or {}
    current_ids = correction.get("qb_selections") or {}
    previous_id = correction.get("supersedes_build_id")
    previous = state.get("builds", {}).get(str(previous_id), {})
    previous_correction = previous.get("correction") or {}
    previous_qbs = previous_correction.get("qb_selection_details") or {}
    previous_ids = previous_correction.get("qb_selections") or {}
    changed = {
        team for team, player_id in current_ids.items()
        if previous_ids.get(team) and previous_ids.get(team) != player_id
    }
    manual = {
        team for team, details in current_qbs.items()
        if details.get("is_user_modeling_assumption") is True
    }
    relevant = sorted(changed | manual)
    if not relevant:
        return
    with st.expander("QB inputs for this model correction", expanded=False):
        if correction.get("reason"):
            st.caption(str(correction["reason"]))
        st.caption(
            "Manual QB choices below are modeling assumptions, not claims that the starter was confirmed."
        )
        qb_notes = []
        for team in relevant:
            current = current_qbs.get(team, {})
            name = current.get("player_name") or current.get("player_id") or current_ids.get(team, "unknown")
            if team in manual:
                note = "user modeling assumption"
            else:
                prior = previous_qbs.get(team, {})
                prior_name = prior.get("player_name") or prior.get("player_id") or previous_ids.get(team, "unknown")
                note = f"previous-game fallback; prior release used {prior_name}"
            qb_notes.append(f"- **{team}:** {name} — {note}")
        st.markdown("\n".join(qb_notes))


def _format_price(value) -> str:
    if value is None or pd.isna(value):
        return ""
    number = float(value)
    return f"{number:+.0f}" if abs(number) >= 10 else f"{number:.2f}"


def _best_quote_label(row, recommended_team: str | None) -> str:
    if not recommended_team:
        return ""
    book = row.get("tuesday_spread_book")
    price = row.get("tuesday_spread_price")
    spread = row.get("tuesday_spread_line", row.get("spread_line"))
    if book is None or pd.isna(book) or price is None or pd.isna(price) or pd.isna(spread):
        return ""
    team_line = -float(spread) if recommended_team == row.get("home_team") else float(spread)
    return (
        f"Best available for {recommended_team}: {team_line:+.1f} "
        f"({_format_price(price)}) at {book}"
    )


def _best_quote_html(row, recommended_team: str | None) -> str:
    """White, not muted. This is the locked execution and grading quote."""
    if not _best_quote_label(row, recommended_team):
        return ""
    book = str(row.get("tuesday_spread_book"))
    price = _format_price(row.get("tuesday_spread_price"))
    spread = row.get("tuesday_spread_line", row.get("spread_line"))
    team_line = -float(spread) if recommended_team == row.get("home_team") else float(spread)
    return (
        "<div style='font-size:13px;color:#e8eaed;margin:0 0 6px 0'>"
        f"Best available for <b style='color:#fff'>{_html.escape(str(recommended_team))}</b>: "
        f"<span style='color:#fff;font-weight:800;font-size:15px'>{team_line:+.1f}</span>"
        f"<span style='color:#fff;font-weight:600'>&nbsp;({_html.escape(price)})</span>"
        f"<span style='color:#e8eaed'>&nbsp;at&nbsp;</span>"
        f"<span style='color:#fff;font-weight:700'>{_html.escape(book)}</span>"
        "</div>"
    )


def _sort_matchups_by_gap(frame: pd.DataFrame, edge_col: str) -> pd.DataFrame:
    """Order matchup cards from the largest absolute model gap to the smallest."""
    out = frame.copy()
    out["_gap_abs"] = pd.to_numeric(out[edge_col], errors="coerce").abs()
    sort_cols = ["_gap_abs"]
    ascending = [False]
    for column in ("gameday", "gametime", "game_id"):
        if column in out.columns:
            sort_cols.append(column)
            ascending.append(True)
    return out.sort_values(sort_cols, ascending=ascending, na_position="last", kind="mergesort").drop(
        columns="_gap_abs"
    )


def render():
    st.title("Weekly predictions")
    st.caption("NFL spread projections, Tuesday HIGH picks, and graded results.")
    try:
        df = dashboard_data.load_predictions()
    except FileNotFoundError:
        st.error("predictions_tracker.csv not found. Run the prediction pipeline first.")
        st.stop()
    except Exception as _load_err:
        st.error(f"Failed to load predictions data: {_load_err}")
        st.stop()
    if df.empty:
        st.warning("predictions_tracker.csv has no rows yet. Run the prediction pipeline to populate it.")
        st.stop()
    _calib = dashboard_data.load_calibration(df)
    totals_df = dashboard_data.load_totals()
    default_season, default_week = page_common.release_default_selection(
        "predictions", (2025, 10)
    )
    def _season_week_controls(cols_container, key_prefix, with_week=True, with_edge=False):
        return page_common._season_week_controls(
            df,
            cols_container,
            key_prefix,
            with_week,
            with_edge,
            default_week={2025: 10, 2026: 1, default_season: default_week},
            default_season=default_season,
        )
    st.markdown(page_common.ATS_BLURB, unsafe_allow_html=True)
    season, week, edge_threshold = _season_week_controls(
        st.columns(2), "wp", with_week=True, with_edge=False)
    release_state = page_common.render_release_status("predictions", int(season), int(week))
    live = is_live_season(season)
    if not live:
        edge_threshold = st.slider(
            "Min Edge (pts)", min_value=0.0, max_value=5.0, value=0.0, step=0.5,
            key="wp_edge",
            help="Only show games where model disagrees with spread by at least this many points",
        )
    if live:
        _live_notice()
        _live_model_context(release_state)
    else:
        _demo_2025_notice()

    week_df    = df[(df['season'] == season) & (df['week'] == week)].copy()
    results_in = week_df['actual_margin'].notna().any()
    _any_pick  = bool(len(week_df) and week_df.apply(has_pick, axis=1).any())

    if live:
        _totals_lookup = {}
    else:
        _totals_week = (
            totals_df[(totals_df['season'] == season) & (totals_df['week'] == week)]
            if not totals_df.empty else pd.DataFrame()
        )
        _totals_lookup = (
            _totals_week.set_index('game_id').to_dict('index')
            if not _totals_week.empty else {}
        )

    st.subheader(f"Week {week} · {season} season")

    _wk_correct_col = 'ens_model_correct' if ('ens_model_correct' in week_df.columns and week_df['ens_model_correct'].notna().any()) else 'model_correct'
    if live and not _any_pick:
        if int(week) == 1:
            st.info(
                "Matchups are locked and the Week 1 Tuesday market capture is recorded. "
                "The Week 1 card lands later this week."
            )
        else:
            st.info("Matchups are locked. Picks use the first valid Tuesday market capture from 09:00–15:30 ET.")
    elif results_in:
        correct = int(week_df[_wk_correct_col].sum())
        total   = int(week_df[_wk_correct_col].notna().sum())
        _n_settled = total
        _n_total   = len(week_df)
        _partial   = _n_settled < _n_total
        _banner_suffix = f" ({_n_settled} of {_n_total} games settled)" if _partial else ""
        if total > 0:
            st.success(
                f"{'Some results are in!' if _partial else 'Results are in!'} Week {week} ATS record: "
                f"**{correct}-{total - correct}** ({correct/total*100:.0f}%){_banner_suffix}"
            )
        else:
            st.info("Games not yet played. Check back after the week's results are in.")
    else:
        st.info("Games not yet played. Check back after the week's results are in.")

    if not week_df.empty and 'mode' in week_df.columns:
        _latest   = week_df.sort_values('logged_at')
        _latest   = _latest.iloc[-1]
        mode      = _latest['mode']
        logged_at = _latest['logged_at']
        if pd.isna(logged_at):
            logged_at = "not yet"
        mode_labels = {
            'monday':   ('🟡', 'Early Lines',       'Updated Monday with initial lines'),
            'thursday': ('🟠', 'Injury Reports In', 'Updated Thursday with injury data'),
            'sunday':   ('🟢', 'Final Predictions', 'Final update, games starting soon'),
            'backfill': ('🔵', 'Backfilled',        'Historical predictions'),
            'matchup':  ('⚪', 'Schedule',          'Matchups locked. Tuesday capture window 09:00–15:30 ET'),
        }
        _icon, label, desc = mode_labels.get(mode, ('⚪', 'Manual run', ''))
        _badge_colors = {
            'monday': 'yellow', 'thursday': 'orange', 'sunday': 'green',
            'backfill': 'blue', 'matchup': 'gray',
        }
        _badge_icons = {
            'monday': ':material/schedule:', 'thursday': ':material/medical_services:',
            'sunday': ':material/check_circle:', 'backfill': ':material/history:',
            'matchup': ':material/calendar_today:',
        }
        with st.container(horizontal=True, vertical_alignment="center"):
            st.badge(
                label,
                color=_badge_colors.get(mode, 'gray'),
                icon=_badge_icons.get(mode, ':material/info:'),
            )
            st.caption(f"{desc} · updated {logged_at}")

    st.divider()

    _primary_edge = 'ens_model_edge'       if ('ens_model_edge'       in week_df.columns and week_df['ens_model_edge'].notna().any())       else 'model_edge'
    if live and not week_df.empty:
        # The Tuesday median drives selection and the displayed model edge. The
        # independently shopped quote is rendered separately and used to grade.
        week_df['_qualifying_edge'] = week_df.apply(row_qualifying_edge, axis=1)
        week_df['_qualifying_line'] = week_df.apply(row_qualifying_spread, axis=1)
        if week_df['_qualifying_edge'].notna().any():
            _primary_edge = '_qualifying_edge'
    _pred_col     = 'ens_predicted_margin' if ('ens_predicted_margin' in week_df.columns and week_df['ens_predicted_margin'].notna().any()) else 'predicted_margin'
    _correct_col  = 'ens_model_correct'    if ('ens_model_correct'    in week_df.columns and week_df['ens_model_correct'].notna().any())    else 'model_correct'
    if live:
        filtered_df  = week_df.copy()
        hidden_count = 0
    else:
        filtered_df  = week_df[week_df[_primary_edge].abs() >= edge_threshold].copy()
        hidden_count = len(week_df) - len(filtered_df)

    with st.container(horizontal=True, key="jsa-metric-even-wp"):
        st.metric("Total games", len(week_df), border=True)
        if live:
            _n_high = int(week_df.apply(_public_high, axis=1).sum()) if not week_df.empty else 0
            st.metric(
                "HIGH picks", _n_high, f"{HIGH_GAP:g}+ points vs Tuesday",
                delta_color="green", delta_arrow="off", border=True,
            )
        else:
            st.metric(
                "Showing", len(filtered_df), f"Edge ≥ {edge_threshold} points",
                delta_color="gray", delta_arrow="off", border=True,
            )
        _avg_edge = week_df[_primary_edge].abs().mean()
        if pd.isna(_avg_edge):
            st.metric("Average ensemble edge", None, border=True)
        else:
            st.metric("Average ensemble edge", f"{_avg_edge:.1f} points", border=True)

        if results_in and len(filtered_df) > 0:
            _settled_mask = filtered_df[_correct_col].notna()
            sc  = int(filtered_df.loc[_settled_mask, _correct_col].sum())
            _n_settled_filt = _settled_mask.sum()
            pct = sc / _n_settled_filt * 100 if _n_settled_filt > 0 else 0
            st.metric(
                "ATS record", f"{sc}/{_n_settled_filt}", f"{pct:.0f}%",
                delta_color="green" if pct >= 52.4 else "red",
                delta_arrow="off", border=True,
            )
        else:
            st.metric("ATS record", "Pending", border=True)

    st.divider()

    cached          = load_agent_analysis(week, season)
    game_analysis   = cached.get('game_analysis',   {}) if cached else {}
    game_confidence = cached.get('game_confidence', {}) if cached else {}
    _show_agent     = (not live) and bool(cached and (game_analysis or game_confidence))

    if _show_agent:
        st.markdown("""
            <div class='jsa-legend' style='display:flex;gap:16px;align-items:center;margin-bottom:12px;flex-wrap:wrap;'>
                <span style='font-size:11px;color:#888;letter-spacing:1px;text-transform:uppercase;'>Agent Confidence:</span>
                <span style='font-size:12px;background:#1a3a1a;border:1px solid #00c853;
                            border-radius:4px;padding:2px 8px;color:#00c853;'>🟢 High</span>
                <span style='font-size:12px;background:#3a3a1a;border:1px solid #ffd600;
                            border-radius:4px;padding:2px 8px;color:#ffd600;'>🟡 Medium</span>
                <span style='font-size:12px;background:#3a1a1a;border:1px solid #ff5252;
                            border-radius:4px;padding:2px 8px;color:#ff5252;'>🔴 Skip</span>
            </div>
        """, unsafe_allow_html=True)

    _has_consensus_col = (not live) and 'consensus_tier' in week_df.columns and week_df['consensus_tier'].notna().any()
    if live:
        st.markdown(f"""
            <div class='jsa-legend' style='display:flex;gap:16px;align-items:center;margin-bottom:12px;flex-wrap:wrap;'>
                <span style='font-size:11px;color:#888;letter-spacing:1px;text-transform:uppercase;'>Tuesday HIGH</span>
                <span style='font-size:12px;background:#1a3a1a;border:1px solid #00c853;
                            border-radius:4px;padding:2px 8px;color:#00c853;'>HIGH</span>
                <span style='font-size:11px;color:#93A0B1;'>Green card = {HIGH_GAP:g}+ points vs the Tuesday US median, and the live line still {HIGH_GAP:g}+. TUESDAY LINE and the displayed edge use the median. Best available names the locked sportsbook quote used for grading. Every other game still shows a pick. No medium tier. A line move can drop HIGH. It cannot create HIGH.</span>
            </div>
        """, unsafe_allow_html=True)
    elif _has_consensus_col:
        st.markdown("""
            <div class='jsa-legend' style='display:flex;gap:16px;align-items:center;margin-bottom:12px;flex-wrap:wrap;'>
                <span style='font-size:11px;color:#888;letter-spacing:1px;text-transform:uppercase;'>Model Consensus:</span>
                <span style='font-size:12px;background:#1a3a1a;border:1px solid #00c853;
                            border-radius:4px;padding:2px 8px;color:#00c853;'>HIGH</span>
                <span style='font-size:12px;background:#3a3a1a;border:1px solid #ffd600;
                            border-radius:4px;padding:2px 8px;color:#ffd600;'>MED</span>
                <span style='font-size:12px;background:#3a1a1a;border:1px solid #ff5252;
                            border-radius:4px;padding:2px 8px;color:#ff5252;'>PASS</span>
                <span style='font-size:11px;color:#93A0B1;'>All 3 models agree direction · Ensemble edge ≥3 pts = HIGH, ≥1 pt = MED</span>
            </div>
        """, unsafe_allow_html=True)

        # One honest line per tab: how each tier has actually covered historically, with a
        # Wilson CI so a thin live sample doesn't read as a guarantee (betting/calibration.py).
        if _calib.get("n_graded"):
            _bt = _calib["by_tier"]
            _parts = []
            for _t, _lbl in (("HIGH", "HIGH"), ("MEDIUM", "MED"), ("PASS", "PASS")):
                _e = _bt.get(_t)
                if _e and _e.n:
                    _parts.append(
                        f"<b style='color:#bbb'>{_lbl}</b> {_e.rate*100:.1f}% "
                        f"<span style='color:#667'>(CI {_e.lo*100:.0f}–{_e.hi*100:.0f}%, n={_e.n})</span>"
                    )
            if _parts:
                st.markdown(
                    f"<div class='jsa-calib' style='font-size:11px;color:#8a93a0;margin:-4px 0 12px 0;'>"
                    f"📊 Historical cover rate ({_calib['n_graded']} graded bets): "
                    + " &nbsp;·&nbsp; ".join(_parts)
                    + " &nbsp;·&nbsp; <span style='color:#667'>break-even 52.4%</span></div>",
                    unsafe_allow_html=True,
                )

    st.subheader("Game Predictions")

    if week_df.empty:
        st.warning("No predictions found for this week.")
    elif filtered_df.empty:
        st.warning(
            f"No games meet the current edge threshold of ±{edge_threshold} pts. "
            f"Lower the slider to see all {len(week_df)} games."
        )
    else:
        if hidden_count > 0:
            st.caption(
                f"Showing {len(filtered_df)} of {len(week_df)} games "
                f"— {hidden_count} filtered out (edge < {edge_threshold} pts). "
                f"Lower the slider to see all games."
            )

        if live:
            filtered_df = filtered_df.copy()
            filtered_df = _sort_matchups_by_gap(filtered_df, _primary_edge)
        else:
            filtered_df = _sort_matchups_by_gap(filtered_df, _primary_edge)

        def fmt(val):
            if val is None or pd.isna(val):
                return "—"
            return f"{val:+.1f}"

        def name_style(is_rec):
            weight = "700" if is_rec else "400"
            color  = "white" if is_rec else "#aaa"
            return weight, color

        # The jsa-gc-* classes are inert on desktop. mobile.py keys on them to keep each
        # game card as a real row on a phone — st.columns stacks below 640px, which
        # otherwise orphaned the SPREAD / PREDICTED / SCORE headers from their values.
        def stat_box(val, is_rec=False, is_result=False):
            bg    = "#1a3a2a" if is_rec else "#1e2a3a"
            color = "#00c853" if is_rec else "white"
            return (
                f"<div class='jsa-gc-stat' style='text-align:center;background:{bg};"
                f"border-radius:6px;"
                f"padding:6px 0;font-size:14px;font-weight:600;color:{color};"
                f"height:32px;line-height:20px'>{val}</div>"
            )

        def bet_box(team, color="#3D95CE"):
            return (
                f"<div class='jsa-gc-bet jsa-gc-pick' style='background:{color}22;border:1.5px solid {color};"
                f"border-radius:6px;padding:0 10px;font-size:13px;font-weight:800;"
                f"color:{color};text-align:center;height:32px;line-height:32px;"
                f"letter-spacing:0.5px'>▶ {team}</div>"
            )

        def empty_box():
            return "<div class='jsa-gc-pick' style='height:32px'></div>"

        for _gc_i, (_, row) in enumerate(filtered_df.iterrows()):
            home      = row['home_team']
            away      = row['away_team']
            spread    = row['_qualifying_line'] if (live and pd.notna(row.get('_qualifying_line'))) else row['spread_line']
            predicted = row[_pred_col]
            edge      = row[_primary_edge]
            tier      = str(row['consensus_tier']) if _has_consensus_col and pd.notna(row.get('consensus_tier')) else ''

            top_team      = home
            bot_team      = away
            top_spread    = fmt(-spread)
            bot_spread    = fmt(spread)
            # Display predictions in sportsbook style (favorite shows negative, underdog positive)
            # to match how the SPREAD column is displayed. Internally `predicted` is the model's
            # home_margin estimate (positive = home wins), so we negate for the home team's display
            # and pass through for the away team.
            top_predicted = fmt(-predicted)
            bot_predicted = fmt(predicted)

            if pd.isna(edge) or edge == 0:
                rec_team  = None
                rec_color = "#888888"
            elif edge > 0:
                rec_team  = home
                rec_color = "#00c853"
            else:
                rec_team  = away
                rec_color = "#2979ff"

            top_is_rec = rec_team == top_team
            bot_is_rec = rec_team == bot_team

            results_available = results_in and pd.notna(row['actual_margin'])
            _row_correct      = (row[_correct_col] == 1) if results_available else False
            actual            = row['actual_margin'] if results_available else None

            if results_available:
                home_score = row.get('home_score', None)
                away_score = row.get('away_score', None)
                has_scores = pd.notna(home_score) and pd.notna(away_score)
                if has_scores:
                    top_score = f"{int(home_score)}"
                    bot_score = f"{int(away_score)}"
                else:
                    top_score = fmt(actual)
                    bot_score = fmt(-actual)
            else:
                top_score = "—"
                bot_score = "—"

            result_label = ("✅ WIN" if _row_correct else "❌ LOSS") if results_available else ""

            if live:
                is_high = bool(_public_high(row))
                dropped = bool(row_high_dropped(row))
                if is_high:
                    tier_html = "&nbsp;&nbsp;<span style='background:#1a3a1a;border:1px solid #00c853;border-radius:4px;padding:1px 6px;font-size:11px;color:#00c853;font-weight:700'>HIGH PICK</span>"
                elif dropped:
                    tier_html = "&nbsp;&nbsp;<span style='background:#3a2a12;border:1px solid #ff9800;border-radius:4px;padding:1px 6px;font-size:11px;color:#ff9800'>LINE MOVED · no longer HIGH</span>"
                    is_high = False
                elif has_pick(row):
                    tier_html = ""
                    is_high = False
                else:
                    tier_html = "&nbsp;&nbsp;<span style='background:#1e1e1e;border:1px solid #666;border-radius:4px;padding:1px 6px;font-size:11px;color:#aaa'>MATCHUP</span>"
                    is_high = False
            elif tier == 'HIGH':
                is_high = True
                tier_html = "&nbsp;&nbsp;<span style='background:#1a3a1a;border:1px solid #00c853;border-radius:4px;padding:1px 6px;font-size:11px;color:#00c853'>HIGH</span>"
            elif tier == 'MEDIUM':
                is_high = False
                tier_html = "&nbsp;&nbsp;<span style='background:#3a3a1a;border:1px solid #ffd600;border-radius:4px;padding:1px 6px;font-size:11px;color:#ffd600'>MED</span>"
            elif tier == 'PASS':
                is_high = False
                tier_html = "&nbsp;&nbsp;<span style='background:#3a1a1a;border:1px solid #ff4444;border-radius:4px;padding:1px 6px;font-size:11px;color:#ff4444'>PASS</span>"
            else:
                is_high = False
                tier_html = ''

            # Column layout is decided per WEEK (results_in), not per game, so a game that
            # has not kicked off yet keeps the same SCORE column (showing a dash) as its
            # finished neighbours instead of collapsing to the narrower 4-column grid.
            _gc_meta = "jsa-gc-meta jsa-gc-scored" if results_in else "jsa-gc-meta"
            if is_high:
                _gc_meta += " jsa-gc-high"
            _meta_box = (
                "background:#0c1a12;border:1.5px solid #00c853;border-radius:8px;padding:8px 10px;"
                if is_high else ""
            )
            with st.container(key=f"jsa-gc-{_gc_i}"):
                st.markdown(
                    f"<div class='{_gc_meta}' style='font-size:13px;color:#888;margin-bottom:6px;{_meta_box}'>"
                    f"<b style='color:#ccc'>{_html.escape(str(away))} @ {_html.escape(str(home))}</b>"
                    f"&nbsp;&nbsp;·&nbsp;&nbsp;{_html.escape(str(row['gameday']))}"
                    f"{tier_html}"
                    f"{'&nbsp;&nbsp;·&nbsp;&nbsp;<b>' + result_label + '</b>' if result_label else ''}"
                    f"</div>",
                    unsafe_allow_html=True
                )

                if live:
                    _quote_html = _best_quote_html(row, rec_team)
                    if _quote_html:
                        st.markdown(_quote_html, unsafe_allow_html=True)

                if results_in:
                    h0, h1, h2, h3, h4 = st.columns([2.2, 1.2, 1.2, 1.2, 1.8])
                    h3.markdown("<div class='jsa-gc-hdr' style='text-align:center;font-size:11px;color:#aaa;letter-spacing:1px'>SCORE</div>", unsafe_allow_html=True)
                else:
                    h0, h1, h2, h4 = st.columns([2.2, 1.2, 1.2, 1.8])

                _spread_header = "TUESDAY LINE" if live else "SPREAD"
                h1.markdown(f"<div class='jsa-gc-hdr' style='text-align:center;font-size:11px;color:#aaa;letter-spacing:1px'>{_spread_header}</div>", unsafe_allow_html=True)
                h2.markdown("<div class='jsa-gc-hdr' style='text-align:center;font-size:11px;color:#aaa;letter-spacing:1px'>PREDICTED</div>", unsafe_allow_html=True)
                h4.markdown("<div class='jsa-gc-hdr jsa-gc-pick'></div>", unsafe_allow_html=True)

                if results_in:
                    a0, a1, a2, a3, a4 = st.columns([2.2, 1.2, 1.2, 1.2, 1.8])
                    a3.markdown(stat_box(top_score, is_result=True), unsafe_allow_html=True)
                else:
                    a0, a1, a2, a4 = st.columns([2.2, 1.2, 1.2, 1.8])

                top_w, top_c = name_style(top_is_rec)
                a0.markdown(
                    f"<div class='jsa-gc-team' style='font-weight:{top_w};font-size:15px;color:{top_c};"
                    f"padding-top:6px;height:32px'>{top_team}</div>",
                    unsafe_allow_html=True
                )
                a1.markdown(stat_box(top_spread),                       unsafe_allow_html=True)
                a2.markdown(stat_box(top_predicted, is_rec=top_is_rec), unsafe_allow_html=True)
                a4.markdown(bet_box(top_team, rec_color) if top_is_rec else empty_box(), unsafe_allow_html=True)

                st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

                if results_in:
                    b0, b1, b2, b3, b4 = st.columns([2.2, 1.2, 1.2, 1.2, 1.8])
                    b3.markdown(stat_box(bot_score, is_result=True), unsafe_allow_html=True)
                else:
                    b0, b1, b2, b4 = st.columns([2.2, 1.2, 1.2, 1.8])

                bot_w, bot_c = name_style(bot_is_rec)
                b0.markdown(
                    f"<div class='jsa-gc-team' style='font-weight:{bot_w};font-size:15px;color:{bot_c};"
                    f"padding-top:6px;height:32px'>{bot_team}</div>",
                    unsafe_allow_html=True
                )
                b1.markdown(stat_box(bot_spread),                       unsafe_allow_html=True)
                b2.markdown(stat_box(bot_predicted, is_rec=bot_is_rec), unsafe_allow_html=True)
                b4.markdown(bet_box(bot_team, rec_color) if bot_is_rec else empty_box(), unsafe_allow_html=True)

                if _show_agent:
                    game_key  = f"{home}_{away}"
                    game_text = game_analysis.get(game_key, None)

                    if game_text:
                        if '🟢' in game_text:
                            btn_color = "#00c853"
                            btn_bg    = "#1a3a1a"
                            btn_label = "🟢 Matchup Analysis"
                        elif '🟡' in game_text:
                            btn_color = "#ffd600"
                            btn_bg    = "#3a3a1a"
                            btn_label = "🟡 Matchup Analysis"
                        elif '🔴' in game_text or 'SKIP' in game_text.upper() or 'PASS' in game_text.upper():
                            btn_color = "#ff5252"
                            btn_bg    = "#3a1a1a"
                            btn_label = "🔴 Matchup Analysis"
                        else:
                            btn_color = "#ff5252"
                            btn_bg    = "#3a1a1a"
                            btn_label = "🔴 Matchup Analysis"
                    else:
                        btn_color = "#aaaaaa"
                        btn_bg    = "#1e1e1e"
                        btn_label = "⚪ Matchup Analysis"

                    content_html = (
                        _md_to_html(game_text) if game_text
                        else "<em style='color:#888'>No analysis yet. Run the notebook to generate.</em>"
                    )

                    col_btn, _ = st.columns([1, 3])
                    with col_btn:
                        st.markdown(
                            f"<details style='--conf-color:{btn_color};"
                            f"--conf-bg:{btn_bg};--conf-border:{btn_color}'>"
                            f"<summary>{btn_label}</summary>"
                            f"<div>{content_html}</div>"
                            f"</details>",
                            unsafe_allow_html=True
                        )

                # ── Totals badge (below matchup analysis). 2026 live has no totals. ──
                if live:
                    _tot_row = None
                else:
                    _tot_row = _totals_lookup.get(row.get('game_id'))
                if _tot_row and _tot_row.get('consensus_tier') == 'HIGH':
                    # Coerce defensively — a corrupted/hand-edited CSV could carry strings.
                    _xgb_tot  = pd.to_numeric(_tot_row.get('xgb_predicted_total'), errors='coerce')
                    _rid_tot  = pd.to_numeric(_tot_row.get('ridge_predicted_total'), errors='coerce')
                    _tot_line = _tot_row.get('total_line', '')
                    _at       = pd.to_numeric(_tot_row.get('actual_total'), errors='coerce')
                    _mc       = _tot_row.get('model_correct')
                    _avg_pred = round((_xgb_tot + _rid_tot) / 2, 1) if pd.notna(_xgb_tot) and pd.notna(_rid_tot) else ''
                    if pd.notna(_at):
                        _result_icon = "✅" if _mc == 1.0 else "❌"
                        _tot_result = f"&nbsp;&nbsp;{_result_icon}&nbsp;Actual: {int(_at)}"
                    else:
                        _tot_result = ""
                    st.markdown(
                        f"<div class='jsa-tot-badge' style='background:#1f1a0e;border:1px dashed #b88a1c;"
                        f"border-radius:6px;"
                        f"padding:6px 12px;margin:14px 0 4px 0;font-size:13px;"
                        f"display:flex;align-items:center;gap:10px'>"
                        f"<span style='background:#b88a1c22;border:1px solid #b88a1c;border-radius:4px;"
                        f"padding:1px 7px;font-size:10px;color:#e0a93a;font-weight:700;"
                        f"letter-spacing:0.5px'>EXPERIMENTAL</span>"
                        f"&nbsp;<span style='color:#e0a93a;font-weight:700'>UNDER {_tot_line}</span>"
                        f"&nbsp;&nbsp;<span style='color:#888'>Model avg:</span>&nbsp;"
                        f"<span style='color:#ccc;font-weight:600'>{_avg_pred}</span>"
                        f"<span style='color:#888'>{_tot_result}</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

                st.divider()

    # ── Agent vs Model Evaluation ─────────────────────────────────────────────
    if (not live) and _show_agent and game_analysis:
        st.divider()
        st.subheader(f"📊 Week {week}: Agent vs Model")

        week_df_eval = week_df.copy()
        week_df_eval['agent_confidence'] = week_df_eval.apply(
            lambda r: get_confidence(r['home_team'], r['away_team'], game_analysis, game_confidence), axis=1
        )

        if results_in:
            _eval_settled = week_df_eval[_correct_col].notna()
            model_correct = int(week_df_eval.loc[_eval_settled, _correct_col].sum())
            model_total   = int(_eval_settled.sum())
            model_pct     = round(model_correct / model_total * 100, 1) if model_total > 0 else 0

            high_df      = week_df_eval[week_df_eval['agent_confidence'] == 'HIGH']
            high_correct = int(high_df[_correct_col].fillna(0).sum())
            high_total   = int(high_df[_correct_col].notna().sum())
            high_pct     = round(high_correct / high_total * 100, 1) if high_total > 0 else 0

            med_df      = week_df_eval[week_df_eval['agent_confidence'] == 'MEDIUM']
            med_correct = int(med_df[_correct_col].fillna(0).sum())
            med_total   = int(med_df[_correct_col].notna().sum())
            med_pct     = round(med_correct / med_total * 100, 1) if med_total > 0 else 0

            bet_df      = week_df_eval[week_df_eval['agent_confidence'].isin(['HIGH', 'MEDIUM'])]
            bet_correct = int(bet_df[_correct_col].fillna(0).sum())
            bet_total   = int(bet_df[_correct_col].notna().sum())
            bet_pct     = round(bet_correct / bet_total * 100, 1) if bet_total > 0 else 0

            skip_df      = week_df_eval[week_df_eval['agent_confidence'].isin(['PASS', 'SKIP'])]
            skip_correct = int(skip_df[_correct_col].fillna(0).sum())
            skip_total   = int(skip_df[_correct_col].notna().sum())
            skip_pct     = round(skip_correct / skip_total * 100, 1) if skip_total > 0 else 0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("📈 Model (all games)",  f"{model_correct}/{model_total}", f"{model_pct}%")
            c2.metric("🟢 Agent HIGH only",    f"{high_correct}/{high_total}",   f"{high_pct}%")
            c3.metric("🟡 Agent HIGH+MED",     f"{bet_correct}/{bet_total}",     f"{bet_pct}%")
            c4.metric("🔴 PASS games",         f"{skip_correct}/{skip_total}",   f"{skip_pct}%",
                      help="Lower % here = agent correctly identified games to avoid")

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            if skip_total > 0:
                # Correct comparison: agent bet picks vs model all-in
                if bet_pct > model_pct:
                    improvement = round(bet_pct - model_pct, 1)
                    st.success(
                        f"✅ Betting only agent HIGH+MED picks improved accuracy by **{improvement}%** — "
                        f"agent picks went {bet_pct}% ({bet_correct}/{bet_total}) vs model's {model_pct}% ({model_correct}/{model_total}) on all games"
                    )
                elif bet_pct == model_pct:
                    st.info(
                        f"➡️ Agent picks matched model accuracy — both went {model_pct}%"
                    )
                else:
                    decline = round(model_pct - bet_pct, 1)
                    st.warning(
                        f"⚠️ Agent picks underperformed by {decline}% — "
                        f"agent picks went {bet_pct}% ({bet_correct}/{bet_total}) vs model's {model_pct}% ({model_correct}/{model_total}) on all games"
                )
        else:
            st.info("Results not yet available for this week. Check back after games are played.")
