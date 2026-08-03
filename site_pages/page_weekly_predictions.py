"""Weekly Predictions page (site revamp Batch 3b). Tab1 body moved byte-identical
from app.py; shared stats/helpers come from dashboard_data / page_common. Its own
Season/Week/Min-edge controls (filter independence) are preserved. The ATS blurb
moved here from the retired sidebar. Stale "tab" wording is verbatim (later sweep).
"""
import glob
import html as _html
import itertools as _it
import json
import os
from datetime import date
from datetime import datetime as dt

import pandas as pd
import streamlit as st

import dashboard_data
import nav_registry
import page_common
from dashboard_utils import metric_card, get_confidence, _md_to_html
from page_common import load_agent_analysis, _MODE_BADGE_COLORS
from seasonal_config import board_refresh_season_start


def _preseason():
    """True until 2026 kickoff (env-overridable, same source as the board)."""
    return date.today() < board_refresh_season_start()


def _demo_notice():
    """Pre-season demo banner: this page shows past games until Week 1, and points
    visitors to the live Draft Board. Auto-hides once the season starts."""
    st.info(
        "👋 **Heads up — Weekly Predictions is a demo until the 2026 season kicks "
        "off.** The games below are from 2025, shown so you can see how the model "
        "works; live 2026 predictions start at Week 1. In the meantime, take a look "
        "around the top nav — my **2026 Draft Board is live and in production**, "
        "refreshing daily from the latest draft data.")
    board = nav_registry.PAGES.get("draft-board")
    if board is not None:
        st.page_link(board, label="Open the Draft Board", icon="📋")


