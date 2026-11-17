"""Track Record page (site revamp Batch 3b). Shared data/helpers from
dashboard_data / page_common; own Season control (filter independence) preserved.
ATS blurb moved here from the retired sidebar.
"""
import pandas as pd
import streamlit as st

import dashboard_data
import page_common
from dashboard_utils import BREAKEVEN_PCT, ats_record_parts, format_ats_metric_delta, format_ats_record, push_mask
from live_2026 import HIGH_GAP, is_live_season, row_display_high


def _high_weekly_table(season_df, high_df, correct_col):
    """Per-week HIGH wins/losses/pushes plus cumulative HIGH win %, over every graded week."""
    weeks = sorted(int(w) for w in season_df['week'].dropna().unique())
    rows = []
    for w in weeks:
        sub = high_df[high_df['week'] == w]
        wins, losses, pushes, _ = ats_record_parts(sub, correct_col)
        rows.append({'week': w, 'wins': wins, 'losses': losses, 'pushes': pushes})
    out = pd.DataFrame(rows, columns=['week', 'wins', 'losses', 'pushes'])
    cw, cl = out['wins'].cumsum(), out['losses'].cumsum()
    out['cum_pct'] = (cw / (cw + cl).where((cw + cl) > 0) * 100).round(1)
    out['picks'] = out['wins'] + out['losses'] + out['pushes']
    return out


# Phone: stack the three hero tiles as compact full-width rows instead of 2 + 1.
_HERO_CSS = """<style>
@media (max-width: 640px){
  .stApp [class*="st-key-jsa-metric-even-tr-hero"]:has(> [data-testid="stElementContainer"] [data-testid="stMetric"]){
    grid-template-columns:minmax(0,1fr) !important;
    grid-auto-rows:auto !important;
    gap:.35rem !important;
  }
  .stApp [class*="st-key-jsa-metric-even-tr-hero"] [data-testid="stMetric"]{
    padding:.55rem .8rem !important;
    min-height:0 !important;
  }
}
</style>"""


def units_profit(sub, correct_col):
    """Flat-stake profit at -110 in units (risk 1.1 to win 1): (profit, wins, losses)."""
    graded = sub[sub[correct_col].notna()]
    wins = int(graded[correct_col].sum())
    losses = int(len(graded) - wins)
    return wins - losses * 1.1, wins, losses


