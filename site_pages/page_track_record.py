"""Track Record page (site revamp Batch 3b). Tab2 body moved byte-identical from
app.py; shared data/helpers from dashboard_data / page_common; own Season control
(filter independence) preserved. ATS blurb moved here from the retired sidebar.
"""
import glob
import html as _html
import itertools as _it
import json
import os
from datetime import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

import dashboard_data
import page_common
from dashboard_utils import get_confidence, _md_to_html
from live_2026 import HIGH_GAP, is_live_season, row_display_high
from page_common import load_agent_analysis, _MODE_BADGE_COLORS

_HERE = Path(__file__).resolve().parents[1]


def render():
    st.title("Track record")
    st.caption("Graded ATS results, confidence tiers, model comparisons, and betting simulations.")
    # Plotly is only needed for this page's charts. Keeping it here avoids paying its
    # import cost when a visitor opens a different top-level navigation page.
    import plotly.graph_objects as go

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
    totals_df = dashboard_data.load_totals()
    def _season_week_controls(cols_container, key_prefix, with_week=True, with_edge=False):
        return page_common._season_week_controls(
            df,
            cols_container,
            key_prefix,
            with_week,
            with_edge,
            default_season=page_common.track_record_default_season(),
        )
    st.markdown(page_common.ATS_BLURB, unsafe_allow_html=True)
    season, _, _ = _season_week_controls(
        [st.columns([1, 2])[0]], "tr", with_week=False, with_edge=False)
    live = is_live_season(season)

    st.subheader(f"{season} season")
    if live:
        st.success(
            "**Live 2026.** Track Record fills in after games grade. "
            "HIGH is the only confidence tier. No medium. No totals on this season."
        )
    else:
        st.info(
            "**Demo test.** 2025 weeks 10 through the end of the season are the old "
            "three-model consensus, left unchanged."
        )
    season_df = df[
        (df['season'] == season) &
        (df['actual_margin'].notna())
    ].copy()

    if season_df.empty:
        if live:
            st.info("No graded 2026 games yet. Weekly Predictions has the full-season matchups.")
        else:
            st.warning("No completed games found for this season.")
    else:

        # ── Season summary metrics ────────────────────────────────────
        _s_edge    = 'ens_model_edge'    if ('ens_model_edge'    in season_df.columns and season_df['ens_model_edge'].notna().any())    else 'model_edge'
        _s_correct = 'ens_model_correct' if ('ens_model_correct' in season_df.columns and season_df['ens_model_correct'].notna().any()) else 'model_correct'

        total_correct = int(season_df[_s_correct].sum())
        total_games   = int(season_df[_s_correct].notna().sum())
        total_pct     = round(total_correct / total_games * 100, 1) if total_games > 0 else 0

        if live:
            _high_mask = season_df.apply(row_display_high, axis=1)
            high_edge_df = season_df[_high_mask]
            he_correct = int(high_edge_df[_s_correct].sum())
            he_total = int(high_edge_df[_s_correct].notna().sum())
            he_pct = round(he_correct / he_total * 100, 1) if he_total > 0 else 0
            rest_df = season_df[~_high_mask]
            re_correct = int(rest_df[_s_correct].sum())
            re_total = int(rest_df[_s_correct].notna().sum())
            re_pct = round(re_correct / re_total * 100, 1) if re_total > 0 else 0
            me_correct = me_total = me_pct = 0
            le_correct = le_total = le_pct = 0
        else:
            high_edge_df  = season_df[season_df[_s_edge].abs() >= 3]
            he_correct    = int(high_edge_df[_s_correct].sum())
            he_total      = int(high_edge_df[_s_correct].notna().sum())
            he_pct        = round(he_correct / he_total * 100, 1) if he_total > 0 else 0

            med_edge_df   = season_df[(season_df[_s_edge].abs() >= 1) & (season_df[_s_edge].abs() < 3)]
            me_correct    = int(med_edge_df[_s_correct].sum())
            me_total      = int(med_edge_df[_s_correct].notna().sum())
            me_pct        = round(me_correct / me_total * 100, 1) if me_total > 0 else 0

            low_edge_df   = season_df[season_df[_s_edge].abs() < 1]
            le_correct    = int(low_edge_df[_s_correct].sum())
            le_total      = int(low_edge_df[_s_correct].notna().sum())
            le_pct        = round(le_correct / le_total * 100, 1) if le_total > 0 else 0

        def _record_metric(label, correct, total, pct):
            st.metric(
                label,
                f"{correct}/{total}",
                f"{pct}%" if total > 0 else "No graded picks",
                delta_color=("green" if pct >= 52.4 else "red") if total > 0 else "gray",
                delta_arrow="off",
                border=True,
            )

        with st.container(horizontal=True, key="jsa-metric-even-tr-ats"):
            if live:
                _record_metric("Season ATS", total_correct, total_games, total_pct)
                _record_metric(f"HIGH (Tuesday {HIGH_GAP:g}+ points)", he_correct, he_total, he_pct)
                _record_metric("Other picks", re_correct, re_total, re_pct)
            else:
                _record_metric("Season ATS", total_correct, total_games, total_pct)
                _record_metric("High edge (3+ points)", he_correct, he_total, he_pct)
                _record_metric("Medium edge (1–3 points)", me_correct, me_total, me_pct)
                _record_metric("Low edge (<1 point)", le_correct, le_total, le_pct)

        _has_ens   = 'ens_model_correct'   in season_df.columns and season_df['ens_model_correct'].notna().any()
        _has_ridge = 'ridge_model_correct' in season_df.columns and season_df['ridge_model_correct'].notna().any()
        _has_lgbm  = 'lgbm_model_correct'  in season_df.columns and season_df['lgbm_model_correct'].notna().any()
        _has_ct    = 'consensus_tier'      in season_df.columns and season_df['consensus_tier'].notna().any()

        _has_xgb  = 'model_correct' in season_df.columns and season_df['model_correct'].notna().any()

        if _has_ens or _has_ridge or _has_lgbm or _has_xgb:
            st.caption("Individual model ATS (direction voters)")
            with st.container(horizontal=True, key="jsa-metric-even-tr-models"):
                if _has_xgb:
                    _xgb_sub = season_df[season_df['model_correct'].notna()]
                    _xgb_c   = int(_xgb_sub['model_correct'].sum())
                    _xgb_t   = len(_xgb_sub)
                    _xgb_pct = round(_xgb_c / _xgb_t * 100, 1) if _xgb_t > 0 else 0
                    _record_metric("XGBoost ATS", _xgb_c, _xgb_t, _xgb_pct)
                if _has_ridge:
                    _ridge_sub = season_df[season_df['ridge_model_correct'].notna()]
                    _ridge_c   = int(_ridge_sub['ridge_model_correct'].sum())
                    _ridge_t   = len(_ridge_sub)
                    _ridge_pct = round(_ridge_c / _ridge_t * 100, 1) if _ridge_t > 0 else 0
                    _record_metric("Ridge ATS", _ridge_c, _ridge_t, _ridge_pct)
                if _has_lgbm:
                    _lgbm_sub = season_df[season_df['lgbm_model_correct'].notna()]
                    _lgbm_c   = int(_lgbm_sub['lgbm_model_correct'].sum())
                    _lgbm_t   = len(_lgbm_sub)
                    _lgbm_pct = round(_lgbm_c / _lgbm_t * 100, 1) if _lgbm_t > 0 else 0
                    _record_metric("LightGBM ATS", _lgbm_c, _lgbm_t, _lgbm_pct)
                if _has_ens:
                    _ens_sub = season_df[season_df['ens_model_correct'].notna()]
                    _ens_c   = int(_ens_sub['ens_model_correct'].sum())
                    _ens_t   = len(_ens_sub)
                    _ens_pct = round(_ens_c / _ens_t * 100, 1) if _ens_t > 0 else 0
                    _record_metric("Ensemble ATS", _ens_c, _ens_t, _ens_pct)

        st.divider()

        # ── Week-by-week summary ──────────────────────────────────────
        weekly = season_df.groupby('week').agg(
            correct=(_s_correct, 'sum'),
            total=(_s_correct, 'count')
        ).reset_index()
        weekly['pct']      = (weekly['correct'] / weekly['total'] * 100).round(1)
        weekly['record']   = (
            weekly['correct'].astype(int).astype(str) + '-' +
            (weekly['total'] - weekly['correct']).astype(int).astype(str)
        )
        weekly['week_lbl'] = 'Week ' + weekly['week'].astype(int).astype(str)

        # Cumulative win %
        weekly['cum_correct'] = weekly['correct'].cumsum()
        weekly['cum_total']   = weekly['total'].cumsum()
        weekly['cum_pct']     = (weekly['cum_correct'] / weekly['cum_total'] * 100).round(1)

        st.subheader("Week by Week ATS Record")

        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            x=weekly['week_lbl'],
            y=weekly['pct'],
            text=weekly['record'],
            textposition='outside',
            marker_color=[
                '#00c853' if p >= 60 else '#ffd600' if p >= 50 else '#ff5252'
                for p in weekly['pct']
            ],
            hovertemplate='%{x}<br>ATS: %{text}<br>Win%%: %{y}%<extra></extra>'
        ))
        fig_bar.add_hline(
            y=52.4, line_dash="dash", line_color="#888",
            annotation_text="Break even (52.4%)", annotation_position="right",
            annotation_font=dict(size=11, color="#9aa4b2")
        )
        fig_bar.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='white',
            yaxis=dict(range=[0, 100], title='ATS Win %', gridcolor='#2d3748'),
            xaxis=dict(gridcolor='#2d3748'),
            showlegend=False,
            height=350,
            margin=dict(t=20, b=20, r=112)
        )
        st.plotly_chart(fig_bar, width="stretch")

        st.divider()

        # ── Cumulative win % chart ─────────────────────────────────────
        st.subheader("Cumulative ATS Win % Over Season")

        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(
            x=weekly['week_lbl'],
            y=weekly['cum_pct'],
            mode='lines+markers',
            line=dict(color='#2979ff', width=2),
            marker=dict(size=8, color='#2979ff'),
            hovertemplate='%{x}<br>Cumulative Win%%: %{y}%<extra></extra>'
        ))
        fig_line.add_hline(
            y=52.4, line_dash="dash", line_color="#888",
            annotation_text="Break even (52.4%)", annotation_position="right",
            annotation_font=dict(size=11, color="#9aa4b2")
        )
        fig_line.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='white',
            yaxis=dict(range=[0, 100], title='Cumulative ATS Win %', gridcolor='#2d3748'),
            xaxis=dict(gridcolor='#2d3748'),
            showlegend=False,
            height=350,
            margin=dict(t=20, b=20, r=112)
        )
        st.plotly_chart(fig_line, width="stretch")

        st.divider()

        # ── High vs low confidence accuracy ──────────────────────────
        if live:
            st.subheader("HIGH vs other picks")
            edge_data = pd.DataFrame([
                {'Tier': f'HIGH (Tue {HIGH_GAP:g}+ pts)', 'Correct': he_correct, 'Total': he_total, 'Pct': he_pct},
                {'Tier': 'Other picks', 'Correct': re_correct, 'Total': re_total, 'Pct': re_pct},
            ])
            _edge_colors = ['#00c853', '#888888']
        else:
            st.subheader("Edge Tier Accuracy")
            edge_data = pd.DataFrame([
                {'Tier': 'High Edge (3+ pts)',  'Correct': he_correct, 'Total': he_total, 'Pct': he_pct},
                {'Tier': 'Med Edge (1-3 pts)',  'Correct': me_correct, 'Total': me_total, 'Pct': me_pct},
                {'Tier': 'Low Edge (<1 pt)',    'Correct': le_correct, 'Total': le_total, 'Pct': le_pct},
            ])
            _edge_colors = ['#00c853', '#ffd600', '#ff5252']

        fig_edge = go.Figure()
        fig_edge.add_trace(go.Bar(
            x=edge_data['Tier'],
            y=edge_data['Pct'],
            text=[f"{r['Correct']}/{r['Total']} ({r['Pct']}%)" for _, r in edge_data.iterrows()],
            textposition='outside',
            marker_color=_edge_colors,
            hovertemplate='%{x}<br>%{text}<extra></extra>'
        ))
        fig_edge.add_hline(
            y=52.4, line_dash="dash", line_color="#888",
            annotation_text="Break even (52.4%)", annotation_position="right",
            annotation_font=dict(size=11, color="#9aa4b2")
        )
        fig_edge.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='white',
            yaxis=dict(range=[0, 100], title='ATS Win %', gridcolor='#2d3748'),
            xaxis=dict(gridcolor='#2d3748'),
            showlegend=False,
            height=350,
            margin=dict(t=20, b=20, r=112)
        )
        st.plotly_chart(fig_edge, width="stretch")

        if _has_ct and not live:
            st.divider()
            st.subheader("Consensus Tier Accuracy")
            st.caption("All 3 models agree on direction · Ensemble edge ≥3 pts = HIGH, ≥1 pt = MEDIUM, else PASS")

            _ct_high = season_df[season_df['consensus_tier'] == 'HIGH']
            _ct_med  = season_df[season_df['consensus_tier'] == 'MEDIUM']
            _ct_pass = season_df[season_df['consensus_tier'] == 'PASS']

            _ch_c = int(_ct_high[_s_correct].sum()); _ch_t = int(_ct_high[_s_correct].notna().sum())
            _cm_c = int(_ct_med[_s_correct].sum());  _cm_t = int(_ct_med[_s_correct].notna().sum())
            _cp_c = int(_ct_pass[_s_correct].sum()); _cp_t = int(_ct_pass[_s_correct].notna().sum())

            _ch_pct = round(_ch_c / _ch_t * 100, 1) if _ch_t > 0 else 0
            _cm_pct = round(_cm_c / _cm_t * 100, 1) if _cm_t > 0 else 0
            _cp_pct = round(_cp_c / _cp_t * 100, 1) if _cp_t > 0 else 0

            with st.container(key="jsa-metric-even-tr-tiers"):
                ct1, ct2, ct3 = st.columns(3)
                ct1.metric("HIGH Tier",   f"{_ch_c}/{_ch_t}", f"{_ch_pct}%",
                           help="All 3 models agree + Ensemble edge ≥3 pts.")
                ct2.metric("MEDIUM Tier", f"{_cm_c}/{_cm_t}", f"{_cm_pct}%",
                           help="All 3 models agree + Ensemble edge 1–3 pts.")
                ct3.metric("PASS Tier",   f"{_cp_c}/{_cp_t}", f"{_cp_pct}%",
                           help="Models disagree or low edge — skipped. Lower % here = better filtering.")

            _ct_data = pd.DataFrame([
                {'Tier': 'HIGH',   'Correct': _ch_c, 'Total': _ch_t, 'Pct': _ch_pct},
                {'Tier': 'MEDIUM', 'Correct': _cm_c, 'Total': _cm_t, 'Pct': _cm_pct},
                {'Tier': 'PASS',   'Correct': _cp_c, 'Total': _cp_t, 'Pct': _cp_pct},
            ])
            fig_ct = go.Figure()
            fig_ct.add_trace(go.Bar(
                x=_ct_data['Tier'],
                y=_ct_data['Pct'],
                text=[f"{r['Correct']}/{r['Total']} ({r['Pct']}%)" for _, r in _ct_data.iterrows()],
                textposition='outside',
                marker_color=['#00c853', '#ffd600', '#888888'],
                hovertemplate='%{x}<br>%{text}<extra></extra>'
            ))
            fig_ct.add_hline(
                y=52.4, line_dash="dash", line_color="#888",
                annotation_text="Break even (52.4%)", annotation_position="right",
                annotation_font=dict(size=11, color="#9aa4b2")
            )
            fig_ct.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font_color='white',
                yaxis=dict(range=[0, 100], title='ATS Win %', gridcolor='#2d3748'),
                xaxis=dict(gridcolor='#2d3748'),
                showlegend=False,
                height=350,
                margin=dict(t=20, b=20, r=112)
            )
            st.plotly_chart(fig_ct, width="stretch")

        st.divider()

        # ── Best and worst weeks ──────────────────────────────────────
        st.subheader("Best & Worst Weeks")

        col_best, col_worst = st.columns(2)

        with col_best:
            st.markdown("**🏆 Best Weeks**")
            best = weekly.nlargest(3, 'pct')[['week_lbl', 'record', 'pct']]
            best.columns = ['Week', 'Record', 'Win %']
            st.dataframe(best, hide_index=True, width="stretch")

        with col_worst:
            st.markdown("**📉 Worst Weeks**")
            worst = weekly.nsmallest(3, 'pct')[['week_lbl', 'record', 'pct']]
            worst.columns = ['Week', 'Record', 'Win %']
            st.dataframe(worst, hide_index=True, width="stretch")

        st.divider()

        # ── Season at a Glance ────────────────────────────────────────
        st.subheader("Season at a Glance")
        st.caption("Profit math assumes flat unit stakes at -110 odds (bet 110 to win 100). Day-of-week breakdown excludes pushes.")

        # Hypothetical profit at -110 odds — three subsets
        def _units_profit(sub):
            graded = sub[sub[_s_correct].notna()]
            wins = int(graded[_s_correct].sum())
            losses = int(len(graded) - wins)
            return wins * 100 - losses * 110, wins, losses

        if live:
            _high_sub = season_df[season_df.apply(row_display_high, axis=1)]
            _med_or_high_sub = _high_sub
        elif _has_ct:
            _high_sub = season_df[season_df['consensus_tier'] == 'HIGH']
            _med_or_high_sub = season_df[season_df['consensus_tier'].isin(['HIGH', 'MEDIUM'])]
        else:
            _high_sub = season_df[season_df[_s_edge].abs() >= 3]
            _med_or_high_sub = season_df[season_df[_s_edge].abs() >= 1]
        _profit_high, _h_w, _h_l = _units_profit(_high_sub)
        _profit_hm,   _hm_w, _hm_l = _units_profit(_med_or_high_sub)
        _profit_all,  _a_w, _a_l = _units_profit(season_df)

        def _profit_metric(label, wins, losses, profit):
            st.metric(
                label,
                f"{wins}-{losses}",
                f"{profit:+,} units",
                delta_color="green" if profit > 0 else "red",
                delta_arrow="off",
                border=True,
            )

        with st.container(horizontal=True, key="jsa-metric-even-profit"):
            if live:
                _profit_metric("Profit (HIGH only)", _h_w, _h_l, _profit_high)
                _profit_metric("Profit (all picks)", _a_w, _a_l, _profit_all)
            else:
                _profit_metric("Profit (HIGH only)", _h_w, _h_l, _profit_high)
                _profit_metric("Profit (HIGH + MED)", _hm_w, _hm_l, _profit_hm)
                _profit_metric("Profit (all picks)", _a_w, _a_l, _profit_all)

        st.space("small")

        # Day-of-week performance
        if 'gameday' in season_df.columns:
            _dow_df = season_df.copy()
            _dow_df['gameday_dt'] = pd.to_datetime(_dow_df['gameday'], errors='coerce')
            _dow_df['dow'] = _dow_df['gameday_dt'].dt.day_name()
            _dow_df = _dow_df[_dow_df[_s_correct].notna()]
            if len(_dow_df) > 0:
                _dow_order = ['Thursday', 'Friday', 'Saturday', 'Sunday', 'Monday']
                _dow_rows = []
                for d in _dow_order:
                    sub = _dow_df[_dow_df['dow'] == d]
                    if len(sub) == 0:
                        continue
                    c = int(sub[_s_correct].sum()); t = len(sub)
                    _dow_rows.append({
                        'Day': d, 'Record': f"{c}-{t-c}", 'Games': t,
                        'Win %': round(c / t * 100, 1)
                    })
                if _dow_rows:
                    dow_table = pd.DataFrame(_dow_rows)
                    dow_col, streak_col = st.columns(2)
                    with dow_col:
                        st.markdown("**📅 By day of week**")
                        st.dataframe(dow_table, hide_index=True, width="stretch")
                    with streak_col:
                        # Streaks — sort by gameday + game_id for deterministic order
                        _str_df = season_df.sort_values(['gameday', 'game_id'] if 'game_id' in season_df.columns else ['gameday'])
                        _str_df = _str_df[_str_df[_s_correct].notna()]
                        longest_w = longest_l = cur_w = cur_l = 0
                        for v in _str_df[_s_correct].values:
                            if v == 1:
                                cur_w += 1; cur_l = 0
                                longest_w = max(longest_w, cur_w)
                            else:
                                cur_l += 1; cur_w = 0
                                longest_l = max(longest_l, cur_l)
                        # Current streak (from end)
                        cur_streak_n = 0; cur_streak_kind = ''
                        for v in _str_df[_s_correct].values[::-1]:
                            if cur_streak_kind == '':
                                cur_streak_kind = 'W' if v == 1 else 'L'
                                cur_streak_n = 1
                            elif (cur_streak_kind == 'W' and v == 1) or (cur_streak_kind == 'L' and v == 0):
                                cur_streak_n += 1
                            else:
                                break
                        st.markdown("**🔥 Streaks**")
                        sk1, sk2 = st.columns(2)
                        sk1.metric("Longest W streak", longest_w)
                        sk2.metric("Longest L streak", longest_l)
                        cur_label = f"{cur_streak_n} {cur_streak_kind}" if cur_streak_kind else "—"
                        st.metric("Current streak (most-recent first)", cur_label)

        st.divider()

        # ── Full season table ─────────────────────────────────────────
        with st.expander("📋 Full season week by week"):
            table = weekly[['week_lbl', 'record', 'pct', 'cum_pct']].copy()
            table.columns = ['Week', 'Record', 'Win %', 'Cumulative %']
            st.dataframe(table, hide_index=True, width="stretch")

        # ── Totals model performance ──────────────────────────────────────────
        totals_season = (
            totals_df[(totals_df['season'] == season) & totals_df['model_correct'].notna()]
            if (not live) and not totals_df.empty else pd.DataFrame()
        )
        if not totals_season.empty:
            st.divider()
            st.subheader("🎯 Over/Under Model Performance — Experimental")
            st.warning(
                "**Tracking only — do not bet.** The totals model has a CV edge (55.7% on 575 picks across "
                "2020–2025) but the live 2025 sample is too small to confirm it. Currently sitting near "
                "break-even live. I track it through the 2026 season and reassess after a full season "
                "(~96 picks) of real evidence."
            )
            st.caption("UNDER picks only — model bets UNDER when both XGBoost and Ridge agree. Break-even: 52.4%.")

            t_high = totals_season[totals_season['consensus_tier'] == 'HIGH']
            t_correct = int(t_high['model_correct'].sum())
            t_total   = len(t_high)
            t_pct     = round(t_correct / t_total * 100, 1) if t_total > 0 else 0

            with st.container(horizontal=True, key="jsa-metric-even-tr-totals"):
                _record_metric("UNDER picks", t_correct, t_total, t_pct)

                _t_over_rate = totals_season['went_over'].mean() if 'went_over' in totals_season.columns and totals_season['went_over'].notna().any() else None
                if _t_over_rate is not None:
                    st.metric(
                        "Actual OVER rate",
                        None,
                        f"{round(_t_over_rate * 100, 1)}% of tracked games",
                        delta_color="gray",
                        delta_arrow="off",
                        border=True,
                    )
                st.metric(
                    "Break-even",
                    "52.4%",
                    "At -110 odds",
                    delta_color="gray",
                    delta_arrow="off",
                    border=True,
                )

            # Week by week totals
            if t_total > 0:
                _t_weekly = t_high.groupby('week').agg(
                    correct=('model_correct', 'sum'),
                    total=('model_correct', 'count')
                ).reset_index()
                _t_weekly['pct'] = (_t_weekly['correct'] / _t_weekly['total'] * 100).round(1)
                _t_weekly['record'] = _t_weekly['correct'].astype(int).astype(str) + '-' + (_t_weekly['total'] - _t_weekly['correct']).astype(int).astype(str)
                with st.expander("📋 Totals week by week (UNDER picks only)"):
                    st.dataframe(
                        _t_weekly[['week', 'record', 'pct']].rename(
                            columns={'week': 'Week', 'record': 'Record', 'pct': 'Win %'}),
                        hide_index=True, width="stretch")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: FANTASY PROJECTIONS
# ══════════════════════════════════════════════════════════════════════════════
