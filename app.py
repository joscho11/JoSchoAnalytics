import streamlit as st
import pandas as pd
import json
import os
import glob
import uuid
import time
import html as _html
import re as _re
import requests as req
from datetime import datetime as dt
import plotly.graph_objects as go

st.set_page_config(
    page_title="BettingEdge | NFL Predictions",
    page_icon="🏈",
    layout="wide"
)

def track_pageview(measurement_id, api_secret):
    if 'ga_client_id' not in st.session_state:
        st.session_state.ga_client_id = str(uuid.uuid4())
    if 'ga_session_id' not in st.session_state:
        st.session_state.ga_session_id = str(int(time.time()))
    try:
        req.post(
            "https://www.google-analytics.com/mp/collect",
            params={"measurement_id": measurement_id, "api_secret": api_secret},
            json={
                "client_id": st.session_state.ga_client_id,
                "events": [{
                    "name": "page_view",
                    "params": {
                        "page_title": "BettingEdge | NFL Predictions",
                        "page_location": "https://joschobetting.streamlit.app",
                        "session_id": st.session_state.ga_session_id,
                        "engagement_time_msec": "100"
                    }
                }]
            },
            timeout=3
        )
    except Exception:
        pass

GOOGLE_ANALYTICS_ID = st.secrets.get('GOOGLE_ANALYTICS_ID', '')
GA_API_SECRET       = st.secrets.get('GA_API_SECRET', '')

if GOOGLE_ANALYTICS_ID and GA_API_SECRET and 'ga_tracked' not in st.session_state:
    st.session_state.ga_tracked = True
    track_pageview(GOOGLE_ANALYTICS_ID, GA_API_SECRET)

