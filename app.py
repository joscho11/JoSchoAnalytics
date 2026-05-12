import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
import os
from datetime import datetime as dt
import plotly.graph_objects as go

st.set_page_config(
    page_title="BettingEdge | NFL Predictions",
    page_icon="🏈",
    layout="wide"
)

def inject_ga(g_id):
    components.html(
        f"""
        <!-- Google tag (gtag.js) -->
        <script async src="https://www.googletagmanager.com/gtag/js?id={g_id}"></script>
        <script>
        window.dataLayer = window.dataLayer || [];
        function gtag(){{dataLayer.push(arguments);}}
        gtag('js', new Date());
        gtag('config', '{g_id}');
        </script>
        """,
        height=1,
        scrolling=False
    )

GOOGLE_ANALYTICS_ID = st.secrets.get('GOOGLE_ANALYTICS_ID', '')

# DEBUG - remove after confirming GA works
st.sidebar.caption(f"GA loaded: {bool(GOOGLE_ANALYTICS_ID)}")

if GOOGLE_ANALYTICS_ID:
    inject_ga(GOOGLE_ANALYTICS_ID)

st.markdown("""
    <style>
    details {
        border: none !important;
        box-shadow: none !important;
    }
    details summary {
        font-size: 11px !important;
        color: #aaa !important;
        background-color: #2d3748 !important;
        border-radius: 6px !important;
        padding: 4px 10px !important;
        border: 1px solid #4a5568 !important;
        width: fit-content !important;
    }
    details summary:hover {
        color: white !important;
        background-color: #3d4f66 !important;
        border-color: #6b8aad !important;
        cursor: pointer !important;
    }
    details[open] summary {
        border-radius: 6px 6px 0 0 !important;
    }
    details > div {
        background-color: #1a2332 !important;
        border: 1px solid #4a5568 !important;
        border-top: none !important;
        border-radius: 0 0 6px 6px !important;
        padding: 10px !important;
    }
    .st-expander {
        border: none !important;
        box-shadow: none !important;
    }
    [data-testid="stExpander"] {
        border: none !important;
        box-shadow: none !important;
    }
    [data-testid="stExpanderDetails"] {
        border: none !important;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def load_tracker():
    df = pd.read_csv('betting/predictions_tracker.csv')
    df['season'] = df['season'].astype(int)
    df['week']   = df['week'].astype(int)
    return df

df = load_tracker()

def load_agent_analysis(week: int, season: int) -> dict:
    cache_file = f"betting/agent_analysis_{season}_week{week}.json"
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            return json.load(f)
    return None

def get_confidence(home, away, game_analysis):
    key  = f"{home}_{away}"
    text = game_analysis.get(key, '')
    if '🟢' in text:
        return 'HIGH'
    elif '🟡' in text:
        return 'MEDIUM'
    elif '🔴' in text or 'SKIP' in text.upper():
        return 'SKIP'
    else:
        return 'NO_ANALYSIS'

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.markdown("""
    <div style='text-align: center; padding: 10px;'>
        <div style='display: inline-block; background: #013369; color: white;
                    border-radius: 50%; width: 60px; height: 60px;
                    line-height: 60px; font-size: 24px; font-weight: bold;'>
            JS
        </div>
    </div>
""", unsafe_allow_html=True)

st.sidebar.title("BettingEdge")
st.sidebar.caption("XGBoost ATS Predictor")
st.sidebar.divider()

seasons = sorted(df['season'].unique(), reverse=True)
season  = st.sidebar.selectbox("Season", seasons, key="season_select")

weeks   = sorted(df[df['season'] == season]['week'].unique(), reverse=True)
week    = st.sidebar.selectbox("Week", weeks, key="week_select")

edge_threshold = st.sidebar.slider(
    "Min Edge (pts)",
    min_value=0.0,
    max_value=5.0,
    value=1.0,
    step=0.5,
    key="edge_slider",
    help="Only show games where model disagrees with spread by at least this many points"
)

# ── Offseason banner ──────────────────────────────────────────────────────────
now           = dt.now()
season_active = (now.month >= 9) or (now.month <= 2)

if not season_active:
    st.info(
        "🏈 **NFL Offseason**: The 2025 season has concluded. Look at WEEK 10 for demo agent analysis. "
        "Predictions will return when the 2026 season kicks off in September. "
        "Browse past predictions using the sidebar."
    )

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🏈 Weekly Predictions", "📈 Season Performance", "❓ Help & Guide"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: WEEKLY PREDICTIONS
# ══════════════════════════════════════════════════════════════════════════════
with tab1:

    week_df    = df[(df['season'] == season) & (df['week'] == week)].copy()
    results_in = week_df['actual_margin'].notna().any()

    st.title(f"🏈 Week {week} Predictions: {season} Season")

    if results_in:
        correct = int(week_df['model_correct'].sum())
        total   = len(week_df)
        st.success(
            f"Results are in! Week {week} ATS record: "
            f"**{correct}-{total - correct}** ({correct/total*100:.0f}%)"
        )
    else:
        st.info("Games not yet played. Check back after the week's results are in.")

    if not week_df.empty and 'mode' in week_df.columns:
        mode      = week_df['mode'].iloc[-1]
        logged_at = week_df['logged_at'].iloc[-1]
        mode_labels = {
            'monday':   ('🟡', 'Early Lines',       'Updated Monday with initial lines'),
            'thursday': ('🟠', 'Injury Reports In', 'Updated Thursday with injury data'),
            'sunday':   ('🟢', 'Final Predictions', 'Final update — games starting soon'),
            'backfill': ('🔵', 'Backfilled',        'Historical predictions'),
        }
        icon, label, desc = mode_labels.get(mode, ('⚪', 'Manual Run', ''))
        st.caption(f"{icon} **{label}** — {desc} · Last updated: {logged_at}")

    st.divider()
    col1, col2, col3, col4 = st.columns(4)

    filtered_df  = week_df[week_df['model_edge'].abs() >= edge_threshold].copy()
    hidden_count = len(week_df) - len(filtered_df)

    col1.metric("Total Games", len(week_df))
    col2.metric("Showing",     len(filtered_df),
                help=f"Games with |edge| ≥ {edge_threshold} pts")
    col3.metric("Avg Edge",    f"{week_df['model_edge'].abs().mean():.1f} pts")

    if results_in and len(filtered_df) > 0:
        sc = int(filtered_df['model_correct'].sum())
        col4.metric("ATS Record", f"{sc}/{len(filtered_df)} ({sc/len(filtered_df)*100:.0f}%)")
    else:
        col4.metric("ATS Record", "Pending")

    st.divider()

    cached        = load_agent_analysis(week, season)
    game_analysis = cached.get('game_analysis', {}) if cached else {}

    st.markdown("""
        <div style='display:flex;gap:16px;align-items:center;margin-bottom:12px;flex-wrap:wrap;'>
            <span style='font-size:11px;color:#888;letter-spacing:1px;text-transform:uppercase;'>Agent Confidence:</span>
            <span style='font-size:12px;background:#1a3a1a;border:1px solid #00c853;
                        border-radius:4px;padding:2px 8px;color:#00c853;'>🟢 High</span>
            <span style='font-size:12px;background:#3a3a1a;border:1px solid #ffd600;
                        border-radius:4px;padding:2px 8px;color:#ffd600;'>🟡 Medium</span>
            <span style='font-size:12px;background:#3a1a1a;border:1px solid #ff5252;
                        border-radius:4px;padding:2px 8px;color:#ff5252;'>🔴 Skip</span>
        </div>
    """, unsafe_allow_html=True)

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

        filtered_df = filtered_df.sort_values('model_edge', key=abs, ascending=False)

        for _, row in filtered_df.iterrows():
            home      = row['home_team']
            away      = row['away_team']
            spread    = row['spread_line']
            predicted = row['predicted_margin']
            edge      = row['model_edge']

            def fmt(val):
                return f"{val:+.1f}"

            home_is_favored = spread > 0

            if home_is_favored:
                top_team      = home
                bot_team      = away
                top_spread    = fmt(-spread)
                bot_spread    = fmt(spread)
                top_predicted = fmt(predicted)
                bot_predicted = fmt(-predicted)
            else:
                top_team      = away
                bot_team      = home
                top_spread    = fmt(spread)
                bot_spread    = fmt(-spread)
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
            correct           = (row['model_correct'] == 1) if results_in else False
            actual            = row['actual_margin'] if results_available else None

            if results_available:
                home_score = row.get('home_score', None)
                away_score = row.get('away_score', None)
                has_scores = pd.notna(home_score) and pd.notna(away_score)
                if has_scores:
                    top_score = f"{int(home_score)}" if home_is_favored else f"{int(away_score)}"
                    bot_score = f"{int(away_score)}" if home_is_favored else f"{int(home_score)}"
                else:
                    top_score = fmt(actual if home_is_favored else -actual)
                    bot_score = fmt(-actual if home_is_favored else actual)
            else:
                top_score = "—"
                bot_score = "—"

            result_label = ("✅ WIN" if correct else "❌ LOSS") if results_in else ""

            def name_style(is_rec):
                weight = "700" if is_rec else "400"
                color  = "white" if is_rec else "#aaa"
                return weight, color

            def stat_box(val, is_rec=False, is_result=False):
                bg    = "#1e2a3a"
                color = "white"
                return (
                    f"<div style='text-align:center;background:{bg};border-radius:6px;"
                    f"padding:6px 0;font-size:14px;font-weight:600;color:{color};"
                    f"height:32px;line-height:20px'>{val}</div>"
                )

            def bet_box(team):
                return (
                    f"<div style='background:#1e2a3a;border-left:3px solid #4a6080;"
                    f"border-radius:4px;padding:0 8px;font-size:12px;font-weight:700;"
                    f"color:white;text-align:center;height:32px;line-height:32px'>"
                    f"BET {team}</div>"
                )

            def empty_box():
                return "<div style='height:32px'></div>"

            with st.container():
                st.markdown(
                    f"<div style='font-size:13px;color:#888;margin-bottom:6px'>"
                    f"<b style='color:#ccc'>{away} @ {home}</b>"
                    f"&nbsp;&nbsp;·&nbsp;&nbsp;{row['gameday']}"
                    f"{'&nbsp;&nbsp;·&nbsp;&nbsp;<b>' + result_label + '</b>' if result_label else ''}"
                    f"</div>",
                    unsafe_allow_html=True
                )

                if results_available:
                    h0, h1, h2, h3, h4 = st.columns([2.2, 1.2, 1.2, 1.2, 1.8])
                    h3.markdown("<div style='text-align:center;font-size:11px;color:#aaa;letter-spacing:1px'>SCORE</div>", unsafe_allow_html=True)
                else:
                    h0, h1, h2, h4 = st.columns([2.2, 1.2, 1.2, 1.8])

                h1.markdown("<div style='text-align:center;font-size:11px;color:#aaa;letter-spacing:1px'>SPREAD</div>",    unsafe_allow_html=True)
                h2.markdown("<div style='text-align:center;font-size:11px;color:#aaa;letter-spacing:1px'>PREDICTED</div>", unsafe_allow_html=True)

                if results_available:
                    a0, a1, a2, a3, a4 = st.columns([2.2, 1.2, 1.2, 1.2, 1.8])
                    a3.markdown(stat_box(top_score, is_result=True), unsafe_allow_html=True)
                else:
                    a0, a1, a2, a4 = st.columns([2.2, 1.2, 1.2, 1.8])

                top_w, top_c = name_style(top_is_rec)
                a0.markdown(
                    f"<div style='font-weight:{top_w};font-size:15px;color:{top_c};"
                    f"padding-top:6px;height:32px'>{top_team}</div>",
                    unsafe_allow_html=True
                )
                a1.markdown(stat_box(top_spread),                       unsafe_allow_html=True)
                a2.markdown(stat_box(top_predicted, is_rec=top_is_rec), unsafe_allow_html=True)
                a4.markdown(bet_box(top_team) if top_is_rec else empty_box(), unsafe_allow_html=True)

                st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

                if results_available:
                    b0, b1, b2, b3, b4 = st.columns([2.2, 1.2, 1.2, 1.2, 1.8])
                    b3.markdown(stat_box(bot_score, is_result=True), unsafe_allow_html=True)
                else:
                    b0, b1, b2, b4 = st.columns([2.2, 1.2, 1.2, 1.8])

                bot_w, bot_c = name_style(bot_is_rec)
                b0.markdown(
                    f"<div style='font-weight:{bot_w};font-size:15px;color:{bot_c};"
                    f"padding-top:6px;height:32px'>{bot_team}</div>",
                    unsafe_allow_html=True
                )
                b1.markdown(stat_box(bot_spread),                       unsafe_allow_html=True)
                b2.markdown(stat_box(bot_predicted, is_rec=bot_is_rec), unsafe_allow_html=True)
                b4.markdown(bet_box(bot_team) if bot_is_rec else empty_box(), unsafe_allow_html=True)

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
                    elif '🔴' in game_text or 'SKIP' in game_text.upper():
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

                col_btn, _ = st.columns([1, 3])
                with col_btn:
                    with st.expander(btn_label):
                        if game_text:
                            st.markdown(game_text)
                        else:
                            st.caption("No analysis yet. Run the notebook to generate.")

                st.divider()

    # ── Agent vs Model Evaluation ─────────────────────────────────────────────
    if cached and game_analysis:
        st.divider()
        st.subheader(f"📊 Week {week}: Agent vs Model")

        def get_confidence_local(home, away):
            key  = f"{home}_{away}"
            text = game_analysis.get(key, '')
            if '🟢' in text:
                return 'HIGH'
            elif '🟡' in text:
                return 'MEDIUM'
            elif '🔴' in text or 'SKIP' in text.upper():
                return 'SKIP'
            else:
                return 'NO_ANALYSIS'

        week_df_eval = week_df.copy()
        week_df_eval['agent_confidence'] = week_df_eval.apply(
            lambda r: get_confidence_local(r['home_team'], r['away_team']), axis=1
        )

        if results_in:
            model_correct = int(week_df_eval['model_correct'].sum())
            model_total   = len(week_df_eval)
            model_pct     = round(model_correct / model_total * 100, 1)

            high_df      = week_df_eval[week_df_eval['agent_confidence'] == 'HIGH']
            high_correct = int(high_df['model_correct'].sum())
            high_total   = len(high_df)
            high_pct     = round(high_correct / high_total * 100, 1) if high_total > 0 else 0

            med_df      = week_df_eval[week_df_eval['agent_confidence'] == 'MEDIUM']
            med_correct = int(med_df['model_correct'].sum())
            med_total   = len(med_df)
            med_pct     = round(med_correct / med_total * 100, 1) if med_total > 0 else 0

            bet_df      = week_df_eval[week_df_eval['agent_confidence'].isin(['HIGH', 'MEDIUM'])]
            bet_correct = int(bet_df['model_correct'].sum())
            bet_total   = len(bet_df)
            bet_pct     = round(bet_correct / bet_total * 100, 1) if bet_total > 0 else 0

            skip_df      = week_df_eval[week_df_eval['agent_confidence'] == 'SKIP']
            skip_correct = int(skip_df['model_correct'].sum())
            skip_total   = len(skip_df)
            skip_pct     = round(skip_correct / skip_total * 100, 1) if skip_total > 0 else 0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("📈 Model (all games)",  f"{model_correct}/{model_total}", f"{model_pct}%")
            c2.metric("🟢 Agent HIGH only",    f"{high_correct}/{high_total}",   f"{high_pct}%")
            c3.metric("🟡 Agent HIGH+MED",     f"{bet_correct}/{bet_total}",     f"{bet_pct}%")
            c4.metric("🔴 Skipped games",      f"{skip_correct}/{skip_total}",   f"{skip_pct}%",
                      help="Lower % here = agent correctly avoided bad bets")

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
with tab2:

    st.title(f"📈 {season} Season Performance")

    # Build season-wide stats from tracker
    season_df = df[
        (df['season'] == season) &
        (df['actual_margin'].notna())
    ].copy()

    if season_df.empty:
        st.warning("No completed games found for this season.")
    else:

        # ── Season summary metrics ────────────────────────────────────
        total_correct = int(season_df['model_correct'].sum())
        total_games   = len(season_df)
        total_pct     = round(total_correct / total_games * 100, 1)

        high_edge_df  = season_df[season_df['model_edge'].abs() >= 3]
        he_correct    = int(high_edge_df['model_correct'].sum())
        he_total      = len(high_edge_df)
        he_pct        = round(he_correct / he_total * 100, 1) if he_total > 0 else 0

        med_edge_df   = season_df[(season_df['model_edge'].abs() >= 1) & (season_df['model_edge'].abs() < 3)]
        me_correct    = int(med_edge_df['model_correct'].sum())
        me_total      = len(med_edge_df)
        me_pct        = round(me_correct / me_total * 100, 1) if me_total > 0 else 0

        low_edge_df   = season_df[season_df['model_edge'].abs() < 1]
        le_correct    = int(low_edge_df['model_correct'].sum())
        le_total      = len(low_edge_df)
        le_pct        = round(le_correct / le_total * 100, 1) if le_total > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Season ATS",          f"{total_correct}/{total_games}", f"{total_pct}%")
        c2.metric("High Edge (3+ pts)",  f"{he_correct}/{he_total}",       f"{he_pct}%")
        c3.metric("Med Edge (1-3 pts)",  f"{me_correct}/{me_total}",       f"{me_pct}%")
        c4.metric("Low Edge (<1 pt)",    f"{le_correct}/{le_total}",       f"{le_pct}%")

        st.divider()

        # ── Week by week ATS chart ────────────────────────────────────
        weekly = season_df.groupby('week').agg(
            correct=('model_correct', 'sum'),
            total=('model_correct', 'count')
        ).reset_index()
        weekly['pct']      = (weekly['correct'] / weekly['total'] * 100).round(1)
        weekly['record']   = weekly['correct'].astype(str) + '-' + (weekly['total'] - weekly['correct']).astype(str)
        weekly['week_lbl'] = 'Week ' + weekly['week'].astype(str)

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
            y=50, line_dash="dash", line_color="#888",
            annotation_text="Break even (50%)", annotation_position="right"
        )
        fig_bar.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='white',
            yaxis=dict(range=[0, 100], title='ATS Win %', gridcolor='#2d3748'),
            xaxis=dict(gridcolor='#2d3748'),
            showlegend=False,
            height=350,
            margin=dict(t=20, b=20)
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()

        # ── Cumulative win % over season ──────────────────────────────
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
            y=50, line_dash="dash", line_color="#888",
            annotation_text="Break even (50%)", annotation_position="right"
        )
        fig_line.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='white',
            yaxis=dict(range=[0, 100], title='Cumulative ATS Win %', gridcolor='#2d3748'),
            xaxis=dict(gridcolor='#2d3748'),
            showlegend=False,
            height=350,
            margin=dict(t=20, b=20)
        )
        st.plotly_chart(fig_line, use_container_width=True)

        st.divider()

        # ── High vs low confidence accuracy ──────────────────────────
        st.subheader("Edge Tier Accuracy")

        edge_data = pd.DataFrame([
            {'Tier': 'High Edge (3+ pts)',  'Correct': he_correct, 'Total': he_total, 'Pct': he_pct},
            {'Tier': 'Med Edge (1-3 pts)',  'Correct': me_correct, 'Total': me_total, 'Pct': me_pct},
            {'Tier': 'Low Edge (<1 pt)',    'Correct': le_correct, 'Total': le_total, 'Pct': le_pct},
        ])

        fig_edge = go.Figure()
        fig_edge.add_trace(go.Bar(
            x=edge_data['Tier'],
            y=edge_data['Pct'],
            text=[f"{r['Correct']}/{r['Total']} ({r['Pct']}%)" for _, r in edge_data.iterrows()],
            textposition='outside',
            marker_color=['#00c853', '#ffd600', '#ff5252'],
            hovertemplate='%{x}<br>%{text}<extra></extra>'
        ))
        fig_edge.add_hline(
            y=50, line_dash="dash", line_color="#888",
            annotation_text="Break even", annotation_position="right"
        )
        fig_edge.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='white',
            yaxis=dict(range=[0, 100], title='ATS Win %', gridcolor='#2d3748'),
            xaxis=dict(gridcolor='#2d3748'),
            showlegend=False,
            height=350,
            margin=dict(t=20, b=20)
        )
        st.plotly_chart(fig_edge, use_container_width=True)

        st.divider()

        # ── Best and worst weeks ──────────────────────────────────────
        st.subheader("Best & Worst Weeks")

        col_best, col_worst = st.columns(2)

        with col_best:
            st.markdown("**🏆 Best Weeks**")
            best = weekly.nlargest(3, 'pct')[['week_lbl', 'record', 'pct']]
            best.columns = ['Week', 'Record', 'Win %']
            st.dataframe(best, hide_index=True, use_container_width=True)

        with col_worst:
            st.markdown("**📉 Worst Weeks**")
            worst = weekly.nsmallest(3, 'pct')[['week_lbl', 'record', 'pct']]
            worst.columns = ['Week', 'Record', 'Win %']
            st.dataframe(worst, hide_index=True, use_container_width=True)

        st.divider()

        # ── Full season table ─────────────────────────────────────────
        with st.expander("📋 Full season week by week"):
            table = weekly[['week_lbl', 'record', 'pct', 'cum_pct']].copy()
            table.columns = ['Week', 'Record', 'Win %', 'Cumulative %']
            st.dataframe(table, hide_index=True, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: HELP & GUIDE
# ══════════════════════════════════════════════════════════════════════════════
with tab3:

    st.title("❓ Help & Guide")
    st.caption("New to sports betting or just not sure how this site works? This page covers everything.")

    st.divider()

    # ── Section 1: Betting Basics ─────────────────────────────────────────────
    st.subheader("🏈 Betting Basics")

    with st.expander("What is ATS (Against The Spread)?"):
        st.markdown("""
ATS stands for **Against The Spread**. It's the most common way to bet on NFL games and it's what this whole site is built around.

Instead of just picking who wins, you're betting on whether a team wins by more or less than a set number of points. That number is called the spread.

**Here's a simple example:**

The Chiefs are favored by 7.5 points. If you bet the Chiefs, they need to win by 8 or more for you to win. If you bet the Raiders, they just need to lose by 7 or fewer or win outright. That's it.

Vegas sets the spread to try and split betting money evenly. They don't care who wins the game. They care about getting 50% of bets on each side so they profit from the juice no matter what.
        """)

    with st.expander("What is the spread and how does Vegas set it?"):
        st.markdown("""
The spread is set by oddsmakers at sportsbooks like DraftKings or FanDuel. They factor in team strength, injuries, home field, recent form, and a bunch of other stuff.

The key thing to understand is the spread is not meant to predict the actual final margin. It's meant to generate equal action on both sides. That distinction matters.

If the public loves the Chiefs and piles money on them, Vegas moves the line to make betting the Raiders more attractive. The line is always adjusting based on where money is flowing.

This is actually where edge comes from. If Vegas has to shade a line one way to balance public money, it can create value on the other side.
        """)

    with st.expander("What is edge and why does it matter?"):
        st.markdown("""
Edge is the gap between what the model predicts and what Vegas set as the spread.

If the model thinks the Chiefs will win by 10 but the spread is only 7.5, that's a 2.5 point edge on the Chiefs. The model is saying Vegas underpriced the Chiefs.

The bigger the edge, the more the model disagrees with the market. Games with a small edge (under 1 point) are basically coin flips in the model's eyes. That's why the default filter on this site hides those games.

You want to be betting games where the model has conviction, not games where it's a coin flip.
        """)

    with st.expander("What does it mean to cover?"):
        st.markdown("""
Covering just means beating the spread.

If the Chiefs are 7.5 point favorites and win 28 to 17, they won by 11. They covered. If they win 24 to 20, they won by 4. They didn't cover.

It works the other way too. If you bet the Raiders plus 7.5 and they lose by 4, the Raiders covered even though they lost the game.

The model is trying to predict the margin of victory and figure out which side of the spread is more likely to cover.
        """)

    with st.expander("How do you actually make money betting?"):
        st.markdown("""
Honestly it's really hard and most people lose money. I want to be upfront about that.

Standard sportsbook odds are around 110 to win 100. That means you need to win about 52.4% of your bets just to break even. Most casual bettors don't hit that number.

To be profitable over time you need to consistently win more than 52.4%, bet games where there's real edge instead of gut feeling, and manage your bankroll properly. A common rule is never betting more than 2 to 5% of your total bankroll on a single game.

The model is currently at 53.85% ATS overall and 55.71% on high confidence picks. Both are above break even, which is encouraging. But I want to be clear that past performance doesn't guarantee anything going forward. There will be bad weeks.

Never bet more than you can afford to lose.
        """)

    with st.expander("What is sharp money vs public money?"):
        st.markdown("""
Public money is casual bettors going with their gut. They tend to bet popular teams, primetime games, and whoever is on a hot streak. They're not doing deep analysis.

Sharp money is professional bettors who are placing large, calculated bets based on models and data. When sharps bet big, the line moves.

Watching line movement can tell you a lot. If the Chiefs open at 7 and move to 7.5, someone is betting the Chiefs heavily. If it's sharp money driving that, it's a signal worth paying attention to.

When the model and sharp money agree on the same side, that's a strong signal. When they disagree, the agent will flag it in the matchup analysis and it's worth being cautious.
        """)

    st.divider()

    # ── Section 2: How to Use the Website ────────────────────────────────────
    st.subheader("🖥️ How to Use This Website")

    with st.expander("How do I read the game cards?"):
        st.markdown("""
Each card shows one matchup for the week. Here's what the columns mean:

**SPREAD** is the Vegas line. A negative number means that team is favored.

**PREDICTED** is what the model thinks the margin will be. Compare this to the spread to understand the edge.

**SCORE** shows the final score after the game is played. It's blank until results come in.

**BET X** shows which side the model recommends. The bold team name is who the model likes.

After results are in, each card will show either WIN or LOSS based on whether the model's pick covered.
        """)

    with st.expander("What do the agent confidence colors mean?"):
        st.markdown("""
The colored button on each game card tells you how confident the AI agent is after analyzing that matchup.

🟢 **High** means the model edge is strong and outside signals like injuries, line movement, and historical data all point the same direction. These are the games worth prioritizing.

🟡 **Medium** means there's edge but something is giving mixed signals. Maybe sharp money is split or there's an injury that could swing things. Worth considering but not a lock.

🔴 **Skip** means the agent is recommending you pass on this game. The edge is too small, signals are conflicting, or there's too much uncertainty. Not every game is worth betting.

Click the Matchup Analysis button on any card to read the full reasoning.
        """)

    with st.expander("What is the edge filter in the sidebar?"):
        st.markdown("""
The Min Edge slider controls which games show up on the page.

At 0.0 you see every game. At 1.0 (the default) you only see games where the model disagrees with Vegas by at least 1 point. At 3.0 you're only seeing the high conviction plays.

I'd recommend keeping it at 1.0 as a starting point. Games under 1 point edge are basically too close to call and not worth the risk.
        """)

    with st.expander("How often does the site update?"):
        st.markdown("""
During the season the site runs on an automated schedule through GitHub Actions.

Monday morning it posts early predictions for the upcoming week using the initial Vegas lines. Thursday night it refreshes those predictions after injury reports come out. Sunday morning it locks in final predictions before kickoff. The following Monday it fills in the results from the previous week and the cycle starts over.

During the offseason the site just shows historical data from past seasons. Everything spins back up when the season kicks off in September.
        """)

    with st.expander("What is the Season Performance tab?"):
        st.markdown("""
The Season Performance tab is where you can see how the model has done across the whole season, not just one week.

It shows a week by week bar chart of ATS win percentage, a cumulative trend line showing how accuracy has moved over time, and a breakdown of how high edge games performed compared to low edge games.

There's also a best and worst weeks section and a full season table if you want to dig into the numbers.
        """)

    st.divider()

    # ── Section 3: Behind the Scenes ─────────────────────────────────────────
    st.subheader("🔧 Behind the Scenes")

    with st.expander("How does the prediction model work?"):
        st.markdown("""
The model is an XGBoost pipeline trained on over 4,300 NFL games going back 15+ seasons.

I engineered 79 features for each game. The main ones are rolling EPA (Expected Points Added) which measures offensive and defensive efficiency, strength of schedule, All-Pro roster quality as a proxy for talent, injury impact, QB changes, coaching history, and home field advantage.

The model predicts the margin of victory for the home team. That predicted margin gets compared to the Vegas spread to calculate edge. If the model says home team wins by 10 and the spread is 7.5, the edge is 2.5 points in favor of betting the home team.

The model is retrained periodically as new data comes in and the All-Pro data gets updated manually each January.
        """)

    with st.expander("What is the LLM agent and what does it do?"):
        st.markdown("""
The agent is built on top of the XGBoost model using LlamaIndex and Anthropic's Claude API.

It has 5 tools it can call: model predictions, injury reports, line movement data, historical head to head matchups going back to 2015, and a model confidence analyzer.

Each week it goes through every game, calls those tools, and reasons about whether the model's prediction is backed up by real world signals. It's not overriding the model. It's asking whether everything else lines up with what the model is saying.

If the model likes a team, sharp money likes that team, they're healthy, and they dominate this matchup historically, the agent marks it high confidence. If the model likes a team but their star QB is out and sharp money is going the other way, the agent will tell you to skip it.

The idea is that raw model predictions are a starting point. The agent adds a layer of reasoning to help filter out plays where the edge might just be noise.
        """)

    with st.expander("How accurate is the model?"):
        st.markdown("""
On random test data the model hit 53.85% ATS overall and 55.71% on high confidence picks. The 2025 season weeks 10-17 were also essentially real-world data for the model, so the results are promising. The break even threshold at standard sportsbook odds is 52.4%, so both numbers are above that.

Week 10 was the strongest week so far at 11 out of 14 correct.

I want to be honest though. One season of data is a small sample. The model has shown real edge but I wouldn't read too much into any single week or even a single season. The goal is to track this over multiple seasons and see if the edge holds up.
        """)

    with st.expander("What data does it use?"):
        st.markdown("""
The model pulls play by play and schedule data from nflreadpy going back to 1999. The All-Pro data is a custom CSV I built covering selections from 1997 to 2025, which gets used as a proxy for roster talent.

The agent currently uses mock injury and line movement data for demonstration purposes. Integrating real time APIs for those two data sources is on the roadmap for the 2026 season, which would make the agent's analysis much more accurate.
        """)

    with st.expander("Is this financial advice?"):
        st.markdown("""
No. This is a personal data science project. I built it to explore whether a machine learning model can find a consistent edge against the spread.

Nothing on this site should be taken as betting or financial advice. Sports betting involves real financial risk. Always bet responsibly.
        """)

    st.divider()
    st.caption("Built by Joseph Schoenbaum · [GitHub](https://github.com/joscho11/BettingEdgeContinued) · [Dashboard](https://joschobetting.streamlit.app)")