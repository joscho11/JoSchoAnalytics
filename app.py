import streamlit as st
import pandas as pd
import json
import os
import glob
import uuid
import time
import html as _html
import itertools as _it
import requests as req
from datetime import datetime as dt
from pathlib import Path
import plotly.graph_objects as go
import concurrent.futures as _cf

_HERE = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(_HERE))   # ensure local modules resolve regardless of launch CWD
from dashboard_utils import (
    load_tracker, load_totals_tracker, _md_to_html, get_confidence, metric_card,
)

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

# load_tracker / load_totals_tracker now live in dashboard_utils.py (testable, no st.* coupling).
# Cached shim preserves the original @st.cache_data behavior (avoid re-reading the CSV every rerun).
@st.cache_data(ttl=300)
def _load_tracker_cached(base):
    return load_tracker(base)

try:
    df = _load_tracker_cached(_HERE)
except FileNotFoundError:
    st.error("predictions_tracker.csv not found. Run the prediction pipeline first.")
    st.stop()
except Exception as _load_err:
    st.error(f"Failed to load predictions data: {_load_err}")
    st.stop()

if df.empty:
    st.warning("predictions_tracker.csv has no rows yet. Run the prediction pipeline to populate it.")
    st.stop()

totals_df = load_totals_tracker(_HERE)

@st.cache_data(ttl=300)
def _compute_hc_stats(acc_col: str, _df: pd.DataFrame) -> tuple:
    hc_correct, hc_total = 0, 0
    for af in glob.glob(str(_HERE / "betting" / "agent_analysis_*.json")):
        try:
            stem = os.path.basename(af).replace('.json', '').split('_')
            s, w = int(stem[2]), int(stem[3].replace('week', ''))
            wdf = _df[(_df['season'] == s) & (_df['week'] == w) & _df[acc_col].notna()]
            with open(af) as f:
                ga = json.load(f)
            _gc = ga.get('game_confidence', {})
            _ga = ga.get('game_analysis',   {})
            for _, r in wdf.iterrows():
                key  = f"{r['home_team']}_{r['away_team']}"
                conf = _gc.get(key) if _gc else None
                if conf is None:
                    text = _ga.get(key, '')
                    conf = 'HIGH' if '🟢' in text else None
                if conf == 'HIGH':
                    hc_total += 1
                    hc_correct += int(float(r[acc_col]))
        except Exception:
            pass
    return hc_correct, hc_total

@st.cache_data(ttl=3600)
def _load_proj_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)

# ── Live accuracy stats (used in Help tab) ────────────────────────────────────
_acc_col   = 'ens_model_correct' if 'ens_model_correct' in df.columns and df['ens_model_correct'].notna().any() else 'model_correct'
_completed = df[df[_acc_col].notna()]
_overall_correct = int(_completed[_acc_col].sum())
_overall_total   = len(_completed)
_overall_pct     = round(_overall_correct / _overall_total * 100, 1) if _overall_total > 0 else 0

_hc_correct, _hc_total = _compute_hc_stats(_acc_col, df)
_hc_pct = round(_hc_correct / _hc_total * 100, 1) if _hc_total > 0 else None

@st.cache_data(ttl=3600)
def load_actual_stats(season: int, week: int) -> dict:
    """Load all actual player stats for a given season/week in one nflreadpy call."""
    try:
        import nflreadpy as nfl
        raw = nfl.load_player_stats([season])
        if hasattr(raw, 'to_pandas'):
            raw = raw.to_pandas()
        stats = raw[
            (raw['season_type'] == 'REG') &
            (raw['week'] == week) &
            raw['position'].isin(['QB', 'RB', 'WR', 'TE'])
        ].copy()
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
        by_pos = {pos: grp.set_index('player_id') for pos, grp in stats.groupby('position')}

        def _col(pos_key, col):
            g = by_pos.get(pos_key)
            return g[col].fillna(0).to_dict() if g is not None and col in g.columns else {}

        return {
            'half_ppr':    stats.set_index('player_id')['actual_half_ppr'].to_dict(),
            'qb_pass_yds': _col('QB', 'passing_yards'),
            'qb_rush_yds': _col('QB', 'rushing_yards'),
            'rb_rush_yds': _col('RB', 'rushing_yards'),
            'rb_rec_yds':  _col('RB', 'receiving_yards'),
            'wr_rec_yds':  _col('WR', 'receiving_yards'),
            'wr_recs':     _col('WR', 'receptions'),
            'te_rec_yds':  _col('TE', 'receiving_yards'),
            'te_recs':     _col('TE', 'receptions'),
        }
    except Exception as _e:
        import logging as _logging
        _logging.warning(f"load_actual_stats({season}, {week}) failed: {_e}")
        return {}