st.markdown("""
    <style>
    details {
        border: none !important;
        box-shadow: none !important;
    }
    details summary {
        font-size: 11px !important;
        color: var(--conf-color, #aaa) !important;
        background-color: var(--conf-bg, #2d3748) !important;
        border-radius: 6px !important;
        padding: 4px 10px !important;
        border: 1px solid var(--conf-border, #4a5568) !important;
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
        border: 1px solid var(--conf-border, #4a5568) !important;
        border-top: none !important;
        border-radius: 0 0 6px 6px !important;
        padding: 10px !important;
        font-size: 13px !important;
        line-height: 1.6 !important;
        color: #ddd !important;
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

# ── Live accuracy stats (used in Help tab) ────────────────────────────────────
_completed = df[df['model_correct'].notna()]
_overall_correct = int(_completed['model_correct'].sum())
_overall_total   = len(_completed)
_overall_pct     = round(_overall_correct / _overall_total * 100, 1) if _overall_total > 0 else 0

_hc_correct, _hc_total = 0, 0
for _af in glob.glob("betting/agent_analysis_*.json"):
    try:
        _stem = os.path.basename(_af).replace('.json', '').split('_')
        _s, _w = int(_stem[2]), int(_stem[3].replace('week', ''))
        _wdf = df[(df['season'] == _s) & (df['week'] == _w) & df['model_correct'].notna()]
        with open(_af) as _f:
            _ga = json.load(_f)
        for _, _r in _wdf.iterrows():
            _text = _ga.get(f"{_r['home_team']}_{_r['away_team']}", '')
            if '🟢' in _text:
                _hc_total += 1
                _hc_correct += int(_r['model_correct'])
    except Exception:
        pass
_hc_pct = round(_hc_correct / _hc_total * 100, 1) if _hc_total > 0 else None

@st.cache_data(ttl=3600)
def load_actual_fantasy_pts(season: int, week: int) -> dict:
    try:
        import nflreadpy as nfl
        stats = nfl.load_player_stats([season])
        if hasattr(stats, 'to_pandas'):
            stats = stats.to_pandas()
        stats = stats[(stats['season_type'] == 'REG') & (stats['week'] == week)]
        stats = stats[stats['position'].isin(['QB', 'RB', 'WR', 'TE'])]
        stats['actual_half_ppr'] = (
            stats['passing_yards'].fillna(0) * 0.04 +
            stats['passing_tds'].fillna(0) * 4 +
            stats['passing_interceptions'].fillna(0) * -2 +
            stats['rushing_yards'].fillna(0) * 0.1 +
            stats['rushing_tds'].fillna(0) * 6 +
            stats['receptions'].fillna(0) * 0.5 +
            stats['receiving_yards'].fillna(0) * 0.1 +
            stats['receiving_tds'].fillna(0) * 6 +
            stats['rushing_fumbles_lost'].fillna(0) * -2 +
            stats['receiving_fumbles_lost'].fillna(0) * -2
        )
        return stats.set_index('player_id')['actual_half_ppr'].to_dict()
    except Exception:
        return {}

@st.cache_data(ttl=3600)
def load_actual_qb_yards(season: int, week: int) -> tuple[dict, dict]:
    try:
        import nflreadpy as nfl
        stats = nfl.load_player_stats([season])
        if hasattr(stats, 'to_pandas'):
            stats = stats.to_pandas()
        stats = stats[(stats['season_type'] == 'REG') & (stats['week'] == week)]
        stats = stats[stats['position'] == 'QB']
        pass_yds = stats.set_index('player_id')['passing_yards'].fillna(0).to_dict()
        rush_yds = stats.set_index('player_id')['rushing_yards'].fillna(0).to_dict()
        return pass_yds, rush_yds
    except Exception:
        return {}, {}

@st.cache_data(ttl=3600)
def load_actual_rb_yards(season: int, week: int) -> tuple[dict, dict]:
    try:
        import nflreadpy as nfl
        stats = nfl.load_player_stats([season])
        if hasattr(stats, 'to_pandas'):
            stats = stats.to_pandas()
        stats = stats[(stats['season_type'] == 'REG') & (stats['week'] == week)]
        stats = stats[stats['position'] == 'RB']
        rush = stats.set_index('player_id')['rushing_yards'].fillna(0).to_dict()
        rec  = stats.set_index('player_id')['receiving_yards'].fillna(0).to_dict()
        return rush, rec
    except Exception:
        return {}, {}

@st.cache_data(ttl=3600)
def load_actual_wr_stats(season: int, week: int) -> tuple[dict, dict]:
    try:
        import nflreadpy as nfl
        stats = nfl.load_player_stats([season])
        if hasattr(stats, 'to_pandas'):
            stats = stats.to_pandas()
        stats = stats[(stats['season_type'] == 'REG') & (stats['week'] == week)]
        stats = stats[stats['position'] == 'WR']
        rec_yds = stats.set_index('player_id')['receiving_yards'].fillna(0).to_dict()
        recs    = stats.set_index('player_id')['receptions'].fillna(0).to_dict()
        return rec_yds, recs
    except Exception:
        return {}, {}

@st.cache_data(ttl=3600)
def load_actual_te_stats(season: int, week: int) -> tuple[dict, dict]:
    try:
        import nflreadpy as nfl
        stats = nfl.load_player_stats([season])
        if hasattr(stats, 'to_pandas'):
            stats = stats.to_pandas()
        stats = stats[(stats['season_type'] == 'REG') & (stats['week'] == week)]
        stats = stats[stats['position'] == 'TE']
        rec_yds = stats.set_index('player_id')['receiving_yards'].fillna(0).to_dict()
        recs    = stats.set_index('player_id')['receptions'].fillna(0).to_dict()
        return rec_yds, recs
    except Exception:
        return {}, {}

@st.cache_data(ttl=3600)
def load_agent_analysis(week: int, season: int) -> dict:
    cache_file = f"betting/agent_analysis_{season}_week{week}.json"
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            return json.load(f)
    return None

def _md_to_html(text: str) -> str:
    """Convert simple agent-analysis markdown to HTML for use inside a <details> block."""
    escaped = _html.escape(text)
    escaped = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
    lines = []
    for line in escaped.split('\n'):
        stripped = line.strip()
        if stripped.startswith('- '):
            lines.append(f'&bull;&nbsp;{stripped[2:]}')
        else:
            lines.append(stripped)
    return '<br>'.join(lines)

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
    current_season = now.year - 1 if now.month < 9 else now.year
    next_season    = current_season + 1
    st.info(
        f"🏈 **NFL Offseason**: The {current_season} season has concluded. Look at WEEK 10 for demo agent analysis. "
        f"Predictions will return when the {next_season} season kicks off in September. "
        "Browse past predictions using the sidebar."
    )

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["🏈 Weekly Predictions", "📈 Season Performance", "🏆 Fantasy", "❓ Help & Guide"])

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

        def fmt(val):
            return f"{val:+.1f}"

        def name_style(is_rec):
            weight = "700" if is_rec else "400"
            color  = "white" if is_rec else "#aaa"
            return weight, color

        def stat_box(val, is_rec=False, is_result=False):
            bg    = "#1a3a2a" if is_rec else "#1e2a3a"
            color = "#00c853" if is_rec else "white"
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

        for _, row in filtered_df.iterrows():
            home      = row['home_team']
            away      = row['away_team']
            spread    = row['spread_line']
            predicted = row['predicted_margin']
            edge      = row['model_edge']

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

                st.divider()

    # ── Agent vs Model Evaluation ─────────────────────────────────────────────
    if cached and game_analysis:
        st.divider()
        st.subheader(f"📊 Week {week}: Agent vs Model")

        week_df_eval = week_df.copy()
        week_df_eval['agent_confidence'] = week_df_eval.apply(
            lambda r: get_confidence(r['home_team'], r['away_team'], game_analysis), axis=1
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
# TAB 3: FANTASY PROJECTIONS
# ══════════════════════════════════════════════════════════════════════════════
with tab3:

    st.title(f"🏆 Week {week} Fantasy Projections — Half-PPR")

    proj_files = sorted(glob.glob("fantasy/fantasy_projections/projections_*.csv"), reverse=True)

    # Build a lookup of available projection files
    available = {}
    for f in proj_files:
        try:
            stem  = os.path.basename(f).replace(".csv", "")
            parts = stem.split("_")
            s = int(parts[1])
            w = int(parts[2].replace("week", ""))
            available[(s, w)] = f
        except (IndexError, ValueError):
            continue

    if not proj_files:
        st.info(
            "No fantasy projections found. "
            f"Open `fantasy/predict_fantasy.ipynb`, set `TARGET_WEEK = {week}` and `TARGET_SEASON = {season}` "
            f"in the Parameters cell, and run all cells to generate Week {week} projections."
        )
    elif (season, week) not in available:
        st.info(
            f"No fantasy projections available for Season {season} · Week {week}. "
            f"Available weeks: {', '.join(f'W{w}' for (s, w) in sorted(available) if s == season) or 'none for this season'}. "
            "Use the sidebar to select a week with projections, or run the fantasy notebook to generate them."
        )
    else:
        proj_df = pd.read_csv(available[(season, week)])

        # Actual results (available after week is played)
        actuals = load_actual_fantasy_pts(season, week)
        actuals_in = bool(actuals)
        actual_qb_pass_yds, actual_qb_rush_yds = load_actual_qb_yards(season, week) if actuals_in else ({}, {})
        actual_rush_yds, actual_rb_rec_yds = load_actual_rb_yards(season, week) if actuals_in else ({}, {})
        actual_wr_rec_yds, actual_wr_recs  = load_actual_wr_stats(season, week) if actuals_in else ({}, {})
        actual_te_rec_yds, actual_te_recs  = load_actual_te_stats(season, week) if actuals_in else ({}, {})

        # Load cached agent analysis if available
        fa_path = f"fantasy/agent_analysis_{season}_week{week}.json"
        fantasy_analysis = None
        if os.path.exists(fa_path):
            with open(fa_path) as _f:
                fantasy_analysis = json.load(_f)

        if actuals_in:
            st.success(f"Results are in! Actual stats are now shown alongside projections for Week {week}.")
        else:
            st.info("Games not yet played. Actual stats will appear here once the week's results are in.")

        st.divider()

        player_search = st.text_input(
            "🔍 Search player",
            placeholder="e.g. Mahomes, Jefferson, Kelce…",
            key="fantasy_search"
        )

        ptab_qb, ptab_rb, ptab_wr, ptab_te = st.tabs(["QB", "RB", "WR", "TE"])

        def injury_icon(score):
            if score >= 0.9:   return "✅"
            if score >= 0.5:   return "🟡"
            if score > 0:      return "⚠️"
            return "❌"

        def ordinal(n):
            n = int(n)
            if 11 <= (n % 100) <= 13:
                return f"{n}th"
            return f"{n}{['th','st','nd','rd','th'][min(n % 10, 4)]}"

        def rank_color(rank, total=32):
            ratio = (total - int(rank)) / (total - 1)
            r = int(255 * (1 - ratio))
            g = int(82 + 118 * ratio)
            return f"color: rgb({r},{g},82); font-weight: 600"

        def total_color(val, lo=16.0, hi=30.0):
            ratio = max(0.0, min(1.0, (val - lo) / (hi - lo)))
            r = int(255 * (1 - ratio))
            g = int(82 + 118 * ratio)
            return f"color: rgb({r},{g},82); font-weight: 600"

        for ptab, pos in zip([ptab_qb, ptab_rb, ptab_wr, ptab_te], ["QB", "RB", "WR", "TE"]):
            with ptab:
                pos_subset = proj_df[proj_df["position"] == pos]
                if pos == "QB":
                    pos_subset = pos_subset[pos_subset["depth_chart_position"] == 1]
                    pos_subset = pos_subset.sort_values("projected_pts", ascending=False).drop_duplicates(subset="team")
                top_n = 40 if pos in ("RB", "WR") else 20
                pos_df = pos_subset.sort_values("projected_pts", ascending=False)
                if player_search:
                    mask = pos_df["player_display_name"].str.contains(player_search, case=False, na=False)
                    pos_df = pos_df[mask]
                else:
                    pos_df = pos_df.head(top_n)
                pos_df = pos_df.reset_index(drop=True)
                pos_df.index += 1

                has_qb_stats = pos == "QB" and "pred_qb_pass_yards" in pos_df.columns
                has_rb_yds   = pos == "RB" and "pred_rush_yards" in pos_df.columns
                has_wr_stats = pos == "WR" and "pred_wr_rec_yards" in pos_df.columns
                has_te_stats = pos == "TE" and "pred_te_rec_yards" in pos_df.columns

                display = pos_df[["player_id", "player_display_name", "team", "opponent_team",
                                   "projected_pts", "injury_status_score",
                                   "is_home", "off_epa_roll4", "off_epa_rank",
                                   "implied_team_total"]].copy()
                if has_qb_stats:
                    display["Proj Pass Yds"] = pos_df["pred_qb_pass_yards"].fillna(0).round(0).astype(int)
                    display["Proj Rush Yds"] = pos_df["pred_qb_rush_yards"].fillna(0).round(0).astype(int)
                if has_rb_yds:
                    display["Proj Rush Yds"] = pos_df["pred_rush_yards"].fillna(0).round(0).astype(int)
                    display["Proj Rec Yds"]  = pos_df["pred_rec_yards"].fillna(0).round(0).astype(int)
                if has_wr_stats:
                    display["Proj Receptions"] = pos_df["pred_wr_receptions"].fillna(0).round(1)
                    display["Proj Rec Yds"]    = pos_df["pred_wr_rec_yards"].fillna(0).round(0).astype(int)
                if has_te_stats:
                    display["Proj Receptions"] = pos_df["pred_te_receptions"].fillna(0).round(1)
                    display["Proj Rec Yds"]    = pos_df["pred_te_rec_yards"].fillna(0).round(0).astype(int)

                sep = display["is_home"].map(lambda h: "vs" if h == 1 else "@")
                display["Player"]      = display["player_display_name"] + " - " + display["team"]
                display["Opponent"]    = sep + " " + display["opponent_team"]
                display["Health"]      = display["injury_status_score"].map(injury_icon)
                display["Proj Pts"]    = display["projected_pts"].round(1)
                display["Off EPA"]     = display["off_epa_roll4"].round(3)
                display["EPA Rank"]    = display["off_epa_rank"].map(ordinal)
                display["Team Total"]  = display["implied_team_total"].round(1)

                if has_qb_stats:
                    base_cols = ["Player", "Opponent", "Proj Pts", "Proj Pass Yds", "Proj Rush Yds", "Off EPA", "EPA Rank", "Team Total", "Health"]
                elif has_rb_yds:
                    base_cols = ["Player", "Opponent", "Proj Pts", "Proj Rush Yds", "Proj Rec Yds", "Off EPA", "EPA Rank", "Team Total", "Health"]
                elif has_wr_stats or has_te_stats:
                    base_cols = ["Player", "Opponent", "Proj Pts", "Proj Receptions", "Proj Rec Yds", "Off EPA", "EPA Rank", "Team Total", "Health"]
                else:
                    base_cols = ["Player", "Opponent", "Proj Pts", "Off EPA", "EPA Rank", "Team Total", "Health"]

                if actuals_in:
                    _actual_raw = display["player_id"].map(actuals)
                    display["Actual Pts"] = pd.to_numeric(_actual_raw, errors="coerce").round(1)
                    if has_qb_stats:
                        display["Actual Pass Yds"] = pd.to_numeric(display["player_id"].map(actual_qb_pass_yds), errors="coerce")
                        display["Actual Rush Yds"] = pd.to_numeric(display["player_id"].map(actual_qb_rush_yds), errors="coerce")
                        tbl_cols = base_cols + ["Actual Pts", "Actual Pass Yds", "Actual Rush Yds"]
                    elif has_rb_yds:
                        display["Actual Rush Yds"] = pd.to_numeric(display["player_id"].map(actual_rush_yds),    errors="coerce")
                        display["Actual Rec Yds"]  = pd.to_numeric(display["player_id"].map(actual_rb_rec_yds),  errors="coerce")
                        tbl_cols = base_cols + ["Actual Pts", "Actual Rush Yds", "Actual Rec Yds"]
                    elif has_wr_stats:
                        display["Actual Receptions"] = pd.to_numeric(display["player_id"].map(actual_wr_recs),    errors="coerce")
                        display["Actual Rec Yds"]    = pd.to_numeric(display["player_id"].map(actual_wr_rec_yds), errors="coerce")
                        tbl_cols = base_cols + ["Actual Pts", "Actual Receptions", "Actual Rec Yds"]
                    elif has_te_stats:
                        display["Actual Receptions"] = pd.to_numeric(display["player_id"].map(actual_te_recs),    errors="coerce")
                        display["Actual Rec Yds"]    = pd.to_numeric(display["player_id"].map(actual_te_rec_yds), errors="coerce")
                        tbl_cols = base_cols + ["Actual Pts", "Actual Receptions", "Actual Rec Yds"]
                    else:
                        tbl_cols = base_cols + ["Actual Pts"]
                else:
                    tbl_cols = base_cols

                tbl = display[tbl_cols].copy()

                def style_table(df, _d=display):
                    styles = pd.DataFrame("", index=df.index, columns=df.columns)
                    for i, rank in enumerate(_d["off_epa_rank"]):
                        styles.iloc[i, df.columns.get_loc("Off EPA")]  = rank_color(rank)
                        styles.iloc[i, df.columns.get_loc("EPA Rank")] = rank_color(rank)
                    for i, val in enumerate(_d["implied_team_total"]):
                        styles.iloc[i, df.columns.get_loc("Team Total")] = total_color(val)
                    styles["Proj Pts"] = "font-weight: 700; font-size: 15px"
                    if "Actual Pts" in df.columns:
                        styles["Actual Pts"] = "font-weight: 700; font-size: 15px"
                    return styles

                _dnp_note = "Blank = player did not play (DNP) in this game."
                col_config = {
                    "Player":     st.column_config.TextColumn("Player",
                                      help="Player name and NFL team."),
                    "Opponent":   st.column_config.TextColumn("Opponent",
                                      help="This week's opponent. '@' = away game, 'vs' = home game. Note: column sorts alphabetically — meaningful numeric sort not available for matchup labels."),
                    "EPA Rank":   st.column_config.TextColumn("EPA Rank",
                                      help="Team's offensive EPA rank among all 32 NFL teams this season (1 = best offense, 32 = worst). Note: sorts alphabetically due to a Streamlit limitation — use Off EPA for accurate numeric sorting."),
                    "Health":     st.column_config.TextColumn("Health",
                                      help="Player's injury status from the weekly NFL injury report.\n\n✅ Healthy  🟡 Questionable  ⚠️ Doubtful  ❌ Out\n\nNote: sorts alphabetically due to a Streamlit limitation."),
                    "Proj Pts":   st.column_config.NumberColumn("Proj Pts",   format="%.1f",
                                      help="Projected half-PPR fantasy points for this week, generated by our XGBoost model. Half-PPR scoring: 0.5 pts per reception, 1 pt per 10 rush/rec yards, 6 pts per TD."),
                    "Off EPA":    st.column_config.NumberColumn("Off EPA",    format="%+.3f",
                                      help="Team's offensive Expected Points Added (EPA) per play, averaged over the last 4 games. EPA measures how many points each play is worth above expectation. Higher = more efficient offense."),
                    "Team Total": st.column_config.NumberColumn("Team Total", format="%.1f",
                                      help="Vegas implied team total — the number of points Vegas expects this team to score. Derived by splitting the game over/under based on the point spread. Higher = Vegas expects more scoring, which generally means more fantasy opportunity."),
                }
                if has_qb_stats:
                    col_config["Proj Pass Yds"] = st.column_config.NumberColumn("Proj Pass Yds", format="%d",
                                      help="Projected passing yards for this game, from a separate XGBoost model trained specifically on QB passing stats. Useful as a reference for pass yards prop bets.")
                    col_config["Proj Rush Yds"] = st.column_config.NumberColumn("Proj Rush Yds", format="%d",
                                      help="Projected rushing yards for this game, from a separate XGBoost model trained on QB rushing stats. Useful as a reference for rush yards prop bets.")
                if has_rb_yds:
                    col_config["Proj Rush Yds"] = st.column_config.NumberColumn("Proj Rush Yds", format="%d",
                                      help="Projected rushing yards for this game, from a separate XGBoost model trained on RB rushing stats. Useful as a reference for rush yards prop bets.")
                    col_config["Proj Rec Yds"]  = st.column_config.NumberColumn("Proj Rec Yds",  format="%d",
                                      help="Projected receiving yards for this game, from a separate XGBoost model trained on RB receiving stats. Useful as a reference for receiving yards prop bets.")
                if (has_wr_stats or has_te_stats):
                    col_config["Proj Receptions"] = st.column_config.NumberColumn("Proj Receptions", format="%.1f",
                                      help="Projected number of receptions for this game, from a separate XGBoost model. Useful as a reference for receptions prop bets.")
                    col_config["Proj Rec Yds"]    = st.column_config.NumberColumn("Proj Rec Yds",    format="%d",
                                      help="Projected receiving yards for this game, from a separate XGBoost model. Useful as a reference for receiving yards prop bets.")
                if actuals_in:
                    col_config["Actual Pts"]        = st.column_config.NumberColumn("Actual Pts",        format="%.1f",
                                      help=f"Actual half-PPR fantasy points scored in this game. {_dnp_note}")
                    col_config["Actual Pass Yds"]   = st.column_config.NumberColumn("Actual Pass Yds",   format="%d",
                                      help=f"Actual passing yards recorded in this game. {_dnp_note}")
                    col_config["Actual Rush Yds"]   = st.column_config.NumberColumn("Actual Rush Yds",   format="%d",
                                      help=f"Actual rushing yards recorded in this game. {_dnp_note}")
                    col_config["Actual Rec Yds"]    = st.column_config.NumberColumn("Actual Rec Yds",    format="%d",
                                      help=f"Actual receiving yards recorded in this game. {_dnp_note}")
                    col_config["Actual Receptions"] = st.column_config.NumberColumn("Actual Receptions", format="%.1f",
                                      help=f"Actual number of receptions recorded in this game. {_dnp_note}")

                st.dataframe(
                    tbl.style.apply(style_table, axis=None),
                    use_container_width=True,
                    column_config=col_config,
                )

                # ── Agent Analysis ────────────────────────────────────────────
                if fantasy_analysis and pos in fantasy_analysis:
                    pa = fantasy_analysis[pos]
                    st.markdown("#### 🤖 Agent Analysis")

                    # Headers row
                    h1, h2 = st.columns(2)
                    h1.markdown(
                        "<div style='background:#0d2b0d;border:1px solid #00c853;"
                        "border-radius:8px;padding:10px 16px'>"
                        "<span style='color:#00c853;font-weight:700;font-size:13px;"
                        "letter-spacing:1px'>📈 LIKELY TO OUTPERFORM</span></div>",
                        unsafe_allow_html=True
                    )
                    h2.markdown(
                        "<div style='background:#2b0d0d;border:1px solid #ff5252;"
                        "border-radius:8px;padding:10px 16px'>"
                        "<span style='color:#ff5252;font-weight:700;font-size:13px;"
                        "letter-spacing:1px'>📉 LIKELY TO UNDERPERFORM</span></div>",
                        unsafe_allow_html=True
                    )

                    # Paired rows so each card pair shares the same height
                    ups = pa.get("upside", [])
                    dns = pa.get("downside", [])
                    for up, dn in zip(ups, dns):
                        card_style = "display:flex;flex-direction:column;justify-content:space-between;" \
                                     "border-radius:4px;padding:10px 14px;height:100%"
                        row_html = (
                            "<div style='display:grid;grid-template-columns:1fr 1fr;"
                            "gap:8px;align-items:stretch;margin-top:8px'>"
                            f"<div style='background:#1a2a1a;border-left:3px solid #00c853;{card_style}'>"
                            f"<b style='color:#e8e8e8'>{up['player']}</b> "
                            f"<span style='color:#888;font-size:12px'>({up['team']})</span><br>"
                            f"<span style='color:#aaa;font-size:13px'>{up['reason']}</span>"
                            f"</div>"
                            f"<div style='background:#2a1a1a;border-left:3px solid #ff5252;{card_style}'>"
                            f"<b style='color:#e8e8e8'>{dn['player']}</b> "
                            f"<span style='color:#888;font-size:12px'>({dn['team']})</span><br>"
                            f"<span style='color:#aaa;font-size:13px'>{dn['reason']}</span>"
                            f"</div>"
                            "</div>"
                        )
                        st.markdown(row_html, unsafe_allow_html=True)
                else:
                    st.info(
                        "No agent analysis available for this week. "
                        "Run `fantasy/fantasy_agent.ipynb` to generate it."
                    )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: HELP & GUIDE
# ══════════════════════════════════════════════════════════════════════════════
with tab4:

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
        _hc_line = f" and **{_hc_pct}%** on high confidence picks" if _hc_pct is not None else ""
        st.markdown(f"""
Honestly it's really hard and most people lose money. I want to be upfront about that.

Standard sportsbook odds are around 110 to win 100. That means you need to win about 52.4% of your bets just to break even. Most casual bettors don't hit that number.

To be profitable over time you need to consistently win more than 52.4%, bet games where there's real edge instead of gut feeling, and manage your bankroll properly. A common rule is never betting more than 2 to 5% of your total bankroll on a single game.

The model is currently at **{_overall_pct}% ATS** overall ({_overall_correct}/{_overall_total}){_hc_line}. Both are above break even, which is encouraging. But I want to be clear that past performance doesn't guarantee anything going forward. There will be bad weeks.

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

    # ── Section 3: Fantasy Projections ───────────────────────────────────────
    st.subheader("🏆 Fantasy Projections")

    with st.expander("How do the fantasy projections work?"):
        st.markdown("""
The Fantasy tab uses a separate machine learning system from the betting model. There are four XGBoost models — one for each position (QB, RB, WR, TE) — each trained on NFL player stats from 2020 through 2024 with the 2025 season held out as a real-world test.

Each model predicts **half-PPR fantasy points** for the upcoming week based on roughly 80 features, including:

- The player's recent production (3 and 5-game rolling averages for targets, carries, receiving yards, etc.)
- Their team's offensive efficiency (EPA per play, yards per play, red zone rate)
- The opponent's defensive quality (EPA allowed, pass rate faced, red zone defense)
- Vegas implied team total — how many points Vegas expects the team to score
- Injury and availability status for the player and their key teammates
- Depth chart position
- Home/away split, weather, and surface

The models are retrained each offseason as more data becomes available.
        """)

    with st.expander("How accurate are the fantasy projections?"):
        st.markdown("""
The models were evaluated on the 2025 season (weeks 10–17) against a simple 3-week rolling average baseline:

| Position | Model MAE | Baseline MAE | Improvement |
|----------|-----------|--------------|-------------|
| QB | 7.1 pts | 7.5 pts | ✅ Better |
| RB | 4.5 pts | 4.6 pts | ✅ Better |
| WR | 3.9 pts | 4.1 pts | ✅ Better |
| TE | 3.3 pts | 3.5 pts | ✅ Better |

MAE (Mean Absolute Error) is the average number of points the projection was off by. So for WR, the model was off by about 3.9 points on average. Given the inherent variance in fantasy football, this is a reasonable result — but any individual week can be much higher or lower.

The projections are most useful as a relative ranking tool rather than a precise point forecast. A player projected at 18 points is likely to outscore one projected at 10, but the exact numbers should be treated as estimates.
        """)

    with st.expander("What are the prop stat columns?"):
        st.markdown("""
In addition to projected fantasy points, each position tab shows position-specific stat projections from eight separate XGBoost models:

| Column | Position | What it predicts |
|--------|----------|-----------------|
| Proj Pass Yds | QB | Passing yards |
| Proj Rush Yds | QB / RB | Rushing yards |
| Proj Rec Yds | RB / WR / TE | Receiving yards |
| Proj Receptions | WR / TE | Number of receptions |

These prop stat models were trained on the same data as the main models but with each individual stat as the target. They're useful as a rough reference when looking at player prop bets on sportsbooks (e.g. over/under pass yards, reception totals).

A few things to keep in mind:
- The prop projections are **independent** models — their values won't perfectly add up to the fantasy point total
- QB passing yards has the highest error (~70 yards off on average), so treat it as directional
- RB and TE receiving yards are the most accurate prop models (~10–14 yards MAE)
        """)

    with st.expander("What do the column headers mean?"):
        st.markdown("""
**Player** — Player name and their NFL team.

**Opponent** — This week's opponent. `@` means away game, `vs` means home game.

**Proj Pts** — Projected half-PPR fantasy points. Half-PPR scoring: 0.5 pts per reception, 1 pt per 10 rush or receiving yards, 6 pts per TD.

**Off EPA** — The team's offensive efficiency over the last 4 games, measured in Expected Points Added per play. Higher is better. See "What is Off EPA?" below for a full explanation.

**EPA Rank** — Where the team's offense ranks among all 32 teams this season (1st = best, 32nd = worst). Color-coded green to red.

**Team Total** — Vegas implied team total: how many points Vegas expects this team to score. Higher means more expected scoring opportunity for that team's players.

**Health** — The player's injury status from the NFL injury report: ✅ Healthy · 🟡 Questionable · ⚠️ Doubtful · ❌ Out. Players officially ruled Out are removed from the projections entirely.

**Actual Pts / Actual [stat]** — Once the week's games are played, actual fantasy points and stats fill in automatically. A blank cell means the player did not play (DNP) in that game.
        """)

    with st.expander("What is Off EPA?"):
        st.markdown("""
**Off EPA** stands for Offensive Expected Points Added per play, averaged over the team's last 4 games.

EPA measures how much each play moves the needle toward scoring. A 5-yard gain on 3rd and 4 is worth a lot more EPA than a 5-yard gain on 1st and 10. So EPA per play is a better measure of offensive efficiency than yards or points, because it accounts for down, distance, and field position.

- **Positive (e.g. +0.15)** — the offense has been efficient recently, generating more value per play than expected
- **Near zero (e.g. +0.01)** — average offense
- **Negative (e.g. -0.12)** — the offense has been struggling

League average hovers near 0. Values above +0.10 are strong, below -0.10 are poor.

This matters for fantasy because players on efficient offenses tend to see more opportunities in positive game scripts and convert them at a higher rate. It's one of the stronger predictors in the model for every position.
        """)

    with st.expander("How often do fantasy projections update?"):
        st.markdown("""
Fantasy projections are generated each week as part of the same automated pipeline that runs the betting predictions.

The projection file for each week is saved once and doesn't change after that — it reflects the injury and depth chart data available at the time it was run. Actual stats fill in automatically after each game is played, pulling live from nflreadpy and caching for 1 hour.

If you're looking at a past week, the actuals shown are the real NFL stats for that game.
        """)

    st.divider()

    # ── Section 4: Behind the Scenes ─────────────────────────────────────────
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
        _best_week = _completed.groupby(['season','week'])['model_correct'].agg(['sum','count'])
        _best_week['pct'] = _best_week['sum'] / _best_week['count']
        _bw = _best_week['pct'].idxmax() if not _best_week.empty else None
        _bw_str = (f"Season {_bw[0]} Week {_bw[1]} was the strongest week so far at "
                   f"{int(_best_week.loc[_bw,'sum'])} out of {int(_best_week.loc[_bw,'count'])} correct. "
                   ) if _bw else ""
        _hc_line2 = f" and **{_hc_pct}%** on high confidence picks" if _hc_pct is not None else ""
        st.markdown(f"""
The model has gone **{_overall_pct}% ATS** across {_overall_total} completed games ({_overall_correct} correct){_hc_line2}. The break even threshold at standard sportsbook odds is 52.4%, so both numbers are above that.

{_bw_str}
I want to be honest though. Past performance doesn't guarantee anything going forward. There will be bad weeks. The goal is to track this over multiple seasons and see if the edge holds up.
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