def render():
    if _preseason():
        _demo_notice()
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
    def _season_week_controls(cols_container, key_prefix, with_week=True, with_edge=False):
        return page_common._season_week_controls(df, cols_container, key_prefix, with_week, with_edge)
    st.markdown(page_common.ATS_BLURB, unsafe_allow_html=True)
    season, week, edge_threshold = _season_week_controls(
        st.columns(3), "wp", with_week=True, with_edge=True)

    week_df    = df[(df['season'] == season) & (df['week'] == week)].copy()
    results_in = week_df['actual_margin'].notna().any()

    # Build a quick lookup: game_id → totals row (HIGH picks only)
    _totals_week = (
        totals_df[(totals_df['season'] == season) & (totals_df['week'] == week)]
        if not totals_df.empty else pd.DataFrame()
    )
    _totals_lookup = (
        _totals_week.set_index('game_id').to_dict('index')
        if not _totals_week.empty else {}
    )

    st.title(f"🏈 Week {week} Predictions: {season} Season")

    _wk_correct_col = 'ens_model_correct' if ('ens_model_correct' in week_df.columns and week_df['ens_model_correct'].notna().any()) else 'model_correct'
    if results_in:
        correct = int(week_df[_wk_correct_col].sum())
        total   = int(week_df[_wk_correct_col].notna().sum())
        _n_settled = total
        _n_total   = len(week_df)
        _partial   = _n_settled < _n_total
        _banner_suffix = f" ({_n_settled} of {_n_total} games settled)" if _partial else ""
        st.success(
            f"{'Some results are in!' if _partial else 'Results are in!'} Week {week} ATS record: "
            f"**{correct}-{total - correct}** ({correct/total*100:.0f}%){_banner_suffix}"
        )
    else:
        st.info("Games not yet played. Check back after the week's results are in.")

    if not week_df.empty and 'mode' in week_df.columns:
        _latest   = week_df.sort_values('logged_at').iloc[-1]
        mode      = _latest['mode']
        logged_at = _latest['logged_at']
        mode_labels = {
            'monday':   ('🟡', 'Early Lines',       'Updated Monday with initial lines'),
            'thursday': ('🟠', 'Injury Reports In', 'Updated Thursday with injury data'),
            'sunday':   ('🟢', 'Final Predictions', 'Final update — games starting soon'),
            'backfill': ('🔵', 'Backfilled',        'Historical predictions'),
        }
        icon, label, desc = mode_labels.get(mode, ('⚪', 'Manual Run', ''))
        _badge_color = _MODE_BADGE_COLORS.get(mode, '#888')
        st.markdown(
            f"<span style='background:{_badge_color}22;border:1px solid {_badge_color};"
            f"border-radius:20px;padding:3px 12px;font-size:12px;font-weight:600;"
            f"color:{_badge_color}'>{icon} {label}</span>"
            f"<span style='font-size:12px;color:#666;margin-left:10px'>{desc} · updated {logged_at}</span>",
            unsafe_allow_html=True
        )

    st.divider()
    col1, col2, col3, col4 = st.columns(4)

    _primary_edge = 'ens_model_edge'       if ('ens_model_edge'       in week_df.columns and week_df['ens_model_edge'].notna().any())       else 'model_edge'
    _pred_col     = 'ens_predicted_margin' if ('ens_predicted_margin' in week_df.columns and week_df['ens_predicted_margin'].notna().any()) else 'predicted_margin'
    _correct_col  = 'ens_model_correct'    if ('ens_model_correct'    in week_df.columns and week_df['ens_model_correct'].notna().any())    else 'model_correct'
    filtered_df  = week_df[week_df[_primary_edge].abs() >= edge_threshold].copy()
    hidden_count = len(week_df) - len(filtered_df)

    col1.markdown(metric_card("Total Games", len(week_df)), unsafe_allow_html=True)
    col2.markdown(metric_card("Showing", len(filtered_df), f"edge ≥ {edge_threshold} pts"), unsafe_allow_html=True)
    _avg_edge = week_df[_primary_edge].abs().mean()
    col3.markdown(metric_card("Avg Ensemble Edge", f"{_avg_edge:.1f} pts",
                              color="green" if _avg_edge >= 1.5 else "blue"), unsafe_allow_html=True)

    if results_in and len(filtered_df) > 0:
        _settled_mask = filtered_df[_correct_col].notna()
        sc  = int(filtered_df.loc[_settled_mask, _correct_col].sum())
        _n_settled_filt = _settled_mask.sum()
        pct = sc / _n_settled_filt * 100 if _n_settled_filt > 0 else 0
        col4.markdown(metric_card("ATS Record", f"{sc}/{_n_settled_filt}",
                                  f"{pct:.0f}%",
                                  color="green" if pct >= 52.4 else "red"), unsafe_allow_html=True)
    else:
        col4.markdown(metric_card("ATS Record", "Pending"), unsafe_allow_html=True)

    st.divider()

    cached          = load_agent_analysis(week, season)
    game_analysis   = cached.get('game_analysis',   {}) if cached else {}
    game_confidence = cached.get('game_confidence', {}) if cached else {}

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

    _has_consensus_col = 'consensus_tier' in week_df.columns and week_df['consensus_tier'].notna().any()
    if _has_consensus_col:
        st.markdown("""
            <div class='jsa-legend' style='display:flex;gap:16px;align-items:center;margin-bottom:12px;flex-wrap:wrap;'>
                <span style='font-size:11px;color:#888;letter-spacing:1px;text-transform:uppercase;'>Model Consensus:</span>
                <span style='font-size:12px;background:#1a3a1a;border:1px solid #00c853;
                            border-radius:4px;padding:2px 8px;color:#00c853;'>HIGH</span>
                <span style='font-size:12px;background:#3a3a1a;border:1px solid #ffd600;
                            border-radius:4px;padding:2px 8px;color:#ffd600;'>MED</span>
                <span style='font-size:12px;background:#3a1a1a;border:1px solid #ff5252;
                            border-radius:4px;padding:2px 8px;color:#ff5252;'>PASS</span>
                <span style='font-size:11px;color:#555;'>All 3 models agree direction · Ensemble edge ≥3 pts = HIGH, ≥1 pt = MED</span>
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

        filtered_df = filtered_df.sort_values(_primary_edge, key=abs, ascending=False)

        def fmt(val):
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
                f"<div class='jsa-gc-bet' style='background:{color}22;border:1.5px solid {color};"
                f"border-radius:6px;padding:0 10px;font-size:13px;font-weight:800;"
                f"color:{color};text-align:center;height:32px;line-height:32px;"
                f"letter-spacing:0.5px'>▶ {team}</div>"
            )

        def empty_box():
            return "<div style='height:32px'></div>"

        for _, row in filtered_df.iterrows():
            home      = row['home_team']
            away      = row['away_team']
            spread    = row['spread_line']
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

            if edge > 0:
                rec_team  = home
                rec_color = "#00c853"
            elif edge < 0:
                rec_team  = away
                rec_color = "#2979ff"
            else:
                rec_team  = None
                rec_color = "#888888"

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

            if tier == 'HIGH':
                tier_html = "&nbsp;&nbsp;<span style='background:#1a3a1a;border:1px solid #00c853;border-radius:4px;padding:1px 6px;font-size:11px;color:#00c853'>HIGH</span>"
            elif tier == 'MEDIUM':
                tier_html = "&nbsp;&nbsp;<span style='background:#3a3a1a;border:1px solid #ffd600;border-radius:4px;padding:1px 6px;font-size:11px;color:#ffd600'>MED</span>"
            elif tier == 'PASS':
                tier_html = "&nbsp;&nbsp;<span style='background:#3a1a1a;border:1px solid #ff4444;border-radius:4px;padding:1px 6px;font-size:11px;color:#ff4444'>PASS</span>"
            else:
                tier_html = ''

            with st.container():
                st.markdown(
                    f"<div class='jsa-gc-meta' style='font-size:13px;color:#888;margin-bottom:6px'>"
                    f"<b style='color:#ccc'>{_html.escape(str(away))} @ {_html.escape(str(home))}</b>"
                    f"&nbsp;&nbsp;·&nbsp;&nbsp;{_html.escape(str(row['gameday']))}"
                    f"{tier_html}"
                    f"{'&nbsp;&nbsp;·&nbsp;&nbsp;<b>' + result_label + '</b>' if result_label else ''}"
                    f"</div>",
                    unsafe_allow_html=True
                )

                if results_available:
                    h0, h1, h2, h3, h4 = st.columns([2.2, 1.2, 1.2, 1.2, 1.8])
                    h3.markdown("<div class='jsa-gc-hdr' style='text-align:center;font-size:11px;color:#aaa;letter-spacing:1px'>SCORE</div>", unsafe_allow_html=True)
                else:
                    h0, h1, h2, h4 = st.columns([2.2, 1.2, 1.2, 1.8])

                h1.markdown("<div class='jsa-gc-hdr' style='text-align:center;font-size:11px;color:#aaa;letter-spacing:1px'>SPREAD</div>",    unsafe_allow_html=True)
                h2.markdown("<div class='jsa-gc-hdr' style='text-align:center;font-size:11px;color:#aaa;letter-spacing:1px'>PREDICTED</div>", unsafe_allow_html=True)

                if results_available:
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

                if results_available:
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

                game_key  = f"{home}_{away}"
                game_text = game_analysis.get(game_key, None)

                # Determine confidence color
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

                # ── Totals badge (below matchup analysis) ────────────────────────────
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
    if cached and game_analysis:
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

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: SEASON PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════
