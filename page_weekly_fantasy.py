"""Weekly Fantasy page (site revamp Batch 3c). Tab3 body + its _load_proj_csv /
load_actual_stats helpers moved byte-identical from app.py; own Season+Week controls
(wf_*, filter independence) preserved. Stale "tab" wording is verbatim.
"""
import glob
import html as _html
import itertools as _it
import json
import os
from datetime import datetime as dt
from pathlib import Path

import nflreadpy as nfl
import pandas as pd
import streamlit as st

from dashboard_chrome import TABLE_HEIGHT   # shared ~20-row height for long tables

import dashboard_data
import page_common
from dashboard_utils import metric_card, get_confidence, _md_to_html
from dashboard_chrome import _OFFLINE

_HERE = Path(__file__).resolve().parent


@st.cache_data(ttl=3600)
def _load_proj_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


@st.cache_data(ttl=3600)
def load_actual_stats(season: int, week: int) -> dict:
    """Load all actual player stats for a given season/week in one nflreadpy call."""
    if _OFFLINE:
        return {}
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


def render():
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
    def _season_week_controls(cols_container, key_prefix, with_week=True, with_edge=False):
        return page_common._season_week_controls(df, cols_container, key_prefix, with_week, with_edge)
    season, week, _ = _season_week_controls(
        st.columns(2), "wf", with_week=True, with_edge=False)

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
            "Use the Week selector above to pick a week with projections, or run the fantasy notebook to generate them."
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
                                      help="Projected half-PPR fantasy points for this week, generated by my XGBoost model. Half-PPR scoring: 0.5 pts per reception, 1 pt per 10 rush/rec yards, 6 pts per TD."),
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
                    width="stretch",
                    height=TABLE_HEIGHT,
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