@st.cache_data(ttl=3600)
def load_agent_analysis(week: int, season: int) -> dict:
    cache_file = str(_HERE / "betting" / f"agent_analysis_{season}_week{week}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None

@st.cache_data(ttl=3600)
def _sleeper_get(url: str):
    try:
        r = req.get(url, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

@st.cache_data(ttl=3600)
def _fetch_sleeper_history(start_league_id: str) -> dict:
    seasons = {}
    league_name = None
    current_id  = start_league_id.strip()
    seen        = set()

    while current_id and current_id not in ("0", "") and current_id not in seen:
        if len(seen) >= 10:
            break
        seen.add(current_id)

        info = _sleeper_get(f"https://api.sleeper.app/v1/league/{current_id}")
        if not info or not isinstance(info, dict):
            break
        if league_name is None:
            league_name = info.get("name", "League")

        yr = info.get("season")
        if not yr:
            break

        users_raw   = _sleeper_get(f"https://api.sleeper.app/v1/league/{current_id}/users")   or []
        rosters_raw = _sleeper_get(f"https://api.sleeper.app/v1/league/{current_id}/rosters")  or []
        bracket_raw = _sleeper_get(f"https://api.sleeper.app/v1/league/{current_id}/winners_bracket") or []

        user_map = {
            u["user_id"]: {
                "username":  u.get("display_name") or "—",
                "team_name": (u.get("metadata") or {}).get("team_name") or "",
            }
            for u in users_raw if isinstance(u, dict)
        }

        playoff_finish = {}
        champion_rid   = None
        runner_up_rid  = None

        if bracket_raw and info.get("status") == "complete":
            valid = [m for m in bracket_raw if isinstance(m, dict)]
            max_r = max((m.get("r", 0) for m in valid), default=0)
            for m in valid:
                if m.get("r") != max_r or m.get("w") is None or m.get("l") is None:
                    continue
                w, l, p = str(m["w"]), str(m["l"]), m.get("p")
                if p == 1:
                    champion_rid  = w
                    runner_up_rid = l
                if p:
                    if w not in playoff_finish or p < playoff_finish[w]:
                        playoff_finish[w] = p
                    if l not in playoff_finish or p + 1 < playoff_finish[l]:
                        playoff_finish[l] = p + 1

        standings = []
        for ro in rosters_raw:
            if not isinstance(ro, dict):
                continue
            rid      = str(ro.get("roster_id", ""))
            owner_id = ro.get("owner_id")
            u        = user_map.get(owner_id, {"username": "—", "team_name": ""})
            s        = ro.get("settings") or {}
            fpts     = s.get("fpts", 0) + s.get("fpts_decimal", 0) / 100
            fpts_ag  = s.get("fpts_against", 0) + s.get("fpts_against_decimal", 0) / 100
            standings.append({
                "roster_id":     ro.get("roster_id"),
                "username":      u["username"],
                "team_name":     u["team_name"],
                "wins":          s.get("wins", 0),
                "losses":        s.get("losses", 0),
                "fpts":          round(fpts, 2),
                "fpts_against":  round(fpts_ag, 2),
                "playoff_finish": playoff_finish.get(rid),
            })

        standings.sort(key=lambda x: (x["playoff_finish"] or 99, -x["wins"], -x["fpts"]))

        def _by_rid(rid_str):
            for row in standings:
                if str(row["roster_id"]) == rid_str:
                    return row
            return {"username": "?", "team_name": ""}

        champ = _by_rid(champion_rid)  if champion_rid  else {"username": "?", "team_name": ""}
        ruup  = _by_rid(runner_up_rid) if runner_up_rid else {"username": "?", "team_name": ""}

        # Fetch weekly matchups — parallelised to avoid 18 serial HTTP calls per season
        _lg_settings  = info.get("settings") or {}
        _playoff_start = int(_lg_settings.get("playoff_week_start") or 15)

        def _fetch_wk(wk):
            try:
                r = req.get(
                    f"https://api.sleeper.app/v1/league/{current_id}/matchups/{wk}",
                    timeout=15,
                )
                r.raise_for_status()
                return wk, r.json()
            except Exception:
                return wk, None

        with _cf.ThreadPoolExecutor(max_workers=18) as _pool:
            _wk_data = dict(_pool.map(_fetch_wk, range(1, 19)))

        _matchups_season: list = []
        for _wk in range(1, 19):
            _wk_raw = _wk_data.get(_wk)
            if not _wk_raw or not isinstance(_wk_raw, list):
                continue
            _grps: dict = {}
            for _entry in _wk_raw:
                if not isinstance(_entry, dict):
                    continue
                _mid = _entry.get("matchup_id")
                if _mid is None:
                    continue
                _grps.setdefault(_mid, []).append(_entry)
            for _mid2, _ents in _grps.items():
                if len(_ents) == 2:
                    _ma, _mb = _ents[0], _ents[1]
                    _sa = float(_ma.get("points") or 0)
                    _sb = float(_mb.get("points") or 0)
                    if _sa == 0 and _sb == 0:
                        continue
                    _matchups_season.append({
                        "season":     yr,
                        "week":       _wk,
                        "is_playoff": _wk >= _playoff_start,
                        "rid_a":      str(_ma.get("roster_id", "")),
                        "score_a":    _sa,
                        "rid_b":      str(_mb.get("roster_id", "")),
                        "score_b":    _sb,
                    })

        seasons[yr] = {
            "league_id": current_id,
            "status":    info.get("status"),
            "champion":  {"username": champ["username"], "team_name": champ.get("team_name", "")},
            "runner_up": {"username": ruup["username"],  "team_name": ruup.get("team_name", "")},
            "standings": standings,
            "matchups":  _matchups_season,
        }

        prev = info.get("previous_league_id")
        current_id = prev if (prev and prev != "0") else ""

    return {"league_name": league_name or "League", "seasons": seasons}

# _md_to_html / get_confidence now live in dashboard_utils.py (testable, no st.* coupling).

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.image(str(_HERE / "assets" / "logo.svg"), use_container_width=True)
st.sidebar.divider()

st.sidebar.markdown(
    """
    <div style="text-align:center; padding: 8px 0 4px 0;">
        <a href="https://venmo.com/u/JoScho" target="_blank" style="
            display: inline-block;
            background-color: #3D95CE;
            color: white;
            font-weight: 600;
            font-size: 14px;
            padding: 8px 18px;
            border-radius: 8px;
            text-decoration: none;
            letter-spacing: 0.3px;
        ">💙 Tip Jar — Venmo @JoScho</a>
        <div style="font-size: 11px; color: #888; margin-top: 6px;">
            If you find this useful, buy me a coffee ☕
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

st.sidebar.markdown(
    """
    <div style="padding: 2px 4px 6px 4px;">
        <p style="font-size:12px;color:#aaa;line-height:1.65;margin:0">
            ML model trained on NFL data since 2014. Predicts each game vs the Vegas spread.
            <b style="color:#3D95CE">52.4% ATS</b> is break-even.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

st.sidebar.divider()

seasons = sorted(df['season'].unique(), reverse=True)
season  = st.sidebar.selectbox("Season", seasons, key="season_select")

weeks   = sorted(df[df['season'] == season]['week'].unique(), reverse=True)
_default_week_idx = next((i for i, w in enumerate(weeks) if w == 10), 0)
week    = st.sidebar.selectbox("Week", weeks, index=_default_week_idx, key="week_select")

edge_threshold = st.sidebar.slider(
    "Min Edge (pts)",
    min_value=0.0,
    max_value=5.0,
    value=0.0,
    step=0.5,
    key="edge_slider",
    help="Only show games where model disagrees with spread by at least this many points"
)

# ── UI helpers ───────────────────────────────────────────────────────────────
# metric_card now lives in dashboard_utils.py (testable, no st.* coupling).

_MODE_BADGE_COLORS = {
    'monday':   '#ffd600',
    'thursday': '#ff9800',
    'sunday':   '#00c853',
    'backfill': '#3D95CE',
}

# ── Offseason banner ──────────────────────────────────────────────────────────
now           = dt.now()
season_active = (now.month >= 9) or (now.month <= 2)

if not season_active:
    current_season = now.year - 1
    next_season    = current_season + 1
    _agent_files   = sorted(glob.glob(str(_HERE / "betting" / f"agent_analysis_{current_season}_week*.json")))
    _demo_hint     = ""
    if _agent_files:
        _demo_wk = os.path.basename(_agent_files[-1]).replace('.json', '').split('week')[-1]
        _demo_hint = f" Look at Week {_demo_wk} for demo agent analysis."
    st.info(
        f"🏈 **NFL Offseason**: The {current_season} season has concluded.{_demo_hint} "
        f"Predictions will return when the {next_season} season kicks off in September. "
        "Browse past predictions using the sidebar."
    )

# ── Tabs ──────────────────────────────────────────────────────────────────────
# Draft Value Finder (tab5) re-enabled 2026-06-08 — our model's calls vs ADP (value_board_*.csv).
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["🏈 Weekly Predictions", "📈 Track Record", "🏆 Weekly Fantasy", "🎯 DFS Optimizer", "📋 Draft Value Finder", "🏅 League History", "❓ Help & Guide"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: WEEKLY PREDICTIONS
# ══════════════════════════════════════════════════════════════════════════════
with tab1:

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

    _has_consensus_col = 'consensus_tier' in week_df.columns and week_df['consensus_tier'].notna().any()
    if _has_consensus_col:
        st.markdown("""
            <div style='display:flex;gap:16px;align-items:center;margin-bottom:12px;flex-wrap:wrap;'>
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

        def stat_box(val, is_rec=False, is_result=False):
            bg    = "#1a3a2a" if is_rec else "#1e2a3a"
            color = "#00c853" if is_rec else "white"
            return (
                f"<div style='text-align:center;background:{bg};border-radius:6px;"
                f"padding:6px 0;font-size:14px;font-weight:600;color:{color};"
                f"height:32px;line-height:20px'>{val}</div>"
            )

        def bet_box(team, color="#3D95CE"):
            return (
                f"<div style='background:{color}22;border:1.5px solid {color};"
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
                    f"<div style='font-size:13px;color:#888;margin-bottom:6px'>"
                    f"<b style='color:#ccc'>{_html.escape(str(away))} @ {_html.escape(str(home))}</b>"
                    f"&nbsp;&nbsp;·&nbsp;&nbsp;{_html.escape(str(row['gameday']))}"
                    f"{tier_html}"
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
                a4.markdown(bet_box(top_team, rec_color) if top_is_rec else empty_box(), unsafe_allow_html=True)

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
                        f"<div style='background:#1f1a0e;border:1px dashed #b88a1c;border-radius:6px;"
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
with tab2:

    st.title(f"📈 {season} Track Record")
    season_df = df[
        (df['season'] == season) &
        (df['actual_margin'].notna())
    ].copy()

    if season_df.empty:
        st.warning("No completed games found for this season.")
    else:

        # ── Season summary metrics ────────────────────────────────────
        _s_edge    = 'ens_model_edge'    if ('ens_model_edge'    in season_df.columns and season_df['ens_model_edge'].notna().any())    else 'model_edge'
        _s_correct = 'ens_model_correct' if ('ens_model_correct' in season_df.columns and season_df['ens_model_correct'].notna().any()) else 'model_correct'

        total_correct = int(season_df[_s_correct].sum())
        total_games   = int(season_df[_s_correct].notna().sum())
        total_pct     = round(total_correct / total_games * 100, 1) if total_games > 0 else 0

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

        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(metric_card("Season ATS", f"{total_correct}/{total_games}", f"{total_pct}%",
                                color="green" if total_pct >= 52.4 else "red"), unsafe_allow_html=True)
        c2.markdown(metric_card("High Edge (3+ pts)", f"{he_correct}/{he_total}",
                                f"{he_pct}%" if he_total > 0 else "—",
                                color="green" if he_pct >= 52.4 else "red"), unsafe_allow_html=True)
        c3.markdown(metric_card("Med Edge (1-3 pts)", f"{me_correct}/{me_total}",
                                f"{me_pct}%" if me_total > 0 else "—",
                                color="green" if me_pct >= 52.4 else "red"), unsafe_allow_html=True)
        c4.markdown(metric_card("Low Edge (<1 pt)", f"{le_correct}/{le_total}",
                                f"{le_pct}%" if le_total > 0 else "—",
                                color="green" if le_pct >= 52.4 else "red"), unsafe_allow_html=True)

        _has_ens   = 'ens_model_correct'   in season_df.columns and season_df['ens_model_correct'].notna().any()
        _has_ridge = 'ridge_model_correct' in season_df.columns and season_df['ridge_model_correct'].notna().any()
        _has_lgbm  = 'lgbm_model_correct'  in season_df.columns and season_df['lgbm_model_correct'].notna().any()
        _has_ct    = 'consensus_tier'      in season_df.columns and season_df['consensus_tier'].notna().any()

        _has_xgb  = 'model_correct' in season_df.columns and season_df['model_correct'].notna().any()

        if _has_ens or _has_ridge or _has_lgbm or _has_xgb:
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
            st.caption("Individual model ATS (direction voters)")
            mc1, mc2, mc3, mc4 = st.columns(4)
            if _has_xgb:
                _xgb_sub = season_df[season_df['model_correct'].notna()]
                _xgb_c   = int(_xgb_sub['model_correct'].sum())
                _xgb_t   = len(_xgb_sub)
                _xgb_pct = round(_xgb_c / _xgb_t * 100, 1) if _xgb_t > 0 else 0
                mc1.markdown(metric_card("XGBoost ATS", f"{_xgb_c}/{_xgb_t}", f"{_xgb_pct}%",
                                         color="green" if _xgb_pct >= 52.4 else "red"), unsafe_allow_html=True)
            if _has_ridge:
                _ridge_sub = season_df[season_df['ridge_model_correct'].notna()]
                _ridge_c   = int(_ridge_sub['ridge_model_correct'].sum())
                _ridge_t   = len(_ridge_sub)
                _ridge_pct = round(_ridge_c / _ridge_t * 100, 1) if _ridge_t > 0 else 0
                mc2.markdown(metric_card("Ridge ATS", f"{_ridge_c}/{_ridge_t}", f"{_ridge_pct}%",
                                         color="green" if _ridge_pct >= 52.4 else "red"), unsafe_allow_html=True)
            if _has_lgbm:
                _lgbm_sub = season_df[season_df['lgbm_model_correct'].notna()]
                _lgbm_c   = int(_lgbm_sub['lgbm_model_correct'].sum())
                _lgbm_t   = len(_lgbm_sub)
                _lgbm_pct = round(_lgbm_c / _lgbm_t * 100, 1) if _lgbm_t > 0 else 0
                mc3.markdown(metric_card("LightGBM ATS", f"{_lgbm_c}/{_lgbm_t}", f"{_lgbm_pct}%",
                                         color="green" if _lgbm_pct >= 52.4 else "red"), unsafe_allow_html=True)
            if _has_ens:
                _ens_sub = season_df[season_df['ens_model_correct'].notna()]
                _ens_c   = int(_ens_sub['ens_model_correct'].sum())
                _ens_t   = len(_ens_sub)
                _ens_pct = round(_ens_c / _ens_t * 100, 1) if _ens_t > 0 else 0
                mc4.markdown(metric_card("Ensemble ATS", f"{_ens_c}/{_ens_t}", f"{_ens_pct}%",
                                         color="green" if _ens_pct >= 52.4 else "red"), unsafe_allow_html=True)

        st.divider()

        # ── Week-by-week summary ──────────────────────────────────────
        weekly = season_df.groupby('week').agg(
            correct=(_s_correct, 'sum'),
            total=(_s_correct, 'count')
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
            y=52.4, line_dash="dash", line_color="#888",
            annotation_text="Break even (52.4%)", annotation_position="right"
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
            annotation_text="Break even (52.4%)", annotation_position="right"
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
            y=52.4, line_dash="dash", line_color="#888",
            annotation_text="Break even (52.4%)", annotation_position="right"
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

        if _has_ct:
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

            ct1, ct2, ct3 = st.columns(3)
            ct1.metric("HIGH Tier",   f"{_ch_c}/{_ch_t}", f"{_ch_pct}%",
                       help="All 3 models agree + Ensemble edge ≥3 pts. Highest expected accuracy.")
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
                annotation_text="Break even (52.4%)", annotation_position="right"
            )
            fig_ct.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font_color='white',
                yaxis=dict(range=[0, 100], title='ATS Win %', gridcolor='#2d3748'),
                xaxis=dict(gridcolor='#2d3748'),
                showlegend=False,
                height=350,
                margin=dict(t=20, b=20)
            )
            st.plotly_chart(fig_ct, use_container_width=True)

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

        # ── Season at a Glance ────────────────────────────────────────
        st.subheader("Season at a Glance")
        st.caption("Profit math assumes flat unit stakes at -110 odds (bet 110 to win 100). Day-of-week breakdown excludes pushes.")

        # Hypothetical profit at -110 odds — three subsets
        def _units_profit(sub):
            graded = sub[sub[_s_correct].notna()]
            wins = int(graded[_s_correct].sum())
            losses = int(len(graded) - wins)
            return wins * 100 - losses * 110, wins, losses

        _high_sub = season_df[season_df[_s_edge].abs() >= 3]
        _med_or_high_sub = season_df[season_df[_s_edge].abs() >= 1]
        _profit_high, _h_w, _h_l = _units_profit(_high_sub)
        _profit_hm,   _hm_w, _hm_l = _units_profit(_med_or_high_sub)
        _profit_all,  _a_w, _a_l = _units_profit(season_df)

        p1, p2, p3 = st.columns(3)
        p1.markdown(metric_card("Profit (HIGH only)",
                                f"{_h_w}-{_h_l}", f"{_profit_high:+,} units",
                                color="green" if _profit_high > 0 else "red"),
                    unsafe_allow_html=True)
        p2.markdown(metric_card("Profit (HIGH + MED)",
                                f"{_hm_w}-{_hm_l}", f"{_profit_hm:+,} units",
                                color="green" if _profit_hm > 0 else "red"),
                    unsafe_allow_html=True)
        p3.markdown(metric_card("Profit (all picks)",
                                f"{_a_w}-{_a_l}", f"{_profit_all:+,} units",
                                color="green" if _profit_all > 0 else "red"),
                    unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

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
                        st.dataframe(dow_table, hide_index=True, use_container_width=True)
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
            st.dataframe(table, hide_index=True, use_container_width=True)

        # ── Totals model performance ──────────────────────────────────────────
        totals_season = (
            totals_df[(totals_df['season'] == season) & totals_df['model_correct'].notna()]
            if not totals_df.empty else pd.DataFrame()
        )
        if not totals_season.empty:
            st.divider()
            st.subheader("🎯 Over/Under Model Performance — Experimental")
            st.warning(
                "**Tracking only — do not bet.** The totals model has a CV edge (55.7% on 575 picks across "
                "2020–2025) but the live 2025 sample is too small to confirm it. Currently sitting near "
                "break-even live. We track it through the 2026 season and reassess after a full season "
                "(~96 picks) of real evidence."
            )
            st.caption("UNDER picks only — model bets UNDER when both XGBoost and Ridge agree. Break-even: 52.4%.")

            t_high = totals_season[totals_season['consensus_tier'] == 'HIGH']
            t_correct = int(t_high['model_correct'].sum())
            t_total   = len(t_high)
            t_pct     = round(t_correct / t_total * 100, 1) if t_total > 0 else 0

            tc1, tc2, tc3 = st.columns(3)
            tc1.markdown(metric_card("UNDER Picks", f"{t_correct}/{t_total}",
                                     f"{t_pct}%" if t_total > 0 else "—",
                                     color="green" if t_pct >= 52.4 else "red"), unsafe_allow_html=True)

            _t_over_rate = totals_season['went_over'].mean() if 'went_over' in totals_season.columns and totals_season['went_over'].notna().any() else None
            if _t_over_rate is not None:
                tc2.markdown(metric_card("Actual OVER rate", "—",
                                         f"{round(_t_over_rate * 100, 1)}% of tracked games",
                                         color="blue"), unsafe_allow_html=True)
            tc3.markdown(metric_card("Break-even", "52.4%", "at -110 odds", color="blue"), unsafe_allow_html=True)

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
                        hide_index=True, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: FANTASY PROJECTIONS
# ══════════════════════════════════════════════════════════════════════════════
with tab3:

    st.title(f"🏆 Week {week} Fantasy Projections — Half-PPR")

    proj_files = sorted(glob.glob(str(_HERE / "fantasy" / "fantasy_projections" / "projections_*.csv")), reverse=True)

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
        proj_df = _load_proj_csv(available[(season, week)])

        # Actual results (available after week is played)
        _actuals       = load_actual_stats(season, week)
        actuals_in     = bool(_actuals.get('half_ppr'))
        _half_ppr_dict     = _actuals.get('half_ppr',    {})
        actual_qb_pass_yds = _actuals.get('qb_pass_yds', {})
        actual_qb_rush_yds = _actuals.get('qb_rush_yds', {})
        actual_rush_yds    = _actuals.get('rb_rush_yds', {})
        actual_rb_rec_yds  = _actuals.get('rb_rec_yds',  {})
        actual_wr_rec_yds  = _actuals.get('wr_rec_yds',  {})
        actual_wr_recs     = _actuals.get('wr_recs',     {})
        actual_te_rec_yds  = _actuals.get('te_rec_yds',  {})
        actual_te_recs     = _actuals.get('te_recs',     {})

        # Load cached agent analysis if available
        fa_path = str(_HERE / "fantasy" / f"agent_analysis_{season}_week{week}.json")
        fantasy_analysis = None
        try:
            if os.path.exists(fa_path):
                with open(fa_path) as _f:
                    fantasy_analysis = json.load(_f)
        except (IOError, json.JSONDecodeError):
            fantasy_analysis = None

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
            if pd.isna(n):
                return "—"
            n = int(n)
            if 11 <= (n % 100) <= 13:
                return f"{n}th"
            return f"{n}{['th','st','nd','rd','th'][min(n % 10, 4)]}"

        def rank_color(rank, total=32):
            if pd.isna(rank):
                return ""
            ratio = (total - int(rank)) / (total - 1)
            r = int(255 * (1 - ratio))
            g = int(82 + 118 * ratio)
            return f"color: rgb({r},{g},82); font-weight: 600"

        def total_color(val, lo=16.0, hi=30.0):
            ratio = max(0.0, min(1.0, (val - lo) / (hi - lo)))
            r = int(255 * (1 - ratio))
            g = int(82 + 118 * ratio)
            return f"color: rgb({r},{g},82); font-weight: 600"

        def make_style_table(display_df):
            def _style(df):
                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                if "Off EPA" in df.columns and "EPA Rank" in df.columns:
                    for i, rank in enumerate(display_df["off_epa_rank"]):
                        styles.iloc[i, df.columns.get_loc("Off EPA")]  = rank_color(rank)
                        styles.iloc[i, df.columns.get_loc("EPA Rank")] = rank_color(rank)
                if "Team Total" in df.columns:
                    for i, val in enumerate(display_df["implied_team_total"]):
                        styles.iloc[i, df.columns.get_loc("Team Total")] = total_color(val)
                styles["Proj Pts"] = "font-weight: 700; font-size: 15px"
                if "Actual Pts" in df.columns:
                    styles["Actual Pts"] = "font-weight: 700; font-size: 15px"
                return styles
            return _style

        _early_req = ["position", "depth_chart_position", "projected_pts"]
        _early_missing = [c for c in _early_req if c not in proj_df.columns]
        if _early_missing:
            st.warning(f"Projection CSV is missing columns: {_early_missing}. Re-run predict_fantasy.ipynb.")
            st.stop()

        for ptab, pos in zip([ptab_qb, ptab_rb, ptab_wr, ptab_te], ["QB", "RB", "WR", "TE"]):
            with ptab:
                pos_subset = proj_df[proj_df["position"] == pos]
                if pos == "QB":
                    pos_subset = pos_subset[pos_subset["depth_chart_position"] == 1]
                    pos_subset = pos_subset.sort_values("projected_pts", ascending=False).drop_duplicates(subset="team")
                top_n = 40 if pos in ("RB", "WR") else 20
                pos_df = pos_subset.sort_values("projected_pts", ascending=False)
                if player_search:
                    mask = pos_df["player_display_name"].str.contains(player_search, case=False, na=False, regex=False)
                    pos_df = pos_df[mask]
                else:
                    pos_df = pos_df.head(top_n)
                pos_df = pos_df.reset_index(drop=True)
                pos_df.index += 1

                has_qb_stats = pos == "QB" and "pred_qb_pass_yards" in pos_df.columns
                has_rb_yds   = pos == "RB" and "pred_rush_yards" in pos_df.columns
                has_wr_stats = pos == "WR" and "pred_wr_rec_yards" in pos_df.columns
                has_te_stats = pos == "TE" and "pred_te_rec_yards" in pos_df.columns

                _req_cols = ["player_id", "player_display_name", "team", "opponent_team",
                             "projected_pts", "injury_status_score",
                             "is_home", "off_epa_roll4", "off_epa_rank",
                             "implied_team_total"]
                _missing_req = [c for c in _req_cols if c not in pos_df.columns]
                if _missing_req:
                    st.warning(f"Projection CSV is missing columns: {_missing_req}. Re-run predict_fantasy.ipynb.")
                    continue
                display = pos_df[_req_cols].copy()
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

                sep = display["is_home"].map(lambda h: "vs" if h in (1, True, 1.0) else "@")
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
                    _actual_raw = display["player_id"].map(_half_ppr_dict)
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
                style_fn = make_style_table(display)

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
                    tbl.style.apply(style_fn, axis=None),
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
                    for up, dn in _it.zip_longest(ups, dns):
                        card_style = "display:flex;flex-direction:column;justify-content:space-between;" \
                                     "border-radius:4px;padding:10px 14px;height:100%"
                        up_html = (
                            f"<div style='background:#1a2a1a;border-left:3px solid #00c853;{card_style}'>"
                            f"<b style='color:#e8e8e8'>{_html.escape(up['player'])}</b> "
                            f"<span style='color:#888;font-size:12px'>({_html.escape(up['team'])})</span><br>"
                            f"<span style='color:#aaa;font-size:13px'>{_html.escape(up['reason'])}</span>"
                            f"</div>"
                        ) if up else "<div></div>"
                        dn_html = (
                            f"<div style='background:#2a1a1a;border-left:3px solid #ff5252;{card_style}'>"
                            f"<b style='color:#e8e8e8'>{_html.escape(dn['player'])}</b> "
                            f"<span style='color:#888;font-size:12px'>({_html.escape(dn['team'])})</span><br>"
                            f"<span style='color:#aaa;font-size:13px'>{_html.escape(dn['reason'])}</span>"
                            f"</div>"
                        ) if dn else "<div></div>"
                        row_html = (
                            "<div style='display:grid;grid-template-columns:1fr 1fr;"
                            "gap:8px;align-items:stretch;margin-top:8px'>"
                            + up_html + dn_html +
                            "</div>"
                        )
                        st.markdown(row_html, unsafe_allow_html=True)
                else:
                    st.info(
                        "No agent analysis available for this week. "
                        "Run `fantasy/fantasy_agent.ipynb` to generate it."
                    )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: DFS
# ══════════════════════════════════════════════════════════════════════════════
with tab4:

    st.title("🎯 DFS Optimizer")
    st.caption("DraftKings NFL Classic lineup optimizer — powered by the same weekly projections as the Weekly Fantasy tab.")

    st.divider()

    st.info(
        "**Coming soon — launching with the 2026 NFL season.**\n\n"
        "The DFS optimizer is currently in development. When live, this tab will let you:\n\n"
        "- Browse this week's projected DraftKings points for every skill-position player\n"
        "- Upload your DraftKings salary CSV (exported from any NFL Classic contest)\n"
        "- Generate an ILP-optimized 9-player lineup (QB / 2 RB / 3 WR / 1 TE / FLEX / DST)\n"
        "- Lock or exclude specific players and re-run in one click\n"
        "- Download the finished lineup ready for DraftKings import\n\n"
        "Projections are converted to full DraftKings Classic scoring automatically, "
        "including the full-PPR reception bonus and milestone bonuses "
        "(300+ passing yards, 100+ rushing yards, 100+ receiving yards)."
    )

    st.divider()

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("Scoring", "DK Classic (full PPR)")
    with col_b:
        st.metric("Salary cap", "$50,000")
    with col_c:
        st.metric("Roster slots", "9 (QB/2RB/3WR/TE/FLEX/DST)")

    st.caption(
        "Under the hood: `fantasy/dfs/dfs_pipeline.ipynb` — "
        "integer linear program via PuLP, projections from our per-position XGBoost models."
    )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5: SEASONAL VALUE FINDER — our model's calls vs the draft room (ADP)
# ══════════════════════════════════════════════════════════════════════════════
with tab5:

    st.title("📋 Draft Value Finder")

    st.markdown(
        "<div style='background:#1f1a0e;border:1px dashed #b88a1c;border-radius:8px;"
        "padding:12px 16px;margin:4px 0 14px 0;font-size:13.5px;line-height:1.5'>"
        "<span style='color:#e0a93a;font-weight:700'>Our model vs the draft room (ADP) — values the room is sleeping on.</span>"
        "<br><span style='color:#bbb'>Our <b>independent</b> season projection ranked against the market's "
        "<b>ADP</b>. <b>BUY</b> = we rank a player above their ADP (undervalued); <b>FADE</b> = below (overvalued). "
        "On confident calls it beats the casual ADP line (~68% on HIGH buys, stable across seasons). <b>Fades</b> are "
        "only shown with a real decline catalyst (aging / declining), never young players. Sharper public projections "
        "(e.g. <b>Sleeper</b>, shown for comparison) are still better than our model — treat this as a draft "
        "cross-check, not a guarantee.</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    _vb_files = glob.glob(str(_HERE / "fantasy" / "seasonal_projections" / "value_board_*.csv"))
    _vbs = {}
    for _f in _vb_files:
        try:
            _vbs[int(os.path.basename(_f).replace("value_board_", "").replace(".csv", ""))] = _f
        except ValueError:
            continue
    if not _vbs:
        st.info(
            "No value board found. Generate one with "
            "`python fantasy/seasonal_projections/build_value_board.py`."
        )
    else:
        _seasons = sorted(_vbs, reverse=True)
        _bseason = st.selectbox("Season", _seasons, index=0, key="vb_season") if len(_seasons) > 1 else _seasons[0]
        vdf = pd.read_csv(_vbs[_bseason])
        for _c in ("our_rank", "adp_rank", "value", "sleeper_rank", "actual_rank",
                   "our_proj", "actual_total", "sleeper_agrees"):
            if _c in vdf.columns:
                vdf[_c] = pd.to_numeric(vdf[_c], errors="coerce")
        for _c in ("call", "contested", "reason"):     # empty cells read back as NaN -> ""
            vdf[_c] = vdf[_c].fillna("") if _c in vdf.columns else ""
        # injured = missed >6 games; outcome is injury-driven so we don't grade the call (robust bool parse)
        vdf["injured"] = (vdf["injured"].astype(str).str.lower().isin(["true", "1", "1.0"])
                          if "injured" in vdf.columns else False)
        _has_actuals = "actual_rank" in vdf.columns and vdf["actual_rank"].notna().any()
        _has_slp = "sleeper_rank" in vdf.columns

        st.caption(
            f"{_bseason} season · {len(vdf):,} drafted players · our model's calls vs ADP."
            + ("  Results are in — actual finishes shown." if _has_actuals
               else "  Upcoming season — projections only, no results yet.")
        )

        with st.expander("How to read this (and what it is / isn't)"):
            st.markdown(
                "Our **independent** season-projection model (LightGBM, no Sleeper) ranked against the market's "
                "draft order, within each position. Each rank reads like a draft label — **RB12** = the 12th "
                "running back. Columns:\n"
                "- **ADP** — Average Draft Position, where the draft market ranks the player. **Our Rank** — where our model does.\n"
                "- **Verdict** — our call. 🟢 green = we rank them above the room (a *value/buy*); 🔴 red = below "
                "(a *fade*); ⚠️ **Contested** = we liked them, but new competition for touches just arrived (a drafted "
                "rookie, a free-agent signing, a starter returning from injury, or a newly-crowded backfield) that our "
                "prior-stats model can't see — so we hold off rather than flag a false value. The number is how many "
                "positional spots we differ. Fades are only shown for aging/declining players, never young ones.\n"
                "- **Finished** *(completed season)* — where the player actually finished; **Result** — ✅ the call "
                "paid off, ❌ it didn't.\n"
                "- **Sleeper** — Sleeper's own projected rank, shown *for comparison only*. It is **not** part of our "
                "call; the call-outs just note whether Sleeper happens to agree.\n\n"
                "**Honest scope:** our confident BUY calls beat the casual ADP line ~68% of the time (season-stable). "
                "Sharper public projections like Sleeper's are still better than our model — so use this as a cross-check "
                "on your draft room, not as gospel. Injuries are unpredictable and not modeled."
            )

        _pos = st.radio("Position", ["All", "QB", "RB", "WR", "TE"], horizontal=True, key="vb_pos")
        view = (vdf if _pos == "All" else vdf[vdf["position"] == _pos]).copy()

        if view.empty:
            st.info("No players for this filter.")
        else:
            def _fin(r):
                if not (_has_actuals and pd.notna(r.get("actual_rank"))):
                    return ""
                tag = " 🏥 (missed time)" if r.get("injured") else ""
                return f" → finished {r['position']}{int(r['actual_rank'])}{tag}"

            def _agree(r):
                if _has_slp and pd.notna(r.get("sleeper_agrees")):
                    return " · ✓ Sleeper agrees" if r["sleeper_agrees"] else " · ✗ Sleeper disagrees"
                return ""

            # drop any row missing a rank so the int(...) formatters below can't crash
            _called = view.dropna(subset=["our_rank", "adp_rank", "value"])
            buys = _called[_called["call"] == "BUY"].sort_values("value", ascending=False)
            fades = _called[_called["call"] == "FADE"].sort_values("value")

            # 🔥 CONSENSUS VALUES — the headline. Where OUR model AND Sleeper BOTH rank a player above
            # their ADP. That agreement is the single strongest signal in the tool (~78% have beaten
            # their draft cost vs ~68% for our model alone), so we lead with it.
            if _has_slp:
                cons = buys[buys["sleeper_agrees"] == 1].copy()
                cons["_c"] = (cons["adp_rank"] - cons["our_rank"]) + (cons["adp_rank"] - cons["sleeper_rank"])
                cons = cons.sort_values("_c", ascending=False)
                if len(cons):
                    def _finh(r):
                        if not (_has_actuals and pd.notna(r.get("actual_rank"))):
                            return ""
                        if r.get("injured"):    # injury-shortened season -> don't grade it
                            return f" &rarr; finished {r['position']}{int(r['actual_rank'])} 🏥"
                        return (f" &rarr; finished {r['position']}{int(r['actual_rank'])} "
                                f"{'✅' if r['actual_rank'] < r['adp_rank'] else '❌'}")
                    items = "".join(
                        f"<li style='margin:4px 0'><b>{r['player']}</b> "
                        f"<span style='color:#888'>({r['position']})</span> — drafted "
                        f"{r['position']}{int(r['adp_rank'])}; we say <b style='color:#3fbf5f'>"
                        f"{r['position']}{int(r['our_rank'])}</b>, Sleeper <b style='color:#3fbf5f'>"
                        f"{r['position']}{int(r['sleeper_rank'])}</b>{_finh(r)}</li>"
                        for _, r in cons.head(6).iterrows())
                    st.markdown(
                        "<div style='background:#0f1a0e;border:1px solid #1a9850;border-radius:8px;"
                        "padding:12px 16px;margin:2px 0 16px 0'>"
                        "<div style='color:#3fbf5f;font-weight:700;font-size:15px;margin-bottom:3px'>"
                        "🔥 Consensus values</div>"
                        "<div style='color:#aaa;font-size:12.5px;margin-bottom:8px'>The players our model "
                        "<b>and</b> Sleeper both rank above where the draft room takes them — the strongest "
                        "signal here (~78% have beaten their ADP, vs ~68% for our model alone).</div>"
                        f"<ul style='margin:0;padding-left:18px;font-size:13.5px;color:#ddd'>{items}</ul></div>",
                        unsafe_allow_html=True)

            cL, cR = st.columns(2)
            with cL:
                st.markdown("**🟢 Best values** — drafted cheap, we rank them higher")
                if len(buys):
                    for _, r in buys.head(8).iterrows():
                        st.markdown(
                            f"- **{r['player']}** ({r['position']}) — drafted {r['position']}{int(r['adp_rank'])}, "
                            f"we rank **{r['position']}{int(r['our_rank'])}** (+{int(r['value'])} spots){_agree(r)}{_fin(r)}"
                        )
                else:
                    st.caption("None at this filter.")
            with cR:
                st.markdown("**🔴 Fades** — drafted high, we'd let someone else pay")
                if len(fades):
                    for _, r in fades.head(8).iterrows():
                        st.markdown(
                            f"- **{r['player']}** ({r['position']}) — drafted {r['position']}{int(r['adp_rank'])}, "
                            f"we rank **{r['position']}{int(r['our_rank'])}** ({int(r['value'])} spots, {r['reason']}){_agree(r)}{_fin(r)}"
                        )
                else:
                    st.caption("None at this filter.")

            # full table — readable AND correctly sortable. Ranks stay NUMERIC (so the grid sorts 1,2,..,10,11
            # not 1,10,11,2), but column_config DISPLAYS them with the position prefix ("RB%d" -> RB12) when a
            # single position is filtered. The 🟢/🔴 emoji in Verdict carry the color, so no Styler is needed.
            st.markdown("**Full board** — every drafted player, by position")
            st.caption(
                "Read a row like this: the market drafts this player at **ADP** and our model ranks them at "
                "**Our Rank** (both within their position — filter to one position to see them labelled RB12, WR8, "
                "etc.). A 🟢 green **Verdict** = a value vs the draft room; 🔴 red = overvalued. **Sleeper** is a "
                "sharper public projection, shown only to compare against. Click any header to sort."
            )
            view = view.sort_values(["position", "adp_rank"]).reset_index(drop=True)

            def _verdict(r):
                v = r["value"]
                if r["call"] == "BUY":
                    return f"🟢 {'Strong buy' if r['tier'] == 'HIGH' else 'Buy'} (+{int(v)})"
                if r["call"] == "FADE":
                    return f"🔴 {'Strong fade' if r['tier'] == 'HIGH' else 'Fade'} ({int(v)})"
                if str(r.get("contested", "")):      # our model liked them, but new competition arrived
                    return f"⚠️ Contested ({r['contested']})"
                return "—"

            def _result(r):
                if r["call"] not in ("BUY", "FADE") or pd.isna(r.get("actual_rank")):
                    return ""
                if r.get("injured"):        # missed >6 games -> outcome is injury luck, not our call
                    return "🏥 injured"
                better = r["actual_rank"] < r["adp_rank"]       # finished above their draft slot
                hit = better if r["call"] == "BUY" else not better
                return "✅ hit" if hit else "❌ miss"

            disp = pd.DataFrame({
                "Player": view["player"], "Pos": view["position"], "Team": view["team"],
                "ADP": view["adp_rank"].astype("Int64"),
                "Our Rank": view["our_rank"].astype("Int64"),
                "Verdict": view.apply(_verdict, axis=1),
            })
            if _has_actuals:
                disp["Finished"] = view["actual_rank"].astype("Int64")
                disp["Result"] = view.apply(_result, axis=1)
            if _has_slp:
                disp["Sleeper"] = view["sleeper_rank"].astype("Int64")
            disp["Proj Pts"] = view["our_proj"].round(0).astype("Int64")

            # prefix the rank display with the position when one is filtered (numbers stay numeric -> sortable)
            _rankfmt = f"{_pos}%d" if _pos != "All" else "%d"
            _num = st.column_config.NumberColumn
            _txt = st.column_config.TextColumn
            _allcfg = {
                "ADP": _num("ADP", help="Average Draft Position — where the draft market ranks this player at their position.", format=_rankfmt),
                "Our Rank": _num("Our Rank", help="Where OUR independent model ranks them at their position (no Sleeper).", format=_rankfmt),
                "Finished": _num("Finished", help="Where the player actually finished at their position.", format=_rankfmt),
                "Sleeper": _num("Sleeper", help="Sleeper's projected rank — shown only for comparison, not part of our call.", format=_rankfmt),
                "Proj Pts": _num("Proj Pts", help="Our model's projected half-PPR season total.", format="%d"),
                "Verdict": _txt("Verdict", help="Our call vs the market — 🟢 = undervalued (buy), 🔴 = overvalued (fade), "
                                "⚠️ Contested = we liked them but new competition arrived (a rookie, signing, returning starter, or "
                                "crowded backfield) that our stats model can't price, so we hold off. The number is how many "
                                "positional spots we differ. Fades only for aging/declining players, never young ones."),
                "Result": _txt("Result", help="Did the call pay off? ✅ = finished on our side of the market, ❌ = it didn't."),
            }
            _colcfg = {c: cfg for c, cfg in _allcfg.items() if c in disp.columns}
            st.dataframe(disp, hide_index=True, use_container_width=True, height=560, column_config=_colcfg)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 6: LEAGUE HISTORY
# ══════════════════════════════════════════════════════════════════════════════
with tab6:

    st.title("🏅 Fantasy League History")

    _league_id_input = st.text_input(
        "Sleeper League ID",
        value="1255197436951932928",
        placeholder="e.g. 1255197436951932928",
        help="Find it in your Sleeper league URL: sleeper.com/leagues/{ID}/league",
        key="lh_league_id",
    )

    if not _league_id_input.strip().isdigit():
        st.info("Enter a numeric Sleeper league ID above to load your league history.")
    else:
        with st.spinner("Loading league history from Sleeper…"):
            _lh = _fetch_sleeper_history(_league_id_input.strip())

        if not _lh["seasons"]:
            st.error("No data found — double-check the league ID and try again.")
        else:
            st.header(_lh["league_name"])

            # Season filter
            _seasons_list = sorted(_lh["seasons"].keys())
            _season_filter = st.selectbox(
                "Season",
                ["All Time"] + _seasons_list,
                key="lh_season_filter",
            )

            # Build cross-season helpers
            _rid_to_user: dict = {}
            for _yr0, _sd0 in _lh["seasons"].items():
                for _row0 in _sd0["standings"]:
                    _rid_to_user[(_yr0, str(_row0["roster_id"]))] = _row0["username"]

            _all_matchups = [
                _m for _sd0 in _lh["seasons"].values()
                for _m in _sd0.get("matchups", [])
            ]

            def _guser(_yr_g, _rid_g):
                return _rid_to_user.get((_yr_g, _rid_g), "?")

            # Expand matchups into per-player game records (full, unfiltered)
            _game_records = []
            for _m0 in _all_matchups:
                _ua0 = _guser(_m0["season"], _m0["rid_a"])
                _ub0 = _guser(_m0["season"], _m0["rid_b"])
                if "?" in (_ua0, _ub0):
                    continue
                _sa0, _sb0 = _m0["score_a"], _m0["score_b"]
                _game_records += [
                    {"season": _m0["season"], "week": _m0["week"],
                     "is_playoff": _m0["is_playoff"],
                     "username": _ua0, "score": _sa0, "won": _sa0 > _sb0,
                     "opp": _ub0, "opp_score": _sb0},
                    {"season": _m0["season"], "week": _m0["week"],
                     "is_playoff": _m0["is_playoff"],
                     "username": _ub0, "score": _sb0, "won": _sb0 > _sa0,
                     "opp": _ua0, "opp_score": _sa0},
                ]

            # Apply season filter
            if _season_filter == "All Time":
                _filt_records  = _game_records
                _filt_matchups = _all_matchups
                _filt_seasons  = _lh["seasons"]
            else:
                _filt_records  = [r for r in _game_records  if r["season"] == _season_filter]
                _filt_matchups = [m for m in _all_matchups  if m["season"] == _season_filter]
                _filt_seasons  = {k: v for k, v in _lh["seasons"].items() if k == _season_filter}

            _all_managers = sorted(set(r["username"] for r in _game_records))

            # Compute manager list once, before sub-tabs (used in both C and D)
            _h2h_managers = sorted(set(r["username"] for r in _filt_records)) if _season_filter != "All Time" else _all_managers

            # Sub-tabs
            _lhA, _lhB, _lhC, _lhD, _lhE, _lhF = st.tabs([
                "🏆 All-Time Records",
                "🎖️ Hall of Fame",
                "⚔️ Head-to-Head",
                "📋 Report Cards",
                "📊 Consistency & Luck",
                "📈 Score Trends",
            ])

            # ── Sub-tab A: All-Time Records ────────────────────────────────────
            with _lhA:
                _rec_label = "Season" if _season_filter != "All Time" else "All-Time"
                st.subheader(f"{_rec_label} Records")

                _at: dict = {}
                for _yr2, _sd2 in _filt_seasons.items():
                    for _s2 in _sd2["standings"]:
                        _u2 = _s2["username"]
                        if not _u2 or _u2 == "—":
                            continue
                        if _u2 not in _at:
                            _at[_u2] = {"titles": 0, "finals": 0, "seasons": 0,
                                        "wins": 0, "losses": 0, "fpts": 0.0, "best": 99}
                        _at[_u2]["seasons"] += 1
                        _at[_u2]["wins"]    += _s2["wins"]
                        _at[_u2]["losses"]  += _s2["losses"]
                        _at[_u2]["fpts"]    += _s2["fpts"]
                        _pf3 = _s2.get("playoff_finish")
                        if _pf3 and _pf3 < _at[_u2]["best"]:
                            _at[_u2]["best"] = _pf3
                    _cu = _sd2["champion"]["username"]
                    _ru = _sd2["runner_up"]["username"]
                    if _cu and _cu not in ("?", "—") and _cu in _at:
                        _at[_cu]["titles"] += 1
                    if _ru and _ru not in ("?", "—") and _ru in _at:
                        _at[_ru]["finals"] += 1

                _pf_label = "PF" if _season_filter != "All Time" else "Career PF"
                _at_rows = []
                for _u2, _stats in _at.items():
                    _tot2 = _stats["wins"] + _stats["losses"]
                    _at_rows.append({
                        "Manager":      _u2,
                        "Titles":       _stats["titles"],
                        "Finals":       _stats["titles"] + _stats["finals"],
                        "Best Finish":  str(_stats["best"]) if _stats["best"] < 99 else "DNQ",
                        "Seasons":      _stats["seasons"],
                        "W":            _stats["wins"],
                        "L":            _stats["losses"],
                        "Win %":        round(_stats["wins"] / _tot2 * 100, 1) if _tot2 > 0 else 0,
                        _pf_label:      round(_stats["fpts"], 2),
                    })

                _at_df = (
                    pd.DataFrame(_at_rows)
                    .sort_values(["Titles", "Win %"], ascending=[False, False])
                    .reset_index(drop=True)
                )
                _at_df.index += 1
                st.dataframe(
                    _at_df,
                    use_container_width=True,
                    column_config={
                        "Titles":    st.column_config.NumberColumn("Titles",   help="Championship wins"),
                        "Finals":    st.column_config.NumberColumn("Finals",   help="Championship appearances"),
                        "Win %":     st.column_config.NumberColumn("Win %",    format="%.1f%%"),
                        _pf_label:   st.column_config.NumberColumn(_pf_label,  format="%.2f"),
                    }
                )

            # ── Sub-tab B: Hall of Fame / Shame ───────────────────────────────
            with _lhB:
                _hof_scope = _season_filter if _season_filter != "All Time" else "all seasons"
                st.subheader("Hall of Fame & Shame")
                st.caption(f"Records from {_hof_scope}, including playoffs.")

                if not _filt_records:
                    st.info("No weekly matchup data available.")
                else:
                    _played_recs = [r for r in _filt_records if r["score"] > 5]
                    _best_score  = max(_played_recs, key=lambda r: r["score"]) if _played_recs else None
                    _worst_score = min(_played_recs, key=lambda r: r["score"]) if _played_recs else None
                    _losses_recs = [r for r in _played_recs if not r["won"]]
                    _wins_recs   = [r for r in _played_recs if r["won"]]
                    _best_loss   = max(_losses_recs, key=lambda r: r["score"]) if _losses_recs else None
                    _luck_win    = min(_wins_recs,   key=lambda r: r["score"]) if _wins_recs   else None

                    _margins = []
                    for _m1 in _filt_matchups:
                        _ua1 = _guser(_m1["season"], _m1["rid_a"])
                        _ub1 = _guser(_m1["season"], _m1["rid_b"])
                        if "?" in (_ua1, _ub1):
                            continue
                        _sa1, _sb1 = _m1["score_a"], _m1["score_b"]
                        if _sa1 < 5 and _sb1 < 5:
                            continue
                        if _sa1 == _sb1:
                            continue
                        _hi1, _lo1 = max(_sa1, _sb1), min(_sa1, _sb1)
                        _win1 = _ua1 if _sa1 > _sb1 else _ub1
                        _los1 = _ub1 if _sa1 > _sb1 else _ua1
                        _margins.append({
                            "season": _m1["season"], "week": _m1["week"],
                            "winner": _win1, "loser": _los1,
                            "winner_score": _hi1, "loser_score": _lo1,
                            "margin": _hi1 - _lo1, "combined": _sa1 + _sb1,
                        })
                    _blowout     = max(_margins, key=lambda m: m["margin"])   if _margins else None
                    _closest     = min(_margins, key=lambda m: m["margin"])   if _margins else None
                    _hi_combined = max(_margins, key=lambda m: m["combined"]) if _margins else None
                    _lo_combined = min(_margins, key=lambda m: m["combined"]) if _margins else None

                    def _hof_card(emoji, title, headline, detail, color="#00c853"):
                        return (
                            f"<div style='background:#1a2332;border:1px solid #2d3748;"
                            f"border-radius:10px;padding:18px;margin-bottom:10px'>"
                            f"<span style='font-size:26px'>{emoji}</span>"
                            f"<div style='font-size:11px;color:#888;text-transform:uppercase;"
                            f"letter-spacing:1px;margin-top:4px'>{title}</div>"
                            f"<div style='font-size:20px;font-weight:800;color:{color};"
                            f"margin-top:2px'>{headline}</div>"
                            f"<div style='font-size:12px;color:#aaa;margin-top:4px'>{detail}</div>"
                            f"</div>"
                        )

                    _hc1, _hc2 = st.columns(2)
                    with _hc1:
                        if _best_score:
                            st.markdown(_hof_card(
                                "🏆", "Highest Single-Week Score",
                                f"{_best_score['score']:.2f} pts",
                                f"{_best_score['username']} · {_best_score['season']} Week {_best_score['week']}",
                                "#ffd700"
                            ), unsafe_allow_html=True)
                        if _best_loss:
                            st.markdown(_hof_card(
                                "😤", "Most Points in a Loss",
                                f"{_best_loss['score']:.2f} pts",
                                f"{_best_loss['username']} lost to {_best_loss['opp']} "
                                f"({_best_loss['opp_score']:.2f}) · "
                                f"{_best_loss['season']} Wk {_best_loss['week']}",
                                "#ff9800"
                            ), unsafe_allow_html=True)
                        if _blowout:
                            st.markdown(_hof_card(
                                "💥", "Biggest Blowout",
                                f"+{_blowout['margin']:.2f} pts",
                                f"{_blowout['winner']} def. {_blowout['loser']} "
                                f"({_blowout['winner_score']:.2f}–{_blowout['loser_score']:.2f}) · "
                                f"{_blowout['season']} Wk {_blowout['week']}",
                                "#e040fb"
                            ), unsafe_allow_html=True)
                        if _hi_combined:
                            st.markdown(_hof_card(
                                "🔥", "Highest-Scoring Game",
                                f"{_hi_combined['combined']:.2f} combined pts",
                                f"{_hi_combined['winner']} vs {_hi_combined['loser']} · "
                                f"{_hi_combined['season']} Wk {_hi_combined['week']}",
                                "#ff6e40"
                            ), unsafe_allow_html=True)
                    with _hc2:
                        if _worst_score:
                            st.markdown(_hof_card(
                                "💀", "Lowest Single-Week Score",
                                f"{_worst_score['score']:.2f} pts",
                                f"{_worst_score['username']} · {_worst_score['season']} Week {_worst_score['week']}",
                                "#ff5252"
                            ), unsafe_allow_html=True)
                        if _luck_win:
                            st.markdown(_hof_card(
                                "🍀", "Luckiest Win",
                                f"{_luck_win['score']:.2f} pts",
                                f"{_luck_win['username']} beat {_luck_win['opp']} "
                                f"({_luck_win['opp_score']:.2f}) · "
                                f"{_luck_win['season']} Wk {_luck_win['week']}",
                                "#00e5ff"
                            ), unsafe_allow_html=True)
                        if _closest:
                            st.markdown(_hof_card(
                                "🤝", "Closest Game",
                                f"{_closest['margin']:.2f} pt margin",
                                f"{_closest['winner']} def. {_closest['loser']} "
                                f"({_closest['winner_score']:.2f}–{_closest['loser_score']:.2f}) · "
                                f"{_closest['season']} Wk {_closest['week']}",
                                "#69f0ae"
                            ), unsafe_allow_html=True)
                        if _lo_combined:
                            st.markdown(_hof_card(
                                "🧊", "Lowest-Scoring Game",
                                f"{_lo_combined['combined']:.2f} combined pts",
                                f"{_lo_combined['winner']} vs {_lo_combined['loser']} · "
                                f"{_lo_combined['season']} Wk {_lo_combined['week']}",
                                "#82b1ff"
                            ), unsafe_allow_html=True)

            # ── Sub-tab C: Head-to-Head ───────────────────────────────────────
            with _lhC:
                _h2h_scope = _season_filter if _season_filter != "All Time" else "all-time"
                st.subheader("Head-to-Head Records")
                st.caption(f"Record against each opponent (W–L), {_h2h_scope}. Includes playoffs. Row beats column.")

                _h2h: dict = {}
                for _rh in _filt_records:
                    if not _rh["won"]:
                        continue
                    _kh = frozenset([_rh["username"], _rh["opp"]])
                    _h2h.setdefault(_kh, {})
                    _h2h[_kh][_rh["username"]] = _h2h[_kh].get(_rh["username"], 0) + 1
                    _h2h[_kh].setdefault(_rh["opp"], 0)

                _mgrs_sorted = _h2h_managers
                _matrix_rows = []
                for _um in _mgrs_sorted:
                    _row_d = {"Manager": _um}
                    for _vm in _mgrs_sorted:
                        if _um == _vm:
                            _row_d[_vm] = "—"
                        else:
                            _kh2 = frozenset([_um, _vm])
                            _w   = _h2h.get(_kh2, {}).get(_um, 0)
                            _l   = _h2h.get(_kh2, {}).get(_vm, 0)
                            _row_d[_vm] = f"{_w}–{_l}"
                    _matrix_rows.append(_row_d)

                _h2h_df = pd.DataFrame(_matrix_rows).set_index("Manager")
                st.dataframe(_h2h_df, use_container_width=True)

            # ── Sub-tab D: Report Cards ───────────────────────────────────────
            with _lhD:
                _rc_scope = _season_filter if _season_filter != "All Time" else "all-time"
                st.subheader("Manager Report Cards")

                if not _h2h_managers:
                    st.info("No managers found for this filter.")
                    _sel_mgr = None
                else:
                    _sel_mgr = st.selectbox("Select a manager", _h2h_managers, key="lh_manager")
                _mgr_games = [r for r in _filt_records if r["username"] == _sel_mgr] if _sel_mgr else []

                # Season history always shows full career (not filtered)
                _mgr_season_rows: dict = {}
                for _yr3, _sd3 in _lh["seasons"].items():
                    for _row3 in _sd3["standings"]:
                        if _row3["username"] == _sel_mgr:
                            _mgr_season_rows[_yr3] = _row3

                if not _mgr_games:
                    st.info(f"No data for this manager in {_rc_scope}.")
                else:
                    _sc_all = [r["score"] for r in _mgr_games]
                    _w_all  = sum(1 for r in _mgr_games if r["won"])
                    _l_all  = sum(1 for r in _mgr_games if not r["won"])
                    _titles = sum(1 for _sd4 in _filt_seasons.values()
                                  if _sd4["champion"]["username"] == _sel_mgr)
                    _finals = sum(1 for _sd4 in _filt_seasons.values()
                                  if _sd4["runner_up"]["username"] == _sel_mgr)
                    _playoff_apps = sum(
                        1 for _yr3p, _s4 in _mgr_season_rows.items()
                        if _s4.get("playoff_finish") is not None
                        and (_season_filter == "All Time" or _yr3p == _season_filter)
                    )

                    _d1, _d2, _d3, _d4, _d5 = st.columns(5)
                    _d1.metric("Championships", _titles)
                    _d2.metric("Finals", _titles + _finals)
                    _d3.metric("Playoff Apps", _playoff_apps)
                    _d4.metric("Record", f"{_w_all}–{_l_all}")
                    _d5.metric("Win %",
                               f"{_w_all / (_w_all + _l_all) * 100:.1f}%"
                               if (_w_all + _l_all) else "N/A")

                    _d6, _d7, _d8 = st.columns(3)
                    _d6.metric("Avg Score",  f"{sum(_sc_all)/len(_sc_all):.2f}")
                    _d7.metric("Best Week",  f"{max(_sc_all):.2f}")
                    _d8.metric("Worst Week", f"{min(_sc_all):.2f}")

                    st.divider()
                    st.markdown("**Season History**")
                    _s_hist = []
                    for _yr4 in sorted(_mgr_season_rows):
                        _row4 = _mgr_season_rows[_yr4]
                        _pf4  = _row4.get("playoff_finish")
                        _fin4 = {1: "🥇 Champion", 2: "🥈 Runner-up", 3: "🥉 3rd"}.get(
                            _pf4, f"{_pf4}th" if _pf4 else "DNQ")
                        _s_hist.append({
                            "Season":    _yr4,
                            "Team Name": _row4.get("team_name") or "—",
                            "Record":    f"{_row4['wins']}–{_row4['losses']}",
                            "PF":        _row4["fpts"],
                            "PA":        _row4["fpts_against"],
                            "Finish":    _fin4,
                        })
                    st.dataframe(
                        pd.DataFrame(_s_hist),
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "PF": st.column_config.NumberColumn("PF", format="%.2f"),
                            "PA": st.column_config.NumberColumn("PA", format="%.2f"),
                        }
                    )

                    st.divider()
                    st.markdown("**Opponent Breakdown**")
                    _opp_recs: dict = {}
                    for _r4 in _mgr_games:
                        _opp4 = _r4["opp"]
                        _opp_recs.setdefault(_opp4, {"wins": 0, "losses": 0})
                        if _r4["won"]:
                            _opp_recs[_opp4]["wins"] += 1
                        else:
                            _opp_recs[_opp4]["losses"] += 1
                    _h2h_rows4 = sorted(
                        [{"Opponent": _o, "W": _v["wins"], "L": _v["losses"],
                          "+/-": _v["wins"] - _v["losses"]}
                         for _o, _v in _opp_recs.items()],
                        key=lambda r: -r["+/-"]
                    )
                    st.dataframe(pd.DataFrame(_h2h_rows4), hide_index=True, use_container_width=True)

            # ── Sub-tab E: Consistency & Luck ─────────────────────────────────
            with _lhE:
                _cl_scope = _season_filter if _season_filter != "All Time" else "all seasons"
                st.subheader("Consistency & Luck")
                st.caption(f"Regular season only · {_cl_scope}. Luck is measured relative to the league average score that week.")

                _rs_recs = [r for r in _filt_records if not r["is_playoff"]]

                _week_avg: dict = {}
                for _r5 in _rs_recs:
                    _k5 = (_r5["season"], _r5["week"])
                    _week_avg.setdefault(_k5, []).append(_r5["score"])
                _week_avg = {k: sum(v) / len(v) for k, v in _week_avg.items()}

                _mgr_cl: dict = {}
                for _r5 in _rs_recs:
                    _u5 = _r5["username"]
                    _mgr_cl.setdefault(_u5, {
                        "scores": [], "wins": 0, "losses": 0,
                        "lucky_wins": 0, "unlucky_losses": 0, "pts_in_losses": []
                    })
                    _mgr_cl[_u5]["scores"].append(_r5["score"])
                    _avg5 = _week_avg.get((_r5["season"], _r5["week"]), 0)
                    if _r5["won"]:
                        _mgr_cl[_u5]["wins"] += 1
                        if _r5["score"] < _avg5:
                            _mgr_cl[_u5]["lucky_wins"] += 1
                    else:
                        _mgr_cl[_u5]["losses"] += 1
                        _mgr_cl[_u5]["pts_in_losses"].append(_r5["score"])
                        if _r5["score"] > _avg5:
                            _mgr_cl[_u5]["unlucky_losses"] += 1

                _cl_rows = []
                for _u5, _st5 in _mgr_cl.items():
                    _sc5 = _st5["scores"]
                    _avg_loss5 = (sum(_st5["pts_in_losses"]) / len(_st5["pts_in_losses"])
                                  if _st5["pts_in_losses"] else 0)
                    _cl_rows.append({
                        "Manager":         _u5,
                        "Avg Score":       round(sum(_sc5) / len(_sc5), 2),
                        "Std Dev":         round(pd.Series(_sc5).std(), 2) if len(_sc5) > 1 else 0,
                        "Avg Pts in Loss": round(_avg_loss5, 2),
                        "Lucky Wins":      _st5["lucky_wins"],
                        "Unlucky Losses":  _st5["unlucky_losses"],
                    })

                _cl_df = (
                    pd.DataFrame(_cl_rows)
                    .sort_values("Avg Score", ascending=False)
                    .reset_index(drop=True)
                )
                _cl_df.index += 1
                st.dataframe(
                    _cl_df, use_container_width=True,
                    column_config={
                        "Avg Score":       st.column_config.NumberColumn("Avg Score",       format="%.2f"),
                        "Std Dev":         st.column_config.NumberColumn("Std Dev",         format="%.2f",
                                           help="Lower = more consistent week to week"),
                        "Avg Pts in Loss": st.column_config.NumberColumn("Avg Pts in Loss", format="%.2f",
                                           help="Average score when losing — higher means more unlucky"),
                        "Lucky Wins":      st.column_config.NumberColumn("Lucky Wins",
                                           help="Wins where you scored below the league average that week"),
                        "Unlucky Losses":  st.column_config.NumberColumn("Unlucky Losses",
                                           help="Losses where you scored above the league average that week"),
                    }
                )

                if _cl_rows:
                    _most_con  = min(_cl_rows, key=lambda r: r["Std Dev"])
                    _most_vol  = max(_cl_rows, key=lambda r: r["Std Dev"])
                    _most_unl  = max(_cl_rows, key=lambda r: r["Unlucky Losses"])
                    _most_luck = max(_cl_rows, key=lambda r: r["Lucky Wins"])
                    st.divider()
                    _e1, _e2 = st.columns(2)
                    with _e1:
                        st.info(
                            f"**Most Consistent:** {_most_con['Manager']}  \n"
                            f"Std Dev: {_most_con['Std Dev']:.2f} pts/week"
                        )
                        st.info(
                            f"**Most Volatile:** {_most_vol['Manager']}  \n"
                            f"Std Dev: {_most_vol['Std Dev']:.2f} pts/week"
                        )
                    with _e2:
                        st.warning(
                            f"**Most Unlucky:** {_most_unl['Manager']}  \n"
                            f"{_most_unl['Unlucky Losses']} losses where they scored above the weekly avg"
                        )
                        st.success(
                            f"**Most Lucky:** {_most_luck['Manager']}  \n"
                            f"{_most_luck['Lucky Wins']} wins where they scored below the weekly avg"
                        )

            # ── Sub-tab F: Score Trends ───────────────────────────────────────
            with _lhF:
                st.subheader("Score Trends")

                # Build avg score per manager per season (always uses full unfiltered data)
                _trend_data = []
                for _yr5, _sd5 in _lh["seasons"].items():
                    for _row5 in _sd5["standings"]:
                        _u5t = _row5["username"]
                        if not _u5t or _u5t in ("—", "?"):
                            continue
                        _wk_scores5 = [
                            r["score"] for r in _game_records
                            if r["username"] == _u5t
                            and r["season"] == _yr5
                            and not r["is_playoff"]
                        ]
                        if _wk_scores5:
                            _trend_data.append({
                                "Season":    _yr5,
                                "Manager":   _u5t,
                                "Avg Score": round(sum(_wk_scores5) / len(_wk_scores5), 2),
                            })

                if not _trend_data:
                    st.info("Not enough weekly data for trend chart.")
                elif _season_filter != "All Time":
                    # Single season: bar chart ranked by avg score
                    st.caption(f"Average regular season score per manager — {_season_filter}.")
                    _bar_data = [d for d in _trend_data if d["Season"] == _season_filter]
                    _bar_data.sort(key=lambda d: d["Avg Score"], reverse=True)
                    if _bar_data:
                        _fig_bar = go.Figure(go.Bar(
                            x=[d["Manager"]   for d in _bar_data],
                            y=[d["Avg Score"] for d in _bar_data],
                            marker_color="#00c853",
                            hovertemplate="%{x}: %{y:.2f} pts<extra></extra>",
                        ))
                        _fig_bar.update_layout(
                            height=420,
                            xaxis_title="Manager",
                            yaxis_title="Avg Weekly Score",
                            template="plotly_dark",
                            yaxis=dict(range=[
                                min(d["Avg Score"] for d in _bar_data) * 0.97,
                                max(d["Avg Score"] for d in _bar_data) * 1.03,
                            ]),
                        )
                        st.plotly_chart(_fig_bar, use_container_width=True)
                else:
                    # All-time: multi-season line chart
                    st.caption("Average regular season score per manager, by season.")
                    _trend_df = pd.DataFrame(_trend_data)
                    _fig_trend = go.Figure()
                    for _mgr_t in sorted(_trend_df["Manager"].unique()):
                        _d_t = _trend_df[_trend_df["Manager"] == _mgr_t].sort_values("Season")
                        _fig_trend.add_trace(go.Scatter(
                            x=_d_t["Season"],
                            y=_d_t["Avg Score"],
                            name=_mgr_t,
                            mode="lines+markers",
                            hovertemplate="%{fullData.name}<br>%{x}: %{y:.2f} pts<extra></extra>",
                        ))
                    _fig_trend.update_layout(
                        height=450,
                        xaxis_title="Season",
                        yaxis_title="Avg Weekly Score",
                        template="plotly_dark",
                        legend_title="Manager",
                        hovermode="x unified",
                    )
                    st.plotly_chart(_fig_trend, use_container_width=True)



# ══════════════════════════════════════════════════════════════════════════════
# TAB 7: HELP & GUIDE
# ══════════════════════════════════════════════════════════════════════════════
with tab7:

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

The bigger the edge, the more the model disagrees with the market. Games with a small edge (under 1 point) are basically coin flips in the model's eyes. Use the Min Edge slider in the sidebar to filter down to only the games where the model has real conviction.

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

The model is currently at **{_overall_pct}% ATS** overall ({_overall_correct}/{_overall_total}){_hc_line}. {"Both are above break even, which is encouraging." if _hc_pct is not None else "This is above break even, which is encouraging."} But I want to be clear that past performance doesn't guarantee anything going forward. There will be bad weeks.

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

**PREDICTED** is the model's version of the line — also shown sportsbook-style (favorite negative, underdog positive). When the model's number is *more* extreme than the Vegas spread on a side, that's where the edge is. Example: Vegas has SEA -7 but the model says SEA -11.3 — the model likes SEA by 4.3 more points than Vegas, so it recommends betting SEA.

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

At 0.0 (the default) you see every game. At 1.0 you only see games where the model disagrees with Vegas by at least 1 point. At 3.0 you're only seeing the high conviction plays.

Slide it up to filter down to your highest-confidence plays.
        """)

    with st.expander("How often does the site update?"):
        st.markdown("""
During the season the site runs on an automated schedule through GitHub Actions.

Tuesday morning it fills in the previous week's results and posts initial predictions for the upcoming week using the opening Vegas lines. Thursday night it refreshes those predictions after injury reports drop. Sunday morning it locks in final predictions before kickoff. Then the cycle repeats on Tuesday.

During the offseason the site just shows historical data from past seasons. Everything spins back up when the season kicks off in September.
        """)

    with st.expander("What is the Track Record tab?"):
        st.markdown("""
The Track Record tab is where you can see how the model has done across the whole season, not just one week.

It shows a week by week bar chart of ATS win percentage, a cumulative trend line showing how accuracy has moved over time, and a breakdown of how high edge games performed compared to low edge games.

There's also a best and worst weeks section, a full season table, and a separate Over/Under model section showing how the totals picks performed.
        """)

    with st.expander("What is the Over/Under (Totals) model? (Experimental)"):
        st.markdown("""
**Status: experimental — tracking only, not yet a confident pick.**

In addition to picking sides against the spread, the site runs a separate model for the over/under total. It predicts whether the final combined score will go over or under the Vegas total line. It uses the same underlying features as the spread model plus 14 totals-specific inputs: the Vegas total line, implied team totals, weather (temperature and wind), dome/outdoor status, rolling points scored and allowed by each team over the last 5 games, the league scoring environment over the last 4 weeks, pace (plays per game), and whether it's a division game.

The key finding from development: the edge only shows up on **UNDER picks**, not OVERs. The reason is that recreational bettors tend to bet OVER — everyone loves a shootout — which causes books to shade totals lines slightly high. That creates a systematic edge on the UNDER side that the model is designed to find.

A pick is only flagged as **UNDER** when both the XGBoost and Ridge models independently predict the score will come in below the line. When they disagree, the model passes.

**Where it stands:**
- Walk-forward CV (2020–2025, n=575): **55.7%** hit rate, comfortably above the 52.4% break-even.
- Live 2025 (weeks 10–17, n=46): **52.2%** hit rate, essentially at break-even. The sample is too small to distinguish real edge from CV noise (95% CI is roughly 37–67%).

That's why the badges on the game cards are amber/dashed instead of green — the model says UNDER, but we haven't yet confirmed live that it's actually profitable. We track it through the 2026 season and reassess after a full season of real evidence (~96 picks). **Don't bet these picks; treat them as something to watch.**
        """)

    with st.expander("What is the Weekly Fantasy tab?"):
        st.markdown("""
The Weekly Fantasy tab shows weekly half-PPR fantasy projections for every active QB, RB, WR, and TE. Each position has its own subtab.

You can filter by team or health status and see projected fantasy points alongside position-specific stat projections (passing yards, rushing yards, receptions, receiving yards). Once the week's games are played, actual stats fill in automatically.

See the Fantasy Projections section below for more detail on how the models work.
        """)

    with st.expander("What is the DFS Optimizer tab?"):
        st.markdown("""
The DFS Optimizer tab is a DraftKings NFL Classic lineup optimizer launching with the 2026 season.

Upload your DraftKings salary CSV and the optimizer generates the highest-projected legal 9-player lineup under the $50,000 salary cap. See the DFS Optimizer section below for a full breakdown.
        """)

    with st.expander("What is the Draft Value Finder tab?"):
        st.markdown("""
The Draft Value Finder is a **pre-season draft tool**, separate from the Weekly Fantasy tab. It runs our own season-projection model and compares it to the market's **ADP** (average draft position) to flag players the draft room is **mis-pricing**.

**What it's doing:** our independent model projects each player's upcoming season and ranks them within their position (e.g. RB12). The board compares our rank to where the draft market (ADP) takes them, and shows a plain-English **Verdict**: 🟢 green means we rank a player *above* their draft cost — a **buy** (undervalued); 🔴 red means below — a **fade** (overvalued). The number is how many positional spots we differ, and HIGH-confidence calls are the biggest disagreements. For a completed season it also shows where they **Finished** and whether the call **hit**.

**Honest scope:** on our confident BUY calls this beats the casual ADP draft line about **68%** of the time, and it's been stable season to season — a real, if modest, edge over the room. It is **not** better than the sharpest public projections (e.g. Sleeper, which we show next to our ranks purely for comparison). **Fades** are only shown when there's a real decline catalyst (aging or declining production) and never for young players — those are the only fades that beat a coin flip. Injuries are unpredictable and not modeled.

Use the **season selector** to switch years and the **Position** filter to focus. For a **completed season** (2025) we show where each player **actually finished**, so you can see which calls hit. Treat it as a cross-check on your draft room, not a guarantee.
        """)

    st.divider()

    # ── Section 3: Fantasy Projections ───────────────────────────────────────
    st.subheader("🏆 Fantasy Projections")

    with st.expander("How do the fantasy projections work?"):
        st.markdown("""
The Weekly Fantasy tab uses a separate machine learning system from the betting model. There are four XGBoost models — one for each position (QB, RB, WR, TE) — each trained on NFL player stats from 2020 through 2024 with the 2025 season held out as a real-world test.

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
The models were evaluated on the full 2025 holdout season against a simple 3-week rolling average baseline:

| Position | Model MAE | Baseline MAE | Improvement |
|----------|-----------|--------------|-------------|
| QB | 7.0 pts | 7.5 pts | ✅ Better |
| RB | 4.5 pts | 4.6 pts | ✅ Better |
| WR | 3.9 pts | 4.1 pts | ✅ Better |
| TE | 3.2 pts | 3.5 pts | ✅ Better |

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

    # ── Section 4: DFS Optimizer ──────────────────────────────────────────────
    st.subheader("🎯 DFS Optimizer")

    with st.expander("What is the DFS Optimizer?"):
        st.markdown("""
The DFS Optimizer tab is a DraftKings NFL Classic lineup optimizer launching with the 2026 season.

It takes this site's weekly fantasy projections and solves for the highest-projected legal lineup under the $50,000 salary cap using an integer linear program. The optimizer fills all 9 roster slots — QB, 2 RB, 3 WR, TE, FLEX, DST — subject to DraftKings' constraints.

The workflow each week is:
1. Download your DraftKings salary CSV from any NFL Classic contest lobby
2. Upload it in the DFS Optimizer tab
3. The optimizer fuzzy-matches DK player names to our projected points and solves the lineup
4. Lock or exclude specific players and re-run if you want to tweak it
5. Download the finished lineup ready for DraftKings import

Note that DST currently uses DraftKings' season average since there is no team-defense projection model yet. That's listed as a known limitation in the tab.
        """)

    with st.expander("How does the optimizer actually work?"):
        st.markdown("""
Under the hood it's an integer linear program (ILP) solved with the PuLP library.

The optimizer treats each player as a binary variable — either in the lineup (1) or out (0) — and maximizes total projected points subject to hard constraints:

- Exactly 1 QB
- At least 2 RBs
- At least 3 WRs
- At least 1 TE
- Exactly 1 DST
- Exactly 9 total players (the FLEX slot is filled implicitly by the solver)
- Total salary ≤ $50,000
- No more than 8 players from the same team

The solver finds the globally optimal combination given those constraints in under a second. It's not greedy — it considers every valid roster combination simultaneously.

Projections are converted to full DraftKings Classic scoring (full PPR, milestone bonuses for 300+ passing yards, 100+ rushing yards, 100+ receiving yards).
        """)

    st.divider()

    # ── Section 5: League History ─────────────────────────────────────────────
    st.subheader("🏅 League History")

    with st.expander("What is the League History tab?"):
        st.markdown("""
The League History tab pulls your Sleeper fantasy league's historical data and displays it in one place.

Enter your Sleeper league ID (found in your league's URL: `sleeper.com/leagues/{ID}/league`) and the tab loads standings, matchup results, and season-by-season records for every manager in the league.

You can filter by season or view all-time records across every year your league has existed. It's useful for settling debates about who's actually been the best manager historically versus just the most recent champion.
        """)

    st.divider()

    # ── Section 6: Behind the Scenes ─────────────────────────────────────────
    st.subheader("🔧 Behind the Scenes")

    with st.expander("How does the prediction model work?"):
        st.markdown("""
The site runs two independent prediction systems: one for the **spread** (ATS picks) and one for the **over/under total**.

**Spread model**

Four models trained on over 3,000 NFL games spanning 11 seasons (2014–2024).

The primary model is the **Ensemble (fixed75)** — a fixed-weight blend of 75% XGBoost and 25% Ridge regression. It sets the predicted edge for each game and determines the sort order.

The three direction voters are **XGBoost**, **Ridge**, and **LightGBM** — three independent models that each predict which side of the spread they favor.

Each game is evaluated by all four models. The consensus tier is assigned based on voter agreement plus Ensemble edge size:

- **HIGH** — all three voters agree on direction *and* the Ensemble edge is 3+ points
- **MEDIUM** — all three voters agree on direction *and* the Ensemble edge is 1+ points (but under 3)
- **PASS** — the voters disagree, or they agree but edge is under 1 point

85 features were engineered, then trimmed to the top 35 via a walk-forward ablation study. The main features are rolling EPA, strength of schedule, All-Pro roster quality, injury impact, QB changes, coaching history, and home field advantage.

**Totals model (experimental)**

A separate two-model system (XGBoost + Ridge) trained to predict whether the final combined score will be over or under the Vegas total line. Uses 35 spread features plus 14 totals-specific inputs (total line, implied team totals, weather, dome status, rolling points, league scoring environment, pace, division game flag).

The CV result (2020–2025, 55.7% on 575 picks) suggests a real UNDER-side edge, consistent with the known retail OVER bias. **But live 2025 results so far (52.2% on 46 picks) are at break-even, not yet confirming the CV.** The 2025 sample is too small to tell — we're tracking through 2026 before treating these as real picks.

All models are retrained each offseason as new data comes in.
        """)

    with st.expander("What is the LLM agent and what does it do?"):
        st.markdown("""
The agent is built on top of the prediction models using LlamaIndex and Anthropic's Claude API.

It has 5 tools it can call: model predictions, injury reports, line movement data, historical head to head matchups going back to 2015, and a model confidence analyzer.

Each week it goes through every game, calls those tools, and reasons about whether the model's prediction is backed up by real world signals. It's not overriding the model. It's asking whether everything else lines up with what the model is saying.

If the model likes a team, sharp money likes that team, they're healthy, and they dominate this matchup historically, the agent marks it high confidence. If the model likes a team but their star QB is out and sharp money is going the other way, the agent will tell you to skip it.

The idea is that raw model predictions are a starting point. The agent adds a layer of reasoning to help filter out plays where the edge might just be noise.
        """)

    with st.expander("How accurate is the model?"):
        _best_week = _completed.groupby(['season','week'])[_acc_col].agg(['sum','count'])
        _best_week['pct'] = _best_week['sum'] / _best_week['count']
        _bw = _best_week['pct'].idxmax() if not _best_week.empty else None
        _bw_str = (f"Season {_bw[0]} Week {_bw[1]} was the strongest week so far at "
                   f"{int(_best_week.loc[_bw,'sum'])} out of {int(_best_week.loc[_bw,'count'])} correct. "
                   ) if _bw else ""
        _hc_line2 = f" and **{_hc_pct}%** on high confidence picks" if _hc_pct is not None else ""
        _be_comment2 = "Both numbers are above that." if _hc_pct is not None else "That number is above break even."
        st.markdown(f"""
The model has gone **{_overall_pct}% ATS** across {_overall_total} completed games ({_overall_correct} correct){_hc_line2}. The break even threshold at standard sportsbook odds is 52.4%, so {_be_comment2}

{_bw_str}
I want to be honest though. Past performance doesn't guarantee anything going forward. There will be bad weeks. The goal is to track this over multiple seasons and see if the edge holds up.
        """)

    with st.expander("What data does it use?"):
        st.markdown("""
The model pulls play-by-play and schedule data from nflreadpy going back to 1999. Real weekly injury reports (from `nfl.load_injuries()`) feed directly into the feature set — Out and Doubtful players reduce a team's weighted All-Pro score, which is one of the stronger predictors.

The All-Pro data is a custom CSV covering selections from 1997 to 2025. It's used as a proxy for roster talent: players are weighted over a 3-year lookback (4/2/1) so recent selections matter more. This gets updated manually each January.

The agent currently uses mock injury and line movement data for demonstration purposes. Integrating real-time APIs for those two sources is on the roadmap for the 2026 season.
        """)

    with st.expander("Is this financial advice?"):
        st.markdown("""
No. This is a personal data science project. I built it to explore whether a machine learning model can find a consistent edge against the spread.

Nothing on this site should be taken as betting or financial advice. Sports betting involves real financial risk. Always bet responsibly.
        """)

    st.markdown("""
        <div style='text-align:center;padding:28px 0 12px 0;border-top:1px solid #2d3748;margin-top:12px'>
            <div style='font-size:11px;color:#444;margin-bottom:10px;letter-spacing:0.3px'>
                Not financial advice. Sports betting involves real risk. Bet responsibly.
            </div>
            <div style='font-size:13px;color:#666'>
                Built by <b style='color:#999'>Joseph Schoenbaum</b>
                &nbsp;·&nbsp;
                <a href='https://github.com/joscho11/BettingEdgeContinued'
                   style='color:#3D95CE;text-decoration:none'>GitHub</a>
                &nbsp;·&nbsp;
                <a href='https://venmo.com/u/JoScho'
                   style='color:#3D95CE;text-decoration:none'>💙 Venmo @JoScho</a>
            </div>
        </div>
    """, unsafe_allow_html=True)