def _pct_range(values):
    """Tight y range around the data and the break-even line, snapped to 10s inside 0-100."""
    vals = [float(v) for v in values if pd.notna(v)] + [BREAKEVEN_PCT]
    lo = max(0, int((min(vals) - 6) // 10 * 10))
    hi = min(100, int(-(-(max(vals) + 6) // 10) * 10))
    return [lo, hi], (10 if hi - lo <= 50 else 20)


def _streaks(df, correct_col):
    """Longest win/loss run and the current run over graded picks, in game order."""
    ordered = df.sort_values(['gameday', 'game_id'] if 'game_id' in df.columns else ['gameday'])
    vals = ordered[ordered[correct_col].notna()][correct_col].values
    longest_w = longest_l = cur_w = cur_l = 0
    for v in vals:
        if v == 1:
            cur_w += 1
            cur_l = 0
            longest_w = max(longest_w, cur_w)
        else:
            cur_l += 1
            cur_w = 0
            longest_l = max(longest_l, cur_l)
    cur_n, cur_kind = 0, ''
    for v in vals[::-1]:
        kind = 'W' if v == 1 else 'L'
        if not cur_kind:
            cur_kind, cur_n = kind, 1
        elif kind == cur_kind:
            cur_n += 1
        else:
            break
    return longest_w, longest_l, cur_n, cur_kind


def _high_weekly_figure(go, hw, phone=False):
    """Two stacked panels on one x axis: cumulative HIGH win % (top), weekly picks (bottom)."""
    from plotly.subplots import make_subplots

    c = page_common.TRACK_COLORS
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, row_heights=[0.5, 0.5],
        subplot_titles=("Cumulative HIGH win %", "HIGH picks per week"),
    )
    x = hw['week']
    hover_rec = [f"{w}-{l}-{p}" for w, l, p in zip(hw['wins'], hw['losses'], hw['pushes'])]
    fig.add_trace(go.Scatter(
        x=x, y=hw['cum_pct'], mode='lines+markers', connectgaps=True, showlegend=False,
        line=dict(color=c['line'], width=2), marker=dict(size=8, color=c['line']),
        customdata=hover_rec,
        hovertemplate='Week %{x}<br>Cumulative HIGH win: %{y}%<br>This week: %{customdata}<extra></extra>',
    ), row=1, col=1)
    page_common.add_breakeven(fig, row=1, col=1)
    series = [('Wins', 'wins', c['win']), ('Losses', 'losses', c['loss'])]
    if int(hw['pushes'].sum()) > 0:
        series.append(('Pushes', 'pushes', c['push']))
    for name, col, color in series:
        fig.add_trace(go.Bar(
            x=x, y=hw[col], name=name, marker_color=color,
            marker_line=dict(width=1, color='rgba(11,15,20,1)'),
            hovertemplate='Week %{x}<br>' + name + ': %{y}<extra></extra>',
        ), row=2, col=1)
    if not phone:
        # Record label above each week's stack; zero-pick weeks say so.
        for w, n, rec in zip(hw['week'], hw['picks'], hover_rec):
            fig.add_annotation(
                x=w, y=n, yref='y2', xref='x2', yanchor='bottom', showarrow=False,
                text=rec if n else "0 picks", font=dict(size=10, color=c['ink2']),
            )
    ymax = max(int(hw['picks'].max()) if len(hw) else 0, 1)
    page_common.style_track_chart(fig, height=430 if phone else 500, phone=phone,
                                  margin=dict(t=30, b=16, l=8, r=8))
    fig.update_layout(
        barmode='stack', hovermode='x unified',
        legend=dict(orientation='h', yanchor='top', y=-0.14, x=0, traceorder='normal'),
    )
    rng, dtick = _pct_range(hw['cum_pct'])
    fig.update_yaxes(range=rng, dtick=dtick, ticksuffix='%', row=1, col=1)
    fig.update_yaxes(range=[0, ymax + 1.2], dtick=1 if ymax <= 8 else None, row=2, col=1)
    fig.update_xaxes(dtick=1, row=1, col=1)
    fig.update_xaxes(dtick=1, row=2, col=1, title_text='Week')
    for a in fig.layout.annotations:
        if a.text in ("Cumulative HIGH win %", "HIGH picks per week"):
            a.update(x=0, xanchor='left', font=dict(size=13, color=c['ink']))
    return fig


def _tier_figure(go, edge_data, colors, phone=False):
    """Compact horizontal comparison of win % by tier against the break-even line."""
    c = page_common.TRACK_COLORS
    pcts = [0 if pd.isna(v) else v for v in edge_data['Pct']]
    fig = go.Figure(go.Bar(
        y=edge_data['Tier'], x=pcts, orientation='h', marker_color=colors,
        text=[
            f"{format_ats_record(r['Wins'], r['Losses'], r['Pushes'])} ({r['Pct']}%)"
            if (r['Wins'] + r['Losses']) else "No graded picks"
            for _, r in edge_data.iterrows()
        ],
        textposition='inside', insidetextanchor='start',
        textfont=dict(color=['#0B0F14' if col == c['win'] else c['ink'] for col in colors],
                      size=11 if phone else 12),
        hovertemplate='%{y}<br>%{text}<extra></extra>',
    ))
    page_common.add_breakeven(fig, axis='x', position='top', color=c['ink'], width=1.5)
    page_common.style_track_chart(
        fig, height=90 + 46 * len(edge_data), phone=phone,
        margin=dict(t=30, b=34, l=8, r=22),
    )
    fig.update_layout(showlegend=False, bargap=0.35)
    fig.update_xaxes(range=[0, 100], tickvals=[0, 25, 50, 75, 100], ticksuffix='%',
                     title_text=f"ATS win %, dashed line is {BREAKEVEN_PCT}% break even")
    fig.update_yaxes(autorange='reversed', automargin=True, showgrid=False)
    return fig


def _weekly_pct_figure(go, weekly, kind, phone=False):
    """Weekly ATS win % bars (kind='bar') or cumulative win % line (kind='line'), all picks."""
    c = page_common.TRACK_COLORS
    if kind == 'bar':
        fig = go.Figure(go.Bar(
            x=weekly['week'], y=weekly['pct'], text=None if phone else weekly['record'],
            textposition='inside', insidetextanchor='start', textfont=dict(color='#0B0F14', size=10),
            marker_color=[c['win'] if p >= BREAKEVEN_PCT else c['loss'] for p in weekly['pct']],
            customdata=weekly['record'],
            hovertemplate='Week %{x}<br>ATS: %{customdata}<br>Win %: %{y}%<extra></extra>',
        ))
        rng, dtick = [0, 100], 20  # bars keep a zero baseline
    else:
        fig = go.Figure(go.Scatter(
            x=weekly['week'], y=weekly['cum_pct'], mode='lines+markers',
            line=dict(color=c['line'], width=2), marker=dict(size=8, color=c['line']),
            hovertemplate='Week %{x}<br>Cumulative win %: %{y}%<extra></extra>',
        ))
        rng, dtick = _pct_range(weekly['cum_pct'])
    page_common.add_breakeven(fig, label=(kind == 'line' and not phone))
    page_common.style_track_chart(fig, height=250 if phone else 300, phone=phone,
                                  margin=dict(t=16, b=16, l=8, r=8))
    fig.update_layout(showlegend=False)
    fig.update_yaxes(range=rng, dtick=dtick, ticksuffix='%')
    fig.update_xaxes(dtick=1, title_text=(
        f"Week. Dashed line is {BREAKEVEN_PCT}% break even" if kind == 'bar' else 'Week'))
    return fig


def render():
    st.title("Track record")
    st.caption("Graded ATS results and flat-stake profit at -110.")
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

        # ── Season summary numbers (everything below is computed from the tracker) ──
        _s_edge    = 'ens_model_edge'    if ('ens_model_edge'    in season_df.columns and season_df['ens_model_edge'].notna().any())    else 'model_edge'
        _s_correct = 'ens_model_correct' if ('ens_model_correct' in season_df.columns and season_df['ens_model_correct'].notna().any()) else 'model_correct'

        total_correct, total_losses, total_pushes, total_pct = ats_record_parts(season_df, _s_correct)

        if live:
            _high_mask = season_df.apply(row_display_high, axis=1)
            high_edge_df = season_df[_high_mask]
            he_correct, he_losses, he_pushes, he_pct = ats_record_parts(high_edge_df, _s_correct)
            he_total = he_correct + he_losses
            rest_df = season_df[~_high_mask]
            re_correct, re_losses, re_pushes, re_pct = ats_record_parts(rest_df, _s_correct)
            re_total = re_correct + re_losses
        else:
            high_edge_df = season_df[season_df[_s_edge].abs() >= 3]
            he_correct, he_losses, he_pushes, he_pct = ats_record_parts(high_edge_df, _s_correct)
            he_total = he_correct + he_losses

            med_edge_df = season_df[(season_df[_s_edge].abs() >= 1) & (season_df[_s_edge].abs() < 3)]
            me_correct, me_losses, me_pushes, me_pct = ats_record_parts(med_edge_df, _s_correct)
            me_total = me_correct + me_losses

            low_edge_df = season_df[season_df[_s_edge].abs() < 1]
            le_correct, le_losses, le_pushes, le_pct = ats_record_parts(low_edge_df, _s_correct)
            le_total = le_correct + le_losses

        _has_ct = 'consensus_tier' in season_df.columns and season_df['consensus_tier'].notna().any()

        # Flat-stake profit at -110 in units (risk 1.1 to win 1), HIGH / HIGH+MED / all picks.
        def _units_profit(sub):
            return units_profit(sub, _s_correct)

        if live:
            _high_sub = high_edge_df
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

        def _record_metric(label, wins, losses, pushes, pct):
            settled = wins + losses
            st.metric(
                label,
                format_ats_record(wins, losses, pushes),
                format_ats_metric_delta(pct, pushes) if settled > 0 or pushes > 0 else "No graded picks",
                delta_color=("green" if (pct or 0) >= BREAKEVEN_PCT else "red") if settled > 0 else "gray",
                delta_arrow="off",
                border=True,
            )

        def _profit_metric(label, wins, losses, profit):
            st.metric(
                label,
                f"{wins}-{losses}",
                f"{profit:+.1f} units",
                delta_color="green" if profit > 0 else "red",
                delta_arrow="off",
                border=True,
            )

        # ── Weekly tables ─────────────────────────────────────────────
        season_df['_is_push'] = push_mask(season_df)
        weekly = season_df.groupby('week').agg(
            correct=(_s_correct, 'sum'),
            total=(_s_correct, 'count'),
            pushes=('_is_push', 'sum'),
        ).reset_index()
        weekly['week'] = weekly['week'].astype(int)
        weekly['pct'] = (weekly['correct'] / weekly['total'] * 100).round(1)
        weekly['record'] = [
            format_ats_record(int(w), int(t - w), int(p))
            for w, t, p in zip(weekly['correct'], weekly['total'], weekly['pushes'])
        ]
        weekly['week_lbl'] = 'Week ' + weekly['week'].astype(str)
        weekly['cum_correct'] = weekly['correct'].cumsum()
        weekly['cum_total']   = weekly['total'].cumsum()
        weekly['cum_pct']     = (weekly['cum_correct'] / weekly['cum_total'] * 100).round(1)

        _tc = page_common.TRACK_COLORS

        # ── Hero: the one number, three tiles, current form ───────────
        if live:
            if he_total:
                _push_txt = f" ({he_pushes} push{'es' if he_pushes != 1 else ''})" if he_pushes else ""
                _headline = f"HIGH picks {he_correct}-{he_losses}{_push_txt}, {he_pct:.1f}%"
            else:
                _headline = "No graded HIGH picks yet"
            st.markdown(
                f"<div style='font-size:1.7rem;font-weight:700;line-height:1.15;"
                f"color:{_tc['ink']};margin:4px 0 2px'>{_headline}</div>",
                unsafe_allow_html=True,
            )
            st.caption(
                f"{season} HIGH picks: Tuesday gap of {HIGH_GAP:g}+ points, win % before pushes. "
                f"{BREAKEVEN_PCT}% breaks even at -110. Weeks with no HIGH pick show as zero picks."
            )
            st.markdown(_HERO_CSS, unsafe_allow_html=True)
            with st.container(horizontal=True, key="jsa-metric-even-tr-hero"):
                _record_metric(
                    f"HIGH (Tuesday {HIGH_GAP:g}+ points)",
                    he_correct, he_losses, he_pushes, he_pct,
                )
                st.metric(
                    "HIGH profit at -110",
                    f"{_profit_high:+.1f} units",
                    f"{_h_w}-{_h_l} flat stake",
                    delta_color="green" if _profit_high > 0 else "red",
                    delta_arrow="off",
                    border=True,
                )
                _record_metric("Season ATS", total_correct, total_losses, total_pushes, total_pct)
            if he_total:
                _lw, _ll, _cn, _ck = _streaks(high_edge_df, _s_correct)
                _chip = (
                    "display:inline-block;padding:3px 10px;margin:0 6px 4px 0;border-radius:999px;"
                    f"border:1px solid {_tc['grid']};font-size:13px;color:{_tc['ink2']}"
                )
                _b = f"<b style='color:{_tc['ink']}'>"
                st.markdown(
                    f"<div><span style='{_chip}'>HIGH current streak {_b}{_cn} {_ck}</b></span>"
                    f"<span style='{_chip}'>Longest win streak {_b}{_lw}</b></span>"
                    f"<span style='{_chip}'>Longest loss streak {_b}{_ll}</b></span></div>",
                    unsafe_allow_html=True,
                )
            st.subheader("HIGH picks week by week")
            _hw = _high_weekly_table(season_df, high_edge_df, _s_correct)
            page_common.plotly_phone_desktop(
                _high_weekly_figure(go, _hw), _high_weekly_figure(go, _hw, phone=True),
                slug="tr-high-weekly",
            )
        else:
            with st.container(horizontal=True, key="jsa-metric-even-tr-ats"):
                _record_metric("Season ATS", total_correct, total_losses, total_pushes, total_pct)
                _record_metric("High edge (3+ points)", he_correct, he_losses, he_pushes, he_pct)
                _record_metric("Medium edge (1–3 points)", me_correct, me_losses, me_pushes, me_pct)
                _record_metric("Low edge (<1 point)", le_correct, le_losses, le_pushes, le_pct)
            st.subheader("Week by Week ATS Record")
            page_common.plotly_phone_desktop(
                _weekly_pct_figure(go, weekly, 'bar'),
                _weekly_pct_figure(go, weekly, 'bar', phone=True),
                slug="tr-weekly-bar",
            )

        # ── The model's main claim: HIGH vs the rest ──────────────────
        if live:
            st.subheader("HIGH vs other picks")
            edge_data = pd.DataFrame([
                {'Tier': f'HIGH (Tue {HIGH_GAP:g}+ pts)', 'Wins': he_correct, 'Losses': he_losses,
                 'Pushes': he_pushes, 'Total': he_total, 'Pct': he_pct},
                {'Tier': 'Other picks', 'Wins': re_correct, 'Losses': re_losses,
                 'Pushes': re_pushes, 'Total': re_total, 'Pct': re_pct},
            ])
            _edge_colors = [_tc['win'], _tc['other']]
        else:
            st.subheader("Edge Tier Accuracy")
            edge_data = pd.DataFrame([
                {'Tier': 'High Edge (3+ pts)', 'Wins': he_correct, 'Losses': he_losses,
                 'Pushes': he_pushes, 'Total': he_total, 'Pct': he_pct},
                {'Tier': 'Med Edge (1-3 pts)', 'Wins': me_correct, 'Losses': me_losses,
                 'Pushes': me_pushes, 'Total': me_total, 'Pct': me_pct},
                {'Tier': 'Low Edge (<1 pt)', 'Wins': le_correct, 'Losses': le_losses,
                 'Pushes': le_pushes, 'Total': le_total, 'Pct': le_pct},
            ])
            _edge_colors = [_tc['win'], _tc['other'], _tc['other']]
        page_common.plotly_phone_desktop(
            _tier_figure(go, edge_data, _edge_colors),
            _tier_figure(go, edge_data, _edge_colors, phone=True),
            slug="tr-tiers",
        )

        # ── Everything else, one click away ───────────────────────────
        with st.expander("More detail"):
            if live:
                st.subheader("All picks week by week")
                page_common.plotly_phone_desktop(
                    _weekly_pct_figure(go, weekly, 'bar'),
                    _weekly_pct_figure(go, weekly, 'bar', phone=True),
                    slug="tr-weekly-bar",
                )
            st.subheader("Cumulative ATS win % over season")
            page_common.plotly_phone_desktop(
                _weekly_pct_figure(go, weekly, 'line'),
                _weekly_pct_figure(go, weekly, 'line', phone=True),
                slug="tr-cumulative",
            )

            st.subheader("Best & worst weeks")
            col_best, col_worst = st.columns(2)
            with col_best:
                st.markdown("**Best weeks**")
                best = weekly.nlargest(3, 'pct')[['week_lbl', 'record', 'pct']]
                best.columns = ['Week', 'Record', 'Win %']
                st.dataframe(best, hide_index=True, width="stretch")
            with col_worst:
                st.markdown("**Worst weeks**")
                worst = weekly.nsmallest(3, 'pct')[['week_lbl', 'record', 'pct']]
                worst.columns = ['Week', 'Record', 'Win %']
                st.dataframe(worst, hide_index=True, width="stretch")

            st.subheader("Profit at -110")
            st.caption("Flat stakes at -110: risk 1.1 units to win 1. Day-of-week breakdown excludes pushes.")
            with st.container(horizontal=True, key="jsa-metric-even-profit"):
                _profit_metric("Profit (HIGH only)", _h_w, _h_l, _profit_high)
                if not live:
                    _profit_metric("Profit (HIGH + MED)", _hm_w, _hm_l, _profit_hm)
                _profit_metric("Profit (all picks)", _a_w, _a_l, _profit_all)
            if not live and _has_ct:
                st.caption(
                    "HIGH and HIGH + MED profit use the three-model consensus tier. The edge "
                    "cards above use the point gap alone, so their records can differ."
                )

            if 'gameday' in season_df.columns:
                _dow_df = season_df.copy()
                _dow_df['dow'] = pd.to_datetime(_dow_df['gameday'], errors='coerce').dt.day_name()
                _dow_df = _dow_df[_dow_df[_s_correct].notna()]
                _dow_rows = []
                for d in ['Thursday', 'Friday', 'Saturday', 'Sunday', 'Monday']:
                    sub = _dow_df[_dow_df['dow'] == d]
                    if len(sub) == 0:
                        continue
                    c = int(sub[_s_correct].sum()); t = len(sub)
                    _dow_rows.append({'Day': d, 'Record': f"{c}-{t-c}", 'Games': t,
                                      'Win %': round(c / t * 100, 1)})
                if _dow_rows:
                    dow_col, streak_col = st.columns(2)
                    with dow_col:
                        st.markdown("**By day of week**")
                        st.dataframe(pd.DataFrame(_dow_rows), hide_index=True, width="stretch")
                    with streak_col:
                        longest_w, longest_l, cur_streak_n, cur_streak_kind = _streaks(season_df, _s_correct)
                        st.markdown("**Streaks, all picks**")
                        sk1, sk2 = st.columns(2)
                        sk1.metric("Longest W streak", longest_w)
                        sk2.metric("Longest L streak", longest_l)
                        st.metric(
                            "Current streak",
                            f"{cur_streak_n} {cur_streak_kind}" if cur_streak_kind else "—",
                        )

            st.subheader("Full season week by week")
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
            t_losses  = t_total - t_correct
            t_pct     = round(t_correct / t_total * 100, 1) if t_total > 0 else None

            with st.container(horizontal=True, key="jsa-metric-even-tr-totals"):
                _record_metric("UNDER picks", t_correct, t_losses, 0, t_pct)

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
